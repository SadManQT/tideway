"""Treasury hub: read-only lender and finance-team views over one business's records.

Four tools, all computed from the same tenant snapshot the dashboard uses:

* ``twcf``      13-week cash flow in weekly buckets, built from the daily projection
                engine (``projection.project``) so totals reconcile exactly.
* ``health``    working-capital health score (0-100) with documented weights.
* ``scan``      deterministic payment-integrity rules over supplier bills.
* passports     an HMAC-signed, expiring JSON summary a business can hand a lender.

Nothing here writes a financial record, approves, blocks or executes anything.
Only passport issuance writes one audit entry.  Every amount is an integer in
minor units of the business's ledger currency.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import analytics, ed25519, security
from .domain import (
    OPEN_INVOICE_STATUSES,
    ValidationError,
    add_days,
    canonical_json,
    days_between,
    human_date,
    money_text,
)
from .projection import project

WEEKS = 13
HORIZON_DAYS = WEEKS * 7
MC_RUNS = 1000
SCENARIOS = {"scheduled": "base", "likely": "likely", "stress": "stress"}
SCENARIO_LABELS = {
    "scheduled": "Scheduled: every invoice arrives on its expected collection date.",
    "likely": "Likely: each open invoice arrives after TidePay's expected delay (the dashboard's likely path).",
    "stress": "Stress: each open invoice arrives after TidePay's 80th-percentile delay.",
}

# ---- health score ------------------------------------------------------------------
# Weights are Tideway design choices, not industry benchmarks. They sum to 100.
HEALTH_WEIGHTS = {"collection_speed": 15, "overdue_share": 15, "concentration": 15,
                  "runway": 15, "reserve_coverage": 20, "breach_risk": 20}
HEALTH_BANDS = ((75, "Strong"), (50, "Watch"), (0, "Weak"))
DSO_SLACK_DAYS = 30        # collection score reaches 0 at 30 days beyond the business's own terms
HHI_FULL_MARKS = 2000      # = 5 equally sized customers
RUNWAY_FULL_DAYS = 90
RESERVE_FULL_MULTIPLE = 2  # lowest likely cash at 2x the reserve floor scores 100

# ---- payment-integrity scan ----------------------------------------------------------
DUPLICATE_WINDOW_DAYS = 7
SPLIT_WINDOW_DAYS = 7
OUTLIER_MIN_HISTORY = 3
OUTLIER_Z = 3.5
OUTLIER_MIN_RELATIVE = 0.25  # and at least 25% away from the payee's median (materiality)
ROUND_UNIT_MINOR = 100_000  # a multiple of 1,000 whole currency units
ROUND_EXTRA_ZEROS = 2      # ...with 2+ more trailing zeros than any of the payee's other bills
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
PAYEE_SUFFIXES = {"ltd", "limited", "co", "company", "inc", "llc", "plc", "pvt", "pte", "corp", "corporation", "the"}

# ---- credit passport -----------------------------------------------------------------
PASSPORT_VERSION = "tideway-credit-passport-v1"
PASSPORT_DAYS = 30
PASSPORT_MAX_BYTES = 200_000
PASSPORT_FIELDS = ("type", "version", "passport_id", "issuer", "business", "as_of", "issued_at", "expires_at",
                   "snapshot_hash", "audit", "twcf", "health", "breach_risk", "limitations", "signature_alg", "public_signature",
                   "signature")


def _clamp(value):
    return max(0, min(100, int(round(value))))


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


# =========================================================================== 13-week cash flow

def horizon(snapshot):
    start = snapshot["business"]["opening_date"]
    return start, add_days(start, HORIZON_DAYS - 1)


def scenario_projection(snapshot, derived, scenario):
    """The existing daily engine over exactly 13 weeks (no look-ahead)."""
    if scenario not in SCENARIOS:
        raise ValidationError("scenario must be scheduled, likely or stress.")
    business, policy, records, state = snapshot["business"], snapshot["policy"], snapshot["records"], snapshot["state"]
    _start, end = horizon(snapshot)
    dates = None if scenario == "scheduled" else derived["likely_dates" if scenario == "likely" else "stress_dates"]
    return project(business, policy, records, end, adjustments=state["adjustments"], scenario=SCENARIOS[scenario],
                   invoice_dates=dates, promises=state["promises"], lookahead_days=0)


def _weekly(snapshot, projection):
    records = snapshot["records"]
    customers = {row["id"]: row["customer"] for row in records["invoices"]}
    reserve = projection["reserve_floor_minor"]
    weeks, by_customer_total = [], defaultdict(int)
    for index in range(WEEKS):
        days = projection["days"][index * 7:(index + 1) * 7]
        receipts = defaultdict(int)
        other_in = supplier = payroll = other_out = 0
        for day in days:
            for event in day["source_references"]:
                effect = event["effect_minor"]
                if effect > 0:
                    if event["kind"] in ("invoice", "invoice_early_payment"):
                        receipts[customers[event["id"]]] += effect
                    else:
                        other_in += effect
                elif event.get("payroll"):
                    payroll -= effect
                elif event["kind"] in ("bill", "bill_deferred"):
                    supplier -= effect
                else:
                    other_out -= effect
        receipts_total = sum(receipts.values()) + other_in
        disbursements = supplier + payroll + other_out
        if receipts_total != sum(day["inflow_minor"] for day in days) or \
                disbursements != sum(day["outflow_minor"] for day in days):
            raise ValidationError("13-week buckets do not reconcile with the daily projection.")
        low_day = min(days, key=lambda day: (day["closing_cash_minor"], day["date"]))
        for name, amount in receipts.items():
            by_customer_total[name] += amount
        weeks.append({
            "week": index + 1, "start_date": days[0]["date"], "end_date": days[-1]["date"],
            "opening_cash_minor": days[0]["opening_cash_minor"],
            "receipts_by_customer": [{"customer": name, "amount_minor": amount}
                                     for name, amount in sorted(receipts.items(), key=lambda item: (-item[1], item[0]))],
            "other_receipts_minor": other_in, "receipts_minor": receipts_total,
            "supplier_bills_minor": supplier, "payroll_minor": payroll, "other_disbursements_minor": other_out,
            "disbursements_minor": disbursements, "net_flow_minor": receipts_total - disbursements,
            "closing_cash_minor": days[-1]["closing_cash_minor"],
            "lowest_cash_minor": low_day["closing_cash_minor"], "lowest_cash_date": low_day["date"],
            "reserve_floor_minor": reserve, "below_reserve": low_day["closing_cash_minor"] < reserve,
        })
    return weeks, by_customer_total


def twcf_scenario(snapshot, derived, scenario):
    projection = scenario_projection(snapshot, derived, scenario)
    weeks, by_customer = _weekly(snapshot, projection)
    opening = projection["opening_cash_minor"]
    receipts = sum(week["receipts_minor"] for week in weeks)
    disbursements = sum(week["disbursements_minor"] for week in weeks)
    closing = weeks[-1]["closing_cash_minor"]
    lowest_week = min(weeks, key=lambda week: (week["lowest_cash_minor"], week["week"]))
    weekly_minimum = min(opening, lowest_week["lowest_cash_minor"])
    reconciliation = {
        "engine": "tideway.projection.project (same function as the dashboard)",
        "engine_closing_cash_minor": projection["closing_cash_minor"], "twcf_closing_cash_minor": closing,
        "engine_minimum_cash_minor": projection["minimum_cash_minor"], "twcf_minimum_cash_minor": weekly_minimum,
        "opening_plus_net_minor": opening + receipts - disbursements,
    }
    reconciliation["matches"] = (closing == projection["closing_cash_minor"] == reconciliation["opening_plus_net_minor"]
                                 and weekly_minimum == projection["minimum_cash_minor"])
    if not reconciliation["matches"]:
        raise ValidationError("13-week cash flow does not reconcile with the projection engine.")
    beyond_in = sum(item["effect_minor"] for item in projection["excluded"]
                    if item["effect_minor"] > 0 and item["reason"] == "after horizon")
    beyond_out = -sum(item["effect_minor"] for item in projection["excluded"]
                      if item["effect_minor"] < 0 and item["reason"] == "after horizon")
    below = [week["week"] for week in weeks if week["below_reserve"]]
    return {"scenario": scenario, "label": SCENARIO_LABELS[scenario], "weeks": weeks,
            "daily": [{"date": day["date"], "closing_cash_minor": day["closing_cash_minor"]} for day in projection["days"]],
            "totals": {"opening_cash_minor": opening, "receipts_minor": receipts, "disbursements_minor": disbursements,
                       "supplier_bills_minor": sum(week["supplier_bills_minor"] for week in weeks),
                       "payroll_minor": sum(week["payroll_minor"] for week in weeks),
                       "other_disbursements_minor": sum(week["other_disbursements_minor"] for week in weeks),
                       "net_flow_minor": receipts - disbursements, "closing_cash_minor": closing,
                       "lowest_cash_minor": projection["minimum_cash_minor"],
                       "lowest_cash_date": projection["minimum_cash_date"],
                       "lowest_week": lowest_week["week"], "weeks_below_reserve": below,
                       "first_week_below_reserve": below[0] if below else None,
                       "first_breach_date": projection["first_breach_date"],
                       "payroll_at_risk": projection["payroll_at_risk"],
                       "receipts_by_customer": [{"customer": name, "amount_minor": amount} for name, amount in
                                                sorted(by_customer.items(), key=lambda item: (-item[1], item[0]))],
                       "beyond_horizon_receipts_minor": beyond_in, "beyond_horizon_disbursements_minor": beyond_out},
            "reconciliation": reconciliation}


def twcf(snapshot, derived):
    start, end = horizon(snapshot)
    business = snapshot["business"]
    return {"business_id": business["business_id"], "business_name": business["name"], "currency": business["currency"],
            "as_of": snapshot["state"]["current_date"], "start_date": start, "end_date": end, "weeks": WEEKS,
            "snapshot_hash": snapshot["snapshot_hash"], "reserve_floor_minor": snapshot["policy"]["reserve_floor_minor"],
            "scenarios": {name: twcf_scenario(snapshot, derived, name) for name in SCENARIOS},
            "read_only": True,
            "method": ("Weekly buckets of Tideway's daily scheduled-cash projection from the ledger opening date (the sandbox "
                       "current date). Receipts are open invoices (by customer) and income transactions; disbursements are "
                       "supplier bills, payroll (bills or transactions marked payroll) and other expenses. Accepted "
                       "sandbox adjustments and customer promises are applied exactly as on the dashboard. A scheduled "
                       "ledger, not a bank balance; synthetic data.")}


# =========================================================================== health score

def _simulation(snapshot):
    business, policy, records, state = snapshot["business"], snapshot["policy"], snapshot["records"], snapshot["state"]
    _start, end = horizon(snapshot)
    seed = analytics.stable_seed(business["business_id"], snapshot["snapshot_hash"], end, "treasury-13w-v1")
    return analytics.monte_carlo(business, policy, records, end, state["adjustments"], state["promises"],
                                 runs=MC_RUNS, seed=seed, lookahead_days=0, as_of=state["current_date"])


def _dpo(snapshot, kpis):
    """Balance-method DPO: open payables / average daily supplier spend over the paid-bill history window."""
    bills = snapshot["records"]["bills"]
    opening = snapshot["business"]["opening_date"]
    paid = [row for row in bills if row["status"] == "paid" and row["due_date"] <= opening]
    if not paid:
        return None, None
    window = max(1, days_between(min(row["due_date"] for row in paid), opening))
    daily = sum(row["amount_minor"] for row in paid) / window
    return (round(kpis["open_payables_minor"] / daily, 1) if daily else None), window


def health(snapshot, derived, plan=None, simulation=None):
    """Composite 0-100 score. ``plan`` is the 13-week cash flow; computed if not supplied."""
    plan = plan or twcf(snapshot, derived)
    simulation = simulation or _simulation(snapshot)
    business, policy, records = snapshot["business"], snapshot["policy"], snapshot["records"]
    currency, as_of = business["currency"], snapshot["state"]["current_date"]
    kpis = analytics.financial_kpis(business, records, derived["profiles"])
    likely = plan["scenarios"]["likely"]["totals"]
    scheduled = plan["scenarios"]["scheduled"]["totals"]
    reserve = policy["reserve_floor_minor"]
    open_rows = [row for row in records["invoices"] if row["status"] in OPEN_INVOICE_STATUSES]
    open_total = sum(row["amount_minor"] for row in open_rows)
    overdue_rows = [row for row in open_rows if row["status"] == "overdue" or row["due_date"] < as_of]
    overdue_total = sum(row["amount_minor"] for row in overdue_rows)
    components = []

    def add(key, label, value, display, score, formula, inputs, unavailable=None):
        components.append({"id": key, "label": label, "value": value, "display": display,
                           "score": score, "weight": HEALTH_WEIGHTS[key], "formula": formula, "inputs": inputs,
                           "available": score is not None, "unavailable_reason": unavailable})

    dso, terms = kpis["dso_days"], kpis["average_terms_days"]
    if dso is None or terms is None:
        add("collection_speed", "Collection speed (DSO vs own terms)", None, "No settled invoices", None,
            "score = 100 − 100 × max(0, DSO − terms) / 30", {}, "No settled invoices to measure DSO.")
    else:
        excess = max(0.0, dso - terms)
        add("collection_speed", "Collection speed (DSO vs own terms)", dso, f"DSO {dso} days vs {terms}-day terms",
            _clamp(100 - 100 * excess / DSO_SLACK_DAYS), "score = 100 − 100 × max(0, DSO − terms) / 30",
            {"dso_days": dso, "average_terms_days": terms, "excess_days": round(excess, 1),
             "settled_invoices": kpis["settled_invoices"]})
    share = _ratio(overdue_total, open_total) or 0.0
    add("overdue_share", "Overdue receivables share", round(share, 4), f"{round(share * 100, 1)}% of open receivables overdue",
        _clamp(100 * (1 - share)), "score = 100 × (1 − overdue open receivables / open receivables)",
        {"overdue_minor": overdue_total, "open_receivables_minor": open_total, "overdue_invoices": len(overdue_rows)})
    hhi, top = kpis["customer_hhi"], kpis["top_customer_share"]
    if hhi is None:
        add("concentration", "Customer concentration (HHI)", None, "No open receivables", None,
            "score = 100 × (10,000 − HHI) / 8,000, capped at 100", {}, "No open receivables to measure concentration.")
    else:
        add("concentration", "Customer concentration (HHI)", hhi,
            f"HHI {hhi:,}; top customer {round((top or 0) * 100)}% of open receivables",
            _clamp(100 * (10_000 - hhi) / (10_000 - HHI_FULL_MARKS)),
            "score = 100 × (10,000 − HHI) / 8,000, capped at 100 (full marks ≤ 2,000 = five equal customers)",
            {"hhi": hhi, "top_customer_share": top, "effective_customers": kpis["effective_customers"]})
    history_daily = (kpis["monthly_expense_run_rate_minor"] or 0) / 30
    forward_daily = scheduled["disbursements_minor"] / HORIZON_DAYS
    burn = max(history_daily, forward_daily)
    cash = business["opening_cash_minor"]
    runway = round(cash / burn, 1) if burn else None
    add("runway", "Cash runway", runway, f"{runway} days of outflows" if runway is not None else "No outflows recorded",
        _clamp(100 * runway / RUNWAY_FULL_DAYS) if runway is not None else 100,
        "runway = opening cash ÷ daily burn; daily burn = max(historical monthly expenses ÷ 30, scheduled 13-week "
        "disbursements ÷ 91); score = 100 × runway / 90, capped",
        {"opening_cash_minor": cash, "historical_daily_burn_minor": int(history_daily),
         "scheduled_daily_burn_minor": int(forward_daily), "daily_burn_used_minor": int(burn)})
    low = likely["lowest_cash_minor"]
    coverage = round(low / reserve, 2) if reserve else None
    coverage_score = _clamp(100 * low / (RESERVE_FULL_MULTIPLE * reserve)) if reserve else (100 if low >= 0 else 0)
    add("reserve_coverage", "Reserve coverage (likely path, 13 weeks)", coverage,
        f"Lowest likely cash {money_text(low, currency)} = {coverage}× reserve" if reserve else "No reserve floor set",
        coverage_score, "score = 100 × lowest likely cash / (2 × reserve floor), clamped 0–100",
        {"lowest_likely_cash_minor": low, "lowest_likely_cash_date": likely["lowest_cash_date"],
         "reserve_floor_minor": reserve})
    probability = simulation["probability_breach"]
    add("breach_risk", "Simulated reserve-breach probability", probability,
        f"{round(probability * 100, 1)}% of {simulation['runs']} futures breach the reserve",
        _clamp(100 * (1 - probability)), "score = 100 × (1 − P(breach within 13 weeks))",
        {"probability_breach": probability, "runs": simulation["runs"], "seed": simulation["seed"],
         "horizon_end": simulation["end_date"]})
    available = [item for item in components if item["available"]]
    weight_total = sum(item["weight"] for item in available)
    score = _clamp(sum(item["weight"] * item["score"] for item in available) / weight_total) if weight_total else None
    for item in components:
        item["points"] = round(item["weight"] * item["score"] / weight_total, 1) if item["available"] else 0
        item["max_gain_points"] = round(item["weight"] * (100 - item["score"]) / weight_total, 1) if item["available"] else 0
    dpo, window = _dpo(snapshot, kpis)
    context = [{"id": "dpo", "label": "DPO (balance method)", "value": dpo,
                "display": f"{dpo} days" if dpo is not None else "No paid-bill history",
                "formula": "open payables ÷ (paid supplier bills ÷ days in the paid-bill history window)",
                "weight": 0, "note": "Shown, not scored: a longer DPO helps cash but can strain suppliers, and no benchmark is assumed.",
                "inputs": {"open_payables_minor": kpis["open_payables_minor"], "history_window_days": window}},
               {"id": "dso", "label": "DSO", "value": dso, "display": f"{dso} days" if dso is not None else "—",
                "formula": "mean days from invoice issue to payment, settled invoices", "weight": 0,
                "note": "Scored above as collection speed against the business's own terms.", "inputs": {}}]
    band = next(label for limit, label in HEALTH_BANDS if score is None or score >= limit) if score is not None else "Unavailable"
    return {"business_id": business["business_id"], "currency": currency, "as_of": as_of,
            "snapshot_hash": snapshot["snapshot_hash"], "score": score, "band": band,
            "bands": [{"from": limit, "label": label} for limit, label in HEALTH_BANDS],
            "components": components, "context_metrics": context,
            "suggestions": _suggestions(components, snapshot, derived, plan, simulation, overdue_rows, weight_total),
            "weights": dict(HEALTH_WEIGHTS), "weight_total_used": weight_total,
            "simulation": {"runs": simulation["runs"], "seed": simulation["seed"],
                           "probability_breach": simulation["probability_breach"],
                           "probability_payroll_unfunded": simulation["probability_payroll_unfunded"],
                           "minimum_cash_p10_minor": simulation["minimum_cash_p10_minor"],
                           "liquidity_gap_minor": simulation["liquidity_gap"]["additional_cash_minor"],
                           "horizon_end": simulation["end_date"]},
            "read_only": True,
            "method": ("Weighted mean of component scores (0–100). Weights and scoring anchors are Tideway design "
                       "parameters, not industry benchmarks; unavailable components are dropped and the remaining weights "
                       "renormalised. Synthetic data; not a credit rating.")}


def _suggestions(components, snapshot, derived, plan, simulation, overdue_rows, weight_total):
    currency = snapshot["business"]["currency"]
    by_id = {item["id"]: item for item in components}
    texts = {}
    profiles = derived["profiles"]["customers"]
    if by_id["collection_speed"]["available"]:
        inputs = by_id["collection_speed"]["inputs"]
        slow = max(profiles.values(), key=lambda item: (item["expected_delay_days"], item["customer"]), default=None)
        texts["collection_speed"] = (f"Customers pay on average {inputs['excess_days']} days beyond the {inputs['average_terms_days']}-day "
                                     f"terms" + (f"; {slow['customer']} is expected to be the slowest (about "
                                                 f"{slow['expected_delay_days']} days late)" if slow else "") +
                                     ". Bringing DSO back to terms (reminders, early-payment terms) would lift the score.")
    if by_id["overdue_share"]["available"] and overdue_rows:
        largest = max(overdue_rows, key=lambda row: (row["amount_minor"], row["id"]))
        texts["overdue_share"] = (f"{len(overdue_rows)} overdue invoice(s) total "
                                  f"{money_text(sum(r['amount_minor'] for r in overdue_rows), currency)}; the largest is "
                                  f"{largest['customer']} ({money_text(largest['amount_minor'], currency)}). Collecting them "
                                  "removes the overdue share.")
    if by_id["concentration"]["available"]:
        top = max(profiles.values(), key=lambda item: (item["open_exposure_minor"], item["customer"]), default=None)
        if top:
            share = by_id["concentration"]["inputs"]["top_customer_share"] or 0
            texts["concentration"] = (f"{top['customer']} holds {round(share * 100)}% of open receivables. Spreading "
                                      "receivables to the equivalent of five equal customers (HHI ≤ 2,000) earns full marks.")
    runway = by_id["runway"]
    if runway["value"] is not None:
        need = -(-max(0, int(RUNWAY_FULL_DAYS * runway["inputs"]["daily_burn_used_minor"]) - runway["inputs"]["opening_cash_minor"]) // 100) * 100
        texts["runway"] = (f"Cash covers about {runway['value']} days of outflows. Reaching {RUNWAY_FULL_DAYS} days needs about "
                           f"{money_text(need, currency)} more cash or proportionally lower outflows.")
    coverage = by_id["reserve_coverage"]["inputs"]
    reserve = coverage["reserve_floor_minor"]
    if reserve:
        need = max(0, RESERVE_FULL_MULTIPLE * reserve - coverage["lowest_likely_cash_minor"])
        texts["reserve_coverage"] = (f"Lowest likely cash is {money_text(coverage['lowest_likely_cash_minor'], currency)} on "
                                     f"{human_date(coverage['lowest_likely_cash_date'], True)}. About {money_text(need, currency)} "
                                     "of additional confirmed receipts before that date would reach 2× the reserve.")
    gap = simulation["liquidity_gap"]["additional_cash_minor"]
    texts["breach_risk"] = (f"{round(simulation['probability_breach'] * 100, 1)}% of {simulation['runs']} simulated futures breach "
                            "the reserve within 13 weeks. " + (f"On these simulated paths about {money_text(gap, currency)} of extra "
                                                                "opening cash would bring that to 10% (a diagnostic, not a funding offer)."
                                                                if gap else "Keep current collection timing on track."))
    ranked = sorted((item for item in components if item["available"] and item["max_gain_points"] > 0 and item["id"] in texts),
                    key=lambda item: (-item["max_gain_points"], item["id"]))
    return [{"component": item["id"], "label": item["label"], "max_gain_points": item["max_gain_points"],
             "text": texts[item["id"]]} for item in ranked[:3]]


# =========================================================================== payment-integrity scan

def payee_key(name):
    words = [word for word in re.findall(r"[a-z0-9]+", str(name or "").casefold()) if word not in PAYEE_SUFFIXES]
    return " ".join(words)


def references(text):
    """Invoice-number-like tokens: 4+ characters containing a digit and a letter, or 5+ digits."""
    tokens = set()
    for letters, digits in re.findall(r"\b([A-Za-z]{2,6})[\s#:./-]*(\d{3,})\b", str(text or "")):
        if not re.fullmatch(r"(19|20)\d\d", digits):  # "Rent 2026" is a year, not a reference
            tokens.add(letters.upper() + digits)
    for raw in re.findall(r"[A-Za-z0-9][A-Za-z0-9/#-]{3,}", str(text or "")):
        token = re.sub(r"[^A-Z0-9]", "", raw.upper())
        if len(token) >= 4 and re.search(r"\d", token) and (re.search(r"[A-Z]", token) or len(token) >= 5) \
                and not re.fullmatch(r"(19|20)\d\d(0[1-9]|1[0-2])?(\d\d)?", token):
            tokens.add(token)
    return tokens


def _trailing_zeros(amount):
    count = 0
    while amount and amount % 10 == 0:
        amount //= 10
        count += 1
    return count


def _finding(rule, severity, title, rows, evidence, explanation):
    ids = sorted(row["id"] for row in rows)
    synthetic = [row.get("_synthetic", False) for row in rows]
    return {"finding_id": "PI-" + hashlib.sha256(f"{rule}|{'|'.join(ids)}".encode()).hexdigest()[:10],
            "rule": rule, "severity": severity, "title": title, "bill_ids": ids,
            "payees": sorted({row["payee"] for row in rows}), "amount_minor": sum(row["amount_minor"] for row in rows),
            "source": "synthetic" if all(synthetic) else "ledger" if not any(synthetic) else "mixed",
            "evidence": evidence, "explanation": explanation, "blocks_nothing": True}


def _modified_z(value, others):
    median = statistics.median(others)
    mad = statistics.median(abs(item - median) for item in others)
    if mad:
        return 0.6745 * (value - median) / mad, median, "median absolute deviation"
    mean_ad = statistics.fmean(abs(item - median) for item in others)
    if mean_ad:
        return (value - median) / (1.253314 * mean_ad), median, "mean absolute deviation (MAD was 0)"
    return (float("inf") if value > median else float("-inf") if value < median else 0.0), median, "constant history"


def run_rules(bills, threshold, currency, verified_accounts):
    """All rules over one bill list. Pure and deterministic: same bills -> same findings."""
    rows = sorted((row for row in bills if row["status"] != "cancelled"), key=lambda row: (row["due_date"], row["id"]))
    by_payee = defaultdict(list)
    for row in rows:
        by_payee[payee_key(row["payee"])].append(row)
    findings, paired = [], set()
    # R1: duplicates (same payee + amount within N days, or same payee + same invoice reference)
    for key in sorted(by_payee):
        group = by_payee[key]
        for i, first in enumerate(group):
            for second in group[i + 1:]:
                gap = abs(days_between(first["due_date"], second["due_date"]))
                same_amount = first["amount_minor"] == second["amount_minor"] and gap <= DUPLICATE_WINDOW_DAYS
                shared = sorted(references(first["description"]) & references(second["description"]))
                if not (same_amount or shared):
                    continue
                pair = tuple(sorted((first["id"], second["id"])))
                paired.add(pair)
                statuses = {first["status"], second["status"]}
                severity = "high" if statuses & {"open", "scheduled", "rescheduled"} else "medium"
                signals = ([f"same amount {money_text(first['amount_minor'], currency)} within {gap} day(s)"] if same_amount else []) + \
                          ([f"same reference {', '.join(shared)}"] if shared else [])
                findings.append(_finding("duplicate_bill", severity, f"Possible duplicate bill: {first['payee']}", [first, second],
                                         {"signals": signals, "days_apart": gap, "statuses": sorted(statuses),
                                          "window_days": DUPLICATE_WINDOW_DAYS},
                                         "Two bills from the same payee look like the same invoice. Confirm with the supplier "
                                         "before paying both" + (" (one is already paid)." if "paid" in statuses else ".")))
    # R2: split under the approval threshold
    if threshold:
        for key in sorted(by_payee):
            group = by_payee[key]
            used = set()
            for i, anchor in enumerate(group):
                if anchor["id"] in used or anchor["amount_minor"] >= threshold:
                    continue
                cluster = [row for row in group[i:] if row["id"] not in used and row["amount_minor"] < threshold
                           and 0 <= days_between(anchor["due_date"], row["due_date"]) <= SPLIT_WINDOW_DAYS]
                total = sum(row["amount_minor"] for row in cluster)
                if len(cluster) >= 2 and total >= threshold:
                    used.update(row["id"] for row in cluster)
                    findings.append(_finding(
                        "split_below_threshold", "medium", f"Bills split below the approval threshold: {anchor['payee']}", cluster,
                        {"threshold_minor": threshold, "threshold_source": "policy.dual_approval_threshold_minor",
                         "amounts_minor": [row["amount_minor"] for row in cluster], "combined_minor": total,
                         "window_days": SPLIT_WINDOW_DAYS,
                         "first_due": cluster[0]["due_date"], "last_due": cluster[-1]["due_date"]},
                        f"{len(cluster)} bills to one payee within {SPLIT_WINDOW_DAYS} days are each below the "
                        f"{money_text(threshold, currency)} two-person threshold but together reach "
                        f"{money_text(total, currency)}. Review them as one payment."))
    # R3: amount outliers against the payee's own other bills (robust modified z-score)
    for key in sorted(by_payee):
        group = by_payee[key]
        for row in group:
            others = [item["amount_minor"] for item in group if item["id"] != row["id"]]
            if len(others) < OUTLIER_MIN_HISTORY:
                continue
            z, median, basis = _modified_z(row["amount_minor"], others)
            relative = abs(row["amount_minor"] - median) / median if median else float("inf")
            if abs(z) > OUTLIER_Z and relative >= OUTLIER_MIN_RELATIVE:
                findings.append(_finding(
                    "amount_outlier", "medium" if z > 0 else "low", f"Unusual amount for {row['payee']}", [row],
                    {"amount_minor": row["amount_minor"], "payee_median_minor": int(median),
                     "modified_z": "infinite" if abs(z) == float("inf") else round(z, 2), "basis": basis,
                     "relative_difference": round(relative, 2) if relative != float("inf") else "infinite",
                     "compared_with_bills": len(others), "z_limit": OUTLIER_Z, "min_relative_difference": OUTLIER_MIN_RELATIVE},
                    f"This bill is {'far above' if z > 0 else 'far below'} {row['payee']}'s other {len(others)} bills "
                    f"(median {money_text(int(median), currency)}). Check the quantity and the invoice."))
    # R4: changed bank details and look-alike payees (the existing risk checks, surfaced)
    payees = analytics.payee_checks(rows, verified_accounts)
    index = {row["id"]: row for row in rows}
    for item in payees["flagged"]:
        row = index[item["bill_id"]]
        findings.append(_finding(
            "bank_details_changed", "high", f"Bank details {'missing' if item['code'] == 'account_missing' else 'changed'}: {row['payee']}",
            [row], {"expected_account": item["expected_account"], "new_account": item["new_account"], "code": item["code"],
                    "existing_control": "Tideway already blocks actions on this bill until callback verification."},
            item["reason"]))
    for item in payees["lookalikes"]:
        row = index[item["bill_id"]]
        findings.append(_finding(
            "lookalike_payee", "high", f"Look-alike payee: {row['payee']}", [row],
            {"similar_to": item["similar_to"], "similarity": str(item["similarity"]),
             "account": analytics.mask_account(item.get("account")),
             "existing_control": "Tideway already blocks actions on this bill until the payee is confirmed."},
            item["reason"]))
    # R5: round amounts far rounder than the payee's own history (or a large round first bill)
    for key in sorted(by_payee):
        group = by_payee[key]
        for row in group:
            if row["amount_minor"] % ROUND_UNIT_MINOR or row["status"] == "paid":
                continue
            others = [item for item in group if item["id"] != row["id"]]
            history_zeros = max((_trailing_zeros(item["amount_minor"]) for item in others), default=0)
            if len(others) >= 2 and _trailing_zeros(row["amount_minor"]) >= history_zeros + ROUND_EXTRA_ZEROS:
                findings.append(_finding(
                    "round_amount", "low", f"Round amount from {row['payee']}", [row],
                    {"amount_minor": row["amount_minor"], "round_unit_minor": ROUND_UNIT_MINOR,
                     "payee_bills_compared": len(others), "trailing_zeros": _trailing_zeros(row["amount_minor"]),
                     "payee_history_max_trailing_zeros": history_zeros},
                    f"{money_text(row['amount_minor'], currency)} is far rounder than any of {row['payee']}'s other "
                    f"{len(others)} bills (at least {ROUND_EXTRA_ZEROS} more trailing zeros). Round amounts can indicate "
                    "estimates or invented invoices; ask for the itemised invoice."))
            elif not others and threshold and row["amount_minor"] >= threshold:
                findings.append(_finding(
                    "round_amount", "low", f"Large round first bill from {row['payee']}", [row],
                    {"amount_minor": row["amount_minor"], "round_unit_minor": ROUND_UNIT_MINOR, "payee_bills_compared": 0,
                     "threshold_minor": threshold},
                    "A first-time payee's bill is a large round amount at or above the approval threshold. Ask for the "
                    "itemised invoice and verify the payee."))
    findings.sort(key=lambda item: (SEVERITY_ORDER[item["severity"]], item["rule"], item["bill_ids"]))
    return findings


RULES = [
    {"rule": "duplicate_bill", "description": f"Same payee and amount within {DUPLICATE_WINDOW_DAYS} days, or same payee and the same "
                                              "invoice-like reference in the description."},
    {"rule": "split_below_threshold", "description": f"Two or more bills to one payee within {SPLIT_WINDOW_DAYS} days, each below "
                                                     "the dual-approval threshold, together at or above it."},
    {"rule": "amount_outlier", "description": f"Modified z-score above {OUTLIER_Z} against the payee's other bills "
                                              f"(at least {OUTLIER_MIN_HISTORY}; median and MAD) and at least "
                                              f"{round(OUTLIER_MIN_RELATIVE * 100)}% away from that median."},
    {"rule": "bank_details_changed", "description": "Existing Tideway check: bank details differ from paid history or callback-verified account."},
    {"rule": "lookalike_payee", "description": "Existing Tideway check: new payee name ≥ 85% similar to an established supplier."},
    {"rule": "round_amount", "description": "Open bill that is a multiple of 1,000 currency units with at least 2 more trailing "
                                            "zeros than any of the payee's other bills (at least 2); or a first-time payee's "
                                            "round bill at or above the threshold."},
]


def synthetic_sample(snapshot):
    """A labelled, in-memory test sample. Never persisted; every id starts with 'syn-'."""
    start = snapshot["business"]["opening_date"]
    currency = snapshot["business"]["currency"]
    threshold = snapshot["policy"].get("dual_approval_threshold_minor") or 1_000_000
    unit = max(threshold, 1_000_000)

    def bill(number, payee, account, offset, fraction, odd, status="open", description=None, exact=None):
        amount = exact if exact is not None else int(unit * fraction) // 100_000 * 100_000 + odd
        return {"id": f"syn-{number:03d}", "payee": payee, "payee_account": account, "due_date": add_days(start, offset),
                "amount_minor": amount, "currency": currency, "status": status, "priority": "normal",
                "description": description or f"SYNTHETIC TEST bill {number:03d}", "risk_flags": [],
                "reschedule_allowed": True, "_synthetic": True}

    rows = [
        # Northwind Fabrics: clean history, one planted duplicate pair and one clean open bill.
        bill(1, "Northwind Fabrics", "SYN-1000-2001", -62, .30, 4_137, "paid"),
        bill(2, "Northwind Fabrics", "SYN-1000-2001", -31, .30, 9_421, "paid"),
        bill(3, "Northwind Fabrics", "SYN-1000-2001", 5, .30, 7_715, description="SYNTHETIC TEST invoice NWF-4471"),
        bill(4, "Northwind Fabrics", "SYN-1000-2001", 8, .30, 7_715, description="SYNTHETIC TEST invoice NWF-4471 (resent)"),
        bill(5, "Northwind Fabrics", "SYN-1000-2001", 33, .32, 2_209),
        # Meridian Logistics: three bills just below the threshold within a week.
        bill(6, "Meridian Logistics", "SYN-2000-3001", 10, 0, 0, exact=int(threshold * .92) + 1),
        bill(7, "Meridian Logistics", "SYN-2000-3001", 12, 0, 0, exact=int(threshold * .88) + 3),
        bill(8, "Meridian Logistics", "SYN-2000-3001", 14, 0, 0, exact=int(threshold * .95) + 7),
        # Coastal Utilities: stable history and one outlier.
        *[bill(9 + i, "Coastal Utilities", "SYN-3000-4001", -150 + 30 * i, .10, odd, "paid")
          for i, odd in enumerate((1_113, 4_871, 2_532, 6_019, 3_388))],
        bill(14, "Coastal Utilities", "SYN-3000-4001", 6, .10, 5_004),
        bill(15, "Coastal Utilities", "SYN-3000-4001", 20, .60, 8_731),
        # Delta Packaging: changed bank account on an open bill.
        bill(16, "Delta Packaging", "SYN-4000-5001", -45, .20, 3_141, "paid"),
        bill(17, "Delta Packaging", "SYN-4000-5001", -15, .20, 5_926, "paid"),
        bill(18, "Delta Packaging", "SYN-9999-0001", 9, .20, 2_653),
        # Look-alike of an established synthetic supplier.
        bill(19, "Northwind Fabrlcs", "SYN-7777-0002", 11, .45, 8_979),
        # Summit Stationery: non-round history, one exact round bill.
        bill(20, "Summit Stationery", "SYN-5000-6001", -60, .50, 23_417, "paid"),
        bill(21, "Summit Stationery", "SYN-5000-6001", -30, .52, 81_233, "paid"),
        bill(22, "Summit Stationery", "SYN-5000-6001", -5, .50, 4_119, "paid"),
        bill(23, "Summit Stationery", "SYN-5000-6001", 25, .50, 0),
        # Riverbend Cleaning: identical monthly retainer 30 days apart (must NOT be a duplicate).
        bill(24, "Riverbend Cleaning", "SYN-6000-7001", -20, .15, 7_777, "paid"),
        bill(25, "Riverbend Cleaning", "SYN-6000-7001", 10, .15, 7_777),
        bill(26, "Riverbend Cleaning", "SYN-6000-7001", 40, .15, 7_777),
    ]
    labels = [
        {"rule": "duplicate_bill", "bill_ids": ["syn-003", "syn-004"]},
        {"rule": "split_below_threshold", "bill_ids": ["syn-006", "syn-007", "syn-008"]},
        {"rule": "amount_outlier", "bill_ids": ["syn-015"]},
        {"rule": "bank_details_changed", "bill_ids": ["syn-018"]},
        {"rule": "lookalike_payee", "bill_ids": ["syn-019"]},
        {"rule": "round_amount", "bill_ids": ["syn-023"]},
    ]
    clean = ["syn-001", "syn-002", "syn-005", "syn-009", "syn-010", "syn-011", "syn-012", "syn-013", "syn-014",
             "syn-016", "syn-017", "syn-020", "syn-021", "syn-022", "syn-024", "syn-025", "syn-026"]
    return rows, labels, clean


def scan(snapshot, derived=None, synthetic_sample_enabled=False):
    business, policy = snapshot["business"], snapshot["policy"]
    threshold = policy.get("dual_approval_threshold_minor")
    verified = {item["name"]: item["verified_account"] for item in snapshot["counterparties"].values()
                if item["kind"] == "supplier" and item["verified_account"]}
    bills = [dict(row) for row in snapshot["records"]["bills"]]
    sample = labels = clean = None
    if synthetic_sample_enabled:
        sample, labels, clean = synthetic_sample(snapshot)
        bills = bills + sample
    findings = run_rules(bills, threshold, business["currency"], verified)
    result = {"business_id": business["business_id"], "currency": business["currency"],
              "snapshot_hash": snapshot["snapshot_hash"], "threshold_minor": threshold,
              "threshold_source": "policy.dual_approval_threshold_minor (Tideway's two-person approval threshold)",
              "bills_scanned": len([row for row in bills if not row.get("_synthetic")]),
              "ledger_findings": [item for item in findings if item["source"] == "ledger"],
              "rules": RULES, "read_only": True,
              "authority": "Advisory only. The scan cannot approve, block or execute anything; Tideway's existing payee "
                           "blocks and approval rules remain authoritative.",
              "synthetic_sample": None}
    if synthetic_sample_enabled:
        found = [item for item in findings if item["source"] != "ledger"]
        matched_labels, true_positive = [], set()
        for label in labels:
            hit = next((item for item in found if item["rule"] == label["rule"] and item["source"] == "synthetic"
                        and set(label["bill_ids"]) <= set(item["bill_ids"])), None)
            matched_labels.append({**label, "detected": hit is not None, "finding_id": hit["finding_id"] if hit else None})
            if hit:
                true_positive.add(hit["finding_id"])
        false_positive = [item for item in found if item["finding_id"] not in true_positive]
        flagged_clean = sorted({bill_id for item in false_positive for bill_id in item["bill_ids"]} & set(clean))
        result["synthetic_sample"] = {
            "label": "SYNTHETIC TEST SAMPLE — in-memory only, never saved to the ledger",
            "bills": len(sample), "planted_anomalies": len(labels), "clean_bills": len(clean),
            "findings": found, "labels": matched_labels,
            "true_positives": len(true_positive), "false_positives": len(false_positive),
            "false_negatives": sum(1 for item in matched_labels if not item["detected"]),
            "precision": round(len(true_positive) / len(found), 4) if found else None,
            "recall": round(sum(1 for item in matched_labels if item["detected"]) / len(labels), 4),
            "clean_bills_flagged": flagged_clean,
            "caveat": "The sample was written alongside the rules, so it checks that each rule fires as specified and leaves "
                      "the clean controls alone. It is not evidence of real-world precision or recall.",
            "sample_bills": [{key: value for key, value in row.items() if not key.startswith("_")}
                             for row in sample],
        }
    return result


# =========================================================================== credit passport

def passport_key(store_key):
    """Purpose-bound sub-key, so a passport signature can never verify as a mandate (and vice versa)."""
    return hmac.new(store_key, PASSPORT_VERSION.encode(), hashlib.sha256).digest()


def passport_signing_secret(store_key):
    """Ed25519 seed for this instance, purpose-bound and derived from the store key (demo-grade key management)."""
    return hmac.new(store_key, b"tideway-credit-passport-ed25519-v1", hashlib.sha256).digest()


def passport_public_key(store_key):
    public = ed25519.public_key(passport_signing_secret(store_key))
    return {"alg": "Ed25519", "public_key": public.hex(), "key_id": hashlib.sha256(public).hexdigest()[:16]}


def public_message(document):
    """Bytes covered by the Ed25519 signature: every field except the two signature fields."""
    body = {key: value for key, value in document.items() if key not in ("signature", "public_signature")}
    return canonical_json(body).encode("utf-8")


def verify_public_signature(document, expected_public_key=None):
    """Offline check a lender can run with only the issuer's public key (hex)."""
    block = document.get("public_signature") if isinstance(document, dict) else None
    if not isinstance(block, dict) or block.get("alg") != "Ed25519":
        return False
    try:
        public, signature = bytes.fromhex(str(block.get("public_key"))), bytes.fromhex(str(block.get("signature")))
    except ValueError:
        return False
    if expected_public_key is not None and public.hex() != str(expected_public_key).lower():
        return False
    return ed25519.verify(public, public_message(document), signature)


