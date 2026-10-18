"""Two-sided synthetic liquidity negotiation, using the production cash engine.

The second ledger is an explicitly supplied sandbox assumption, never another
tenant's private records. Exact terms and assumptions are bound to the proposal.
"""
from __future__ import annotations
from copy import deepcopy
from .domain import ValidationError, add_days, valid_date, MAX_AMOUNT_MINOR
from .projection import project, summary
from .resilience import digest, integer


def validate_ledger(value, business):
    allowed = {"opening_cash_minor", "reserve_floor_minor", "payroll_minor", "payroll_date", "other_income_minor", "other_income_date"}
    if not isinstance(value, dict) or set(value) != allowed:
        raise ValidationError("Supply the six synthetic supplier liquidity fields.")
    result = dict(value)
    for key in ("opening_cash_minor", "reserve_floor_minor", "payroll_minor", "other_income_minor"):
        integer(result[key], key, 0, MAX_AMOUNT_MINOR)
    for key in ("payroll_date", "other_income_date"):
        result[key] = valid_date(result[key], key)
        if not business["opening_date"] <= result[key] <= add_days(business["opening_date"], 366):
            raise ValidationError("Supplier dates must lie within the supported shared horizon.")
    return result


def supplier_projection(business, target, lookahead, bill, action, ledger):
    ledger = validate_ledger(ledger, business)
    supplier = {**business, "business_id": "synthetic-supplier", "opening_cash_minor": ledger["opening_cash_minor"]}
    records = {"invoices": [], "bills": [], "transactions": []}
    receipts = [("contract-original", bill["due_date"], bill["amount_minor"] - action["amount_minor"]),
                ("contract-deferred", action["to_date"], action["amount_minor"]),
                ("other-income", ledger["other_income_date"], ledger["other_income_minor"])]
    for identifier, date, amount in receipts:
        if amount:
            records["transactions"].append({"id": identifier, "date": date, "amount_minor": amount, "type": "income", "category": "Receipts", "risk_flags": []})
    if ledger["payroll_minor"]:
        records["transactions"].append({"id": "supplier-payroll", "date": ledger["payroll_date"], "amount_minor": ledger["payroll_minor"],
                                         "type": "expense", "category": "Payroll", "risk_flags": []})
    # Always include both sides' obligations, even beyond the original target.
    end_target = max(target, ledger["payroll_date"], ledger["other_income_date"], action["to_date"])
    return project(supplier, {"reserve_floor_minor": ledger["reserve_floor_minor"]}, records, end_target, lookahead_days=lookahead)


def validate_bundle(snapshot, bundle, target):
    pact = bundle.get("bilateral")
    if pact is None:
        return None
    if not isinstance(pact, dict) or set(pact) != {"bill_id", "supplier_ledger", "assumptions_sha256", "simulated"} or pact["simulated"] is not True:
        raise ValidationError("Invalid bilateral terms.")
    ledger = validate_ledger(pact["supplier_ledger"], snapshot["business"])
    if digest(ledger) != pact["assumptions_sha256"]:
        raise ValidationError("Bilateral liquidity assumptions changed.")
    bill = next((r for r in snapshot["records"]["bills"] if r["id"] == pact["bill_id"]), None)
    actions = [a for a in bundle["actions"] if a["type"] == "supplier_deferral" and a["record_id"] == pact["bill_id"]]
    if not bill or len(actions) != 1:
        raise ValidationError("The negotiated bill terms are missing or ambiguous.")
    result = supplier_projection(snapshot["business"], target, snapshot["policy"]["lookahead_days"], bill, actions[0], ledger)
    if result["reserve_shortfall_minor"] or result["payroll_at_risk"]:
        raise ValidationError("The negotiated terms would breach the synthetic supplier's reserve or payroll.")
    return summary(result)


def carry_terms(snapshot, bundles, pact, target):
    """Retained supplier requests cannot shed their previously reviewed limits."""
    if not pact:
        return
    for bundle in bundles:
        if any(a["type"] == "supplier_deferral" and a["record_id"] == pact["bill_id"] for a in bundle["actions"]):
            if bundle.get("bilateral", pact) != pact:
                raise ValidationError("Replacement cannot change the reviewed supplier liquidity assumptions.")
            bundle["bilateral"] = deepcopy(pact)
            if bundle["feasible"]:
                validate_bundle(snapshot, bundle, target)
