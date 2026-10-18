"""Copilot tools that TideLM plans can call, plus the validator that runs those plans.

The language model only proposes a JSON plan. This module checks every call
(known tool, typed arguments, counterparty names that exist in this business,
amounts within limits) before anything runs, and every tool here is read or
propose only. Unknown or unsafe calls are rejected, never "best-guessed".
"""
from __future__ import annotations

import copy
import hashlib
import time
import statistics
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from . import analytics, conversation, i18n
from .domain import (MAX_UNITS, OPEN_INVOICE_STATUSES, SETTLED_INVOICE_STATUSES, SecurityError, ValidationError, add_days, days_between,
                     canonical_json, money_text, valid_date)
from .ml.model import BUCKETS, predict_for
from .projection import horizon_end, summary

TOOLS = {
    "project_cash": {"scenario"},
    "simulate_risk": set(),
    "reverse_stress": set(),
    "agreement_stress": set(),
    "recovery_options": set(),
    "what_if": {"customer_delays", "extra_expense", "drop_invoice_customer"},
    "propose_plan": {"exclude_counterparties", "max_discount_pct", "prefer"},
    "explain_plan": set(),
    "credit_check": {"customer", "amount", "terms_days", "currency"},
    "draft_reminders": {"customers"},
    "bank_pack": set(),
    "customer_report": {"customer"},
    "counterparty_risk": set(),
    "security_check": set(),
    "refuse": {"reason"},
}
MAX_CALLS = 4
MAX_RESULT_BYTES = 32768
MAX_NAMES = 20
PLANNER_ROLES = ("owner", "accountant")
PROPOSING_TOOLS = ("propose_plan", "draft_reminders")


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 160 or any(ord(c) < 32 for c in value):
        raise ValidationError(f"{field} must be non-empty text.")


