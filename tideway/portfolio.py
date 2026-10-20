"""Portfolio radar: lender-side early warning over a SYNTHETIC SME portfolio.

Banks, lenders and large buyers serve thousands of SMEs.  The radar ranks a
portfolio by the chance that each business breaches its own cash reserve floor
in the next 60 days, explains the main driver and suggests an advisory early
intervention.

Security and privacy design
---------------------------
* The radar never reads tenant workspaces.  This module does not import the
  store, the service layer or the server; it generates its own fictional
  portfolio from a seed (``generate_portfolio``) and every output carries
  ``"synthetic": True`` and a visible label.  Tenant isolation is unaffected.
* Interventions are advisory text only (``"executable": False``).  Nothing here
  can approve, execute, contact a customer or make a credit decision.
* Inputs are whitelisted and bounded; errors are ``ValidationError``.

Reused engines
--------------
Records are built with the normal ``tideway.domain`` validators, cash events
come from ``projection.build_events``, payment-timing probabilities come from
TidePay (``analytics.tidepay_predictions``) and are sampled with
``analytics.delay_quantile``/``delay_cdf``.  At zero shock the radar's breach
probability equals ``analytics.monte_carlo`` exactly for the same seed and runs
(a unit test checks this); the radar loop only drops the fan chart, works in day
offsets and records breach days and late customers.

The realised futures used by the backtest come from the generative payment
process (customer personalities from ``tideway.ml.synth``) with an independent
seed, never from the radar's own draws.
"""
from __future__ import annotations

import json
import math
import random
import statistics
from collections import Counter
from datetime import date, timedelta
from functools import lru_cache
from itertools import accumulate

from .analytics import delay_cdf, delay_quantile, stable_seed, tidepay_predictions
from .domain import (
    CURRENCIES,
    OPEN_INVOICE_STATUSES,
    ValidationError,
    add_days,
    days_between,
    validate_bill,
    validate_business,
    validate_invoice,
    validate_policy,
)
from .ml.model import auc
from .ml.synth import FESTIVAL_MONTHS, PERSONALITIES, PERSONALITY_WEIGHTS, SECTORS
from .projection import build_events, horizon_end, project

PORTFOLIO_VERSION = "tideway-portfolio-radar-v1"
LABEL = "SYNTHETIC PORTFOLIO: fictional SMEs generated from a seed. Not tenant data, not a credit decision."
OPENING_DATE = "2026-10-01"
HORIZON_DAYS = 60
TARGET_DATE = add_days(OPENING_DATE, HORIZON_DAYS)
DEFAULT_SEED = 2026
DEFAULT_SIZE = 60
DEFAULT_RUNS = 400           # measured: whole 60-SME radar well under 3 s cold on the build PC
MIN_SIZE, MAX_SIZE = 10, 200
MIN_RUNS, MAX_RUNS = 50, 2000
MAX_SHOCK_DAYS = 60
RED_THRESHOLD = 0.50         # same cut-offs as the app's cash weather (Storm >= 50%, Unsettled >= 15%)
AMBER_THRESHOLD = 0.15
AT_RISK_WINDOWS = (14, 30)   # "at risk within N days" = P(first breach by day N) >= AMBER_THRESHOLD
TIERS = ("red", "amber", "green")
TIER_ORDER = {"green": 0, "amber": 1, "red": 2}
UNEXPECTED_EXPENSE_CHANCE = 0.15   # realised futures only: a cost the radar cannot see
CONDITIONED_DRAW_TRIES = 200
OUTCOME_SALT = "realised-future-v1"

# Markets already demonstrated in Tideway (BDT, CNY, SGD demo businesses) plus INR.
MARKETS = (("BD", "BDT", 0.40), ("CN", "CNY", 0.20), ("SG", "SGD", 0.20), ("IN", "INR", 0.20))
SECTOR_NOUNS = {"services": ("Facility Services", "Cleaning Co", "Consulting"),
                "wholesale": ("Wholesale", "Trading", "Distributors"),
                "retail": ("Retail", "Stores", "Mart"),
                "manufacturing": ("Fabrication", "Works", "Components"),
                "print": ("Print", "Press", "Packaging Print")}
NAME_PREFIXES = ("Meghna", "Padma", "Jamuna", "Karnaphuli", "Teesta", "Surma", "Kaveri", "Narmada", "Godavari",
                 "Yangtze", "Pearl Bay", "Jade Lane", "Lotusbridge", "Merlion", "Orchid Row", "Kampong", "Saffron",
                 "Monsoon", "Mangrove", "Banyan", "Kestrel", "Coral", "Indigo", "Silverline", "Northstar",
                 "Tamarind", "Cinnamon", "Riverbend", "Hillside", "Seabreeze")
