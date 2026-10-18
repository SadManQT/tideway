"""Plain-language decisions, exact cash witnesses and goal-led recovery previews.

Financial calculations stay in the production ledger/planner. No model-generated
number, confidence score, approval or settlement is introduced here.
"""
from __future__ import annotations
from copy import deepcopy
from html import escape
import re

from . import bilateral
from .constraints import check_plan_constraints
from .domain import MAX_AMOUNT_MINOR, OPEN_INVOICE_STATUSES, ValidationError, valid_date, money_text
from .projection import project
from .planner import RISK_TARGET
from .resilience import digest, integer

PRIORITIES = ("lowest_cost", "fewest_asks", "lowest_risk")


def _projection(snapshot, facts, *, omit_customers=(), extra=None):
    records = deepcopy(snapshot["records"])
    omitted = {r["id"] for r in records["invoices"] if r["status"] in OPEN_INVOICE_STATUSES and r["customer"] in omit_customers}
    for row in records["invoices"]:
        if row["id"] in omitted:
            row["status"] = "cancelled"
    adjustments = [a for a in snapshot["state"]["adjustments"] if a.get("invoice_id") not in omitted]
    if extra and extra["amount_minor"]:
        # The private shadow record can never overwrite a real transaction.
        identifier = "owner-expense-scenario"
        existing = {r["id"] for r in records["transactions"]}
        while identifier in existing:
            identifier += "-x"
        records["transactions"].append({"id": identifier, "type": "expense", "category": "Scenario",
                                         "date": extra["date"], "amount_minor": extra["amount_minor"]})
    return project(snapshot["business"], snapshot["policy"], records, facts["target_date"], adjustments,
                   scenario="likely", invoice_dates=facts["derived"]["likely_dates"],
                   promises=snapshot["state"]["promises"], lookahead_days=snapshot["policy"]["lookahead_days"])


def _window(projection, as_of):
    days = [d for d in projection["days"] if d["date"] >= as_of]
    if not days:
        return {"available": False, "minimum_cash_minor": None, "minimum_cash_date": None,
                "reserve_shortfall_minor": None, "payroll_unfunded": None}
    minimum = min(days, key=lambda d: d["closing_cash_minor"])
    return {"available": True, "minimum_cash_minor": minimum["closing_cash_minor"], "minimum_cash_date": minimum["date"],
            "reserve_shortfall_minor": max(0, projection["reserve_floor_minor"] - minimum["closing_cash_minor"]),
            "payroll_unfunded": any(d["closing_cash_minor"] < 0 and any(e.get("payroll") for e in d["source_references"]) for d in days)}


def _spending_room(projection, as_of, spending_date):
    window = _window(projection, as_of)
    if not window["available"]:
        return {"available": False, "ceiling_minor": 0, "reason": "historical_horizon"}
    reserve = projection["reserve_floor_minor"]
    before = [d for d in projection["days"] if as_of <= d["date"] < spending_date]
    after = [d for d in projection["days"] if d["date"] >= spending_date]
    if any(d["closing_cash_minor"] < reserve for d in before):
        return {"available": True, "ceiling_minor": 0, "reason": "earlier_shortfall", "binding_date": window["minimum_cash_date"]}
    binding = min(after, key=lambda d: d["closing_cash_minor"])
    raw = max(0, binding["closing_cash_minor"] - reserve)
    return {"available": True, "ceiling_minor": min(raw, MAX_AMOUNT_MINOR),
            "reason": "existing_shortfall" if binding["closing_cash_minor"] < reserve else "bounded_by_cash_path",
            "binding_date": binding["date"], "amount_cap_applies": raw > MAX_AMOUNT_MINOR}


