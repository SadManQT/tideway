"""Explainable analytics: payment behaviour, stress tests, early warnings and KPIs.

Everything here is deterministic for a given snapshot.  Monte Carlo runs use
a seed derived from the business snapshot and only ``Random.random()`` (the
one stream Python guarantees across versions), so the same records always
give the same probabilities and tests can assert exact values.
"""
from __future__ import annotations

import difflib
import hashlib
import math
import random
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

from .domain import OPEN_INVOICE_STATUSES, SETTLED_INVOICE_STATUSES, add_days, days_between, human_date
from .projection import build_events, horizon_end


PRIOR_WEIGHT = 5             # credibility weight k: own history counts n/(n+k)
DEFAULT_DELAYS = (0, 3, 7, 10, 14)   # only when a business has no payment history at all
GRADES = (("A", 2), ("B", 7), ("C", 15))
OVERDUE_FALLBACK_DAYS = 7    # extra wait assumed when an overdue invoice is later than all history


def _percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    index = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def _pick(rng, items):
    return items[int(rng.random() * len(items))]


def _histories(invoices, as_of=None):
    history = defaultdict(list)
    for row in invoices:
        if (row["status"] in SETTLED_INVOICE_STATUSES and row.get("paid_date")
                and (as_of is None or row["paid_date"] <= as_of)):
            history[row["customer"]].append(days_between(row["due_date"], row["paid_date"]))
    return history


def customer_profiles(invoices, as_of=None):
    """Per-customer lateness from settled invoices, pooled with the portfolio.

    days_late = paid_date - due_date.  A customer's own history gets weight
    n/(n+k) (Buhlmann credibility); the rest comes from the business-wide
    history, so one lucky payment never makes a customer look perfectly reliable.
    """
    history = _histories(invoices, as_of)
    pool = [value for values in history.values() for value in values]
    prior_mean = statistics.fmean(pool) if pool else statistics.fmean(DEFAULT_DELAYS)
    open_exposure, open_count = defaultdict(int), Counter()
    oldest_overdue = defaultdict(int)
    for row in invoices:
        if row["status"] in OPEN_INVOICE_STATUSES:
            open_exposure[row["customer"]] += row["amount_minor"]
            open_count[row["customer"]] += 1
            if as_of and row["due_date"] < as_of:
                oldest_overdue[row["customer"]] = max(oldest_overdue[row["customer"]], days_between(row["due_date"], as_of))
    profiles = {}
    for customer in sorted(set(history) | set(open_exposure)):
        values = history.get(customer, [])
        n = len(values)
        weight = n / (n + PRIOR_WEIGHT)
        shrunk = (sum(values) + PRIOR_WEIGHT * prior_mean) / (n + PRIOR_WEIGHT)
        grade = next((label for label, limit in GRADES if shrunk <= limit), "D")
        mixture = values + (pool or list(DEFAULT_DELAYS))
        own = f"{n} settled invoice{'s' if n != 1 else ''}, average {statistics.fmean(values):.1f} days late" if values \
            else "no settled history yet"
        profiles[customer] = {
            "customer": customer, "settled_invoices": n,
            "mean_days_late": round(statistics.fmean(values), 1) if values else None,
            "median_days_late": statistics.median(values) if values else None,
            "on_time_rate": round(sum(1 for value in values if value <= 0) / n, 2) if n else None,
            "expected_delay_days": max(0, round(shrunk)), "own_history_weight": round(weight, 2),
            "p80_delay_days": max(0, _percentile(mixture, 0.8) or 0),
            "p90_delay_days": max(0, _percentile(mixture, 0.9) or 0),
            "grade": grade, "confidence": "low" if n < 3 else "medium" if n < 8 else "high",
            "open_invoices": open_count[customer], "open_exposure_minor": open_exposure[customer],
            "days_overdue": oldest_overdue.get(customer, 0),
            "explanation": f"{own}; weighted {round(weight * 100)}% own history, {round((1 - weight) * 100)}% "
                           f"business-wide average of {prior_mean:.1f} days.",
        }
    return {"customers": profiles, "portfolio_mean_days_late": round(prior_mean, 1),
            "history_observations": len(pool), "prior_weight": PRIOR_WEIGHT}


