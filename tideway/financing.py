"""Read-only, deterministic MOCK funding comparisons, including repayment pressure.

Catalogue assumptions are illustrative. There is no lender decision, eligibility
approval, external request, or executable financing action in this module.
"""
from . import analytics
from .domain import add_days, days_between
from .projection import horizon_end, project, summary

CATALOGUE = (
    {"variant": "invoice_advance", "label": "MOCK invoice advance", "fee_bps": 200, "term_days": 30,
     "days_to_cash": 2, "collateral": "Assigned receivable", "eligibility": "Illustrative: needs a confirmed invoice"},
    {"variant": "working_capital", "label": "MOCK working-capital line", "fee_bps": 350, "term_days": 60,
     "days_to_cash": 5, "collateral": "None (unsecured)", "eligibility": "Illustrative: lender credit check"},
    {"variant": "guaranteed_loan", "label": "MOCK credit-guarantee bank loan", "fee_bps": 180, "term_days": 90,
     "days_to_cash": 21, "collateral": "Guarantee scheme", "eligibility": "Illustrative: weeks of paperwork"},
)


def compare(business, policy, records, target_date, gap, breach_date, *, as_of=None,
            adjustments=(), invoice_dates=None, promises=None):
    as_of = as_of or business["opening_date"]
    principal = ((gap + 99_999) // 100_000) * 100_000 if gap > 0 else 0
    original_end = horizon_end(business, target_date, policy["lookahead_days"])
    adjustments = tuple(adjustments)
    committed = {item["invoice_id"] for item in adjustments if item["kind"] == "invoice_early_payment"}
    invoice_cover = sum(row["amount_minor"] for row in records["invoices"]
                        if row["status"] in ("confirmed", "overdue") and not row.get("risk_flags")
                        and row["id"] not in committed and row.get("issue_date", as_of) <= as_of)
    candidates = []
    for product in CATALOGUE:
        fee = principal * product["fee_bps"] // 10_000
        arrival = add_days(as_of, product["days_to_cash"])
        repayment_date = add_days(arrival, product["term_days"])
        reasons, unknown = [], ["No lender eligibility, creditworthiness or product availability has been verified."]
        ledger_match = product["variant"] != "invoice_advance" or invoice_cover >= principal
        if not principal:
            reasons.append("The likely path has no reserve shortfall; borrowing is not needed for this projection.")
        if product["variant"] == "invoice_advance":
            unknown += ["Assumes a lender accepts the eligible receivable; concentration, disputes and assignment checks are not assessed."]
            if not ledger_match:
                reasons.append("Issued, uncommitted, non-quarantined invoice face value is below the illustrated principal.")
        elif product["variant"] == "working_capital":
            unknown += ["Credit assessment, security and an actual credit limit are unknown."]
        else:
            unknown += ["Scheme eligibility, guarantee approval and documentation are unknown."]
        arrives = bool(breach_date) and arrival <= breach_date
        if principal and not arrives:
            reasons.append("Illustrated cash arrives after the first likely reserve breach, or that breach predates the simulation date.")
        candidate = {"action_id": f"mock-{product['variant']}", "type": "mock_financing", **product,
                     "principal_minor": principal, "fee_minor": fee, "repayment_minor": principal + fee,
                     "apr_bps": analytics.apr_bps(fee, principal, product["term_days"]),
                     "apr_convention": "Fee / principal * 365 / term; simple annualised illustration, not a regulatory APR quote.",
                     "available_date": arrival, "repayment_date": repayment_date,
                     "arrives_in_time": arrives, "ledger_requirement_met": ledger_match,
                     "eligibility_status": "unverified", "eligibility_unknowns": unknown,
                     "economic_cost_minor": fee, "currency": business["currency"],
                     "executable": False, "mock": True, "feasible": False,
                     "comparison_status": "not_needed" if not principal else "review_required",
                     "reasons": reasons,
                     "note": "MOCK comparison only: no lender decision, financing execution or bank connection. Forecasts assume listed records only."}
        # Extend through repayment so principal cannot disappear beyond look-ahead.
        end = max(original_end, repayment_date)
        if principal and days_between(business["opening_date"], end) <= 366:
            simulated = {kind: [dict(row) for row in rows] for kind, rows in records.items()}
            simulated["transactions"] += [
                {"id": "mock-finance-in", "date": arrival, "description": "MOCK principal", "type": "income",
                 "amount_minor": principal, "currency": business["currency"], "category": "MOCK financing"},
                {"id": "mock-finance-repay", "date": repayment_date, "description": "MOCK repayment", "type": "expense",
                 "amount_minor": principal + fee, "currency": business["currency"], "category": "MOCK financing"}]
            facts = project(business, policy, simulated, end, adjustments=adjustments, invoice_dates=invoice_dates,
                            promises=promises, scenario="mock_financing", lookahead_days=0)
            candidate["repayment_projection"] = summary(facts)
            candidate["projected_closing_at_repayment_minor"] = next(
                day["closing_cash_minor"] for day in facts["days"] if day["date"] == repayment_date)
            candidate["feasible"] = ledger_match and arrives and not facts["reserve_shortfall_minor"] and not facts["payroll_at_risk"]
            if facts["reserve_shortfall_minor"]:
                reasons.append("Reserve shortfall remains or returns when the forecast includes repayment.")
            if facts["payroll_at_risk"]:
                reasons.append("Payroll remains unfunded on at least one projected payroll date.")
            candidate["comparison_status"] = "illustrative_path_holds" if candidate["feasible"] else "does_not_clear_constraints"
        elif principal:
            reasons.append("Repayment falls outside the supported one-year forecast; affordability is not evaluated.")
        candidates.append(candidate)
    return candidates