def build_report(snapshot, facts, expense_minor=0, expense_date=None):
    integer(expense_minor, "Extra expense", 0, MAX_AMOUNT_MINOR)
    business, records, state = snapshot["business"], snapshot["records"], snapshot["state"]
    likely = facts["projections"]["likely"]
    as_of, end = state["current_date"], likely["end_date"]
    date = valid_date(min(as_of, end) if expense_date is None else expense_date, "Expense date")
    if expense_date is not None and not as_of <= date <= end:
        raise ValidationError("Expense date must be within the current simulation date and planning horizon.")
    if expense_minor and as_of > end:
        raise ValidationError("Extend the target to include the current simulation date before testing spending.")
    customers = sorted({r["customer"] for r in records["invoices"] if r["status"] in OPEN_INVOICE_STATUSES})
    extra = {"amount_minor": expense_minor, "date": date}
    without = _projection(snapshot, facts, omit_customers=customers)
    after = _projection(snapshot, facts, extra=extra)
    base_window, after_window = _window(likely, as_of), _window(after, as_of)
    dependencies = []
    for customer in customers[:10]:
        altered = _window(_projection(snapshot, facts, omit_customers=(customer,)), as_of)
        impact = max(0, base_window["minimum_cash_minor"] - altered["minimum_cash_minor"]) if base_window["available"] else 0
        dependencies.append({"customer": customer, "impact_on_lowest_cash_minor": impact,
                             "without_customer": altered})
    dependencies.sort(key=lambda r: (-r["impact_on_lowest_cash_minor"], r["customer"]))
    lookup = {"transaction": {r["id"]: r for r in records["transactions"]},
              "invoice": {r["id"]: r for r in records["invoices"]}, "bill": {r["id"]: r for r in records["bills"]}}
    calendar = []
    for day in likely["days"]:
        if day["date"] < as_of or not day["source_references"]:
            continue
        sources = []
        for event in day["source_references"][:100]:
            kind = "invoice" if event["kind"].startswith("invoice") else "bill" if event["kind"].startswith("bill") else "transaction"
            original = lookup[kind].get(event["id"], {})
            sources.append({"kind": kind, "id": event["id"], "party": original.get("customer", original.get("payee", original.get("category", "Ledger record"))),
                            "effect_minor": event["effect_minor"], "payroll": bool(event.get("payroll")),
                            "basis": {"invoice": "expected_receipt", "invoice_early_payment": "unsettled_agreement", "bill_deferred": "executed_deferral"}.get(event["kind"], "ledger_schedule")})
        calendar.append({k: day[k] for k in ("date", "opening_cash_minor", "inflow_minor", "outflow_minor", "closing_cash_minor")} |
                        {"sources": sources, "source_count": len(day["source_references"]), "sources_complete": len(sources) == len(day["source_references"]),
                         "below_reserve": day["closing_cash_minor"] < snapshot["policy"]["reserve_floor_minor"]})
    payroll = [e for e in likely["source_references"] if e.get("payroll") and e["date"] >= as_of]
    payroll_date = min((e["date"] for e in payroll), default=None)
    thin = sorted(name for name in customers if facts["derived"]["profiles"]["customers"].get(name, {}).get("settled_invoices", 0) < 3)
    quarantined = sum(bool(r["risk_flags"]) for rows in records.values() for r in rows)
    status = "historical_horizon" if not base_window["available"] else "payroll_unfunded" if base_window["payroll_unfunded"] else "buffer_shortfall" if base_window["reserve_shortfall_minor"] else "no_payroll_identified" if not payroll else "likely_path_holds"
    if not any(records.values()):
        status = "no_records"
    return {"version": "owner-view-v1", "business_id": business["business_id"], "business_name": business["name"], "currency": business["currency"],
            "snapshot_hash": snapshot["snapshot_hash"], "target_date": facts["target_date"], "as_of": as_of, "end_date": end,
            "read_only": True, "executed": False, "status": status, "reserve_floor_minor": snapshot["policy"]["reserve_floor_minor"],
            "likely": base_window, "after_expense": after_window, "expense": extra,
            "spending_room": {"likely": _spending_room(likely, as_of, date), "without_unpaid_customers": _spending_room(without, as_of, date)},
            "payroll": {"identified": bool(payroll), "next_date": payroll_date,
                        "next_amount_minor": sum(-e["effect_minor"] for e in payroll if e["date"] == payroll_date)},
            "dependencies": dependencies, "dependency_coverage": {"customers_total": len(customers), "tested": len(dependencies), "complete": len(customers) <= 10},
            "calendar": calendar, "data_checks": {"quarantined_records": quarantined, "customers_under_three_settlements": thin,
                      "unpaid_invoices": sum(r["status"] in OPEN_INVOICE_STATUSES for r in records["invoices"]), "payroll_identified": bool(payroll)},
            "proposal_counted_as_cash": False,
            "scope": "Daily closing cash from the simulation date through target plus look-ahead; scheduled ledger, not a bank balance or intraday guarantee. Unpaid customer receipts and accepted agreements are assumptions. Spending room is not approval; fees and funding costs are not added automatically. Customer-removal impacts are separate scenarios and cannot be added together."}