# ---- TidePay: the trained payment-delay model ----------------------------------

SAMPLE_RANGES = ((0, 0), (1, 7), (8, 15), (16, 30), (31, 60))  # days late used when sampling each bucket
_MODEL = None


def tidepay_model():
    global _MODEL
    if _MODEL is None:
        from .ml.model import load
        _MODEL = load(Path(__file__).with_name("ml") / "tidepay_model.json")
    return _MODEL


def delay_quantile(probs, u):
    """Inverse CDF of the bucket distribution, uniform within each bucket's day range."""
    cumulative = 0.0
    for p, (low, high) in zip(probs, SAMPLE_RANGES):
        if p > 0 and u <= cumulative + p:
            share = (u - cumulative) / p
            return low + round(share * (high - low))
        cumulative += p
    return SAMPLE_RANGES[-1][1]


def delay_cdf(probs, days):
    cumulative = 0.0
    for p, (low, high) in zip(probs, SAMPLE_RANGES):
        if days >= high:
            cumulative += p
        elif days >= low:
            cumulative += p * (days - low + 1) / (high - low + 1)
    return min(1.0, cumulative)


def tidepay_predictions(invoices, as_of):
    """TidePay forecast for every open invoice, from history settled on or before ``as_of``."""
    from datetime import date as _date
    from .ml.model import predict_for
    model = tidepay_model()
    settled = [row for row in invoices if row["status"] in SETTLED_INVOICE_STATUSES and row.get("paid_date")
               and row["paid_date"] <= as_of]
    portfolio = statistics.fmean(days_between(r["due_date"], r["paid_date"]) for r in settled) if settled else 5.0
    result = {}
    for row in invoices:
        if row["status"] not in OPEN_INVOICE_STATUSES:
            continue
        history = sorted(({"delay": days_between(r["due_date"], r["paid_date"]), "amount": r["amount_minor"] / 100,
                           "paid_date": r["paid_date"]} for r in settled if r["customer"] == row["customer"]),
                         key=lambda item: item["paid_date"])
        terms = max(1, days_between(row["issue_date"], row["due_date"]))
        prediction = predict_for(model, history, row["amount_minor"] / 100, terms,
                                 _date.fromisoformat(row["due_date"]), portfolio)
        probs = prediction["probabilities"]
        prediction.update({"invoice_id": row["id"], "customer": row["customer"], "history_used": len(history),
                           "likely_delay_days": max(0, round(prediction["expected_delay_days"])),
                           "p80_delay_days": delay_quantile(probs, 0.8)})
        result[row["id"]] = prediction
    return result


def scenario_dates(invoices, profiles, mode, predictions=None):
    """Payment dates for open invoices: 'likely' = TidePay expected delay, 'stress' = its 80th percentile.

    Falls back to the credibility-weighted customer profile only if no model prediction exists.
    """
    customers = profiles["customers"]
    result = {}
    for row in invoices:
        if row["status"] not in OPEN_INVOICE_STATUSES:
            continue
        prediction = (predictions or {}).get(row["id"])
        if prediction:
            delay = prediction["likely_delay_days" if mode == "likely" else "p80_delay_days"]
        else:
            profile = customers.get(row["customer"])
            delay = profile["expected_delay_days" if mode == "likely" else "p80_delay_days"] if profile else 0
        result[row["id"]] = max(row["expected_collection_date"], add_days(row["due_date"], delay))
    return result


