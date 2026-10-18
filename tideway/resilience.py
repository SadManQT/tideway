"""Bounded, read-only tests of a proposed recovery on the exact ledger engine."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import time

from . import analytics, planner
from .domain import OPEN_INVOICE_STATUSES, ValidationError, add_days, canonical_json
from .projection import project, summary

VERSION = "resilience-v1"
MAX_CUSTOMERS = 20


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValidationError(f"{name} must be an integer from {low} to {high}.")
    return value


class Context:
    def __init__(self, snapshot, target, payload=None, bundle_id=None):
        self.snapshot, self.target, self.payload = snapshot, target, payload
        self.business, self.policy, self.records, self.state = (snapshot[k] for k in ("business", "policy", "records", "state"))
        from .store import Store
        self.derived = Store.derived(snapshot)
        self.bundle = None
        if payload and payload.get("bundles"):
            self.bundle = next((b for b in payload["bundles"] if b["bundle_id"] == (bundle_id or payload["bundles"][0]["bundle_id"])), None)
            if self.bundle is None:
                raise ValidationError("Select a bundle from the current proposal.")
        elif bundle_id:
            raise ValidationError("A current proposal is required for that bundle.")
        self.adjustments = list(self.state["adjustments"]) + [a["adjustment"] for a in (self.bundle or {}).get("actions", [])]
        self.seed = analytics.stable_seed(snapshot["snapshot_hash"], target, "decision-lab-v1")

    def projection(self, delays=None, adjustments=None, cash=0):
        dates = dict(self.derived["likely_dates"])
        moved = deepcopy(self.adjustments if adjustments is None else adjustments)
        by_id = {r["id"]: r for r in self.records["invoices"]}
        for row in self.records["invoices"]:
            if row["status"] in OPEN_INVOICE_STATUSES and row["customer"] in (delays or {}):
                baseline_date = max(dates.get(row["id"], row["expected_collection_date"]),
                                    self.state["promises"].get(row["id"], row["expected_collection_date"]),
                                    self.business["opening_date"])
                dates[row["id"]] = add_days(baseline_date, delays[row["customer"]])
        for item in moved:
            if item["kind"] == "invoice_early_payment":
                customer = by_id[item["invoice_id"]]["customer"]
                item["to_date"] = add_days(item["to_date"], (delays or {}).get(customer, 0))
        return project({**self.business, "opening_cash_minor": self.business["opening_cash_minor"] + cash},
                       self.policy, self.records, self.target, moved, scenario="likely", invoice_dates=dates,
                       promises=self.state["promises"], lookahead_days=self.policy["lookahead_days"])

    def simulation(self, *, adjustments=None, cash=0, seed=None, runs=1000, **kwargs):
        return analytics.monte_carlo({**self.business, "opening_cash_minor": self.business["opening_cash_minor"] + cash},
                                    self.policy, self.records, self.target, self.adjustments if adjustments is None else adjustments,
                                    self.state["promises"], runs=runs, seed=self.seed if seed is None else seed,
                                    lookahead_days=self.policy["lookahead_days"], as_of=self.state["current_date"], **kwargs)

    def envelope(self, result):
        return {"version": VERSION, "business_id": self.business["business_id"], "currency": self.business["currency"],
                "snapshot_hash": self.snapshot["snapshot_hash"], "target_date": self.target,
                "plan_id": (self.payload or {}).get("plan_id"), "bundle_id": (self.bundle or {}).get("bundle_id"),
                "read_only": True, "executed": False, **result}


def reverse_stress(context, max_days=30):
    max_days = integer(max_days, "Maximum delay", 1, 60)
    started = time.perf_counter()
    baseline = context.projection()
    names = sorted({r["customer"] for r in context.records["invoices"] if r["status"] in OPEN_INVOICE_STATUSES})
    rows, evaluations = [], 1
    for customer in names[:MAX_CUSTOMERS]:
        def check(days):
            nonlocal evaluations
            evaluations += 1
            return context.projection({customer: days})
        if baseline["reserve_shortfall_minor"] or baseline["payroll_at_risk"]:
            days, failed, witness = 0, baseline, None
        else:
            failed = check(max_days)
            if not failed["reserve_shortfall_minor"] and not failed["payroll_at_risk"]:
                rows.append({"customer": customer, "minimum_delay_days": None, "tested_through_days": max_days,
                             "status": "holds_within_tested_bound", "after": summary(failed)})
                continue
            low, high = 1, max_days
            while low < high:
                middle = (low + high) // 2
                value = check(middle)
                if value["reserve_shortfall_minor"] or value["payroll_at_risk"]:
                    high = middle
                else:
                    low = middle + 1
            days, failed, witness = low, check(low), check(low - 1)
        rows.append({"customer": customer, "minimum_delay_days": days, "status": "already_breaches" if days == 0 else "breakpoint_found",
                     "after": summary(failed), "one_day_less": summary(witness) if witness else None,
                     "invoice_ids": [r["id"] for r in context.records["invoices"] if r["customer"] == customer and r["status"] in OPEN_INVOICE_STATUSES]})
    rows.sort(key=lambda row: (row["minimum_delay_days"] is None, row["minimum_delay_days"] or 0, row["customer"]))
    return context.envelope({"kind": "reverse_stress", "baseline": summary(baseline), "rows": rows,
                             "customers_total": len(names), "customers_tested": len(rows), "complete_customer_coverage": len(names) <= MAX_CUSTOMERS,
                             "projection_evaluations": evaluations, "elapsed_ms": round((time.perf_counter() - started) * 1000),
                             "scope": "Smallest integer delay for one customer at a time, with all other likely receipts fixed; simultaneous shocks and model error are not covered."})


def promise_stress(context, delay_days=7):
    delay_days = integer(delay_days, "Agreement delay", 1, 60)
    count = sum(a["kind"] == "invoice_early_payment" for a in context.adjustments)
    rows = []
    for bps in (0, 1000, 2500, 5000, 10000):
        simulation = context.simulation(agreement_failure_bps=bps, agreement_delay_days=delay_days)
        rows.append({"assumed_failure_bps": bps, "probability_breach": simulation["probability_breach"],
                     "probability_payroll_unfunded": simulation["probability_payroll_unfunded"],
                     "minimum_cash_p10_minor": simulation["minimum_cash_p10_minor"], "runs": simulation["runs"]})
    return context.envelope({"kind": "promise_stress", "agreements_tested": count, "delay_days": delay_days,
                             "rows": rows, "seed": context.seed, "failure_rates_are_assumptions": True,
                             "scope": "Assumed late performance of accepted early-payment agreements; correlated within customer, not an observed reliability score or default-loss model. Reminder promises never become collected cash."})


def recovery_frontier(context):
    choices = [{"bundle_id": "no-action", "actions": [], "economic_cost_minor": 0}]
    choices += list((context.payload or {}).get("bundles", []))
    rows = []
    for bundle in choices:
        adjustments = context.state["adjustments"] + [a["adjustment"] for a in bundle["actions"]]
        simulation = context.simulation(adjustments=adjustments)
        projection = context.projection(adjustments=adjustments)
        cash = simulation["liquidity_gap"]["additional_cash_minor"]
        fresh = context.simulation(adjustments=adjustments, cash=cash, seed=analytics.stable_seed(context.seed, "cash-validation"))
        rows.append({"bundle_id": bundle["bundle_id"], "actions": [{k: a[k] for k in ("type", "counterparty", "amount_minor", "from_date", "to_date")} for a in bundle["actions"]],
                     "cost_minor": bundle["economic_cost_minor"], "probability_breach": simulation["probability_breach"],
                     "likely": summary(projection), "additional_opening_cash_minor": cash,
                     "conditional_funded_probability_breach": fresh["probability_breach"], "funding_confirmed": False,
                     "selection_seed": context.seed, "validation_seed": fresh["seed"], "runs_each": simulation["runs"],
                     "fresh_approval_required": bool(bundle["actions"]), "consents_required": sorted({a["counterparty"] for a in bundle["actions"]})})
    for row in rows:
        row["dominated_on_displayed_axes"] = any(other is not row and other["cost_minor"] <= row["cost_minor"] and other["probability_breach"] <= row["probability_breach"]
                                                 and (other["cost_minor"] < row["cost_minor"] or other["probability_breach"] < row["probability_breach"]) for other in rows)
    return context.envelope({"kind": "recovery_frontier", "risk_target": planner.RISK_TARGET, "rows": rows,
                             "scope": "Comparison of available bundles, not a global optimality proof. Extra cash is assumed present at opening without fees or repayment; its availability and timing require confirmation. Fresh draws measure sampling, not calibration."})