class OwnerView:
    def __init__(self, app):
        self.app, self.store = app, app.store

    def analyze(self, business_id, target=None, expense_minor=0, expense_date=None, expected_snapshot=None):
        facts = self.app.analysis(business_id, target)
        if expected_snapshot is not None and facts["snapshot"]["snapshot_hash"] != expected_snapshot:
            raise ValidationError("Records changed. Refresh this view before comparing or exporting.")
        return build_report(facts["snapshot"], facts, expense_minor, expense_date)

    def _criteria(self, business_id, target, cap, protected):
        snapshot = self.store.snapshot(business_id)
        target = self.app._target(snapshot, target)
        previous = self.store.latest_plan(business_id, target)
        if previous and previous["snapshot_hash"] != snapshot["snapshot_hash"]:
            previous = None
        current_cap = snapshot["policy"]["max_discount_bps"]
        if previous:
            current_cap = min(current_cap, check_plan_constraints(previous, snapshot["policy"])["max_discount_bps"])
        cap = current_cap if cap is None else integer(cap, "Discount ceiling", 0, current_cap)
        if not isinstance(protected, list) or len(protected) > 20 or any(not isinstance(x, str) for x in protected):
            raise ValidationError("Protect at most 20 exact counterparty names.")
        names = {r["customer"] for r in snapshot["records"]["invoices"]} | {r["payee"] for r in snapshot["records"]["bills"]}
        if set(protected) - names:
            raise ValidationError("Select counterparties from this business; names cannot be substituted.")
        exclusions = sorted(set(protected) | set((previous or {}).get("excluded_counterparties", [])))
        pacts = {(digest(b["bilateral"])) for b in (previous or {}).get("bundles", []) if b.get("bilateral")}
        return snapshot, target, {"max_discount_bps": cap, "protected_counterparties": exclusions,
                                  "current_max_discount_bps": current_cap, "bilateral_assumptions": sorted(pacts)}, previous

    def _build(self, snapshot, target, criteria, priority, previous):
        from .decision_lab import DecisionLab
        payload = DecisionLab(self.app).build_payload(snapshot, target, constraints={"max_discount_bps": criteria["max_discount_bps"], "prefer": priority}, excluded=criteria["protected_counterparties"])
        for b in (previous or {}).get("bundles", []):
            if b.get("bilateral"):
                bilateral.carry_terms(snapshot, payload["bundles"], b["bilateral"], target)
        return payload

    @staticmethod
    def _option_id(snapshot, target, criteria, priority):
        return digest({"snapshot": snapshot["snapshot_hash"], "target": target, "cap": criteria["max_discount_bps"],
                       "protected": criteria["protected_counterparties"], "bilateral": criteria["bilateral_assumptions"], "priority": priority})

    def coach(self, business_id, target=None, cap=None, protected=None, expected_snapshot=None):
        snapshot, target, criteria, previous = self._criteria(business_id, target, cap, [] if protected is None else protected)
        if expected_snapshot is not None and snapshot["snapshot_hash"] != expected_snapshot:
            raise ValidationError("Records changed. Refresh before previewing priorities.")
        options = []
        for priority in PRIORITIES:
            try:
                payload = self._build(snapshot, target, criteria, priority, previous)
                best = payload["bundles"][0] if payload["bundles"] else None
                options.append({"priority": priority, "option_id": self._option_id(snapshot, target, criteria, priority),
                                "status": "proposal_available" if best and best["feasible"] else "infeasible" if payload["action_needed"] else "no_action_needed",
                                "cost_minor": best["economic_cost_minor"] if best else 0, "risk": best["probability_breach_after"] if best else payload["probability_breach_before"],
                                "actions": [{k:a[k] for k in ("type", "counterparty", "amount_minor", "to_date")} for a in (best or {}).get("actions", [])],
                                "asks": len({a["counterparty"] for a in (best or {}).get("actions", [])}),
                                "lowest_cash_minor": best["after"]["minimum_cash_minor"] if best else payload["basis_projection"]["minimum_cash_minor"],
                                "risk_target_met": best["risk_target_met"] if best else payload["probability_breach_before"] <= RISK_TARGET})
            except ValidationError as exc:
                options.append({"priority": priority, "status": "needs_review", "reason": str(exc)})
        return {"read_only": True, "executed": False, "business_id": business_id, "snapshot_hash": snapshot["snapshot_hash"],
                "target_date": target, "criteria": criteria, "options": options,
                "scope": "Bounded planner priorities, not a global optimality guarantee. Equal choices are possible. Protected relationships and current discount limits remain binding. Every saved proposal needs fresh human approval and exact counterparty consent."}

    def propose(self, business_id, target, cap, protected, priority, option_id, expected_snapshot, request_id, actor):
        if priority not in PRIORITIES:
            raise ValidationError("Select a supported recovery priority.")
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_id):
            raise ValidationError("Use a valid proposal request id.")
        snapshot, target, criteria, previous = self._criteria(business_id, target, cap, protected)
        if snapshot["snapshot_hash"] != expected_snapshot or option_id != self._option_id(snapshot, target, criteria, priority):
            raise ValidationError("The preview or owner instructions changed. Preview priorities again.")
        payload = self._build(snapshot, target, criteria, priority, previous)
        if not payload["bundles"] or not any(b["feasible"] for b in payload["bundles"]):
            raise ValidationError("No feasible recovery is available under these instructions; nothing was saved.")
        payload["owner_coach"] = {"source_plan_id": (previous or {}).get("plan_id"), "source_plan_hash": (previous or {}).get("plan_hash"), "criteria": criteria}
        signature = digest({"snapshot": expected_snapshot, "option": option_id, "actor": actor, "priority": priority})
        return self.store.create_plan(business_id, payload, expected_snapshot, "agent:owner-coach", actor,
                                      owner_request={"request_id": request_id, "signature": signature})