def _delay_sampler(invoices, as_of):
    """Sample a customer's lateness; overdue invoices are conditioned on still being unpaid."""
    history = {customer: [max(0, value) for value in values] for customer, values in _histories(invoices, as_of).items()}
    pool = sorted(value for values in history.values() for value in values) or list(DEFAULT_DELAYS)

    def sample(rng, customer, minimum_late):
        own = history.get(customer, [])
        source = own if own and rng.random() < len(own) / (len(own) + PRIOR_WEIGHT) else pool
        eligible = [value for value in source if value >= minimum_late]
        if not eligible:
            return minimum_late + OVERDUE_FALLBACK_DAYS
        return _pick(rng, eligible)
    return sample


def stable_seed(*parts):
    return int(hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()[:12], 16)


def liquidity_gap(minimums, reserve, risk_target=.1):
    """Smallest opening-cash top-up reaching a target on these sampled paths.

    A constant cash addition shifts every daily balance by exactly that amount.
    This is a read-only counterfactual, never evidence that funding is available.
    A separate set of draws is needed to evaluate a selected amount.
    """
    if (not minimums or type(reserve) is not int or reserve < 0
            or any(type(value) is not int for value in minimums)
            or isinstance(risk_target, bool) or not isinstance(risk_target, (int, float))
            or not math.isfinite(risk_target) or not 0 <= risk_target < 1):
        raise ValueError("Invalid liquidity diagnostic inputs.")
    needs = sorted(max(0, reserve - minimum) for minimum in minimums)
    fraction = Fraction(str(risk_target)) * len(needs)
    allowed = fraction.numerator // fraction.denominator
    buffer = needs[len(needs) - allowed - 1]
    breaches = sum(need > buffer for need in needs)
    return {"additional_cash_minor": buffer, "risk_target": risk_target,
            "sample_runs": len(needs), "sample_breaches_after": breaches,
            "sample_probability_breach_after": breaches / len(needs),
            "breaches_with_one_minor_less": sum(need > buffer - 1 for need in needs) if buffer else None,
            "funding_confirmed": False, "executable": False,
            "assumption": "Additional confirmed cash is available at the opening date and remains in the business; all other timing, costs and obligations stay unchanged.",
            "limitation": "Minimum on these simulated paths only; excludes model error and funding costs. Confirm availability and rerun on fresh draws before relying on the amount."}


