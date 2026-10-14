"""Copilot tools that TideLM plans can call, plus the validator that runs those plans.

The language model only proposes a JSON plan. This module checks every call
(known tool, typed arguments, counterparty names that exist in this business,
amounts within limits) before anything runs, and every tool here is read or
propose only. Unknown or unsafe calls are rejected, never "best-guessed".
"""
from __future__ import annotations

import difflib
import statistics
from datetime import date, timedelta

from . import analytics, conversation
from .domain import (MAX_UNITS, OPEN_INVOICE_STATUSES, SETTLED_INVOICE_STATUSES, SecurityError, ValidationError, add_days, days_between,
                     human_date, money_text)
from .ml.model import BUCKETS, predict_for
from .projection import summary

TOOLS = {
    "project_cash": {"scenario"},
    "simulate_risk": set(),
    "what_if": {"customer_delays", "extra_expense", "drop_invoice_customer"},
    "propose_plan": {"exclude_counterparties", "max_discount_pct", "prefer"},
    "explain_plan": set(),
    "credit_check": {"customer", "amount", "terms_days"},
    "draft_reminders": {"customers"},
    "bank_pack": set(),
    "customer_report": {"customer"},
    "refuse": {"reason"},
}
MAX_CALLS = 4


def resolve_name(name, candidates):
    """Map a typed name to a real counterparty; ambiguity or no match is an error, not a guess."""
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("A counterparty name is required.")
    exact = [c for c in candidates if c.casefold() == name.strip().casefold()]
    if exact:
        return exact[0]
    close = difflib.get_close_matches(name.strip().casefold(), [c.casefold() for c in candidates], n=2, cutoff=0.82)
    if len(close) == 1:
        return next(c for c in candidates if c.casefold() == close[0])
    raise ValidationError(f"'{name[:60]}' does not match one counterparty of this business. Known: {', '.join(sorted(candidates))}.")


def validate_plan(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("calls"), list) or not plan["calls"]:
        raise ValidationError("TideLM returned no tool calls.")
    if len(plan["calls"]) > MAX_CALLS:
        raise ValidationError("Too many tool calls in one plan.")
    for call in plan["calls"]:
        if not isinstance(call, dict) or call.get("tool") not in TOOLS:
            raise SecurityError("forbidden_tool",
                                f"tool {str(call.get('tool') if isinstance(call, dict) else call)[:40]} is not permitted.")
        args = call.get("args") or {}
        if not isinstance(args, dict) or not set(args) <= TOOLS[call["tool"]]:
            raise ValidationError(f"Arguments for {call['tool']} do not match its schema.")
    return plan


def customers_of(snapshot):
    return sorted({row["customer"] for row in snapshot["records"]["invoices"]})


def suppliers_of(snapshot):
    return sorted({row["payee"] for row in snapshot["records"]["bills"]})


def credit_check(app, business_id, customer, amount_units, terms_days, target_date=None):
    """Should we sell on credit to this customer? TidePay risk + exposure + cash timing, explained."""
    snapshot = app.store.snapshot(business_id)
    business, records = snapshot["business"], snapshot["records"]
    customer = resolve_name(customer, customers_of(snapshot))
    if isinstance(amount_units, bool) or not isinstance(amount_units, (int, float)) or not 0 < amount_units <= MAX_UNITS:
        raise ValidationError("Amount must be a positive number.")
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
    new_minor = int(round(amount_units * 100))
    share = (open_now + new_minor) / max(1, open_total + new_minor)
    if p_over_30 >= 0.25:
        verdict, advice = "high_risk", "Ask for at least 50% upfront or cash on delivery; do not extend full credit."
        safe_terms = 0
    elif p_over_30 >= 0.10 or p_over_15 >= 0.35:
        verdict, advice = "caution", "Offer shorter terms or take a 30% deposit."
        safe_terms = max(7, terms_days - 15)
    else:
        verdict, advice = "safe", "These terms look safe based on this customer's history."
        safe_terms = terms_days
    expected_arrival = add_days(due.isoformat(), max(0, round(prediction["expected_delay_days"])))
    reasons = [f"{len(history)} settled invoice(s) on record" + (f", average {statistics.fmean(h['delay'] for h in history):.1f} days late"
                                                                   if history else "; using the business-wide pattern"),
               f"TidePay expects about {max(0, round(prediction['expected_delay_days']))} days of delay "
               f"({round(p_over_30 * 100)}% chance of more than 30 days)",
               f"expected payment around {human_date(expected_arrival, True)}"]
    if share >= 0.5:
        reasons.append(f"after this sale {round(share * 100)}% of all money owed to you would sit with {customer}")
        if verdict == "safe":
            verdict, advice = "caution", "The customer pays well, but this sale concentrates too much risk in one account; consider a deposit."
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