def brief_html(report, display_currency=None):
    """Private, script-free handover document, generated from the same report."""
    e = lambda value: escape(str(value), quote=True)
    from .currency_view import display
    money = lambda value: e(display(value, report["currency"], display_currency)) if value is not None else "Not available"
    rows = "".join(f"<tr><td>{e(d['date'])}</td><td>{money(d['inflow_minor'])}</td><td>{money(d['outflow_minor'])}</td><td>{money(d['closing_cash_minor'])}</td></tr>" for d in report["calendar"])
    dependencies = "".join(f"<li>{e(r['customer'])}: lowest cash falls by {money(r['impact_on_lowest_cash_minor'])} if its unpaid receipts do not arrive.</li>" for r in report["dependencies"][:3])
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Tideway decision brief</title>
<style>@page{{size:A4;margin:16mm}}body{{font:15px/1.5 system-ui;color:#152643;max-width:900px;margin:30px auto;padding:0 18px}}h1,h2{{color:#203775}}table{{width:100%;border-collapse:collapse}}td,th{{padding:7px;border-bottom:1px solid #bbb;text-align:left}}tr{{break-inside:avoid}}.note{{background:#eef3fa;padding:12px}}code{{overflow-wrap:anywhere;font-size:11px}}@media print{{body{{margin:0;padding:0}}}}</style>
<h1>{e(report['business_name'])}: decision brief</h1><p>Simulation date {e(report['as_of'])}; target {e(report['target_date'])}; protects through {e(report['end_date'])}.</p>
<p class="note">Private business figures. Share only with trusted people. Read-only analysis; no approval, financial execution or counterparty contact occurred.</p>
<h2>The decision</h2><p>Status: {e(report['status'].replace('_',' '))}. Lowest likely closing cash: {money(report['likely']['minimum_cash_minor'])}. Reserve shortfall: {money(report['likely']['reserve_shortfall_minor'])}.</p>
<p>Extra expense tested: {money(report['expense']['amount_minor'])} on {e(report['expense']['date'])}. After this expense, lowest cash: {money(report['after_expense']['minimum_cash_minor'])}.</p>
<p>Additional spending room under expected receipts: {money(report['spending_room']['likely']['ceiling_minor'])}; without unpaid customer receipts: {money(report['spending_room']['without_unpaid_customers']['ceiling_minor'])}. These are scheduled cash-path bounds, not permission to spend.</p>
<h2>Receipts that matter</h2><ul>{dependencies or '<li>No unpaid-customer dependency identified in this horizon.</li>'}</ul>
<h2>Check before relying on this</h2><p>Payroll identified: {e(report['payroll']['identified'])}; flagged records: {report['data_checks']['quarantined_records']}; customers with fewer than three settled invoices: {len(report['data_checks']['customers_under_three_settlements'])}. No confidence percentage or bank verification is implied.</p>
<h2>Dated cash story</h2><table><thead><tr><th>Date</th><th>Money in</th><th>Money out</th><th>Closing cash</th></tr></thead><tbody>{rows}</tbody></table>
<p>{e(report['scope'])}</p><p>Proposed actions are not counted as collected cash. To act, return to Tideway, review a fresh proposal, obtain the required PIN approvals and counterparty consent, then execute through the normal workflow.</p>
<p>Source snapshot: <code>{e(report['snapshot_hash'])}</code>. This document is a private explanation, not an authorship signature. Print using the browser's Print command.</p></html>"""