def monte_carlo(business, policy, records, target_date, adjustments=(), promises=None,
                runs=1000, seed=0, lookahead_days=0, as_of=None):
    """Probability of breaching the reserve floor under payment-timing uncertainty.

    Only the timing of open customer invoices is uncertain; every other event
    (payroll, bills, agreed adjustments) is fixed.  One delay is drawn per
    customer per simulated future, so a slow customer is slow on all its
    invoices (the cautious choice).  No invoice is paid before its expected date.
    """
    as_of = as_of or business["opening_date"]
    end = horizon_end(business, target_date, lookahead_days)
    events, _ = build_events(business, records, end, adjustments, promises=promises)
    start = business["opening_date"]
    length = days_between(start, end) + 1
    fixed = [0] * length
    payroll_index = set()
    uncertain = []
    invoices = {row["id"]: row for row in records["invoices"]}
    for event in events:
        index = days_between(start, event["date"])
        if event["kind"] == "invoice":
            row = invoices[event["id"]]
            minimum_late = max(0, days_between(row["due_date"], as_of))
            uncertain.append((event["id"], event["amount_minor"], event["date"], row["due_date"], row["customer"], minimum_late))
        else:
            fixed[index] += event["effect_minor"]
            if event.get("payroll"):
                payroll_index.add(index)
    predictions = tidepay_predictions(records["invoices"], as_of)
    fallback = _delay_sampler(records["invoices"], as_of)

    def sample(local, invoice_id, customer, minimum_late, u):
        prediction = predictions.get(invoice_id)
        if not prediction:
            return fallback(local, customer, minimum_late)
        probs = prediction["probabilities"]
        floor = delay_cdf(probs, minimum_late - 1) if minimum_late > 0 else 0.0  # still unpaid today
        return max(minimum_late, delay_quantile(probs, floor + u * (1 - floor)))
    rng = random.Random(seed)
    reserve = policy["reserve_floor_minor"]
    # Keep the random stream aligned when comparing bundles. An early-payment
    # agreement removes an uncertain event, but must not give every remaining
    # customer a different draw merely by changing this event set. Include all
    # open-record customers even when an agreement fixes their receipt date or
    # their expected receipt falls outside the current horizon.
    customers = sorted({row["customer"] for row in records["invoices"]
                        if row["status"] in OPEN_INVOICE_STATUSES})
    columns = [[] for _ in range(length)]
    breaches = negatives = payroll_failures = 0
    shortfalls, minimums, first_breaches = [], [], Counter()
    late_after = Counter()
    for _ in range(runs):
        draws = {customer: rng.random() for customer in customers}
        net = fixed[:]
        arrivals = {}
        for invoice_id, amount, expected, due, customer, minimum_late in uncertain:
            local = random.Random(int(draws[customer] * 2 ** 53))
            paid = max(expected, add_days(due, sample(local, invoice_id, customer, minimum_late, draws[customer])))
            arrivals[invoice_id] = paid
            offset = days_between(start, paid)
            if offset < length:
                net[offset] += amount
        balance = business["opening_cash_minor"]
        minimum, breach_day, payroll_failed = balance, start if balance < reserve else None, False
        for index, change in enumerate(net):
            balance += change
            columns[index].append(balance)
            if balance < minimum:
                minimum = balance
            if balance < reserve and breach_day is None:
                breach_day = (date.fromisoformat(start) + timedelta(days=index)).isoformat()
            if index in payroll_index and balance < 0:
                payroll_failed = True
        minimums.append(minimum)
        if breach_day:
            breaches += 1
            shortfalls.append(reserve - minimum)
            first_breaches[breach_day] += 1
            for invoice_id, paid in arrivals.items():
                if paid > breach_day:
                    late_after[invoice_id] += 1
        negatives += minimum < 0
        payroll_failures += payroll_failed
    fan = []
    for index, values in enumerate(columns):
        day = (date.fromisoformat(start) + timedelta(days=index)).isoformat()
        fan.append({"date": day, "p10_minor": _percentile(values, 0.1),
                    "p50_minor": _percentile(values, 0.5), "p90_minor": _percentile(values, 0.9)})
    probability = breaches / runs
    return {"runs": runs, "seed": seed, "uncertain_invoices": len(uncertain), "end_date": end,
            "probability_breach": round(probability, 4),
            "futures_short_of_20": round(probability * 20),
            "probability_negative_cash": round(negatives / runs, 4),
            "probability_payroll_unfunded": round(payroll_failures / runs, 4),
            "expected_shortfall_if_breach_minor": int(statistics.fmean(shortfalls)) if shortfalls else 0,
            "p90_shortfall_minor": _percentile(shortfalls, 0.9) or 0,
            "minimum_cash_p10_minor": _percentile(minimums, 0.1),
            "minimum_cash_p50_minor": _percentile(minimums, 0.5),
            "liquidity_gap": liquidity_gap(minimums, reserve),
            "most_common_breach_date": first_breaches.most_common(1)[0][0] if first_breaches else None,
            "invoice_late_share": {invoice_id: round(count / runs, 3) for invoice_id, count in sorted(late_after.items())},
            "fan": fan,
            "method": "Seeded Monte Carlo over open-invoice payment dates. Each invoice's lateness is drawn from TidePay, "
                      "Tideway's own federated-trained model; one shared draw per customer per future, so a slow customer "
                      "is slow on all its invoices. Overdue invoices only draw delays at least as long as their current "
                      "lateness. All other events are fixed. Estimates from synthetic data, not a guarantee."}


