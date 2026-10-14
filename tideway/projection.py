"""Deterministic daily cash projection.

The projection is a scheduled ledger, not a bank balance.  It starts from
the business opening cash on ``opening_date`` and applies dated events from
transactions, open invoices and open bills.  Accepted sandbox adjustments
(supplier deferrals and early-payment agreements) move existing obligations;
they never create money.  Every event keeps a reference to its source record.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .domain import (
    MAX_PROJECTION_DAYS,
    OPEN_BILL_STATUSES,
    OPEN_INVOICE_STATUSES,
    ValidationError,
    days_between,
    valid_date,
)


ADJUSTMENT_KINDS = ("bill_deferral", "invoice_early_payment")


def _is_payroll_transaction(row):
    return row["type"] == "expense" and str(row.get("category", "")).strip().casefold() == "payroll"


def check_adjustments(records, adjustments):
    """Reject adjustments that do not match the records they move."""
    bills = {row["id"]: row for row in records["bills"]}
    invoices = {row["id"]: row for row in records["invoices"]}
    deferred = defaultdict(int)
    early = set()
    for item in adjustments:
        kind = item.get("kind")
        if kind == "bill_deferral":
            bill = bills.get(item.get("bill_id"))
            if not bill:
                raise ValidationError("A deferral references an unknown bill.")
            if bill["priority"] == "payroll":
                raise ValidationError("Payroll obligations can never be deferred.")
            if bill["status"] not in ("open", "scheduled") or bill.get("rescheduled_date"):
                raise ValidationError("Only open, not-yet-rescheduled bills can be deferred.")
            amount = item.get("amount_minor")
            if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
                raise ValidationError("Deferral amount must be a positive integer.")
            if item.get("from_date") != bill["due_date"]:
                raise ValidationError("Deferral no longer matches the bill due date.")
            if valid_date(item.get("to_date", ""), "to_date") <= bill["due_date"]:
                raise ValidationError("A deferral must move the payment later.")
            deferred[bill["id"]] += amount
            if deferred[bill["id"]] > bill["amount_minor"]:
                raise ValidationError("Deferrals cannot exceed the bill amount.")
        elif kind == "invoice_early_payment":
            invoice = invoices.get(item.get("invoice_id"))
            if not invoice or invoice["status"] not in OPEN_INVOICE_STATUSES:
                raise ValidationError("Early payment references an unknown or settled invoice.")
            if invoice["id"] in early:
                raise ValidationError("An invoice can have only one early-payment agreement.")
            early.add(invoice["id"])
            if item.get("face_minor") != invoice["amount_minor"]:
                raise ValidationError("Early-payment face value no longer matches the invoice.")
            amount = item.get("amount_minor")
            if isinstance(amount, bool) or not isinstance(amount, int) or not 0 < amount <= invoice["amount_minor"]:
                raise ValidationError("Early-payment amount must be positive and at most the invoice amount.")
            valid_date(item.get("to_date", ""), "to_date")
        else:
            raise ValidationError("Unsupported adjustment kind.")
    return True


def build_events(business, records, end_date, adjustments=(), invoice_dates=None, promises=None):
    """Return (events, excluded) for the horizon [opening_date, end_date]."""
    opening = business["opening_date"]
    invoice_dates = invoice_dates or {}
    promises = promises or {}
    adjustments = list(adjustments)
    check_adjustments(records, adjustments)
    early = {item["invoice_id"]: item for item in adjustments if item["kind"] == "invoice_early_payment"}
    deferrals = defaultdict(list)
    for item in adjustments:
        if item["kind"] == "bill_deferral":
            deferrals[item["bill_id"]].append(item)
    events, excluded = [], []

    def add(day, effect, ref):
        ref = {**ref, "date": day, "effect_minor": effect}
        if opening <= day <= end_date:
            events.append(ref)
        else:
            excluded.append({**ref, "reason": "before opening date" if day < opening else "after horizon"})

    for row in records["transactions"]:
        effect = row["amount_minor"] if row["type"] == "income" else -row["amount_minor"]
        if row["date"] < opening:
            continue  # history: already reflected in opening cash
        add(row["date"], effect, {"kind": "transaction", "id": row["id"], "amount_minor": row["amount_minor"],
                                  "payroll": _is_payroll_transaction(row), "certainty": "scheduled"})
    for row in records["invoices"]:
        if row["status"] not in OPEN_INVOICE_STATUSES:
            continue
        if row["id"] in early:
            agreement = early[row["id"]]
            add(agreement["to_date"], agreement["amount_minor"],
                {"kind": "invoice_early_payment", "id": row["id"], "amount_minor": agreement["amount_minor"],
                 "face_minor": row["amount_minor"], "certainty": "agreed"})
            continue
        day = invoice_dates.get(row["id"]) or promises.get(row["id"]) or row["expected_collection_date"]
        if day < opening:
            excluded.append({"kind": "invoice", "id": row["id"], "date": day, "effect_minor": row["amount_minor"],
                             "reason": "overdue with no future expected date"})
            continue
        add(day, row["amount_minor"], {"kind": "invoice", "id": row["id"], "amount_minor": row["amount_minor"],
                                       "certainty": "promised" if row["id"] in promises else "expected"})
    for row in records["bills"]:
        if row["status"] not in OPEN_BILL_STATUSES:
            continue
        payroll = row["priority"] == "payroll"
        base = {"kind": "bill", "id": row["id"], "payroll": payroll, "certainty": "scheduled"}
        if row.get("rescheduled_date"):
            add(row["rescheduled_date"], -row["amount_minor"], {**base, "amount_minor": row["amount_minor"]})
            continue
        moved = deferrals.get(row["id"], [])
        remaining = row["amount_minor"] - sum(item["amount_minor"] for item in moved)
        if remaining:
            add(row["due_date"], -remaining, {**base, "amount_minor": remaining})
        for item in moved:
            add(item["to_date"], -item["amount_minor"],
                {**base, "kind": "bill_deferred", "amount_minor": item["amount_minor"],
                 "from_date": item["from_date"], "certainty": "agreed"})
    events.sort(key=lambda event: (event["date"], event["effect_minor"] > 0, event["kind"], str(event["id"])))
    return events, excluded


def horizon_end(business, target_date, lookahead_days=0):
    target = valid_date(target_date, "target_date")
    if target < business["opening_date"]:
        raise ValidationError("target_date cannot be before the opening date.")
    end = (date.fromisoformat(target) + timedelta(days=lookahead_days)).isoformat()
    if days_between(business["opening_date"], end) > MAX_PROJECTION_DAYS:
        raise ValidationError("The projection horizon is limited to 366 days after opening.")
    return end


def project(business, policy, records, target_date, adjustments=(), scenario="base",
            invoice_dates=None, promises=None, lookahead_days=0):
    """Project daily scheduled cash through ``target_date`` plus look-ahead."""
    end = horizon_end(business, target_date, lookahead_days)
    events, excluded = build_events(business, records, end, adjustments, invoice_dates, promises)
    reserve = policy["reserve_floor_minor"]
    by_day = defaultdict(list)
    for event in events:
        by_day[event["date"]].append(event)
    balance = business["opening_cash_minor"]
    start = date.fromisoformat(business["opening_date"])
    days = []
    minimum, minimum_date = balance, business["opening_date"]
    first_breach = business["opening_date"] if balance < reserve else None
    first_negative = None
    payroll_at_risk = False
    target_closing = None
    for offset in range(days_between(business["opening_date"], end) + 1):
        day = (start + timedelta(days=offset)).isoformat()
        todays = by_day.get(day, [])
        inflow = sum(event["effect_minor"] for event in todays if event["effect_minor"] > 0)
        outflow = -sum(event["effect_minor"] for event in todays if event["effect_minor"] < 0)
        opening_balance = balance
        balance += inflow - outflow
        if balance < minimum:
            minimum, minimum_date = balance, day
        if balance < reserve and first_breach is None:
            first_breach = day
        if balance < 0 and first_negative is None:
            first_negative = day
        if balance < 0 and any(event.get("payroll") for event in todays):
            payroll_at_risk = True
        if day == target_date:
            target_closing = balance
        days.append({"date": day, "opening_cash_minor": opening_balance, "inflow_minor": inflow,
                     "outflow_minor": outflow, "closing_cash_minor": balance,
                     "source_references": todays})
    total_in = sum(day["inflow_minor"] for day in days)
    total_out = sum(day["outflow_minor"] for day in days)
    if business["opening_cash_minor"] + total_in - total_out != balance:
        raise ValidationError("Projection totals do not reconcile.")
    shortfall = max(0, reserve - minimum)
    return {"business_id": business["business_id"], "currency": business["currency"], "scenario": scenario,
            "opening_date": business["opening_date"], "target_date": target_date, "end_date": end,
            "opening_cash_minor": business["opening_cash_minor"], "closing_cash_minor": balance,
            "target_closing_cash_minor": target_closing, "minimum_cash_minor": minimum,
            "minimum_cash_date": minimum_date, "reserve_floor_minor": reserve,
            "reserve_shortfall_minor": shortfall, "first_breach_date": first_breach,
            "first_negative_date": first_negative, "payroll_at_risk": payroll_at_risk,
            "payroll_outflow_minor": -sum(event["effect_minor"] for event in events if event.get("payroll")),
            "total_inflow_minor": total_in, "total_outflow_minor": total_out,
            "days": days, "source_references": events, "excluded": excluded,
            "assumptions": {"lookahead_days": lookahead_days,
                            "reminders_are_not_collections": True,
                            "scheduled_projection_not_bank_balance": True}}


def summary(projection):
    """Small, model-safe view of a projection (no per-day source details)."""
    keys = ("scenario", "currency", "opening_date", "target_date", "end_date", "opening_cash_minor",
            "closing_cash_minor", "target_closing_cash_minor", "minimum_cash_minor", "minimum_cash_date",
            "reserve_floor_minor", "reserve_shortfall_minor", "first_breach_date", "first_negative_date",
            "payroll_at_risk", "payroll_outflow_minor", "total_inflow_minor", "total_outflow_minor")
    return {key: projection.get(key) for key in keys}


def daily_series(projection):
    return [{"date": day["date"], "closing_cash_minor": day["closing_cash_minor"]} for day in projection["days"]]