def _signable(value):
    """Integers and strings only: decimals become strings so the signature survives any JSON round-trip."""
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        return repr(round(value, 4))
    if isinstance(value, dict):
        return {str(key): _signable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_signable(item) for item in value]
    return str(value)


def _iso(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def build_passport(store_key, snapshot, plan, score, simulation, audit_evidence, issued_by, now=None, days=PASSPORT_DAYS):
    now = now or datetime.now(timezone.utc)
    business = snapshot["business"]

    def summary(name):
        totals = plan["scenarios"][name]["totals"]
        return {key: totals[key] for key in ("opening_cash_minor", "receipts_minor", "disbursements_minor",
                                              "net_flow_minor", "closing_cash_minor", "lowest_cash_minor",
                                              "lowest_cash_date", "weeks_below_reserve", "first_week_below_reserve")}

    document = {
        "type": "TidewayCreditPassport", "version": PASSPORT_VERSION, "passport_id": secrets.token_hex(16),
        "issuer": {"name": "Tideway sandbox instance", "key_id": hashlib.sha256(passport_key(store_key)).hexdigest()[:16],
                   "issued_by": issued_by},
        "business": {"business_id": business["business_id"], "name": business["name"], "currency": business["currency"],
                     "synthetic": bool(business.get("synthetic"))},
        "as_of": snapshot["state"]["current_date"], "issued_at": _iso(now), "expires_at": _iso(now + timedelta(days=days)),
        "snapshot_hash": snapshot["snapshot_hash"],
        "audit": {"head_hash": audit_evidence["head_hash"], "entries": len(audit_evidence["entries"]),
                  "chain_valid": audit_evidence["hash_chain_valid"],
                  "note": "Audit-chain head before this passport's own issuance entry."},
        "twcf": {"start_date": plan["start_date"], "end_date": plan["end_date"], "weeks": plan["weeks"],
                 "reserve_floor_minor": plan["reserve_floor_minor"],
                 "scheduled": summary("scheduled"), "likely": summary("likely"), "stress": summary("stress")},
        "health": {"score": score["score"], "band": score["band"], "weights": score["weights"],
                   "components": [{"id": item["id"], "value": item["value"], "score": item["score"],
                                   "weight": item["weight"], "formula": item["formula"]} for item in score["components"]]},
        "breach_risk": {"probability_breach": simulation["probability_breach"], "runs": simulation["runs"],
                        "seed": simulation["seed"], "horizon_end": simulation["end_date"],
                        "probability_payroll_unfunded": simulation["probability_payroll_unfunded"]},
        "limitations": ("Synthetic sandbox data. Scheduled ledger, not a bank balance. The Ed25519 signature lets anyone "
                        "verify the passport with the issuer's public key; the issuer key is demo-grade (derived from the "
                        "instance key, no HSM or revocation list). Not a credit rating, offer or guarantee."),
        "signature_alg": "Ed25519 (public) + HMAC-SHA256 (issuer)",
    }
    document = _signable(document)
    signer = passport_public_key(store_key)
    document["public_signature"] = {**signer, "signature": ed25519.sign(passport_signing_secret(store_key), public_message(document)).hex(),
                                    "covers": "every field except signature and public_signature",
                                    "verify_offline": "python scripts/verify_passport.py passport.json"}
    document["signature"] = security.sign(passport_key(store_key), document)
    return document


def verify_passport(store_key, document, business_id, now=None):
    now = now or datetime.now(timezone.utc)
    base = {"valid": False, "checked_at": _iso(now), "signature_alg": "Ed25519 (public) + HMAC-SHA256 (issuer)",
            "note": "Lenders can also verify offline with the issuer's public key: python scripts/verify_passport.py passport.json"}
    if not isinstance(document, dict) or set(document) != set(PASSPORT_FIELDS) \
            or document.get("version") != PASSPORT_VERSION or document.get("type") != "TidewayCreditPassport":
        return {**base, "reason": "malformed", "message": "Not a Tideway credit passport in the expected format."}
    try:
        size = len(canonical_json(document).encode("utf-8"))
    except (TypeError, ValueError):
        size = PASSPORT_MAX_BYTES + 1
    if size > PASSPORT_MAX_BYTES:
        return {**base, "reason": "malformed", "message": "Passport is too large."}
    if not security.verify(passport_key(store_key), document) or not verify_public_signature(
            document, passport_public_key(store_key)["public_key"]):
        return {**base, "reason": "signature_mismatch",
                "message": "Signature does not match: the passport was altered after issuance or was not issued by this "
                           "Tideway instance. A signature cannot show which field changed."}
    owner = document.get("business") if isinstance(document.get("business"), dict) else {}
    if owner.get("business_id") != business_id:
        return {**base, "reason": "wrong_business", "signature_valid": True,
                "message": "The signature is genuine but the passport belongs to a different business."}
    issued, expires = _parse(document.get("issued_at")), _parse(document.get("expires_at"))
    if issued is None or expires is None:
        return {**base, "reason": "malformed", "message": "Passport dates are invalid."}
    if expires <= now:
        return {**base, "reason": "expired", "signature_valid": True, "expires_at": document["expires_at"],
                "message": f"The passport expired at {document['expires_at']}. Ask the business for a fresh one."}
    if issued > now + timedelta(minutes=5):
        return {**base, "reason": "not_yet_valid", "signature_valid": True,
                "message": "The passport's issue time is in the future."}
    return {**base, "valid": True, "reason": "valid", "signature_valid": True, "public_signature_valid": True,
            "public_key": document["public_signature"]["public_key"], "passport_id": document["passport_id"],
            "business_id": business_id, "issued_at": document["issued_at"], "expires_at": document["expires_at"],
            "snapshot_hash": document["snapshot_hash"],
            "message": "Genuine and unaltered: issued by this Tideway instance for this business and not expired."}


# =========================================================================== service

class Treasury:
    def __init__(self, tideway):
        self.tideway, self.store = tideway, tideway.store

    def _context(self, business_id):
        snapshot = self.store.snapshot(business_id)
        return snapshot, self.store.derived(snapshot)

    def twcf(self, business_id):
        snapshot, derived = self._context(business_id)
        return twcf(snapshot, derived)

    def health(self, business_id):
        snapshot, derived = self._context(business_id)
        return health(snapshot, derived)

    def scan(self, business_id, synthetic_sample_enabled=False):
        if not isinstance(synthetic_sample_enabled, bool):
            raise ValidationError("synthetic_sample must be true or false.")
        snapshot, derived = self._context(business_id)
        return scan(snapshot, derived, synthetic_sample_enabled)

    def issue_passport(self, business_id, operator, actor, now=None, days=PASSPORT_DAYS):
        snapshot, derived = self._context(business_id)
        plan = twcf(snapshot, derived)
        simulation = _simulation(snapshot)
        score = health(snapshot, derived, plan, simulation)
        evidence = self.store.evidence(business_id)
        document = build_passport(self.store.key, snapshot, plan, score, simulation, evidence,
                                  f"{operator['role']}:{operator['id']}", now, days)
        receipt = self.store.audit(business_id, "treasury.passport.issue", actor, "human_approval",
                                   {"passport_id": document["passport_id"], "expires_at": document["expires_at"],
                                    "snapshot_hash": document["snapshot_hash"], "health_score": document["health"]["score"],
                                    "document_sha256": hashlib.sha256(canonical_json(document).encode()).hexdigest(),
                                    "executed": False})
        return {"passport": document, "audit": receipt, "read_only_records": True}

    def verify_passport(self, business_id, document, now=None):
        result = verify_passport(self.store.key, document, business_id, now)
        if result["valid"]:
            evidence = self.store.evidence(business_id)
            result["issuance_logged"] = any(entry["action"] == "treasury.passport.issue"
                                            and isinstance(entry["details"], dict)
                                            and entry["details"].get("passport_id") == document["passport_id"]
                                            for entry in evidence["entries"])
            result["records_changed_since_issue"] = self.store.snapshot(business_id)["snapshot_hash"] != document["snapshot_hash"]
        return result