def weather(probability_breach, scheduled_shortfall):
    if scheduled_shortfall > 0 or probability_breach >= 0.5:
        return {"label": "Storm", "level": "storm",
                "text": "A reserve breach is scheduled or more likely than not. Act before the first breach date."}
    if probability_breach >= 0.15:
        return {"label": "Unsettled", "level": "unsettled",
                "text": "Late customer payments could push cash below the reserve floor."}
    return {"label": "Clear", "level": "clear", "text": "The reserve floor holds in almost every simulated future."}


def apr_bps(cost_minor, principal_minor, days):
    """Simple annualised cost in basis points: cost / principal x 365 / days."""
    if principal_minor <= 0 or days <= 0:
        return None
    return int(round(cost_minor / principal_minor * 365 / days * 10_000))


def discount_apr_bps(discount_bps, days_accelerated):
    """Annualised cost of an early-payment discount, d/(1-d) x 365/days (2/10 net 30 ~ 37%)."""
    if days_accelerated <= 0 or discount_bps <= 0:
        return None
    rate = discount_bps / 10_000
    return int(round(rate / (1 - rate) * 365 / days_accelerated * 10_000))


def mask_account(account):
    if not account:
        return None
    digits = account.replace(" ", "")
    return "•" * max(0, len(digits) - 4) + digits[-4:]


def payee_checks(bills, verified_accounts=None):
    """Bank-detail changes and look-alike payee names (business-email-compromise signals)."""
    verified_accounts = dict(verified_accounts or {})
    history = defaultdict(Counter)
    display_names = {}
    for row in bills:
        if row["status"] == "paid" and row.get("payee_account"):
            identity = row["payee"].casefold()
            display_names.setdefault(identity, row["payee"])
            history[identity][row["payee_account"]] += 1
    known = {display_names[identity]: counts.most_common(1)[0][0] for identity, counts in history.items()}
    known.update({payee: account for payee, account in verified_accounts.items() if account})
    # A capitalisation change must not turn an established supplier into an
    # unknown payee and bypass the changed-bank-account check. Aggregate its
    # paid history under the same case-insensitive identity; callback-verified
    # accounts override that history under the same identity too.
    known_by_identity = {identity: counts.most_common(1)[0][0] for identity, counts in history.items()}
    verified_by_identity = {payee.casefold(): account for payee, account in verified_accounts.items() if account}
    known_by_identity.update(verified_by_identity)
    established = sorted({row["payee"] for row in bills if row["status"] == "paid"})
    established_identities = {payee.casefold() for payee in established}
    flagged, lookalikes = [], []
    for row in bills:
        if row["status"] not in ("open", "scheduled", "rescheduled"):
            continue
        identity = row["payee"].casefold()
        reference = known_by_identity.get(identity)
        if reference and reference != row.get("payee_account"):
            missing = not row.get("payee_account")
            flagged.append({"bill_id": row["id"], "payee": row["payee"],
                            "expected_account": mask_account(reference), "new_account": mask_account(row.get("payee_account")),
                            "account": row.get("payee_account"),
                            "code": "account_missing" if missing else "account_changed",
                            "reason": ("Bank details are missing for an established supplier. Restore and verify the account "
                                       if missing else "Bank details differ from the account used or verified before. Verify ")
                                      + "by calling a number already on file before any action."})
        cleared = bool(row.get("payee_account")) and verified_by_identity.get(identity) == row["payee_account"]
        if identity not in established_identities and not cleared:
            for name in established:
                ratio = difflib.SequenceMatcher(None, row["payee"].casefold(), name.casefold()).ratio()
                if 0.85 <= ratio < 1:
                    lookalikes.append({"bill_id": row["id"], "payee": row["payee"], "account": row.get("payee_account"),
                                       "similar_to": name,
                                       "similarity": round(ratio, 2),
                                       "reason": "New payee name is almost identical to an established supplier."})
                    break
    return {"known_accounts": {payee: mask_account(account) for payee, account in known.items()},
            "flagged": flagged, "lookalikes": lookalikes}