CUSTOMER_NAMES = ("Arcadia Foods", "Brightway Mart", "Cobalt Hospitals", "Dunmore Hotels", "Evergreen Schools",
                  "Fairview Clinics", "Granite Builders", "Horizon Telecom", "Ironbridge Logistics", "Juniper Pharma",
                  "Kingfisher Resorts", "Lighthouse Media", "Maple Garments", "Nimbus Airlines", "Oakridge Textiles",
                  "Pinnacle Motors", "Quayside Ports", "Redwood Energy", "Summit Apparel", "Tidewater Exports",
                  "Umber Ceramics", "Vantage Retail", "Willow Agro", "Xenon Labs", "Yellowfin Seafood", "Zephyr Tech")
SUPPLIER_NAMES = ("Alpha Raw Materials", "Beacon Freight", "Crescent Paper Mills", "Delta Chemicals",
                  "Eastline Packaging", "Fortune Steel Traders", "Global Inks", "Harvest Commodities")


# ---------------------------------------------------------------------------
# Validation helpers


def _whole(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValidationError(f"{name} must be a whole number from {low} to {high}.")
    return value


def _check_size(n, seed, runs=None):
    _whole(n, "Portfolio size", MIN_SIZE, MAX_SIZE)
    _whole(seed, "seed", 0, 2 ** 31 - 1)
    if runs is not None:
        _whole(runs, "Monte Carlo runs", MIN_RUNS, MAX_RUNS)


def validate_shock(shock):
    """Return (customer_delay_days, sector) from a shock dict; (0, 'all') means no shock."""
    if shock is None:
        return 0, "all"
    if not isinstance(shock, dict):
        raise ValidationError("shock must be an object such as {\"customer_delay_days\": 15}.")
    unknown = sorted(set(shock) - {"customer_delay_days", "sector"})
    if unknown:
        raise ValidationError(f"Unknown shock field(s): {', '.join(str(key)[:40] for key in unknown)}. "
                              "Use customer_delay_days and optionally sector.")
    days = _whole(shock.get("customer_delay_days", 0), "customer_delay_days", 0, MAX_SHOCK_DAYS)
    sector = shock.get("sector") or "all"
    if not isinstance(sector, str) or sector not in ("all",) + SECTORS:
        raise ValidationError(f"sector must be 'all' or one of: {', '.join(SECTORS)}.")
    return days, sector


def radar_from_query(query):
    """Server helper: ``query`` is ``urllib.parse.parse_qs`` output; only shock_days and sector are accepted."""
    if not isinstance(query, dict):
        raise ValidationError("Invalid query.")
    unknown = sorted(set(query) - {"shock_days", "sector"})
    if unknown:
        raise ValidationError(f"Unknown parameter(s): {', '.join(str(key)[:40] for key in unknown)}. "
                              "Use shock_days (0-60) and sector.")
    values = {}
    for key in ("shock_days", "sector"):
        if key in query:
            items = query[key]
            if not isinstance(items, (list, tuple)) or len(items) != 1 or not isinstance(items[0], str):
                raise ValidationError(f"Give {key} at most once.")
            values[key] = items[0].strip()
    raw_days = values.get("shock_days", "0") or "0"
    if not raw_days.isdigit() or len(raw_days) > 2:
        raise ValidationError(f"shock_days must be a whole number from 0 to {MAX_SHOCK_DAYS}.")
    shock = {"customer_delay_days": int(raw_days), "sector": values.get("sector") or "all"}
    return radar(shock=shock)


# ---------------------------------------------------------------------------
# Synthetic portfolio generation


def _choice(rng, items):
    return items[int(rng.random() * len(items))]


def _personality(rng):
    roll, total = rng.random(), 0.0
    for name, weight in PERSONALITY_WEIGHTS:
        total += weight
        if roll <= total:
            return name
    return "typical"


def _true_delay(rng, customer, amount_minor, due, index):
    """Days late drawn from the generative process TidePay was trained on (tideway.ml.synth)."""
    mean, spread, tail = PERSONALITIES[customer["personality"]]
    delay = rng.gauss(mean, spread)
    delay += 4.0 * max(0.0, amount_minor / customer["typical_minor"] - 1.3)  # unusually large invoices are paid later
    delay += 3.0 if due.day >= 26 else 0.0                                   # month-end crunch
    delay += 5.0 if due.month in FESTIVAL_MONTHS else 0.0
    delay += customer["trend"] * index                                       # drifting behaviour
    delay += 0.08 * (customer["terms"] - 30)
    if rng.random() < tail:
        delay += rng.uniform(20, 60)
    if customer["personality"] == "prompt" and rng.random() < 0.6:
        delay = min(delay, 0.0)
    return max(-5, int(round(delay)))


def _units(rng_value, fx):
    """USD-scale value -> local minor units rounded to 10 local units."""
    return max(10, int(round(rng_value * fx / 10)) * 10) * 100


def _make_sme(seed, index, used_names):
    rng = random.Random(stable_seed(seed, PORTFOLIO_VERSION, "sme", index))
    sector = _choice(rng, SECTORS)
    roll, total, market = rng.random(), 0.0, MARKETS[0]
    for item in MARKETS:
        total += item[2]
        if roll <= total:
            market = item
            break
    country, currency = market[0], market[1]
    fx = CURRENCIES[currency][1]
    sme_id = f"pf-sme-{index + 1:03d}"
    name = f"{_choice(rng, NAME_PREFIXES)} {_choice(rng, SECTOR_NOUNS[sector])}"
    base, suffix = name, 2
    while name in used_names:
        name, suffix = f"{base} {suffix}", suffix + 1
    used_names.add(name)

    health = rng.random()                                       # latent; never shown to the radar
    payroll_usd = min(45_000.0, max(1_500.0, rng.lognormvariate(math.log(5_500), 0.55)))
    payroll = _units(payroll_usd, fx)
    revenue_multiple = 1.7 + 0.9 * health + rng.uniform(-0.2, 0.2)   # monthly billing / payroll
    cost_multiple = rng.uniform(0.55, 0.95)                         # non-payroll monthly costs / payroll
    reserve_multiple = rng.uniform(0.15, 0.45)
    cash_multiple = reserve_multiple + 0.2 + 2.0 * (0.5 * health + 0.5 * rng.random()) ** 1.5
    opening_cash = _units(payroll_usd * cash_multiple, fx)
    reserve = _units(payroll_usd * reserve_multiple, fx)

    business = validate_business({"business_id": sme_id, "name": name, "currency": currency,
                                  "opening_cash_minor": opening_cash, "opening_date": OPENING_DATE,
                                  "default_target_date": TARGET_DATE, "country": country, "sector": sector,
                                  "synthetic": True})
    policy = validate_policy({"reserve_floor_minor": reserve, "action_limit_minor": payroll,
                              "lookahead_days": 0}, sme_id, currency)

    # Bills: payroll (never deferrable), rent, utilities and two or three suppliers per month.
    bills = []
    pattern = _choice(rng, ("25th", "25th", "month-end", "month-end", "semi-monthly"))
    for month, last in (("2026-10", 31), ("2026-11", 30)):
        if pattern == "semi-monthly":
            dates = ((f"{month}-10", payroll // 2), (f"{month}-25", payroll - payroll // 2))
        else:
            dates = ((f"{month}-{25 if pattern == '25th' else last}", payroll),)
        for k, (due, amount) in enumerate(dates, 1):
            bills.append({"id": f"bill-{sme_id}-{month}-pay{k}", "payee": "Staff payroll", "description": "Monthly payroll",
                          "due_date": due, "amount_minor": amount, "priority": "payroll"})
    monthly_costs = cost_multiple * payroll_usd
    suppliers = rng.sample(SUPPLIER_NAMES, 2 + int(rng.random() * 2))
    supplier_days = [3 + int(rng.random() * 25) for _ in suppliers]
    for month in ("2026-10", "2026-11"):
        bills.append({"id": f"bill-{sme_id}-{month}-rent", "payee": "Landlord", "description": "Premises rent",
                      "due_date": f"{month}-05", "amount_minor": _units(0.3 * monthly_costs, fx), "priority": "high"})
        bills.append({"id": f"bill-{sme_id}-{month}-util", "payee": "Utility company", "description": "Power and water",
                      "due_date": f"{month}-15", "amount_minor": _units(0.1 * monthly_costs, fx), "priority": "normal"})
        for k, (supplier, day) in enumerate(zip(suppliers, supplier_days), 1):
            amount = _units(0.6 * monthly_costs / len(suppliers) * rng.uniform(0.8, 1.2), fx)
            bills.append({"id": f"bill-{sme_id}-{month}-s{k}", "payee": supplier, "description": "Supplier invoice",
                          "due_date": f"{month}-{day:02d}", "amount_minor": amount, "priority": "normal"})
    bills = [validate_bill({**row, "status": "open", "currency": currency}, sme_id, currency) for row in bills]

    # Customers with a latent payment personality, and their invoice streams.
    n_customers = 3 + int(rng.random() * 6)
    weights = [rng.random() ** 2 + 0.05 for _ in range(n_customers)]
    total_weight = sum(weights)
    monthly_billing = revenue_multiple * payroll_usd
    invoices, truth = [], {}
    opening = date.fromisoformat(OPENING_DATE)
    billing_end = opening + timedelta(days=30)       # confirmed/contracted billing up to day 30 of the horizon
    for c, customer_name in enumerate(rng.sample(CUSTOMER_NAMES, n_customers)):
        frequency = rng.uniform(0.8, 2.5)             # invoices per month
        customer = {"name": customer_name, "personality": _personality(rng),
                    "terms": _choice(rng, (15, 30, 30, 45, 60)), "trend": rng.uniform(-0.15, 0.25)}
        customer["typical_minor"] = _units(monthly_billing * weights[c] / total_weight / frequency, fx)
        day = date(2026, 6, 1) + timedelta(days=int(rng.random() * 21))
        number = 0
        while day <= billing_end:
            amount = max(1_000, int(round(rng.lognormvariate(math.log(customer["typical_minor"]), 0.35) / 1_000)) * 1_000)
            due = day + timedelta(days=customer["terms"])
            delay = _true_delay(rng, customer, amount, due, number)
            paid = due + timedelta(days=delay)
            invoice_id = f"inv-{sme_id}-c{c + 1}-{number + 1:02d}"
            row = {"id": invoice_id, "customer": customer_name, "description": "Goods and services",
                   "issue_date": day.isoformat(), "due_date": due.isoformat(),
                   "expected_collection_date": due.isoformat(), "amount_minor": amount}
            if paid < opening:
                row.update(status="paid", paid_date=paid.isoformat())
            else:
                row["status"] = "overdue" if due < opening else "confirmed"
                truth[invoice_id] = {"customer": c, "index": number}
            invoices.append(validate_invoice({**row, "currency": currency}, sme_id, currency))
            number += 1
            day += timedelta(days=max(5, int(rng.expovariate(frequency / 30))))
        customer.pop("name")
        truth.setdefault("_customers", []).append(customer)
    return {"sme_id": sme_id, "name": name, "sector": sector, "country": country, "currency": currency,
            "monthly_payroll_minor": payroll, "synthetic": True,
            "business": business, "policy": policy,
            "records": {"transactions": [], "invoices": invoices, "bills": bills},
            "truth": truth}


def generate_portfolio(n=DEFAULT_SIZE, seed=DEFAULT_SEED):
    """Deterministic synthetic SME ledgers (validated Tideway records).  Never reads tenant data."""
    _check_size(n, seed)
    used = set()
    return [_make_sme(seed, index, used) for index in range(n)]


# ---------------------------------------------------------------------------
# Monte Carlo radar


def _prepare(sme):
    business, policy, records = sme["business"], sme["policy"], sme["records"]
    start = business["opening_date"]
    end = horizon_end(business, TARGET_DATE, 0)
    events, _ = build_events(business, records, end)
    length = days_between(start, end) + 1
    fixed = [0] * length
    invoices = {row["id"]: row for row in records["invoices"]}
    predictions = tidepay_predictions(records["invoices"], start)
    uncertain = []
    for event in events:
        index = days_between(start, event["date"])
        if event["kind"] == "invoice":
            row = invoices[event["id"]]
            minimum_late = max(0, days_between(row["due_date"], start))
            probs = predictions[row["id"]]["probabilities"]
            floor = delay_cdf(probs, minimum_late - 1) if minimum_late > 0 else 0.0  # still unpaid today
            uncertain.append((row["customer"], event["amount_minor"], index, days_between(start, row["due_date"]),
                              minimum_late, probs, floor, row["id"]))
        else:
            fixed[index] += event["effect_minor"]
    scheduled = project(business, policy, records, TARGET_DATE)
    customers = sorted({row["customer"] for row in records["invoices"] if row["status"] in OPEN_INVOICE_STATUSES})
    return {"sme": sme, "fixed": fixed, "length": length, "uncertain": uncertain, "customers": customers,
            "opening": business["opening_cash_minor"], "reserve": policy["reserve_floor_minor"],
            "scheduled_minimum": scheduled["minimum_cash_minor"],
            "scheduled_breach": scheduled["first_breach_date"] is not None,
            "open_receivables": sum(row["amount_minor"] for row in records["invoices"]
                                    if row["status"] in OPEN_INVOICE_STATUSES)}


def _simulate(prep, runs, seed, extra_days=0):
    """Same random stream and sampling rule as analytics.monte_carlo; payments optionally arrive later."""
    rng = random.Random(seed)
    fixed, length, opening, reserve = prep["fixed"], prep["length"], prep["opening"], prep["reserve"]
    customers, uncertain = prep["customers"], prep["uncertain"]
    breach_days, shortfalls, late_cash = [], [], Counter()
    for _ in range(runs):
        draws = {customer: rng.random() for customer in customers}
        net = fixed[:]
        arrivals = []
        for customer, amount, expected, due, minimum_late, probs, floor, _invoice in uncertain:
            delay = max(minimum_late, delay_quantile(probs, floor + draws[customer] * (1 - floor)))
            offset = max(expected, due + delay) + extra_days
            if offset < length:
                net[offset] += amount
            arrivals.append(offset)
        path = list(accumulate(net, initial=opening))      # path[0] = opening, path[i + 1] = close of day i
        minimum = min(path)
        if minimum < reserve:
            first = next(i for i, value in enumerate(path) if value < reserve)
            breach = max(0, first - 1)
            breach_days.append(breach)
            shortfalls.append(reserve - minimum)
            for (customer, amount, expected, *_rest), offset in zip(uncertain, arrivals):
                if expected <= breach < offset:            # was due to arrive in time, arrived after the breach
                    late_cash[customer] += amount
        else:
            shortfalls.append(0)
    return {"runs": runs, "breach_days": breach_days, "shortfalls": shortfalls, "late_cash": late_cash}


def _quantile(sorted_values, fraction):
    if not sorted_values:
        return None
    return sorted_values[max(0, min(len(sorted_values) - 1, int(round(fraction * (len(sorted_values) - 1)))))]


def tier_for(probability):
    """Documented thresholds: red >= 0.50, amber >= 0.15, otherwise green."""
    if probability >= RED_THRESHOLD:
        return "red"
    if probability >= AMBER_THRESHOLD:
        return "amber"
    return "green"


def _driver(prep, result):
    if prep["scheduled_breach"]:
        return {"kind": "structural", "name": "Scheduled outflows",
                "share": None, "detail": "Cash falls below the reserve even if every customer pays on its due date."}
    late = result["late_cash"]
    total = sum(late.values())
    if not total:
        return {"kind": "none", "name": None, "share": None,
                "detail": "No simulated future breached because of a late customer payment."}
    name, amount = sorted(late.items(), key=lambda item: (-item[1], item[0]))[0]
    share = round(amount / total, 3)
    return {"kind": "customer", "name": name, "share": share,
            "detail": f"{round(share * 100)}% of the receipts that were due before the breach but arrived after it "
                      f"in breaching futures came from {name}."}


def _intervention(tier, driver, p_14):
    named = driver["kind"] == "customer"
    receivables = f"receivables from {driver['name']}" if named else "its open receivables"
    chase = driver["name"] if named else "overdue customers"
    if tier == "red" and driver["kind"] == "structural" and p_14 >= AMBER_THRESHOLD:
        code, text = "rm_call_urgent", ("Relationship-manager call within two business days: scheduled outflows exceed cash "
                                        "even with on-time collections. Discuss a MOCK working-capital comparison.")
    elif tier == "red" and driver["kind"] == "structural":
        code, text = "rm_review_structural", ("Relationship-manager review before the breach window: scheduled outflows "
                                              "exceed cash even with on-time collections. Prepare a MOCK working-capital "
                                              "comparison.")
    elif tier == "red" and p_14 >= AMBER_THRESHOLD:
        code, text = "rm_call", (f"Relationship-manager call this week; offer a MOCK invoice-financing comparison "
                                 f"against {receivables}.")
    elif tier == "red":
        code, text = "mock_invoice_financing", (f"Offer a MOCK invoice-financing comparison against {receivables} "
                                                "before the breach window.")
    elif tier == "amber":
        code, text = "monitor", f"Monitor weekly and suggest the owner sends collection reminders to {chase}."
    else:
        code, text = "no_action", "No action: the reserve floor holds in almost every simulated future."
    return {"code": code, "text": text, "advisory_only": True, "executable": False}


def _assess(prep, result):
    runs = result["runs"]
    days = result["breach_days"]
    probability = len(days) / runs
    within = {window: sum(1 for value in days if value <= window) / runs for window in AT_RISK_WINDOWS}
    shortfalls = sorted(result["shortfalls"])
    tier = tier_for(probability)
    driver = _driver(prep, result)
    return {"breach_probability": round(probability, 4),
            "p_breach_14d": round(within[14], 4), "p_breach_30d": round(within[30], 4),
            "days_to_breach": _quantile(sorted(days), 0.5),
            "expected_shortfall_minor": int(sum(shortfalls) / runs),
            "worst_shortfall_minor": _quantile(shortfalls, 0.95),
            "tier": tier, "top_driver": driver, "intervention": _intervention(tier, driver, within[14])}


def _summary(rows, key=None):
    """Aggregates over rows; ``key`` selects a stressed sub-dict instead of the baseline fields."""
    get = (lambda row: row[key]) if key else (lambda row: row)
    tiers = Counter(get(row)["tier"] for row in rows)
    shortfall, sector_tier, currency_tier = {}, {}, {}
    for row in rows:
        values = get(row)
        shortfall[row["currency"]] = shortfall.get(row["currency"], 0) + values["expected_shortfall_minor"]
        sector_tier.setdefault(row["sector"], {tier: 0 for tier in TIERS})[values["tier"]] += 1
        currency_tier.setdefault(row["currency"], {tier: 0 for tier in TIERS})[values["tier"]] += 1
    return {"smes": len(rows), "tiers": {tier: tiers.get(tier, 0) for tier in TIERS},
            "expected_shortfall_by_currency_minor": dict(sorted(shortfall.items())),
            "at_risk_within_14d": sum(1 for row in rows if get(row)["p_breach_14d"] >= AMBER_THRESHOLD),
            "at_risk_within_30d": sum(1 for row in rows if get(row)["p_breach_30d"] >= AMBER_THRESHOLD),
            "mean_breach_probability": round(statistics.fmean(get(row)["breach_probability"] for row in rows), 4),
            "sector_tier": dict(sorted(sector_tier.items())), "currency_tier": dict(sorted(currency_tier.items()))}


# ---------------------------------------------------------------------------
# Realised futures and backtest


def _realise(prep, outcome_seed):
    """One realised future from the generative process with an independent seed (not the radar's draws)."""
    sme = prep["sme"]
    rng = random.Random(stable_seed(outcome_seed, sme["sme_id"], OUTCOME_SALT))
    customers = sme["truth"]["_customers"]
    opening = date.fromisoformat(OPENING_DATE)
    net = prep["fixed"][:]
    fallbacks = 0
    for _customer, amount, _expected, due, _minimum, _probs, _floor, invoice_id in prep["uncertain"]:
        meta = sme["truth"][invoice_id]
        customer = customers[meta["customer"]]
        due_date = opening + timedelta(days=due)
        earliest = -due                           # still unpaid at the opening date: paid on or after it
        for _ in range(CONDITIONED_DRAW_TRIES):
            delay = _true_delay(rng, customer, amount, due_date, meta["index"])
            if delay >= earliest:
                break
        else:
            fallbacks += 1
            delay = earliest + int(rng.random() * 15)
        offset = due + delay
        if 0 <= offset < prep["length"]:
            net[offset] += amount
    if rng.random() < UNEXPECTED_EXPENSE_CHANCE:
        net[int(rng.random() * prep["length"])] -= int(sme["monthly_payroll_minor"] * rng.uniform(0.1, 0.4))
    breached = min(accumulate(net, initial=prep["opening"])) < prep["reserve"]
    return breached, fallbacks


def _metrics(scores, outcomes, flags=None, probabilities=None):
    result = {"auc": auc(list(zip(scores, outcomes)))}
    if probabilities is not None:
        result["brier"] = round(statistics.fmean((p - y) ** 2 for p, y in zip(probabilities, outcomes)), 4)
    if flags is not None:
        tp = sum(1 for f, y in zip(flags, outcomes) if f and y)
        fp = sum(1 for f, y in zip(flags, outcomes) if f and not y)
        fn = sum(1 for f, y in zip(flags, outcomes) if not f and y)
        result.update({"flagged": tp + fp, "true_positives": tp,
                       "red_precision": round(tp / (tp + fp), 4) if tp + fp else None,
                       "red_recall": round(tp / (tp + fn), 4) if tp + fn else None})
    return result


def backtest_rows(preps, assessed, outcome_seed):
    """Per-SME (radar probability, baselines, realised outcome)."""
    rows = []
    for prep, assessment in zip(preps, assessed):
        breached, fallbacks = _realise(prep, outcome_seed)
        payroll = prep["sme"]["monthly_payroll_minor"]
        rows.append({"sme_id": prep["sme"]["sme_id"], "p": assessment["breach_probability"],
                     "red": assessment["tier"] == "red", "breached": breached, "fallbacks": fallbacks,
                     "scheduled_score": (prep["reserve"] - prep["scheduled_minimum"]) / payroll,
                     "scheduled_breach": prep["scheduled_breach"],
                     "cash_ratio_score": -prep["opening"] / payroll})
    return rows


def backtest_metrics(rows):
    outcomes = [1 if row["breached"] else 0 for row in rows]
    prevalence = statistics.fmean(outcomes) if outcomes else 0.0
    probabilities = [row["p"] for row in rows]
    return {"n": len(rows), "breached": sum(outcomes), "prevalence": round(prevalence, 4),
            "radar": _metrics(probabilities, outcomes, [row["red"] for row in rows], probabilities),
            "baseline_scheduled_projection": _metrics([row["scheduled_score"] for row in rows], outcomes,
                                                      [row["scheduled_breach"] for row in rows],
                                                      [1.0 if row["scheduled_breach"] else 0.0 for row in rows]),
            "baseline_cash_to_payroll": _metrics([row["cash_ratio_score"] for row in rows], outcomes),
            "brier_climatology": round(prevalence * (1 - prevalence), 4),
            "conditioned_draw_fallbacks": sum(row["fallbacks"] for row in rows)}


BACKTEST_METHOD = ("For every SME one realised 60-day future is drawn from the generative payment process "
                   "(customer personality, invoice size, month-end, terms, trend and tail delays) with an independent "
                   "seed, plus a 15% chance of an unexpected expense the radar cannot see. A breach is any day below the "
                   "reserve floor. The radar's breach probability is scored with ROC AUC and Brier score and its red tier "
                   "with precision/recall, against (a) the deterministic scheduled projection (every invoice paid on its "
                   "due date; score = reserve minus scheduled minimum cash, per month of payroll; red = scheduled breach) "
                   "and (b) the opening cash-to-payroll ratio. Synthetic, in-distribution for TidePay: not real-world "
                   "validation.")


# ---------------------------------------------------------------------------
# Public radar


@lru_cache(maxsize=4)
def _state(n, seed, runs):
    """Generated portfolio, prepared events and baseline simulations (internal, never mutated)."""
    preps = [_prepare(sme) for sme in generate_portfolio(n, seed)]
    sims = [_simulate(prep, runs, stable_seed(seed, prep["sme"]["sme_id"], "radar")) for prep in preps]
    return preps, sims, [_assess(prep, sim) for prep, sim in zip(preps, sims)]


def _row(prep, assessment):
    sme = prep["sme"]
    payroll = sme["monthly_payroll_minor"]
    return {"sme_id": sme["sme_id"], "name": sme["name"], "sector": sme["sector"], "country": sme["country"],
            "currency": sme["currency"], "synthetic": True,
            "opening_cash_minor": prep["opening"], "reserve_floor_minor": prep["reserve"],
            "monthly_payroll_minor": payroll, "cash_to_payroll": round(prep["opening"] / payroll, 2),
            "open_receivables_minor": prep["open_receivables"], "customers": len(prep["customers"]),
            "scheduled_breach": prep["scheduled_breach"],
            "scheduled_headroom_minor": prep["scheduled_minimum"] - prep["reserve"],
            **assessment}


@lru_cache(maxsize=64)
def _radar_json(n, seed, runs, delay_days, sector, outcome_seed):
    preps, sims, assessed = _state(n, seed, runs)
    rows = [_row(prep, assessment) for prep, assessment in zip(preps, assessed)]
    shock = None
    if delay_days:
        migration = {before: {after: 0 for after in TIERS} for before in TIERS}
        newly = []
        for prep, row in zip(preps, rows):
            in_scope = sector == "all" or row["sector"] == sector
            if in_scope:
                stressed = _assess(prep, _simulate(prep, runs, stable_seed(seed, row["sme_id"], "radar"), delay_days))
            else:
                stressed = {key: row[key] for key in ("breach_probability", "p_breach_14d", "p_breach_30d",
                                                      "days_to_breach", "expected_shortfall_minor",
                                                      "worst_shortfall_minor", "tier", "top_driver", "intervention")}
            row["stressed"] = {**stressed, "in_scope": in_scope}
            migration[row["tier"]][stressed["tier"]] += 1
            if TIER_ORDER[stressed["tier"]] > TIER_ORDER[row["tier"]]:
                newly.append({"sme_id": row["sme_id"], "name": row["name"], "sector": row["sector"],
                              "currency": row["currency"], "before_tier": row["tier"], "after_tier": stressed["tier"],
                              "before_probability": row["breach_probability"],
                              "after_probability": stressed["breach_probability"]})
        newly.sort(key=lambda item: (-item["after_probability"], item["sme_id"]))
        shock = {"customer_delay_days": delay_days, "sector": sector,
                 "description": f"Every open customer payment{'' if sector == 'all' else f' to {sector} SMEs'} arrives "
                                f"{delay_days} days later than it otherwise would (same random draws as the baseline).",
                 "migration": migration, "newly_at_risk": newly, "summary_after": _summary(rows, "stressed")}
    ranked = sorted(rows, key=lambda row: (-row["breach_probability"],
                                           -row["expected_shortfall_minor"] / row["monthly_payroll_minor"], row["sme_id"]))
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank
    backtest = backtest_metrics(backtest_rows(preps, assessed, outcome_seed))
    backtest.update({"outcome_seed": outcome_seed, "method": BACKTEST_METHOD})
    result = {
        "synthetic": True, "label": LABEL, "version": PORTFOLIO_VERSION,
        "generated": {"smes": n, "seed": seed, "runs": runs, "opening_date": OPENING_DATE,
                      "horizon_days": HORIZON_DAYS, "end_date": TARGET_DATE,
                      "markets": [{"country": c, "currency": cur} for c, cur, _ in MARKETS], "sectors": list(SECTORS)},
        "thresholds": {"red_at_least": RED_THRESHOLD, "amber_at_least": AMBER_THRESHOLD,
                       "at_risk_window_probability": AMBER_THRESHOLD, "at_risk_windows_days": list(AT_RISK_WINDOWS)},
        "method": ("Seeded Monte Carlo per SME over open-invoice payment dates using TidePay lateness probabilities "
                   "(one shared draw per customer per future; overdue invoices only draw delays at least as long as "
                   "their current lateness). Payroll, rent and supplier bills are fixed. Breach = any day below the "
                   "SME's reserve floor in the 60-day horizon."),
        "smes": ranked, "summary": _summary(rows), "shock": shock, "backtest": backtest,
        "security": {"tenant_data_read": False, "store_access": False, "executable_actions": False,
                     "credit_decision": False},
        "limits": ["Synthetic portfolio only; not validated on real SME or lender data.",
                   "Not a credit decision or a credit score; interventions are advisory text only.",
                   "Only customer payment timing is uncertain in the radar; costs and new sales are fixed assumptions.",
                   "Ledgers include confirmed billing up to day 30; later sales are not modelled, so late-horizon "
                   "risk is conservative.",
                   "Expected shortfall totals are per currency and never summed across currencies."]}
    return json.dumps(result, sort_keys=True, separators=(",", ":"))


def radar(shock=None, seed=DEFAULT_SEED, n=DEFAULT_SIZE, runs=DEFAULT_RUNS, outcome_seed=None):
    """Lender-side early-warning radar over the synthetic portfolio.  Plain JSON-serialisable dict out."""
    _check_size(n, seed, runs)
    delay_days, sector = validate_shock(shock)
    if outcome_seed is None:
        outcome_seed = stable_seed(seed, OUTCOME_SALT) % (2 ** 31)
    _whole(outcome_seed, "outcome_seed", 0, 2 ** 31 - 1)
    if not delay_days:
        sector = "all"
    return json.loads(_radar_json(n, seed, runs, delay_days, sector, outcome_seed))


def backtest(seed=DEFAULT_SEED, n=DEFAULT_SIZE, runs=DEFAULT_RUNS, outcome_seed=None, include_rows=False):
    """Backtest one synthetic portfolio against one independently drawn realised future per SME."""
    _check_size(n, seed, runs)
    if outcome_seed is None:
        outcome_seed = stable_seed(seed, OUTCOME_SALT) % (2 ** 31)
    _whole(outcome_seed, "outcome_seed", 0, 2 ** 31 - 1)
    preps, _sims, assessed = _state(n, seed, runs)
    rows = backtest_rows(preps, assessed, outcome_seed)
    result = {**backtest_metrics(rows), "seed": seed, "outcome_seed": outcome_seed, "runs": runs,
              "synthetic": True, "method": BACKTEST_METHOD}
    if include_rows:
        result["rows"] = rows
    return result


def clear_cache():
    _state.cache_clear()
    _radar_json.cache_clear()