def _number(value, field, *, minimum=None, maximum=None, decimals=None):
    """Validate a JSON number without allowing bools, NaN, infinity or overflow."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{field} must be a number.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, AttributeError):
        raise ValidationError(f"{field} must be a number.") from None
    if not number.is_finite():
        raise ValidationError(f"{field} must be a finite number.")
    if minimum is not None and number < minimum:
        raise ValidationError(f"{field} must be at least {minimum}.")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{field} must be at most {maximum}.")
    if decimals is not None:
        quantum = Decimal(1).scaleb(-decimals)
        if number != number.quantize(quantum):
            raise ValidationError(f"{field} may have at most {decimals} decimal places.")


def _text_list(value, field):
    if not isinstance(value, list) or len(value) > MAX_NAMES:
        raise ValidationError(f"{field} must be a list of up to {MAX_NAMES} names.")
    for index, item in enumerate(value):
        _text(item, f"{field}[{index}]")


def _validate_what_if_args(args):
    delays = args.get("customer_delays")
    if delays is not None:
        if not isinstance(delays, dict) or len(delays) > 20:
            raise ValidationError("what_if.customer_delays must map up to 20 customers to extra days.")
        for customer, days in delays.items():
            _text(customer, "what_if.customer_delays customer")
            if isinstance(days, bool) or not isinstance(days, int) or not -30 <= days <= 90:
                raise ValidationError("what_if customer delays must be whole numbers from -30 to 90 days.")

    expense = args.get("extra_expense")
    if expense is not None:
        if not isinstance(expense, dict):
            raise ValidationError("what_if.extra_expense must be an object.")
        unknown = [key for key in expense if key not in {"amount", "date", "currency"}]
        if unknown:
            raise ValidationError("what_if.extra_expense takes only amount, date and optional currency.")
        if "amount" not in expense or "date" not in expense:
            raise ValidationError("what_if.extra_expense needs amount and date.")
        _number(expense["amount"], "what_if.extra_expense.amount", minimum=Decimal("0.01"),
                maximum=MAX_UNITS, decimals=2)
        valid_date(expense["date"], "what_if.extra_expense.date")

    if "drop_invoice_customer" in args and args["drop_invoice_customer"] is not None:
        _text(args["drop_invoice_customer"], "what_if.drop_invoice_customer")


def _validate_tool_args(tool, args):
    """Validate model-produced argument values before any tool implementation sees them."""
    if tool == "project_cash":
        if "scenario" in args:
            _text(args["scenario"], "project_cash.scenario")
            if args["scenario"] not in ("base", "likely", "stress"):
                raise ValidationError("project_cash.scenario must be base, likely or stress.")
    elif tool == "what_if":
        _validate_what_if_args(args)
    elif tool == "propose_plan":
        if "exclude_counterparties" in args and args["exclude_counterparties"] is not None:
            _text_list(args["exclude_counterparties"], "propose_plan.exclude_counterparties")
        if "max_discount_pct" in args and args["max_discount_pct"] is not None:
            _number(args["max_discount_pct"], "propose_plan.max_discount_pct", minimum=Decimal("0"), maximum=Decimal("10"), decimals=2)
        if "prefer" in args and args["prefer"] is not None:
            _text(args["prefer"], "propose_plan.prefer")
            if args["prefer"] not in ("lowest_cost", "lowest_risk", "fewest_asks"):
                raise ValidationError("propose_plan.prefer is not recognised.")
    elif tool == "credit_check":
        missing = [field for field in ("customer", "amount", "terms_days") if field not in args]
        if missing:
            raise ValidationError(f"credit_check needs: {', '.join(missing)}.")
        _text(args["customer"], "credit_check.customer")
        _number(args["amount"], "credit_check.amount", minimum=Decimal("0.01"), maximum=MAX_UNITS, decimals=2)
        if "currency" in args:
            _text(args["currency"], "credit_check.currency")
        if isinstance(args["terms_days"], bool) or not isinstance(args["terms_days"], int) or not 0 <= args["terms_days"] <= 180:
            raise ValidationError("credit_check.terms_days must be a whole number from 0 to 180.")
    elif tool == "draft_reminders":
        if "customers" in args and args["customers"] is not None:
            _text_list(args["customers"], "draft_reminders.customers")
    elif tool == "customer_report":
        if "customer" in args and args["customer"] is not None:
            _text(args["customer"], "customer_report.customer")
    elif tool == "refuse":
        if "reason" in args:
            _text(args["reason"], "refuse.reason")
            if args["reason"] not in ("approve_or_move_money", "out_of_scope"):
                raise ValidationError("refuse.reason is not recognised.")


def resolve_name(name, candidates):
    """Map a typed name to a real counterparty; ambiguity or no match is an error, not a guess."""
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("A counterparty name is required.")
    exact = [c for c in candidates if c.casefold() == name.strip().casefold()]
    if len(exact) == 1:
        return exact[0]
    raise ValidationError(f"'{name[:60]}' does not match exactly one counterparty of this business. "
                          f"Use the ledger spelling: {', '.join(sorted(candidates)[:20])}.")


def validate_plan(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("calls"), list) or not plan["calls"]:
        raise ValidationError("TideLM returned no tool calls.")
    if set(plan) - {"intent", "calls"}:
        raise ValidationError("Plan has unsupported fields; only intent and calls are allowed.")
    if len(plan["calls"]) > MAX_CALLS:
        raise ValidationError("Too many tool calls in one plan.")
    for call in plan["calls"]:
        if not isinstance(call, dict):
            raise SecurityError("forbidden_tool",
                                f"tool {str(call)[:40]} is not permitted.")
        tool = call.get("tool")
        if not isinstance(tool, str) or tool not in TOOLS:
            raise SecurityError("forbidden_tool", f"tool {str(tool)[:40]} is not permitted.")
        unknown_call_fields = set(call) - {"tool", "args"}
        if unknown_call_fields:
            raise ValidationError(f"Call for {tool} has unsupported fields.")
        if "args" in call and not isinstance(call["args"], dict):
            raise ValidationError(f"Arguments for {tool} must be an object.")
        args = call.get("args", {})
        if not set(args) <= TOOLS[tool]:
            raise ValidationError(f"Arguments for {call['tool']} do not match its schema.")
        _validate_tool_args(tool, args)
    if "intent" in plan:
        _text(plan["intent"], "Plan intent")
    return plan


def customers_of(snapshot):
    return sorted({row["customer"] for row in snapshot["records"]["invoices"]})


def suppliers_of(snapshot):
    return sorted({row["payee"] for row in snapshot["records"]["bills"]})


def credit_check(app, business_id, customer, amount_units, terms_days, target_date=None, lang="en"):
    """Should we sell on credit to this customer? TidePay risk + exposure + cash timing, explained."""
    snapshot = app.store.snapshot(business_id)
    business, records = snapshot["business"], snapshot["records"]
    customer = resolve_name(customer, customers_of(snapshot))
    _number(amount_units, "credit_check.amount", minimum=Decimal("0.01"), maximum=MAX_UNITS, decimals=2)
    if isinstance(terms_days, bool) or not isinstance(terms_days, int) or not 0 <= terms_days <= 180:
        raise ValidationError("Terms must be 0-180 days.")
    today = snapshot["state"]["current_date"]
    settled = [r for r in records["invoices"] if r["status"] in SETTLED_INVOICE_STATUSES and r.get("paid_date")]
    history = sorted(({"delay": days_between(r["due_date"], r["paid_date"]), "amount": r["amount_minor"] / 100,
                       "paid_date": r["paid_date"]} for r in settled if r["customer"] == customer), key=lambda h: h["paid_date"])
    portfolio = statistics.fmean(days_between(r["due_date"], r["paid_date"]) for r in settled) if settled else 5.0
    due = date.fromisoformat(today) + timedelta(days=terms_days)
    model = analytics.tidepay_model()
    prediction = predict_for(model, history, float(amount_units), max(1, terms_days), due, portfolio)
    probs = prediction["probabilities"]
    p_over_15, p_over_30 = sum(probs[3:]), probs[4]
    open_now = sum(r["amount_minor"] for r in records["invoices"] if r["status"] in OPEN_INVOICE_STATUSES and r["customer"] == customer)
    open_total = sum(r["amount_minor"] for r in records["invoices"] if r["status"] in OPEN_INVOICE_STATUSES)
    new_minor = int(Decimal(str(amount_units)) * 100)
    share = (open_now + new_minor) / max(1, open_total + new_minor)
    if p_over_30 >= 0.25:
        verdict, safe_terms = "high_risk", 0
    elif p_over_30 >= 0.10 or p_over_15 >= 0.35:
        verdict, safe_terms = "caution", max(7, terms_days - 15)
    else:
        verdict, safe_terms = "safe", terms_days
    advice_key = f"advice_{verdict}"
    expected_arrival = add_days(due.isoformat(), max(0, round(prediction["expected_delay_days"])))
    reasons = [i18n.t(lang, "r_history", n=len(history), late=f"{statistics.fmean(h['delay'] for h in history):.1f}")
               if history else i18n.t(lang, "r_nohistory"),
               i18n.t(lang, "r_tidepay", days=max(0, round(prediction["expected_delay_days"])), p30=round(p_over_30 * 100)),
               i18n.t(lang, "r_arrival", date=i18n.day(lang, expected_arrival))]
    if share >= 0.5:
        reasons.append(i18n.t(lang, "r_share", share=round(share * 100), who=customer))
        if verdict == "safe":
            verdict, advice_key = "caution", "advice_concentration"
    advice = i18n.t(lang, advice_key)
    return {"customer": customer, "amount_minor": new_minor, "currency": business["currency"], "terms_days": terms_days,
            "verdict": verdict, "advice": advice, "suggested_terms_days": safe_terms,
            "probabilities": dict(zip([b[2] for b in BUCKETS], probs)), "expected_delay_days": prediction["expected_delay_days"],
            "expected_payment_date": expected_arrival, "exposure_share_after": round(share, 3), "reasons": reasons,
            "model": "TidePay (federated-trained, Tideway's own model)"}


def customer_report(app, business_id, customer=None):
    snapshot = app.store.snapshot(business_id)
    derived = app.store.derived(snapshot)
    profiles = derived["profiles"]["customers"]
    if customer:
        name = resolve_name(customer, list(profiles))
        rows = [profiles[name]]
    else:
        rows = sorted(profiles.values(), key=lambda item: -item["expected_delay_days"])
    for row in rows:
        row["open_invoice_forecasts"] = [p for p in derived["predictions"].values() if p["customer"] == row["customer"]]
    return {"customers": rows, "currency": snapshot["business"]["currency"]}


def bank_pack(app, business_id, target_date=None):
    """Everything a lender asks a small business for, assembled from the ledger (read-only)."""
    snapshot = app.store.snapshot(business_id)
    analysis = app.analysis(business_id, target_date, snapshot)
    business, records = snapshot["business"], snapshot["records"]
    history = [r for r in records["transactions"] if r["date"] < business["opening_date"]]
    months = {}
    for row in history:
        bucket = months.setdefault(row["date"][:7], {"month": row["date"][:7], "in_minor": 0, "out_minor": 0})
        bucket["in_minor" if row["type"] == "income" else "out_minor"] += row["amount_minor"]
    for invoice in records["invoices"]:
        if invoice["status"] in SETTLED_INVOICE_STATUSES and invoice.get("paid_date", "") < business["opening_date"] and invoice.get("paid_date"):
            months.setdefault(invoice["paid_date"][:7], {"month": invoice["paid_date"][:7], "in_minor": 0, "out_minor": 0})["in_minor"] += invoice["amount_minor"]
    aging = {"current": 0, "1-30": 0, "31-60": 0, "60+": 0}
    for invoice in records["invoices"]:
        if invoice["status"] not in OPEN_INVOICE_STATUSES:
            continue
        late = days_between(invoice["due_date"], snapshot["state"]["current_date"])
        aging["current" if late <= 0 else "1-30" if late <= 30 else "31-60" if late <= 60 else "60+"] += invoice["amount_minor"]
    plan = app.store.latest_plan(business_id, analysis["target_date"])
    return {"business": {key: business[key] for key in ("name", "currency", "country", "sector", "opening_date")},
            "prepared_on": snapshot["state"]["current_date"], "monthly_cash_history": [months[k] for k in sorted(months)],
            "receivables_aging_minor": aging, "kpis": analysis["kpis"], "forecast": summary(analysis["projections"]["likely"]),
            "risk": {key: analysis["simulation"][key] for key in ("probability_breach", "futures_short_of_20", "runs", "seed")},
            "funding_need_minor": analysis["projections"]["likely"]["reserve_shortfall_minor"],
            "recovery_plan": plan["explanation"] if plan else None,
            "evidence": {"audit_head": app.store.evidence(business_id)["head_hash"]},
            "note": "Prepared from the business's own records by Tideway. Synthetic sandbox data; not a credit decision."}


def preflight_plan(app, business_id, target_date, plan, role="owner"):
    """Resolve the *whole* plan before any proposal can be stored.

    Currency defaults to the scoped ledger's currency, never to a model-selected
    exchange rate. Names must match a unique ledger spelling; typos need clarification.
    """
    validate_plan(plan)
    if len(canonical_json(plan).encode()) > 16384:
        raise ValidationError("Tool plan exceeded the 16 KiB limit.")
    requested_tools = [call["tool"] for call in plan["calls"]]
    if requested_tools.count("propose_plan") > 1:
        raise ValidationError("Only one rescue proposal can be requested per selection.")
    if "what_if" in requested_tools and any(tool in PROPOSING_TOOLS for tool in requested_tools):
        raise ValidationError("A hypothetical scenario cannot create a live proposal. Ask for the what-if separately.")
    if role not in ("owner", "accountant", "viewer"):
        raise ValidationError("Unknown role; no tools were run.")
    snapshot = app.store.snapshot(business_id)
    target = app._target(snapshot, target_date)
    end = horizon_end(snapshot["business"], target, snapshot["policy"]["lookahead_days"])
    names, suppliers = customers_of(snapshot), suppliers_of(snapshot)
    resolved = copy.deepcopy(plan)
    for call in resolved["calls"]:
        tool, args = call["tool"], call.setdefault("args", {})
        if tool in PROPOSING_TOOLS:
            if role not in PLANNER_ROLES:
                raise ValidationError("Viewers can read forecasts and risk, but only an owner or accountant can build a plan.")
            if snapshot["policy"]["agent_paused"]:
                raise ValidationError("The agent is paused (kill switch); no proposal was created.")
            if snapshot["policy"]["autonomy_level"] == "advise":
                raise ValidationError("Autonomy is set to advise; the agent may read but cannot create proposals.")
        if tool in ("credit_check", "customer_report") and args.get("customer"):
            args["customer"] = resolve_name(args["customer"], names)
        if tool == "draft_reminders" and args.get("customers"):
            args["customers"] = [resolve_name(name, names) for name in args["customers"]]
        if tool == "propose_plan" and args.get("exclude_counterparties"):
            args["exclude_counterparties"] = [resolve_name(name, names + suppliers) for name in args["exclude_counterparties"]]
        if tool == "what_if":
            if args.get("customer_delays"):
                args["customer_delays"] = {resolve_name(name, names): days for name, days in args["customer_delays"].items()}
            if args.get("drop_invoice_customer"):
                customer = resolve_name(args["drop_invoice_customer"], names)
                if not any(row["customer"] == customer and row["status"] in OPEN_INVOICE_STATUSES
                           for row in snapshot["records"]["invoices"]):
                    raise ValidationError(f"{customer} has no open invoice to drop.")
                args["drop_invoice_customer"] = customer
            expense = args.get("extra_expense")
            if expense and not snapshot["business"]["opening_date"] <= expense["date"] <= end:
                raise ValidationError("what_if.extra_expense.date must be inside the planning horizon.")
        money_args = args.get("extra_expense") if tool == "what_if" else args if tool == "credit_check" else None
        if money_args is not None and "currency" in money_args:
            if money_args["currency"] != snapshot["business"]["currency"]:
                raise ValidationError(f"Use {snapshot['business']['currency']}; cross-currency conversion is not available.")
    return resolved


def _bounded_result(value):
    """Bound record-heavy results without truncating or inventing financial facts."""
    if len(canonical_json(value).encode()) <= MAX_RESULT_BYTES:
        return value
    return {"omitted": True, "reason": "Tool result exceeded the display budget; narrow the request.",
            "output_sha256": hashlib.sha256(canonical_json(value).encode()).hexdigest()}


def run_plan(app, business_id, target_date, plan, actor, lang="en", role="owner", trace=None, source="model_selected", deadline=None):
    """Execute a validated TideLM plan. Returns tool results for the reply writer."""
    plan = preflight_plan(app, business_id, target_date, plan, role)
    snapshot = app.store.snapshot(business_id)
    names = customers_of(snapshot)
    results = []
    for call in plan["calls"]:
        if deadline is not None and time.monotonic() >= deadline:
            raise ValidationError("The tool time budget was reached; no further calls were run.")
        started = time.monotonic()
        tool, args = call["tool"], call.get("args", {})
        if tool == "refuse":
            results.append({"tool": tool, "result": {"refused": True, "reason": args.get("reason", "out_of_scope")}})
        elif tool == "project_cash":
            scenario = args.get("scenario", "likely")
            if scenario not in ("base", "likely", "stress"):
                raise ValidationError("Unknown scenario.")
            analysis = app.analysis(business_id, target_date, snapshot)
            results.append({"tool": tool, "result": summary(analysis["projections"][scenario])})
        elif tool == "simulate_risk":
            simulation = app.analysis(business_id, target_date, snapshot)["simulation"]
            results.append({"tool": tool, "result": {k: simulation[k] for k in ("probability_breach", "futures_short_of_20",
                                                                               "probability_payroll_unfunded", "most_common_breach_date", "runs")}})
        elif tool in ("reverse_stress", "agreement_stress", "recovery_options"):
            from .decision_lab import DecisionLab
            kind = {"reverse_stress": "reverse", "agreement_stress": "promises", "recovery_options": "frontier"}[tool]
            results.append({"tool": tool, "result": DecisionLab(app).analyze(business_id, target_date, kind)})
        elif tool == "what_if":
            changes = {}
            delays = args.get("customer_delays") or {}
            if not isinstance(delays, dict):
                raise ValidationError("customer_delays must be an object.")
            changes["customer_delays"] = {resolve_name(k, names): int(v) for k, v in delays.items()}
            expense = args.get("extra_expense")
            if expense:
                changes["extra_expense"] = {"amount_minor": int(Decimal(str(expense["amount"])) * 100), "date": expense["date"]}
            drop = args.get("drop_invoice_customer")
            if drop:
                customer = resolve_name(drop, names)
                invoice = next((r for r in snapshot["records"]["invoices"] if r["customer"] == customer
                                and r["status"] in OPEN_INVOICE_STATUSES), None)
                if not invoice:
                    raise ValidationError(f"{customer} has no open invoice to drop.")
                changes["drop_invoice"] = invoice["id"]
            result = app.what_if(business_id, target_date, changes)
            baseline = summary(app.analysis(business_id, target_date, snapshot)["projections"]["likely"])
            results.append({"tool": tool, "result": {"projection": result["projection"], "baseline": baseline, "changes": changes}})
        elif tool == "propose_plan":
            everyone = names + suppliers_of(snapshot)
            excluded = [resolve_name(n, everyone) for n in (args.get("exclude_counterparties") or [])]
            pct = args.get("max_discount_pct")
            if pct is not None and (isinstance(pct, bool) or not isinstance(pct, (int, float)) or not 0 <= pct <= 10):
                raise ValidationError("max_discount_pct must be 0-10.")
            prefer = args.get("prefer") or "lowest_cost"
            if prefer not in ("lowest_cost", "lowest_risk", "fewest_asks"):
                raise ValidationError("Unknown preference.")
            proposal = app.propose(business_id, target_date, actor, proposed_by="agent:tidelm", excluded=tuple(excluded),
                                   max_discount_bps=None if pct is None else int(round(pct * 100)), prefer=prefer)
            best = proposal["bundles"][0] if proposal["bundles"] else None
            results.append({"tool": tool, "result": {"plan_id": proposal["plan_id"],
                                                     "action_needed": proposal["action_needed"],
                                                     "feasible": bool(best and best["feasible"]),
                                                     "outcome": ("no_action_needed" if not proposal["action_needed"] else "proposal_for_review" if best and best["feasible"] else "no_safe_plan"),
                                                     "remaining_shortfall_minor": best["remaining_shortfall_minor"] if best else proposal["gap_minor"],
                                                     "explanation": conversation.plan_summary(proposal, snapshot["business"]["currency"], lang),
                                                     "excluded": excluded, "prefer": prefer,
                                                     "recommended_cost_minor": best["economic_cost_minor"] if best else None,
                                                     "futures_short_of_20_after": best["futures_short_of_20_after"] if best else None}})
        elif tool == "explain_plan":
            plan_row = app.store.latest_plan(business_id, target_date or snapshot["business"]["default_target_date"])
            results.append({"tool": tool, "result": {"explanation": conversation.explain_choice(plan_row, snapshot["business"]["currency"], lang),
                                                     "why_not": (plan_row or {}).get("why_not", [])[:4]}})
        elif tool == "credit_check":
            results.append({"tool": tool, "result": credit_check(app, business_id, args.get("customer"), args.get("amount"),
                                                                 args.get("terms_days"), target_date, lang)})
        elif tool == "draft_reminders":
            wanted = [resolve_name(n, names) for n in (args.get("customers") or [])]
            plan_row = app.store.latest_plan(business_id, target_date or snapshot["business"]["default_target_date"])
            if not plan_row:
                plan_row = app.propose(business_id, target_date, actor, proposed_by="agent:tidelm")
            drafts = [r for r in plan_row["reminders"] if not wanted or r["counterparty"] in wanted]
            results.append({"tool": tool, "result": {"drafts": [{"customer": r["counterparty"], "tone": r["tone"],
                                                                  "message": r["message"]} for r in drafts],
                                                     "note": "Drafts only. Sending needs a person (or the standing mandate)."}})
        elif tool == "bank_pack":
            results.append({"tool": tool, "result": {"ready": True, "summary": bank_pack(app, business_id, target_date)["kpis"]}})
        elif tool == "customer_report":
            results.append({"tool": tool, "result": customer_report(app, business_id, args.get("customer"))})
        elif tool == "counterparty_risk":
            network = app.network(business_id, target_date)
            results.append({"tool": tool, "result": {"customers": network["customers"][:3], "suppliers": network["suppliers"],
                                                     "end_date": network["baseline"]["end_date"]}})
        elif tool == "security_check":
            derived = app.store.derived(snapshot)
            quarantined = sum(bool(row["risk_flags"]) for rows in snapshot["records"].values() for row in rows)
            results.append({"tool": tool, "result": {"agent_paused": snapshot["policy"]["agent_paused"],
                                                     "blocked": [{"bill_id": item["bill_id"], "payee": item["payee"], "kind": "changed_account"}
                                                                 for item in derived["payees"]["flagged"]] +
                                                                [{"bill_id": item["bill_id"], "payee": item["payee"], "kind": "lookalike",
                                                                  "similar_to": item["similar_to"]} for item in derived["payees"]["lookalikes"]],
                                                     "quarantined_records": quarantined}})
        result = results[-1]["result"]
        digest = hashlib.sha256(canonical_json(result).encode()).hexdigest()
        permission = "agent_propose" if tool in PROPOSING_TOOLS else "agent_read"
        receipt = app.store.audit(business_id, "agent.tool", actor, permission,
                                  {"tool": tool, "source": source, "output_sha256": digest,
                                   "snapshot_hash": snapshot["snapshot_hash"]})
        results[-1]["result"] = _bounded_result(result)
        if trace is not None:
            trace.append({"tool": tool, "args": args, "source": source, "status": "done",
                          "permission": permission, "duration_ms": int((time.monotonic() - started) * 1000),
                          "output_sha256": digest, "audit_id": receipt["audit_id"]})
    return results


def reply_from_results(results, currency, lang="en"):
    """Number-safe reply in the reader's language, composed from tool output (TideLM decides what to do; code states the facts)."""
    t, day = i18n.t, i18n.day
    lines = []
    for item in results:
        tool, r = item["tool"], item["result"]
        if r.get("omitted"):
            lines.append(r["reason"])
        elif tool == "refuse":
            lines.append(t(lang, "refuse_money") if r["reason"] == "approve_or_move_money" else conversation.out_of_scope(lang))
        elif tool == "project_cash":
            lines.append(t(lang, "projection", scenario=t(lang, "scenario")[r["scenario"]],
                           amount=money_text(r["minimum_cash_minor"], currency), date=day(lang, r["minimum_cash_date"]),
                           short=money_text(r["reserve_shortfall_minor"], currency),
                           payroll=t(lang, "payroll_risk" if r["payroll_at_risk"] else "payroll_ok")))
        elif tool == "simulate_risk":
            lines.append(t(lang, "risk", short=r["futures_short_of_20"], payroll=round(r["probability_payroll_unfunded"] * 100),
                           runs=r["runs"]))
        elif tool == "reverse_stress":
            hits = [x for x in r["rows"] if x["minimum_delay_days"] is not None]
            lines.append((f"Smallest tested single-customer breaking point: {hits[0]['customer']}, {hits[0]['minimum_delay_days']} extra days. "
                          f"Reserve shortfall {money_text(hits[0]['after']['reserve_shortfall_minor'], currency)}. ") if hits else "No single-customer breaking point was found inside the tested delay bound. ")
            lines.append(r["scope"])
        elif tool == "agreement_stress":
            lines.append(f"Stress-tested {r['agreements_tested']} accepted early-payment agreements with {r['delay_days']} extra days. "
                         f"At an assumed 25% late-performance rate, reserve-breach risk is {r['rows'][2]['probability_breach']*100:.2f}% of simulated futures. These are assumptions, not observed reliability.")
        elif tool == "recovery_options":
            lines.append(f"Compared {len(r['rows'])} recovery options. Additional cash estimates require confirmed funding at opening; all actions still need fresh human approval. Open Decision lab for the costs, dates and consent requirements.")
        elif tool == "what_if":
            lines.append(conversation.whatif_text(r["projection"], r["baseline"], currency, lang))
        elif tool in ("propose_plan", "explain_plan"):
            lines.append(r["explanation"])
        elif tool == "credit_check":
            lines.append(t(lang, "credit", who=r["customer"], amount=money_text(r["amount_minor"], currency), days=r["terms_days"],
                           verdict=t(lang, "verdict")[r["verdict"]], advice=r["advice"],
                           reasons=("；" if lang == "zh" else "; ").join(r["reasons"])))
        elif tool == "draft_reminders":
            lines.append(t(lang, "drafts", n=len(r["drafts"]), names=", ".join(d["customer"] for d in r["drafts"]) or "—"))
        elif tool == "bank_pack":
            lines.append(t(lang, "bank_pack"))
        elif tool == "counterparty_risk":
            top = r["customers"][0] if r["customers"] else None
            if not top:
                lines.append(t(lang, "network_empty"))
            elif top["impact_if_never_pays_minor"] == 0:
                lines.append(t(lang, "network_outside", who=top["name"], p30=round(top["p_over_30_days"] * 100), date=day(lang, r["end_date"])))
            else:
                lines.append(t(lang, "network_top", who=top["name"], p30=round(top["p_over_30_days"] * 100),
                               loss=money_text(top["impact_if_never_pays_minor"], currency), date=day(lang, r["end_date"]),
                               days=top["if_never_pays"]["extra_days_below_reserve"]))
        elif tool == "security_check":
            parts = [t(lang, "paused")] if r["agent_paused"] else []
            items = [t(lang, "b_changed", payee=b["payee"]) if b["kind"] == "changed_account"
                     else t(lang, "b_lookalike", payee=b["payee"], similar=b["similar_to"]) for b in r["blocked"]]
            parts.append(t(lang, "blocked_list", n=len(items), items=("；" if lang == "zh" else "; ").join(items))
                         if items else t(lang, "nothing_blocked"))
            if r["quarantined_records"]:
                parts.append(t(lang, "quarantined", n=r["quarantined_records"]))
            lines.append(("" if lang == "zh" else " ").join(parts))
        elif tool == "customer_report":
            parts = []
            for c in r["customers"]:
                forecast = c["open_invoice_forecasts"][0] if c["open_invoice_forecasts"] else None
                parts.append(t(lang, "customer", who=c["customer"], grade=c["grade"],
                               late=forecast["likely_delay_days"] if forecast else c["expected_delay_days"],
                               open=money_text(c["open_exposure_minor"], currency)))
            lines.append(("；" if lang == "zh" else "; ").join(parts) + ("。" if lang == "zh" else "."))
    return ("" if lang == "zh" else " ").join(lines)