def financial_kpis(business, records, profiles):
    """Business financial analysis (Topic E): DSO, days late, concentration and runway inputs."""
    settled = [row for row in records["invoices"] if row["status"] in SETTLED_INVOICE_STATUSES and row.get("paid_date")]
    open_rows = [row for row in records["invoices"] if row["status"] in OPEN_INVOICE_STATUSES]
    dso = statistics.fmean(days_between(row["issue_date"], row["paid_date"]) for row in settled) if settled else None
    terms = statistics.fmean(days_between(row["issue_date"], row["due_date"]) for row in settled) if settled else None
    paid_bills = [row for row in records["bills"] if row["status"] == "paid"]
    open_total = sum(row["amount_minor"] for row in open_rows)
    shares = [item["open_exposure_minor"] / open_total for item in profiles["customers"].values()
              if open_total and item["open_exposure_minor"]]
    hhi = round(10_000 * sum(share * share for share in shares)) if shares else None
    expenses = [row for row in records["transactions"] if row["type"] == "expense" and row["date"] < business["opening_date"]]
    months = {row["date"][:7] for row in expenses}
    burn = sum(row["amount_minor"] for row in expenses) // len(months) if months else None
    late = [days_between(row["due_date"], row["paid_date"]) for row in settled]
    return {"dso_days": round(dso, 1) if dso is not None else None,
            "average_terms_days": round(terms, 1) if terms is not None else None,
            "average_days_late": round(statistics.fmean(late), 1) if late else None,
            "on_time_share": round(sum(1 for value in late if value <= 0) / len(late), 2) if late else None,
            "open_receivables_minor": open_total,
            "open_payables_minor": sum(row["amount_minor"] for row in records["bills"] if row["status"] in ("open", "scheduled", "rescheduled")),
            "customer_hhi": hhi, "effective_customers": round(10_000 / hhi, 1) if hhi else None,
            "top_customer_share": round(max(shares), 2) if shares else None,
            "monthly_expense_run_rate_minor": burn,
            "settled_invoices": len(settled), "paid_bills": len(paid_bills),
            "notes": "DSO = average days from invoice issue to payment for settled invoices. HHI = 10,000 x sum of squared "
                     "customer shares of open receivables (concentration analogy only)."}


def backtest(invoices, as_of=None):
    """Leave-one-out check of the pooled delay estimate on settled invoices (illustrative)."""
    settled = [row for row in invoices if row["status"] in SETTLED_INVOICE_STATUSES and row.get("paid_date")
               and (as_of is None or row["paid_date"] <= as_of)]
    if len(settled) < 8:
        return {"available": False, "reason": "At least 8 settled invoices are needed for a backtest.", "n": len(settled)}
    errors, inside = [], 0
    for index, held in enumerate(settled):
        rest = settled[:index] + settled[index + 1:]
        profiles = customer_profiles(rest)
        profile = profiles["customers"].get(held["customer"])
        predicted = profile["expected_delay_days"] if profile else round(profiles["portfolio_mean_days_late"])
        actual = days_between(held["due_date"], held["paid_date"])
        errors.append(abs(actual - predicted))
        if profile and actual <= profile["p80_delay_days"]:
            inside += 1
    return {"available": True, "n": len(settled), "mean_absolute_error_days": round(statistics.fmean(errors), 1),
            "p80_coverage": round(inside / len(settled), 2),
            "note": "Leave-one-out on synthetic history: shows internal consistency, not real-world accuracy."}


