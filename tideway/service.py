"""Application service: composes the store, analytics, planner and counterparties.

The HTTP layer calls this module; it never talks to SQLite directly.  Every
method takes the acting operator (or the agent) explicitly so the audit trail
always names who did what.
"""
from __future__ import annotations

import re
import secrets
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from . import analytics, counterparty, planner
from .constraints import owner_constraints
from .domain import CURRENCIES, MAX_AMOUNT_MINOR, OPEN_INVOICE_STATUSES, ValidationError, add_days, human_date, money_text, parse_combined_csv, parse_nonnegative, valid_date
from .fixtures import FIXTURE_VERSION, OPERATORS, fixtures
from .projection import horizon_end, project, summary
from .store import PLANS, Store


MC_RUNS = 1000
_CARD = None


def deployed_tidepay_evaluation(root):
    """Expose scores only for an intact report tied to the installed weights."""
    import hashlib
    import json
    import math

    summary = {"available": False, "status": "unavailable", "artifact_sha256": None,
               "note": "Exact deployed-model evaluation is unavailable; older benchmark scores do not describe the installed artifact."}
    try:
        artifact = root / "tideway/ml/tidepay_model.json"
        summary["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        folder = root / "evidence/readiness-v3/tidepay"
        report_bytes = (folder / "report.json").read_bytes()
        manifest = json.loads((folder / "artifact_sha256.json").read_text(encoding="utf-8"))
        if manifest.get("report.json") != hashlib.sha256(report_bytes).hexdigest():
            summary.update(status="invalid", reason="Saved evaluation report failed its integrity check.")
            return summary
        report = json.loads(report_bytes)
        if report["artifacts"]["deployed"]["sha256"] != summary["artifact_sha256"]:
            summary.update(status="artifact_mismatch", reason="Installed model weights differ from the evaluated artifact; rerun the deployed-model evaluation.")
            return summary
        if report["version"] != "deployed-tidepay-fresh-cohorts-v1":
            raise ValueError("unrecognized evaluation version")
        provenance = report["provenance"]
        if not provenance["same_test_ids_for_all_models"] or provenance["fitting_on_fresh_examples"]:
            raise ValueError("evaluation cohort or fitting policy is invalid")
        test = report["balance"]["test"]
        results = report["results"]
        if test["n"] < 1 or test["businesses"] < 2:
            raise ValueError("evaluation cohort is empty")
        for name in ("deployed", "audited_v2", "historical_training_prior", "customer_history_heuristic"):
            metrics = results[name]
            if metrics["n"] != test["n"] or any(not math.isfinite(metrics[key]) or metrics[key] < 0
                                                for key in ("mae_days", "log_loss", "brier_sum")):
                raise ValueError("invalid or mismatched evaluation metrics")
        cold = report["subgroups"]["history:none"]
        summary.update(available=True, status="verified", version=report["version"],
                       test_invoices=test["n"], test_businesses=test["businesses"],
                       cohort_count=len(report["config"]["seeds"]), labels_as_of=report["config"]["labels_as_of"],
                       censored_invoices=report["balance"]["censored"]["n"], results=results,
                       cold_start={"n": cold["deployed"]["n"], "deployed": cold["deployed"],
                                   "prior": cold["historical_training_prior"]},
                       note="Exact installed weights, fresh synthetic SMEs and issue-time forecasts; no fitting on these cohorts. Synthetic performance does not establish real-world accuracy or calibrated cash-risk probabilities.",
                       report_url="/benchmarks/tidepay-deployed.json",
                       reliability_url="/benchmarks/tidepay-deployed-reliability.svg")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        summary.update(reason="Exact deployed-model evaluation is missing or invalid; prediction scores are not shown.")
    return summary


def tidepay_card():
    """Model card shown in the UI: what TidePay is, how it was trained and how it scored."""
    global _CARD
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    if _CARD is None:
        import json
        _CARD = {"meta": {}, "results": {}, "historical_status": "unavailable"}
        try:
            report = json.loads((root / "evidence" / "ml" / "tidepay_report.json").read_text(encoding="utf-8"))
            _CARD.update(meta=report["meta"], results=report["results"], historical_status="historical_observation")
        except (OSError, ValueError, KeyError, TypeError):
            pass
        audited = root / "evidence" / "upgrade-v1" / "tidepay" / "report.json"
        try:
            new = json.loads(audited.read_text(encoding="utf-8"))
            _CARD["audit_benchmark"] = {"status": "benchmark_only", "version": new["version"], "results": new["results"],
                                       "test_businesses": new["balance"]["test"]["businesses"],
                                       "note": "Chronological synthetic benchmark; shipped model unchanged. Single-process federation, no deployed privacy guarantee."}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    # Recheck artifact/report bytes even when historical metadata is cached.
    _CARD["deployed_evaluation"] = deployed_tidepay_evaluation(root)
    return _CARD
PLAN_MC_RUNS = 400


class Tideway:
    def __init__(self, db_path, seed=True, key_path=None, witness_path=None):
        self.store = Store(db_path, key_path, witness_path)
        if seed and not self.store.seeded():
            self.seed()
        if seed:
            self.ensure_demo_access()

    # ---- setup ---------------------------------------------------------------

    def ensure_demo_access(self):
        """Demo operators are members of the demo businesses only (also upgrades databases made before memberships)."""
        existing = {item["id"] for item in self.store.list_businesses()}
        for fixture in fixtures():
            business_id = fixture["business"]["business_id"]
            if business_id in existing:
                for item in OPERATORS:
                    self.store.ensure_membership(business_id, item["id"], item["role"])

    def signup(self, body):
        """A new workspace with sensible, editable safety defaults derived from the owner's own numbers."""
        fields = ("business_name", "currency", "country", "sector", "opening_cash", "reserve_floor", "owner_name",
                  "username", "pin", "plan")
        if not isinstance(body, dict) or set(body) - set(fields):
            raise ValidationError("Unexpected sign-up field.")
        opening = parse_nonnegative(body.get("opening_cash"), "Current cash balance")
        reserve = parse_nonnegative(body.get("reserve_floor"), "Safety reserve")
        limit = max(reserve, opening // 4, 10_000)
        name = str(body.get("business_name") or "").strip()
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "business"
        today = datetime.now(timezone.utc).date().isoformat()
        business = {"business_id": f"{slug}-{secrets.token_hex(3)}", "name": name, "currency": body.get("currency"),
                    "opening_cash_minor": opening, "opening_date": today, "default_target_date": add_days(today, 30),
                    "country": str(body.get("country") or "").upper(), "sector": body.get("sector") or "", "synthetic": False}
        policy = {"reserve_floor_minor": reserve, "action_limit_minor": limit, "daily_cap_minor": limit * 2,
                  "dual_approval_threshold_minor": limit, "autonomy_level": "propose"}
        return self.store.signup(business, policy, body.get("username"), body.get("owner_name"), body.get("pin"),
                                 body.get("plan") or "starter")

    def seed(self):
        for item in OPERATORS:
            self.store.ensure_operator(item["id"], item["name"], item["role"], item["pin"])
        existing = {item["id"] for item in self.store.list_businesses()}
        for fixture in fixtures():
            business = fixture["business"]
            if business["business_id"] in existing:
                continue
            self.store.create_business(business, fixture["policy"], fixture["counterparties"], actor="system:seed")
            currency = business["currency"]
            parsed = {kind: [{**row, "currency": row.get("currency") or currency} for row in fixture[kind]]
                      for kind in ("transactions", "invoices", "bills")}
            self.store.import_records(business["business_id"], parsed, actor="system:seed", source="demo")
        self.store.mark_seeded(FIXTURE_VERSION)

    def config(self, operator=None):
        """Public settings, plus only the businesses this operator is a member of (never other tenants)."""
        businesses = self.store.businesses_for(operator["id"]) if operator else []
        stories = {item["business"]["business_id"]: item["story"] for item in fixtures()}
        return {"name": "Tideway", "tagline": "Approval-gated cash-flow rescue for small businesses",
                "currencies": [{"code": code, "name": name, "illustrative_per_usd": rate}
                               for code, (name, rate) in CURRENCIES.items()],
                "version": "3.0.0", "track": "FinTechathon 2026 International Track, Topic E: SME Finance Copilot",
                "businesses": [{"business_id": item["id"], "name": item["name"], "currency": item["currency"],
                                "country": item["country"], "sector": item["sector"],
                                "opening_date": item["opening_date"], "default_target_date": item["default_target_date"],
                                "synthetic": item["synthetic"], "story": stories.get(item["id"], ""), "role": item["role"]}
                               for item in businesses],
                "demo_accounts": [{"id": item["id"], "name": item["name"], "role": item["role"], "pin": item["pin"]}
                                  for item in OPERATORS],
                "plans": [{"id": key, **value} for key, value in PLANS.items() if key != "demo"],
                "permission_tiers": [
                    {"tier": "agent_read", "who": "Agent", "can": "Read records, project cash, simulate, analyse"},
                    {"tier": "agent_propose", "who": "Agent", "can": "Create plan proposals and message drafts"},
                    {"tier": "human_approval", "who": "Owner / accountant", "can": "Approve bundles with PIN step-up; "
                                                                                 "two people above the dual-approval threshold"},
                    {"tier": "sandbox_execute", "who": "Owner / accountant", "can": "Execute a signed, accepted mandate once"},
                    {"tier": "delegated_execute", "who": "Agent under a standing mandate", "can": "Zero-cash reminders only, capped per day"},
                    {"tier": "denied", "who": "Everyone", "can": "Moving money, credit decisions, payroll deferral, "
                                                                  "acting on unverified bank details"},
                ],
                "autonomy_matrix": [
                    {"action": "Read, project, simulate, explain", "advise": "agent", "propose": "agent", "delegate": "agent"},
                    {"action": "Propose recovery bundles", "advise": "blocked", "propose": "agent", "delegate": "agent"},
                    {"action": "Send collection reminders (zero cash)", "advise": "blocked", "propose": "human",
                     "delegate": "agent (standing mandate, 5/day)"},
                    {"action": "Supplier deferral / early-payment offer", "advise": "blocked", "propose": "human approval",
                     "delegate": "human approval"},
                    {"action": "Financing", "advise": "comparison only", "propose": "comparison only", "delegate": "comparison only"},
                    {"action": "Pay, transfer or defer payroll", "advise": "never", "propose": "never", "delegate": "never"},
                ]}

    # ---- analysis --------------------------------------------------------------

    def _target(self, snapshot, target_date):
        business = snapshot["business"]
        target = valid_date(target_date or business["default_target_date"], "target_date")
        if target < business["opening_date"]:
            raise ValidationError("target_date cannot be before the opening date.")
        return target

    def analysis(self, business_id, target_date=None, snapshot=None):
        snapshot = snapshot or self.store.snapshot(business_id)
        target = self._target(snapshot, target_date)
        derived = self.store.derived(snapshot)
        business, policy, records, state = snapshot["business"], snapshot["policy"], snapshot["records"], snapshot["state"]
        common = {"adjustments": state["adjustments"], "promises": state["promises"], "lookahead_days": policy["lookahead_days"]}
        base = project(business, policy, records, target, scenario="base", **common)
        likely = project(business, policy, records, target, scenario="likely", invoice_dates=derived["likely_dates"], **common)
        stress = project(business, policy, records, target, scenario="stress", invoice_dates=derived["stress_dates"], **common)
        seed = analytics.stable_seed(business_id, snapshot["snapshot_hash"], target)
        simulation = analytics.monte_carlo(business, policy, records, target, state["adjustments"], state["promises"],
                                           runs=MC_RUNS, seed=seed, lookahead_days=policy["lookahead_days"],
                                           as_of=state["current_date"])
        kpis = analytics.financial_kpis(business, records, derived["profiles"])
        alerts = analytics.warnings(business, records, base, simulation, derived["profiles"], derived["payees"], kpis)
        weather = analytics.weather(simulation["probability_breach"], base["reserve_shortfall_minor"])
        return {"snapshot": snapshot, "derived": derived, "target_date": target, "seed": seed,
                "projections": {"base": base, "likely": likely, "stress": stress},
                "simulation": simulation, "kpis": kpis, "warnings": alerts, "weather": weather,
                "backtest": analytics.backtest(records["invoices"], as_of=state["current_date"]),
                "brief": self._brief(business, base, likely, simulation, weather)}

    @staticmethod
    def _brief(business, base, likely, simulation, weather):
        currency = business["currency"]
        payroll = next((event for event in base["source_references"] if event.get("payroll")), None)
        head = f"{simulation['futures_short_of_20']} of 20 simulated futures breach the reserve floor"
        if base["first_breach_date"]:
            head = (f"Scheduled cash breaches the reserve on {human_date(base['first_breach_date'])}; "
                    f"{simulation['futures_short_of_20']} of 20 simulated futures do too")
        detail = (f"Lowest likely cash {money_text(likely['minimum_cash_minor'], currency)} on {human_date(likely['minimum_cash_date'])}.")
        if payroll:
            detail += f" Payroll of {money_text(-payroll['effect_minor'], currency)} is due {human_date(payroll['date'])}."
        return {"headline": head, "detail": detail, "weather": weather["label"]}

    def dashboard(self, business_id, target_date=None):
        result = self.analysis(business_id, target_date)
        snapshot, target = result.pop("snapshot"), result["target_date"]
        derived = result.pop("derived")
        records = snapshot["records"]
        latest = self.store.latest_plan(business_id, target)
        if latest and latest.get("snapshot_hash") != snapshot["snapshot_hash"]:
            latest = None
        evidence = self.store.evidence(business_id)
        return {**result, "business": snapshot["business"], "policy": snapshot["policy"],
                "state": {key: snapshot["state"][key] for key in ("version", "state_hash", "current_date", "adjustments",
                                                                  "promises", "executed_exposure", "reset_count")},
                "snapshot_hash": snapshot["snapshot_hash"], "records": records,
                "profiles": derived["profiles"], "payees": derived["payees"], "blocked": derived["blocked"],
                "tidepay": {"predictions": derived["predictions"], "card": tidepay_card()},
                "feedback": self.store.feedback_summary(business_id),
                "counterparties": list(snapshot["counterparties"].values()),
                "plan": latest, "mandates": self.store.live_mandates(business_id),
                "standing_mandate": self.store.standing_mandate(business_id),
                "messages": self.store.messages(business_id), "executions": self.store.executions(business_id),
                "evidence_summary": {"hash_chain_valid": evidence["hash_chain_valid"], "entries": len(evidence["entries"]),
                                     "head_hash": evidence["head_hash"], "witness": evidence["witness"]}}

    # ---- planning ----------------------------------------------------------------

    def apply_demo_delay(self, business_id, invoice_id, collection_date, expected_snapshot, request_id,
                         operator, pin, actor, target_date=None):
        # Validate the requested horizon before committing any ledger change.
        snapshot = self.store.snapshot(business_id)
        target = self._target(snapshot, target_date)
        horizon_end(snapshot["business"], target, snapshot["policy"]["lookahead_days"])
        receipt = self.store.apply_demo_delay(business_id, invoice_id, collection_date, expected_snapshot,
                                              request_id, operator, pin, actor)
        response = {key: value for key, value in receipt.items() if key not in ("before", "after")}
        response["currency"] = receipt["before"]["business"]["currency"]
        response["target_date"] = target
        for phase in ("before", "after"):
            facts = self.analysis(business_id, target, snapshot=receipt[phase])
            response[phase] = {"scheduled": summary(facts["projections"]["base"]),
                               "likely": summary(facts["projections"]["likely"]),
                               "probability_breach": facts["simulation"]["probability_breach"],
                               "weather": facts["weather"]["label"]}
        response["next"] = "Old approvals are invalid. Create a fresh proposal, review and approve again, then negotiate."
        return response

    def propose(self, business_id, target_date, actor, proposed_by="agent", excluded=(), max_discount_bps=None,
                prefer="lowest_cost", replaces_mandate=None):
        snapshot = self.store.snapshot(business_id)
        if snapshot["policy"]["agent_paused"]:
            raise ValidationError("The agent is paused (kill switch). Resume it to create new proposals.")
        if snapshot["policy"]["autonomy_level"] == "advise" and proposed_by.startswith("agent"):
            raise ValidationError("Autonomy is set to 'advise': the agent may explain but not create proposals.")
        target = self._target(snapshot, target_date)
        derived = self.store.derived(snapshot)
        state, policy = snapshot["state"], snapshot["policy"]
        constraints = owner_constraints({"max_discount_bps": policy["max_discount_bps"] if max_discount_bps is None else max_discount_bps,
                                         "prefer": prefer}, policy)
        seed = analytics.stable_seed(business_id, snapshot["snapshot_hash"], target)
        base_sim = analytics.monte_carlo(snapshot["business"], policy, snapshot["records"], target, state["adjustments"],
                                         state["promises"], runs=PLAN_MC_RUNS, seed=seed,
                                         lookahead_days=policy["lookahead_days"], as_of=state["current_date"])
        planning_policy = dict(policy)
        planning_policy["max_discount_bps"] = constraints["max_discount_bps"]
        payload = planner.plan_recovery(snapshot["business"], planning_policy, snapshot["records"], target,
                                        accepted=state["adjustments"], promises=state["promises"],
                                        profiles=derived["profiles"], basis_dates=derived["likely_dates"],
                                        blocked=derived["blocked"], excluded_counterparties=excluded,
                                        mc_seed=seed, mc_runs=PLAN_MC_RUNS,
                                        late_share=base_sim["invoice_late_share"], as_of=state["current_date"],
                                        prefer=prefer)
        payload["probability_breach_before"] = base_sim["probability_breach"]
        payload["futures_short_of_20_before"] = base_sim["futures_short_of_20"]
        payload["excluded_counterparties"] = sorted(excluded)
        payload["owner_constraints"] = constraints
        return self.store.create_plan(business_id, payload, snapshot["snapshot_hash"], proposed_by, actor,
                                      replaces_mandate=replaces_mandate)

    def negotiate(self, business_id, mandate_id, actor):
        """Send the mandate's requests to the simulated counterparties (deterministic rules)."""
        view = self.store.mandate(business_id, mandate_id)
        document = view["mandate"]
        plan = self.store.plan(business_id, document["plan_id"])
        bundle = next(item for item in plan["bundles"] if item["bundle_id"] == document["bundle_id"])
        snapshot = self.store.snapshot(business_id)
        answered = {item["action_id"] for item in view["negotiations"]}
        replies = []
        for action in bundle["actions"]:
            if action["action_id"] in answered:
                continue
            kind = action["counterparty_kind"]
            profile = snapshot["counterparties"].get(f"{kind}:{action['counterparty']}", {}).get("profile")
            response = counterparty.respond(action, profile)
            replies.append(self.store.record_negotiation(business_id, mandate_id, action, response,
                                                         counterparty.AGENT_VERSION, actor))
        return {"replies": replies, **self.store.mandate(business_id, mandate_id)}

    def simulate_decision(self, business_id, mandate_id, action_id, accept, operator, actor):
        """Operator override for drills: force a counterparty to accept or reject (clearly labelled)."""
        if operator["role"] not in ("owner", "accountant"):
            raise ValidationError("Viewers cannot simulate counterparty decisions.")
        if not isinstance(accept, bool):
            raise ValidationError("accept must be true or false.")
        document = self.store.mandate(business_id, mandate_id)["mandate"]
        plan = self.store.plan(business_id, document["plan_id"])
        bundle = next(item for item in plan["bundles"] if item["bundle_id"] == document["bundle_id"])
        action = next((item for item in bundle["actions"] if item["action_id"] == action_id), None)
        if not action:
            raise ValidationError("Action is not part of this mandate.")
        response = {"agent": "operator-simulation", "simulated": True, "counterparty": action["counterparty"],
                    "action_id": action_id, "status": "accepted" if accept else "rejected", "counter_terms": None,
                    "message": f"Operator-simulated {'acceptance' if accept else 'refusal'} by {action['counterparty']}. "
                               "Not genuine counterparty consent."}
        return self.store.record_negotiation(business_id, mandate_id, action, response, f"operator:{operator['id']}", actor)

    def accept_counter(self, business_id, mandate_id, actor):
        """Turn counter-offers into a new proposal; a signed mandate is never amended in place."""
        view = self.store.mandate(business_id, mandate_id)
        document = view["mandate"]
        latest = {item["action_id"]: item for item in view["negotiations"]}
        if view["status"] != "countered" or not any(item["status"] == "countered" and item["response"].get("counter_terms")
                                                    for item in latest.values()):
            raise ValidationError("This mandate has no counter-offer to accept.")
        plan = self.store.plan(business_id, document["plan_id"])
        bundle = next(item for item in plan["bundles"] if item["bundle_id"] == document["bundle_id"])
        snapshot = self.store.snapshot(business_id)
        derived = self.store.derived(snapshot)
        policy, business = snapshot["policy"], snapshot["business"]
        constraints = owner_constraints(plan.get("owner_constraints"), policy)
        policy = {**policy, "max_discount_bps": constraints["max_discount_bps"]}
        revised = []
        for action in bundle["actions"]:
            reply = latest.get(action["action_id"], {}).get("response", {})
            terms = reply.get("counter_terms") if reply.get("status") == "countered" else None
            item = {key: value for key, value in action.items() if key not in ("shortfall_without_minor",)}
            if terms and action["type"] == "supplier_deferral":
                item.update({"amount_minor": terms["amount_minor"], "days": terms["days"], "to_date": terms["to_date"]})
                item["economic_cost_minor"] = terms["amount_minor"] * terms["days"] * planner.SUPPLIER_CREDIT_APR_BPS // (365 * 10_000)
                item["adjustment"] = {**action["adjustment"], "amount_minor": terms["amount_minor"], "to_date": terms["to_date"]}
            elif terms and action["type"] == "early_payment_offer":
                bps = terms["discount_bps"]
                if type(bps) is not int or not 0 <= bps <= policy["max_discount_bps"]:
                    raise ValidationError("The customer's counter-offer exceeds the owner or policy discount ceiling. "
                                          "Create a new owner-reviewed proposal to change instructions.")
                discount = action["face_minor"] * bps // 10_000
                item.update({"discount_bps": bps, "discount_minor": discount, "amount_minor": action["face_minor"] - discount,
                             "economic_cost_minor": discount,
                             "apr_equivalent_bps": analytics.discount_apr_bps(bps, action["days"])})
                item["adjustment"] = {**action["adjustment"], "amount_minor": action["face_minor"] - discount}
            if terms:
                item["action_id"] = f"{action['action_id']}-counter"
                item["counter_offer_from"] = action["counterparty"]
            item["message"] = planner.message_for(item, business["name"])
            revised.append(item)
        check = planner.evaluate_bundle(business, policy, snapshot["records"], document["target_date"],
                                        [dict(item, deltas=None) for item in revised],
                                        accepted=snapshot["state"]["adjustments"], promises=snapshot["state"]["promises"],
                                        basis_dates=derived["likely_dates"])
        exposure = sum(item.get("face_minor", item["amount_minor"]) for item in revised)
        state = snapshot["state"]
        adjustments = state["adjustments"] + [item["adjustment"] for item in revised]
        after = project(business, policy, snapshot["records"], document["target_date"], scenario="likely",
                        invoice_dates=derived["likely_dates"], adjustments=adjustments, promises=state["promises"],
                        lookahead_days=policy["lookahead_days"])
        after_base = project(business, policy, snapshot["records"], document["target_date"], scenario="base",
                             adjustments=adjustments, promises=state["promises"], lookahead_days=policy["lookahead_days"])
        repair_seed = analytics.stable_seed(business_id, snapshot["snapshot_hash"], document["target_date"], "counter-repair-v5")
        validation_seed = analytics.stable_seed(repair_seed, "planner-final-validation-v5")
        validation_runs = max(PLAN_MC_RUNS, min(2000, PLAN_MC_RUNS * 3))
        simulation = analytics.monte_carlo(business, policy, snapshot["records"], document["target_date"],
                                           adjustments, state["promises"],
                                           runs=validation_runs, seed=validation_seed,
                                           lookahead_days=policy["lookahead_days"], as_of=state["current_date"])
        payload = {**{key: plan[key] for key in ("business_id", "target_date", "currency", "basis", "planning_horizon_end",
                                                 "risk_target", "baseline", "basis_projection", "gap_minor", "action_needed",
                                                 "financing", "reminders", "rejected", "levers", "assumptions",
                                                 "probability_breach_before", "futures_short_of_20_before",
                                                 "excluded_counterparties", "owner_constraints") if key in plan},
                   "bundles": [{"bundle_id": "counter-offer", "feasible": check["feasible"], "actions": revised,
                                "economic_cost_minor": sum(item["economic_cost_minor"] for item in revised),
                                "counterparties": len({item["counterparty"] for item in revised}),
                                "exposure_minor": exposure, "probability_breach_after": simulation["probability_breach"],
                                "futures_short_of_20_after": simulation["futures_short_of_20"],
                                "risk_target_met": simulation["probability_breach"] <= planner.RISK_TARGET,
                                "dual_approval_required": exposure > policy["dual_approval_threshold_minor"],
                                "after": summary(after), "after_base": summary(after_base),
                                "remaining_shortfall_minor": check["shortfall_minor"],
                                "risk_evaluation": {"validation_runs": validation_runs, "validation_seed": validation_seed,
                                                    "independent_of_search": True, "search_runs": 0}}],
                   "single_option_checks": [], "why_not": [],
                   "explanation": ("Counter-offer terms restore the likely-path reserve floor and need fresh approval: a signed mandate "
                                   "is never edited in place." if check["feasible"] else
                                   "The counter-offer terms do not restore the reserve floor; re-plan instead."),
                   "search": {"source": "counter-offer", "from_mandate": mandate_id,
                              "monte_carlo_runs_each": PLAN_MC_RUNS, "validation_runs_each": validation_runs}}
        # Changed terms can re-open timing risk even when the likely path is
        # funded. Keep those exact counter-offers fixed and search for extra
        # bounded requests. Nothing is agreed or executed here; every request
        # in a replacement plan needs fresh approval and exact consent again.
        if not check["feasible"] or simulation["probability_breach"] > planner.RISK_TARGET:
            repair_policy = policy
            repair = planner.plan_recovery(business, repair_policy, snapshot["records"], document["target_date"],
                                            accepted=state["adjustments"], promises=state["promises"],
                                            profiles=derived["profiles"], basis_dates=derived["likely_dates"],
                                            blocked=derived["blocked"], excluded_counterparties=plan.get("excluded_counterparties", ()),
                                            mc_seed=repair_seed, mc_runs=PLAN_MC_RUNS, as_of=state["current_date"],
                                            prefer=constraints["prefer"], required_actions=revised)
            best = repair["bundles"][0] if repair["bundles"] else None
            if best and best["feasible"] and (not check["feasible"] or
                                              best["probability_breach_after"] < simulation["probability_breach"]):
                best["bundle_id"] = "counter-offer"
                repair["search"].update(source="counter-offer repair", from_mandate=mandate_id,
                                         original_counter_probability_breach=simulation["probability_breach"])
                repair["explanation"] = ("Exact counter-offer terms are retained with additional recovery requests. "
                                           "All actions need fresh approval and counterparty consent. " + repair["explanation"])
                for key in ("probability_breach_before", "futures_short_of_20_before", "excluded_counterparties", "owner_constraints"):
                    if key in plan:
                        repair[key] = plan[key]
                payload = repair
            elif simulation["probability_breach"] > planner.RISK_TARGET:
                payload["explanation"] += " The simulated risk target remains unmet; explicit residual-risk acknowledgement is required."
        payload["owner_constraints"] = constraints
        return self.store.create_plan(business_id, payload, snapshot["snapshot_hash"], "agent:counter-offer", actor,
                                      replaces_mandate=mandate_id)

    def replan_without(self, business_id, mandate_id, actor):
        view = self.store.mandate(business_id, mandate_id)
        if view["status"] not in ("rejected", "countered"):
            raise ValidationError(f"This mandate is {view['status']}; re-planning is only for refused or countered requests.")
        refused = sorted({item["counterparty"] for item in view["negotiations"] if item["status"] in ("rejected", "countered")})
        if not refused:
            raise ValidationError("No counterparty refused or countered this mandate.")
        target = view["mandate"]["target_date"]
        previous = self.store.plan(business_id, view["mandate"]["plan_id"])
        constraints = owner_constraints(previous.get("owner_constraints"), self.store.snapshot(business_id)["policy"])
        excluded = set(refused) | set(previous.get("excluded_counterparties", []))
        return self.propose(business_id, target, actor, "agent:replan", tuple(sorted(excluded)),
                            max_discount_bps=constraints["max_discount_bps"], prefer=constraints["prefer"],
                            replaces_mandate=mandate_id)

    def send_reminder(self, business_id, target_date, action_id, operator, actor, standing=False):
        snapshot = self.store.snapshot(business_id)
        plan = self.store.latest_plan(business_id, self._target(snapshot, target_date))
        if not plan:
            raise ValidationError("Compare plans first; reminders come from the current proposal.")
        action = next((item for item in plan["reminders"] if item["action_id"] == action_id), None)
        if not action:
            raise ValidationError("That reminder is not part of the current proposal.")
        profile = snapshot["counterparties"].get(f"customer:{action['counterparty']}", {}).get("profile")
        reply = counterparty.respond(action, profile)
        standing_id = None
        if standing:
            document = self.store.standing_mandate(business_id)
            standing_id = document["mandate_id"] if document else None
        return self.store.send_reminder(business_id, action, reply, None if standing else operator, actor, standing_id)

    # ---- read-only tools -----------------------------------------------------------

    def what_if(self, business_id, target_date, changes):
        """Read-only scenario: delay customers, add an expense, or drop a receivable. Nothing is written."""
        if not isinstance(changes, dict):
            raise ValidationError("changes must be an object.")
        unknown = sorted(set(changes) - {"customer_delays", "extra_expense", "drop_invoice"})
        if unknown:
            raise ValidationError(f"Unknown what-if change(s): {', '.join(unknown)[:120]}. "
                                  "Use customer_delays, extra_expense or drop_invoice.")
        snapshot = self.store.snapshot(business_id)
        target = self._target(snapshot, target_date)
        derived = self.store.derived(snapshot)
        business, policy, state = snapshot["business"], snapshot["policy"], snapshot["state"]
        records = {kind: [dict(row) for row in rows] for kind, rows in snapshot["records"].items()}
        dates = dict(derived["likely_dates"])
        delays = changes.get("customer_delays", {})
        if not isinstance(delays, dict) or len(delays) > 20:
            raise ValidationError("customer_delays must map up to 20 customers to extra days.")
        customers = {row["customer"] for row in records["invoices"]}
        for customer, days in delays.items():
            if customer not in customers:
                raise ValidationError(f"No invoice belongs to a customer named {str(customer)[:80]!r}.")
            if isinstance(days, bool) or not isinstance(days, int) or not -30 <= days <= 90:
                raise ValidationError("Each customer delay must be a whole number of days from -30 to 90.")
            for row in records["invoices"]:
                if row["customer"] == customer and row["id"] in dates:
                    dates[row["id"]] = max(business["opening_date"], add_days(dates[row["id"]], days))
        expense = changes.get("extra_expense")
        if expense is not None:
            if not isinstance(expense, dict):
                raise ValidationError("extra_expense must be an object.")
            amount = expense.get("amount_minor")
            if isinstance(amount, bool) or not isinstance(amount, int) or not 0 < amount <= MAX_AMOUNT_MINOR:
                raise ValidationError("extra_expense.amount_minor must be a positive integer.")
            if set(expense) - {"amount_minor", "date"}:
                raise ValidationError("extra_expense takes only amount_minor and date.")
            day = valid_date(expense.get("date", ""), "extra_expense.date")
            end = horizon_end(business, target, policy["lookahead_days"])
            if not business["opening_date"] <= day <= end:
                raise ValidationError(f"extra_expense.date must be between {human_date(business['opening_date'])} and "
                                      f"{human_date(end)} (the planning horizon).")
            records["transactions"].append({"id": "what-if-expense", "date": day,
                                            "description": "What-if expense", "type": "expense", "amount_minor": amount,
                                            "currency": business["currency"], "category": "What-if"})
        drop = changes.get("drop_invoice")
        if drop is not None:
            if not isinstance(drop, str) or not any(row["id"] == drop and row["status"] in OPEN_INVOICE_STATUSES
                                                    for row in records["invoices"]):
                raise ValidationError("drop_invoice must name an open invoice of this business.")
            if any(item.get("invoice_id") == drop for item in state["adjustments"]):
                raise ValidationError("This invoice already has an agreed early-payment deal, so it cannot be dropped "
                                      "in a what-if. Reset the sandbox to try it.")
            records["invoices"] = [row for row in records["invoices"] if row["id"] != drop]
            dates.pop(drop, None)
        projection = project(business, policy, records, target, adjustments=state["adjustments"], scenario="what-if",
                             invoice_dates=dates, promises=state["promises"], lookahead_days=policy["lookahead_days"])
        return {"projection": summary(projection), "series": [{"date": day["date"], "closing_cash_minor": day["closing_cash_minor"]}
                                                              for day in projection["days"]],
                "changes": changes, "written": False}

    def network(self, business_id, target_date=None):
        """Counterparty risk map: how much each customer and supplier can hurt this business's cash.

        For every customer with open invoices: the cash impact if they pay 30 days later than expected and
        if they never pay, and TidePay's probability that they pay more than 30 days late.  Expected
        impact = P(>30 days) x never-pays impact + P(8-30 days) x 30-days-late impact, so a reliable
        large customer and an unreliable small one can be compared on one scale.  Read-only.
        """
        snapshot = self.store.snapshot(business_id)
        target = self._target(snapshot, target_date)
        derived = self.store.derived(snapshot)
        business, policy, state, records = snapshot["business"], snapshot["policy"], snapshot["state"], snapshot["records"]
        dates = derived["likely_dates"]

        def run(rows=None, invoice_dates=None):
            projection = project(business, policy, rows or records, target, adjustments=state["adjustments"], scenario="what-if",
                                 invoice_dates=invoice_dates or dates, promises=state["promises"],
                                 lookahead_days=policy["lookahead_days"])
            result = summary(projection)
            result["days_below_reserve"] = sum(day["closing_cash_minor"] < policy["reserve_floor_minor"] for day in projection["days"])
            return result

        def hit(after):
            """Lowest-cash drop, cash lost by the horizon end, and extra days under the reserve."""
            return {"lowest_cash_drop_minor": baseline["minimum_cash_minor"] - after["minimum_cash_minor"],
                    "horizon_cash_drop_minor": baseline["closing_cash_minor"] - after["closing_cash_minor"],
                    "extra_days_below_reserve": after["days_below_reserve"] - baseline["days_below_reserve"]}

        baseline = run()
        open_rows = [row for row in records["invoices"] if row["status"] in OPEN_INVOICE_STATUSES]
        receivables = sum(row["amount_minor"] for row in open_rows) or 1
        customers = []
        for name in sorted({row["customer"] for row in open_rows}):
            own = [row for row in open_rows if row["customer"] == name]
            late = run(invoice_dates={**dates, **{row["id"]: add_days(dates.get(row["id"], row["expected_collection_date"]), 30)
                                                  for row in own}})
            never = run(rows={**records, "invoices": [row for row in records["invoices"] if row not in own]})
            forecasts = [derived["predictions"][row["id"]] for row in own if row["id"] in derived["predictions"]]
            p30 = max((f["probabilities"][4] for f in forecasts), default=0.0)
            p8 = max((sum(f["probabilities"][2:4]) for f in forecasts), default=0.0)
            if_late, if_never = hit(late), hit(never)
            loss_late = max(if_late["lowest_cash_drop_minor"], if_late["horizon_cash_drop_minor"])
            loss_never = max(if_never["lowest_cash_drop_minor"], if_never["horizon_cash_drop_minor"])
            exposure = sum(row["amount_minor"] for row in own)
            customers.append({
                "name": name, "kind": "customer", "open_minor": exposure, "share_of_receivables": round(exposure / receivables, 3),
                "p_over_30_days": round(p30, 3), "p_8_to_30_days": round(p8, 3),
                "tidepay_delay_days": max((f["likely_delay_days"] for f in forecasts), default=None),
                "if_30_days_late": if_late, "if_never_pays": if_never,
                "impact_if_30_days_late_minor": loss_late, "impact_if_never_pays_minor": loss_never,
                "expected_impact_minor": round(p30 * loss_never + p8 * loss_late),
                "breaks_payroll_if_never_pays": never["payroll_at_risk"] and not baseline["payroll_at_risk"],
                "new_breach_if_never_pays": never["reserve_shortfall_minor"] > 0 and baseline["reserve_shortfall_minor"] == 0})
        customers.sort(key=lambda item: (-item["expected_impact_minor"], -item["impact_if_never_pays_minor"],
                                         -item["p_over_30_days"] * item["open_minor"]))
        suppliers = []
        for name in sorted({row["payee"] for row in records["bills"] if row["status"] in ("open", "scheduled", "rescheduled")}):
            bills = [row for row in records["bills"] if row["payee"] == name and row["status"] in ("open", "scheduled", "rescheduled")]
            profile = snapshot["counterparties"].get(f"supplier:{name}", {}).get("profile", {})
            suppliers.append({
                "name": name, "kind": "supplier", "open_minor": sum(row["amount_minor"] for row in bills),
                "next_due": min(row["due_date"] for row in bills),
                "can_defer": any(row["reschedule_allowed"] and row["priority"] != "payroll" for row in bills)
                and profile.get("style") != "strict",
                "blocked": [derived["blocked"][row["id"]] for row in bills if row["id"] in derived["blocked"]]})
        suppliers.sort(key=lambda item: -item["open_minor"])
        top = customers[0] if customers else None
        currency = business["currency"]
        if not top:
            headline = "No open receivables, so no customer can delay your cash."
        else:
            never = top["if_never_pays"]
            headline = (f"{top['name']} is the riskiest payer (TidePay: {round(top['p_over_30_days'] * 100)}% chance of more than "
                        f"30 days late), but its payment is not expected before {human_date(baseline['end_date'])}, so your "
                        "forecast already does not count on it.") if top["impact_if_never_pays_minor"] == 0 else (
                       f"{top['name']} is your biggest counterparty risk: TidePay gives a {round(top['p_over_30_days'] * 100)}% "
                        f"chance of paying more than 30 days late, and if they never pay you lose "
                        f"{money_text(top['impact_if_never_pays_minor'], currency)} of cash by {human_date(baseline['end_date'])}"
                        + (f" and spend {never['extra_days_below_reserve']} more day(s) under the reserve" if never["extra_days_below_reserve"] > 0 else "")
                        + (", and payroll fails." if top["breaks_payroll_if_never_pays"] else "."))
        return {"business": {"name": business["name"], "currency": business["currency"]}, "target_date": target,
                "baseline": baseline, "customers": customers, "suppliers": suppliers, "headline": headline,
                "method": "Each customer is stressed alone on the likely projection: paying 30 days later than TidePay "
                          "expects, and never paying. Impact is the larger of the drop in lowest cash and the cash lost by "
                          "the horizon end. Expected impact = P(>30 days late) x never-pays impact + P(8-30 days) x "
                          "30-days-late impact. Read-only; synthetic data."}

    def iso20022(self, business_id):
        """Draft ISO 20022 pain.001 instructions for the deferred supplier payments. Never transmitted."""
        snapshot = self.store.snapshot(business_id)
        business, records = snapshot["business"], snapshot["records"]
        bills = {row["id"]: row for row in records["bills"]}
        adjustments = [item for item in snapshot["state"]["adjustments"] if item["kind"] == "bill_deferral"]
        if not adjustments:
            raise ValidationError("No executed supplier deferrals yet; nothing to schedule.")
        ns = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"
        ET.register_namespace("", ns)
        q = lambda tag: f"{{{ns}}}{tag}"  # noqa: E731
        root = ET.Element(q("Document"))
        initiation = ET.SubElement(root, q("CstmrCdtTrfInitn"))
        header = ET.SubElement(initiation, q("GrpHdr"))
        ET.SubElement(header, q("MsgId")).text = f"TW-{snapshot['state']['version']:04d}-{business_id[:20]}"[:35]
        ET.SubElement(header, q("CreDtTm")).text = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        ET.SubElement(header, q("NbOfTxs")).text = str(len(adjustments))
        ET.SubElement(header, q("CtrlSum")).text = f"{sum(item['amount_minor'] for item in adjustments) / 100:.2f}"
        ET.SubElement(ET.SubElement(header, q("InitgPty")), q("Nm")).text = business["name"]
        for index, item in enumerate(adjustments, 1):
            bill = bills[item["bill_id"]]
            info = ET.SubElement(initiation, q("PmtInf"))
            ET.SubElement(info, q("PmtInfId")).text = f"{item['bill_id']}-{index}"[:35]
            ET.SubElement(info, q("PmtMtd")).text = "TRF"
            ET.SubElement(ET.SubElement(info, q("ReqdExctnDt")), q("Dt")).text = item["to_date"]
            ET.SubElement(ET.SubElement(info, q("Dbtr")), q("Nm")).text = business["name"]
            ET.SubElement(ET.SubElement(ET.SubElement(ET.SubElement(info, q("DbtrAcct")), q("Id")), q("Othr")), q("Id")).text = "SANDBOX-ACCOUNT"
            ET.SubElement(ET.SubElement(ET.SubElement(info, q("DbtrAgt")), q("FinInstnId")), q("Nm")).text = "Sandbox bank (not connected)"
            transfer = ET.SubElement(info, q("CdtTrfTxInf"))
            ET.SubElement(ET.SubElement(transfer, q("PmtId")), q("EndToEndId")).text = f"{item['bill_id']}"[:35]
            amount = ET.SubElement(ET.SubElement(transfer, q("Amt")), q("InstdAmt"), Ccy=business["currency"])
            amount.text = f"{item['amount_minor'] / 100:.2f}"
            creditor = ET.SubElement(transfer, q("Cdtr"))
            ET.SubElement(creditor, q("Nm")).text = bill["payee"]
            address = ET.SubElement(creditor, q("PstlAdr"))
            ET.SubElement(address, q("TwnNm")).text = "Sandbox"
            ET.SubElement(address, q("Ctry")).text = business["country"] or "BD"
            ET.SubElement(ET.SubElement(ET.SubElement(ET.SubElement(transfer, q("CdtrAcct")), q("Id")), q("Othr")), q("Id")).text = \
                bill["payee_account"] or "UNVERIFIED"
            ET.SubElement(ET.SubElement(transfer, q("RmtInf")), q("Ustrd")).text = \
                f"Deferred portion of bill {bill['id']} (sandbox draft; never sent)"[:140]
        body = ET.tostring(root, encoding="unicode")
        comment = "<!-- Tideway sandbox draft. Generated, never transmitted. Not schema-validated; modelled on pain.001.001.09. -->"
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + comment + "\n" + body + "\n"

    def import_csv(self, business_id, text, actor, replace_demo=False):
        business = self.store.get_business(business_id)
        parsed = parse_combined_csv(text, business_id, business["currency"])
        return self.store.import_records(business_id, parsed, actor, "csv", replace_demo)