def bank_pack_html(pack, display_currency=None):
    """The bank-ready pack as one printable, self-contained HTML page (no scripts, everything escaped)."""
    from html import escape
    currency = pack["business"]["currency"]
    from .currency_view import display
    m = lambda minor: escape(display(minor, currency, display_currency))  # noqa: E731
    kpis, forecast, risk = pack["kpis"], pack["forecast"], pack["risk"]
    pct = lambda value: "—" if value is None else f"{value * 100:.0f}%"  # noqa: E731
    rows = "".join(f"<tr><td>{escape(item['month'])}</td><td>{m(item['in_minor'])}</td><td>{m(item['out_minor'])}</td>"
                   f"<td>{m(item['in_minor'] - item['out_minor'])}</td></tr>" for item in pack["monthly_cash_history"])
    aging = "".join(f"<tr><td>{escape(bucket)}</td><td>{m(amount)}</td></tr>" for bucket, amount in pack["receivables_aging_minor"].items())
    facts = [("Days sales outstanding", "—" if kpis.get("dso_days") is None else f"{kpis['dso_days']:.0f} days"),
             ("Paid on time", pct(kpis.get("on_time_share"))), ("Open receivables", m(kpis["open_receivables_minor"])),
             ("Open payables", m(kpis["open_payables_minor"])), ("Largest customer share", pct(kpis.get("top_customer_share"))),
             ("Monthly expense run-rate", m(kpis["monthly_expense_run_rate_minor"]))]
    business = pack["business"]
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Bank-ready pack · {escape(business['name'])}</title>
<style>body{{font:11pt/1.5 -apple-system,'Segoe UI',Helvetica,Arial,sans-serif;color:#14221f;max-width:820px;margin:32px auto;padding:0 20px}}
h1{{color:#0f3d36;border-bottom:3px solid #1f8a70;padding-bottom:6px}}h2{{color:#0f3d36;margin-top:26px}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #c7d6d1;padding:5px 8px;text-align:left}}th{{background:#e6f2ee}}.note{{color:#5b6b67;font-size:9.5pt}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px 24px}}@media print{{body{{margin:0}}}}</style>
<h1>Bank-ready pack: {escape(business['name'])}</h1>
<p>{escape(business.get('sector') or 'Small business')} · {escape(business.get('country') or '')} · view currency {escape(display_currency or currency)} · prepared on {escape(pack['prepared_on'])}</p>
<p class="note">Converted figures use illustrative fixed rates; the original ledger is in {escape(currency)}. This is not an FX trade or signed financial authority.</p>
<h2>Key figures</h2><div class="grid">{''.join(f'<div><strong>{escape(label)}</strong><br>{value}</div>' for label, value in facts)}</div>
<h2>Cash history (settled)</h2><table><tr><th>Month</th><th>In</th><th>Out</th><th>Net</th></tr>{rows or '<tr><td colspan=4>No history yet</td></tr>'}</table>
<h2>Receivables aging</h2><table><tr><th>Days overdue</th><th>Amount</th></tr>{aging}</table>
<h2>Forecast and risk</h2><p>Lowest likely cash {m(forecast['minimum_cash_minor'])} on {escape(forecast['minimum_cash_date'])};
reserve shortfall {m(forecast['reserve_shortfall_minor'])}. In {risk['runs']} simulated futures (seed {risk['seed']}),
{risk['futures_short_of_20']} of 20 fall below the reserve. Funding need: <strong>{m(pack['funding_need_minor'])}</strong>.</p>
<h2>Recovery plan</h2><p>{escape(pack['recovery_plan'] or 'No plan has been prepared yet.')}</p>
<p class="note">{escape(pack['note'])} Audit chain head: <code>{escape(pack['evidence']['audit_head'] or '')}</code>.</p></html>"""