def warnings(business, records, base_projection, stress, profiles, payee_report, kpis):
    """Early-warning signals, most severe first."""
    currency = business["currency"]
    result = []
    if base_projection["first_breach_date"]:
        days = days_between(business["opening_date"], base_projection["first_breach_date"])
        result.append({"severity": "critical", "code": "reserve_breach",
                       "title": f"Reserve breached in {days} day{'s' if days != 1 else ''}",
                       "detail": f"Scheduled cash falls below the reserve floor on {human_date(base_projection['first_breach_date'], True)}."})
    if base_projection["payroll_at_risk"]:
        result.append({"severity": "critical", "code": "payroll_at_risk", "title": "Payroll is not fully funded",
                       "detail": "Cash would be negative on a payroll day without action. Payroll is never deferred."})
    if payee_report["flagged"]:
        result.append({"severity": "critical", "code": "payee_account_changed",
                       "title": f"{len(payee_report['flagged'])} bill(s) with missing or changed bank details",
                       "detail": "Actions on these bills are blocked until the owner verifies the payee by callback."})
    if payee_report["lookalikes"]:
        item = payee_report["lookalikes"][0]
        result.append({"severity": "critical", "code": "lookalike_payee",
                       "title": f"Look-alike payee: '{item['payee']}'",
                       "detail": f"Almost identical to '{item['similar_to']}'. Possible impostor; actions are blocked."})
    flagged_text = sum(1 for kind in ("transactions", "invoices", "bills") for row in records[kind] if row.get("risk_flags"))
    if flagged_text:
        result.append({"severity": "warning", "code": "untrusted_text",
                       "title": f"{flagged_text} record(s) contain instruction-like or hidden text",
                       "detail": "Quarantined as data: the assistant never receives this text and it cannot change any action."})
    if stress["probability_breach"] >= 0.15 and not base_projection["first_breach_date"]:
        result.append({"severity": "warning", "code": "breach_probability",
                       "title": f"{stress['futures_short_of_20']} of 20 simulated futures breach the reserve",
                       "detail": "Based on customers' own payment history."})
    if kpis["top_customer_share"] and kpis["top_customer_share"] >= 0.5:
        top = max(profiles["customers"].values(), key=lambda item: item["open_exposure_minor"])
        result.append({"severity": "info", "code": "concentration",
                       "title": f"{round(kpis['top_customer_share'] * 100)}% of receivables depend on one customer",
                       "detail": f"{top['customer']} holds the largest open balance; a delay there moves the whole forecast."})
    overdue = [row for row in records["invoices"] if row["status"] == "overdue"]
    if overdue:
        total = sum(row["amount_minor"] for row in overdue)
        result.append({"severity": "warning", "code": "overdue", "title": f"{len(overdue)} overdue invoice(s)",
                       "detail": f"{currency} {total / 100:,.0f} is past due."})
    seen = {}
    for row in sorted(records["bills"], key=lambda item: item["due_date"]):
        if row["status"] not in ("open", "scheduled"):
            continue
        key = (row["payee"].casefold(), row["amount_minor"])
        if key in seen and abs(days_between(seen[key], row["due_date"])) <= 7:
            result.append({"severity": "warning", "code": "duplicate_bill", "title": f"Possible duplicate bill from {row['payee']}",
                           "detail": "Same payee and amount within seven days. Confirm before paying both."})
            break
        seen[key] = row["due_date"]
    expenses = [row for row in records["transactions"] if row["type"] == "expense"
                and str(row.get("category", "")).casefold() != "payroll"]
    if len(expenses) >= 8:
        amounts = [row["amount_minor"] for row in expenses]
        median = statistics.median(amounts)
        mad = statistics.median([abs(value - median) for value in amounts])
        if mad:
            unusual = [row for row in expenses if abs(0.6745 * (row["amount_minor"] - median) / mad) > 3.5]
            if unusual:
                result.append({"severity": "info", "code": "unusual_expense",
                               "title": f"{len(unusual)} unusually large expense(s)",
                               "detail": "Modified z-score above 3.5 against this business's own expense history."})
    order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(result, key=lambda item: order[item["severity"]])
