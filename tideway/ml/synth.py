"""Synthetic SME invoice histories for training and evaluating TidePay.

Real SME invoice data is not public, so we generate it, and say so. Each
business has customers with a latent payment personality (prompt, typical,
slow, distressed). Lateness also depends on invoice size relative to the
customer's usual order, payment terms, month-end crunches, festival months
(cash is tight around Eid in Bangladesh and the Spring Festival in China),
and the customer's own trend. The model never sees the personality; it has
to infer it from observable history, which is the real task.
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

PERSONALITIES = {
    # base mean delay, spread, chance of a long default-like delay
    "prompt": (0.5, 1.5, 0.01),
    "typical": (6.0, 4.0, 0.04),
    "slow": (16.0, 7.0, 0.10),
    "distressed": (28.0, 12.0, 0.25),
}
PERSONALITY_WEIGHTS = (("prompt", 0.30), ("typical", 0.40), ("slow", 0.20), ("distressed", 0.10))
FESTIVAL_MONTHS = {3, 4, 6, 2}  # illustrative months of tight cash (festival seasons)
SECTORS = ("services", "wholesale", "retail", "manufacturing", "print")


def _pick_personality(rng):
    roll, total = rng.random(), 0.0
    for name, weight in PERSONALITY_WEIGHTS:
        total += weight
        if roll <= total:
            return name
    return "typical"


def generate(n_businesses=12, seed=7, start=date(2024, 1, 1), months=22):
    """Return a list of businesses, each with customers and chronologically ordered invoices."""
    rng = random.Random(seed)
    businesses = []
    for b in range(n_businesses):
        sector = SECTORS[b % len(SECTORS)]
        n_customers = rng.randint(4, 14)
        customers = []
        for c in range(n_customers):
            personality = _pick_personality(rng)
            customers.append({"id": f"b{b}-c{c}", "personality": personality,
                              "typical_amount": rng.choice([8_000, 15_000, 25_000, 40_000, 70_000]),
                              "terms": rng.choice([15, 30, 30, 45, 60]),
                              "trend": rng.uniform(-0.15, 0.25),  # some customers get slower over time
                              "frequency": rng.uniform(0.6, 3.0)})  # invoices per month
        invoices = []
        for customer in customers:
            mean, spread, tail = PERSONALITIES[customer["personality"]]
            day = start + timedelta(days=rng.randint(0, 40))
            end = start + timedelta(days=30 * months)
            index = 0
            while day < end:
                amount = max(1_000, int(rng.lognormvariate(math.log(customer["typical_amount"]), 0.45)))
                due = day + timedelta(days=customer["terms"])
                size_ratio = amount / customer["typical_amount"]
                delay = rng.gauss(mean, spread)
                delay += 4.0 * max(0.0, size_ratio - 1.3)  # unusually large invoices are paid later
                delay += 3.0 if due.day >= 26 else 0.0       # month-end crunch
                delay += 5.0 if due.month in FESTIVAL_MONTHS else 0.0
                delay += customer["trend"] * index         # drifting behaviour
                delay += 0.08 * (customer["terms"] - 30)   # long terms, longer tails
                if rng.random() < tail:
                    delay += rng.uniform(20, 60)
                if customer["personality"] == "prompt" and rng.random() < 0.6:
                    delay = min(delay, 0.0)
                delay = max(-5, int(round(delay)))
                invoices.append({"business": b, "sector": sector, "customer": customer["id"],
                                 "issue_date": day, "due_date": due, "paid_date": due + timedelta(days=delay),
                                 "amount": amount, "terms": customer["terms"], "delay": delay,
                                 "personality": customer["personality"]})
                index += 1
                day += timedelta(days=max(3, int(rng.expovariate(customer["frequency"] / 30))))
        invoices.sort(key=lambda row: (row["issue_date"], row["customer"]))
        businesses.append({"business": b, "sector": sector, "customers": customers, "invoices": invoices})
    return businesses