def run_plan(app, business_id, target_date, plan, actor):
    """Execute a validated TideLM plan. Returns tool results for the reply writer."""
    validate_plan(plan)
    snapshot = app.store.snapshot(business_id)
    names = customers_of(snapshot)
    results = []
    for call in plan["calls"]:
        tool, args = call["tool"], call.get("args") or {}
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
        elif tool == "what_if":
            changes = {}
            delays = args.get("customer_delays") or {}
            if not isinstance(delays, dict):
                raise ValidationError("customer_delays must be an object.")
            changes["customer_delays"] = {resolve_name(k, names): int(v) for k, v in delays.items()}
            expense = args.get("extra_expense")
            if expense:
                changes["extra_expense"] = {"amount_minor": int(round(float(expense["amount"]) * 100)), "date": expense["date"]}
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
            results.append({"tool": tool, "result": {"plan_id": proposal["plan_id"], "explanation": proposal["explanation"],
                                                     "excluded": excluded, "prefer": prefer,
                                                     "recommended_cost_minor": best["economic_cost_minor"] if best else None,
                                                     "futures_short_of_20_after": best["futures_short_of_20_after"] if best else None}})
        elif tool == "explain_plan":
            plan_row = app.store.latest_plan(business_id, target_date or snapshot["business"]["default_target_date"])
            results.append({"tool": tool, "result": {"explanation": conversation.explain_choice(plan_row, snapshot["business"]["currency"]),
                                                     "why_not": (plan_row or {}).get("why_not", [])[:4]}})
        elif tool == "credit_check":
            results.append({"tool": tool, "result": credit_check(app, business_id, args.get("customer"), args.get("amount"),
                                                                 args.get("terms_days"), target_date)})
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
    return results


def reply_from_results(results, currency):
    """Deterministic, number-safe reply composed from tool output (TideLM decides what to do; code states the facts)."""
    lines = []
    for item in results:
        tool, r = item["tool"], item["result"]
        if tool == "refuse":
            lines.append("I can't approve, pay or transfer money; a person approves in the app with a PIN."
                         if r["reason"] == "approve_or_move_money" else conversation.out_of_scope())
        elif tool == "project_cash":
            lines.append(f"{r['scenario'].title()} view: lowest cash {money_text(r['minimum_cash_minor'], currency)} on "
                         f"{human_date(r['minimum_cash_date'])}; reserve shortfall {money_text(r['reserve_shortfall_minor'], currency)}"
                         + ("; payroll is at risk." if r["payroll_at_risk"] else "; payroll is funded."))
        elif tool == "simulate_risk":
            lines.append(f"{r['futures_short_of_20']} of 20 simulated futures breach the reserve; payroll unfunded in "
                         f"{round(r['probability_payroll_unfunded'] * 100)}% of {r['runs']} runs.")
        elif tool == "what_if":
            lines.append(conversation.whatif_text("With that change", r["projection"], r["baseline"], currency))
        elif tool == "propose_plan":
            lines.append(r["explanation"] + " It is waiting for human approval in the Rescue plan view.")
        elif tool == "explain_plan":
            lines.append(r["explanation"] or "There is no current plan yet. Ask me for a rescue plan.")
        elif tool == "credit_check":
            lines.append(f"Credit check for {r['customer']} ({money_text(r['amount_minor'], currency)}, {r['terms_days']} days): "
                         f"{r['verdict'].replace('_', ' ').upper()}. {r['advice']} " + "; ".join(r["reasons"]) + ".")
        elif tool == "draft_reminders":
            lines.append(f"{len(r['drafts'])} reminder draft(s) ready: " + ", ".join(f"{d['customer']} ({d['tone']})" for d in r["drafts"])
                         + ". Review and send them from the Rescue plan view.")
        elif tool == "bank_pack":
            lines.append("Your bank-ready pack is prepared: cash history, receivables aging, forecast, risk and plan. Open it from Cash weather.")
        elif tool == "customer_report":
            parts = []
            for c in r["customers"]:
                forecast = c["open_invoice_forecasts"][0] if c["open_invoice_forecasts"] else None
                delay = forecast["likely_delay_days"] if forecast else c["expected_delay_days"]
                parts.append(f"{c['customer']}: grade {c['grade']}, TidePay expects about {delay} days late on the open invoice, "
                             f"{money_text(c['open_exposure_minor'], currency)} open")
            lines.append("; ".join(parts) + ".")
    return " ".join(lines)
