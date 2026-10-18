"""Diagnose H11 without changing its ledger, constraints, target or baseline.

An opening-cash addition is a conditional owner decision, not executed funding.
The buffer is selected on one seed and evaluated on three different seeds.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_upgrade_scenarios import FIXTURE, load_spec, new_business
from scripts.verify_submission import source_digest
from tideway import analytics, planner
from tideway.service import Tideway


def interval(count, total):
    p, z = count / total, 1.96
    centre = (p + z*z/(2*total)) / (1 + z*z/total)
    half = z*(p*(1-p)/total + z*z/(4*total*total))**.5 / (1 + z*z/total)
    return [max(0, centre-half), min(1, centre+half)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("Use a new output path; do not overwrite prior observations.")
    digest = source_digest()[0]
    spec = load_spec()
    case = next(case for case in spec["scenarios"] if case["id"] == "H11")
    app = Tideway(":memory:", seed=False)
    try:
        identifier = new_business(app, case, spec["defaults"])
        snapshot = app.store.snapshot(identifier)
        business, policy, records = (snapshot[key] for key in ("business", "policy", "records"))
        target = business["default_target_date"]
        end = planner.horizon_end(business, target, policy["lookahead_days"])
        actions = [max(planner._deferral_options(business, policy, bill, end, {})[0],
                       key=lambda a: (a["days"], a["amount_minor"])) for bill in records["bills"]]
        def simulate(cash_addition, seed, runs):
            return analytics.monte_carlo({**business, "opening_cash_minor": business["opening_cash_minor"] + cash_addition},
                                         policy, records, target, [a["adjustment"] for a in actions], runs=runs, seed=seed,
                                         lookahead_days=policy["lookahead_days"], as_of=snapshot["state"]["current_date"])
        selection_seed, selection_runs = 70279, 20000
        fit = simulate(0, selection_seed, selection_runs)
        gap = fit["liquidity_gap"]
        amount = gap["additional_cash_minor"]
        rows = []
        for seed in (20261017, 50737, 91729):
            baseline = simulate(0, seed, 10000)
            funded = simulate(amount, seed, 10000)
            rows.append({"seed": seed, "runs": 10000, "original_probability_breach": baseline["probability_breach"],
                         "conditional_cash_added_probability_breach": funded["probability_breach"]})
        def aggregate(field):
            count = sum(round(row[field] * row["runs"]) for row in rows)
            return {"breaches": count, "runs": 30000, "probability": count / 30000,
                    "sampling_interval_95_percent": interval(count, 30000)}
        unchanged = app.store.snapshot(identifier)["snapshot_hash"] == snapshot["snapshot_hash"]
        report = {"run_at_utc": datetime.now(timezone.utc).isoformat(), "source_tree_sha256": digest,
                  "source_unchanged": source_digest()[0] == digest,
                  "fixture_sha256": hashlib.sha256(Path(FIXTURE).read_bytes()).hexdigest(),
                  "case": "H11", "currency": business["currency"], "actions": actions,
                  "selection_seed": selection_seed, "selection_runs": selection_runs, "liquidity_gap": gap,
                  "validation_seeds_disjoint_from_selection": True, "fresh_validation": rows,
                  "original": aggregate("original_probability_breach"),
                  "conditional_cash_added": aggregate("conditional_cash_added_probability_breach"),
                  "ledger_unchanged": unchanged, "funding_confirmed": False, "executed": False,
                  "target": planner.RISK_TARGET,
                  "limitations": ["Disclosed synthetic case. The original unfunded risk is retained and still above target.",
                                  "No confirmed cash source, investor, loan approval or executable funding action is supplied.",
                                  "Additional cash is assumed present at opening, without fees or repayment; later funding needs a different time-path calculation.",
                                  "Sampling intervals exclude model miscalibration, unmodelled risks and counterparty reliability."]}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: report[k] for k in ("liquidity_gap", "original", "conditional_cash_added", "ledger_unchanged")}, indent=2))
        return 0 if unchanged and report["source_unchanged"] else 1
    finally:
        app.store.close()


if __name__ == "__main__":
    raise SystemExit(main())
