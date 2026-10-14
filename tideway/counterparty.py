"""Deterministic simulated counterparties for the sandbox.

Suppliers and customers are played by small rule-based agents so the
business agent's requests get realistic, repeatable answers: accept, a
counter-offer within the counterparty's own limits, or a refusal.  They are
clearly labelled simulations; no real supplier or customer is contacted.
"""
from __future__ import annotations

from .domain import add_days, days_between, human_date, money_text


AGENT_VERSION = "counterparty-sim-v1"
SUPPLIER_STYLES = {
    "flexible": {"max_deferral_days": 14, "max_share_pct": 100},
    "standard": {"max_deferral_days": 7, "max_share_pct": 100},
    "cautious": {"max_deferral_days": 7, "max_share_pct": 50},
    "strict": {"max_deferral_days": 0, "max_share_pct": 0},
}
DEFAULT_CUSTOMER = {"min_discount_bps": 200, "max_acceleration_days": 30, "typical_delay_days": 7}


def supplier_profile(profile):
    profile = dict(profile or {})
    style = profile.get("style", "standard")
    base = SUPPLIER_STYLES.get(style, SUPPLIER_STYLES["standard"])
    return {"style": style if style in SUPPLIER_STYLES else "standard", **base,
            **{key: profile[key] for key in ("max_deferral_days", "max_share_pct") if key in profile}}


def customer_profile(profile):
    return {**DEFAULT_CUSTOMER, **{key: value for key, value in dict(profile or {}).items() if key in DEFAULT_CUSTOMER}}


def respond(action, profile):
    """Return the simulated counterparty's reply to one requested action."""
    kind = action["type"]
    currency = action["currency"]
    name = action["counterparty"]
    reply = {"agent": AGENT_VERSION, "simulated": True, "counterparty": name, "action_id": action["action_id"]}
    if kind == "supplier_deferral":
        rules = supplier_profile(profile)
        if rules["max_deferral_days"] == 0 or rules["max_share_pct"] == 0:
            return {**reply, "status": "rejected", "counter_terms": None,
                    "message": f"{name}: We cannot move this payment. Please pay on {human_date(action['from_date'], True)}."}
        max_amount = action["bill_amount_minor"] * rules["max_share_pct"] // 100
        days = min(action["days"], rules["max_deferral_days"])
        amount = min(action["amount_minor"], max_amount)
        if days == action["days"] and amount == action["amount_minor"]:
            return {**reply, "status": "accepted", "counter_terms": None,
                    "message": f"{name}: Agreed. {money_text(amount, currency)} moves to {human_date(action['to_date'], True)}."}
        to_date = add_days(action["from_date"], days)
        return {**reply, "status": "countered",
                "counter_terms": {"amount_minor": amount, "days": days, "to_date": to_date},
                "message": f"{name}: We can move {money_text(amount, currency)} to {human_date(to_date, True)}, but not the full request."}
    if kind == "early_payment_offer":
        rules = customer_profile(profile)
        if action["days"] > rules["max_acceleration_days"]:
            return {**reply, "status": "rejected", "counter_terms": None,
                    "message": f"{name}: We cannot pay that early this month."}
        if action["discount_bps"] >= rules["min_discount_bps"]:
            return {**reply, "status": "accepted", "counter_terms": None,
                    "message": f"{name}: Accepted. We will pay {money_text(action['amount_minor'], currency)} by {human_date(action['to_date'], True)}."}
        return {**reply, "status": "countered", "counter_terms": {"discount_bps": rules["min_discount_bps"]},
                "message": f"{name}: We would pay early for a {rules['min_discount_bps'] / 100:.0f}% discount."}
    if kind == "collection_reminder":
        rules = customer_profile(profile)
        promised = add_days(action["from_date"], max(0, rules["typical_delay_days"]))
        return {**reply, "status": "acknowledged", "counter_terms": None, "promise_to_pay_date": promised,
                "message": f"{name}: Thanks for the reminder. We plan to pay on {human_date(promised, True)}.",
                "note": "A promise to pay is information, not cash. It is tracked, never counted as collected."}
    return {**reply, "status": "rejected", "counter_terms": None, "message": "Unsupported request."}


def promise_is_broken(promise_date, current_date, settled):
    return not settled and days_between(promise_date, current_date) > 0
