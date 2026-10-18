"""Service orchestration for bounded decision support and guarded event replans."""
from __future__ import annotations
from copy import deepcopy
import time

from . import analytics, bilateral, counterparty, planner
from .constraints import owner_constraints
from .domain import ValidationError
from .projection import horizon_end, summary
from .resilience import Context, digest, reverse_stress, promise_stress, recovery_frontier


class DecisionLab:
    def __init__(self, app):
        self.app, self.store = app, app.store

    def context(self, business_id, target=None, plan_id=None, bundle_id=None):
        import os
        if os.environ.get("TIDEWAY_DECISION_LAB", "1").strip() == "0":
            raise ValidationError("Decision lab is disabled.")
        snapshot = self.store.snapshot(business_id)
        target = self.app._target(snapshot, target)
        horizon_end(snapshot["business"], target, snapshot["policy"]["lookahead_days"])
        plan = self.store.plan(business_id, plan_id) if plan_id else self.store.latest_plan(business_id, target)
        if plan and (plan["snapshot_hash"] != snapshot["snapshot_hash"] or plan["target_date"] != target
                     or plan["status"] in ("invalidated", "cancelled", "superseded")):
            if plan_id:
                raise ValidationError("That proposal is stale. Refresh the decision lab.")
            plan = None
        if plan and plan["status"] == "executed":
            plan = None  # executed adjustments already live in snapshot state
        if plan is None:
            plan = self.build_payload(snapshot, target)
        return Context(snapshot, target, plan, bundle_id)

    def build_payload(self, snapshot, target, *, constraints=None, excluded=(), required=()):
        policy = dict(snapshot["policy"])
        constraints = owner_constraints(constraints or {"max_discount_bps": policy["max_discount_bps"], "prefer": "lowest_cost"}, policy)
        policy["max_discount_bps"] = constraints["max_discount_bps"]
        derived = self.store.derived(snapshot)
        seed = analytics.stable_seed(snapshot["snapshot_hash"], target)
        result = planner.plan_recovery(snapshot["business"], policy, snapshot["records"], target,
                    accepted=snapshot["state"]["adjustments"], promises=snapshot["state"]["promises"],
                    basis_dates=derived["likely_dates"], profiles=derived["profiles"], blocked=derived["blocked"],
                    excluded_counterparties=excluded, mc_seed=seed, mc_runs=400,
                    as_of=snapshot["state"]["current_date"], prefer=constraints["prefer"], required_actions=required)
        result.update(owner_constraints=constraints, excluded_counterparties=sorted(excluded))
        baseline = Context(snapshot, target).simulation(runs=400)
        result.update(probability_breach_before=baseline["probability_breach"], futures_short_of_20_before=baseline["futures_short_of_20"])
        return result

    def analyze(self, business_id, target, kind, *, plan_id=None, bundle_id=None, max_days=30, delay_days=7):
        if kind not in ("reverse", "promises", "frontier"):
            raise ValidationError("Select reverse, promises or frontier analysis.")
        context = self.context(business_id, target, plan_id, bundle_id)
        return {"reverse": lambda: reverse_stress(context, max_days),
                "promises": lambda: promise_stress(context, delay_days),
                "frontier": lambda: recovery_frontier(context)}[kind]()

    def event(self, business_id, target, event, expected_snapshot, request_id, operator, pin, actor):
        snapshot = self.store.snapshot(business_id)
        target = self.app._target(snapshot, target)
        horizon_end(snapshot["business"], target, snapshot["policy"]["lookahead_days"])
        receipt = self.store.apply_lab_event(business_id, event, target, expected_snapshot, request_id, operator, pin, actor)
        latest = self.store.snapshot(business_id)
        result = {**receipt, "proposal": None, "executed": False, "trace": []}
        if receipt.get("plan_id"):
            result.update(proposal=self.store.plan(business_id, receipt["plan_id"]), replan_status="replayed")
            return result
        if not receipt["watch_enabled"]:
            result["replan_status"] = "watch_not_armed"
            return result
        if latest["policy"]["autonomy_level"] == "advise":
            result["replan_status"] = "owner_proposal_required_in_advise_mode"
            return result
        if latest["snapshot_hash"] != receipt["after_snapshot"]:
            result["replan_status"] = "superseded_by_newer_records"
            return result
        started = time.perf_counter()
        try:
            payload = self.build_payload(latest, target, constraints=receipt["owner_constraints"], excluded=receipt["excluded_counterparties"])
            payload["event_origin"] = {"request_id": request_id, "previous_plan_id": receipt["previous_plan_id"], "event_type": event["type"]}
            result["proposal"] = self.store.create_plan(business_id, payload, latest["snapshot_hash"], "agent:events", "agent:events", event_request_id=request_id)
        except ValidationError as exc:
            result.update(replan_status="event_applied_replan_requires_review", replan_error=str(exc))
            return result
        result["replan_status"] = "proposal_waiting_for_human_approval"
        result["trace"] = [{"tool": tool, "mode": "deterministic", "permission": permission} for tool, permission in
                           (("read_changed_ledger", "read"), ("project_cash", "read"), ("simulate_risk", "read"), ("propose_recovery", "propose"))]
        result["replan_elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        return result

    def bilateral_quotes(self, business_id, target, bill_id, supplier_ledger, plan_id=None):
        context = self.context(business_id, target, plan_id)
        snapshot = context.snapshot
        if not context.business["synthetic"]:
            raise ValidationError("Two-business negotiation requires a synthetic workspace.")
        ledger = bilateral.validate_ledger(supplier_ledger, context.business)
        bill = next((r for r in context.records["bills"] if r["id"] == bill_id), None)
        if not bill:
            raise ValidationError("Select a bill from this business.")
        options, reason = planner._deferral_options(context.business, context.policy, bill,
                                                    horizon_end(context.business, context.target, context.policy["lookahead_days"]), context.derived["blocked"])
        if bill["payee"] in context.payload.get("excluded_counterparties", []):
            options, reason = [], "The owner excluded this supplier."
        quotes = []
        for action in options:
            supplier = bilateral.supplier_projection(context.business, context.target, context.policy["lookahead_days"], bill, action, ledger)
            profile = snapshot["counterparties"].get("supplier:" + bill["payee"], {}).get("profile")
            reply = counterparty.respond(action, profile)
            payload = self.build_payload(snapshot, context.target, constraints=context.payload["owner_constraints"],
                                         excluded=context.payload.get("excluded_counterparties", []), required=[action])
            feasible = [b for b in payload["bundles"] if b["feasible"]]
            buyer = feasible[0] if feasible else (payload["bundles"][0] if payload["bundles"] else None)
            joint = bool(buyer and buyer["feasible"] and not supplier["reserve_shortfall_minor"] and not supplier["payroll_at_risk"] and reply["status"] == "accepted")
            quote_id = digest({"snapshot": snapshot["snapshot_hash"], "action": action, "ledger": ledger,
                               "constraints": context.payload["owner_constraints"], "target": context.target})
            quotes.append({"quote_id": quote_id, "jointly_feasible": joint, "action": action,
                           "buyer": buyer["after"] if buyer else None, "supplier": summary(supplier),
                           "buyer_probability_breach": buyer["probability_breach_after"] if buyer else None,
                           "counterparty_reply": reply["status"], "economic_cost_minor": buyer["economic_cost_minor"] if buyer else None,
                           "supplier_burden_minor_days": action["amount_minor"] * action["days"]})
        quotes.sort(key=lambda q: (not q["jointly_feasible"], q["economic_cost_minor"] if q["economic_cost_minor"] is not None else 10**30, q["supplier_burden_minor_days"]))
        return context.envelope({"kind": "bilateral", "bill_id": bill_id, "supplier_ledger": ledger,
                                 "assumptions_sha256": digest(ledger), "quotes": quotes, "unavailable_reason": reason,
                                 "scope": "Both ledgers are synthetic. Supplier figures are supplied assumptions, not another tenant's records. Joint feasibility is a deterministic cash-path check, not a guarantee of either party's liquidity."})

    def bilateral_propose(self, business_id, target, bill_id, ledger, quote_id, expected_snapshot, actor, plan_id=None):
        report = self.bilateral_quotes(business_id, target, bill_id, ledger, plan_id)
        if report["snapshot_hash"] != expected_snapshot:
            raise ValidationError("Records changed. Re-negotiate before creating a proposal.")
        quote = next((q for q in report["quotes"] if q["quote_id"] == quote_id and q["jointly_feasible"]), None)
        if quote is None:
            raise ValidationError("Select a jointly feasible quote from the current negotiation.")
        context = self.context(business_id, target, plan_id)
        payload = self.build_payload(context.snapshot, context.target, constraints=context.payload["owner_constraints"],
                                     excluded=context.payload.get("excluded_counterparties", []), required=[quote["action"]])
        for bundle in payload["bundles"]:
            bundle["bilateral"] = {"bill_id": bill_id, "supplier_ledger": report["supplier_ledger"],
                                   "assumptions_sha256": report["assumptions_sha256"], "simulated": True}
            if bundle["feasible"]:
                bilateral.validate_bundle(context.snapshot, bundle, context.target)
        payload["explanation"] += " Synthetic bilateral terms also preserve the supplier's stated reserve and payroll on its supplied ledger. Review these assumptions before approval."
        return self.store.create_plan(business_id, payload, expected_snapshot, "agent:bilateral", actor)
