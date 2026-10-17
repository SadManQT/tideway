"""Re-evaluate known planner regressions with fresh simulation draws.

This is post-fix evidence on disclosed synthetic cases, never a new holdout or
real-business accuracy claim. Historical observations are copied byte-for-byte
once and never overwritten. No model inference, network or financial mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_upgrade_scenarios import FIXTURE, load_spec, new_business, run_case  # noqa: E402
from scripts.verify_submission import source_digest  # noqa: E402
from tideway import analytics, planner  # noqa: E402
from tideway.service import Tideway  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def risk_followup(snapshot, actions, runs):
    rows = []
    for seed in (20261017, 50737, 91729):
        start = time.perf_counter()
        simulation = analytics.monte_carlo(snapshot["business"], snapshot["policy"], snapshot["records"],
                                           snapshot["business"]["default_target_date"],
                                           [action["adjustment"] for action in actions],
                                           runs=runs, seed=seed,
                                           lookahead_days=snapshot["policy"]["lookahead_days"],
                                           as_of=snapshot["state"]["current_date"])
        rows.append({"seed": seed, "runs": runs, "probability_breach": simulation["probability_breach"],
                     "milliseconds": (time.perf_counter() - start) * 1000})
    # Probability is saved to four decimals by the public simulation. Counts
    # below preserve that precision rather than pretending to have raw draws.
    mean = statistics.fmean(row["probability_breach"] for row in rows)
    count = runs * len(rows)
    z2 = 1.96 ** 2
    denominator = 1 + z2 / count
    centre = (mean + z2 / (2 * count)) / denominator
    half = 1.96 * (mean * (1 - mean) / count + z2 / (4 * count ** 2)) ** .5 / denominator
    return {"per_seed": rows, "total_runs": runs * len(rows), "mean_probability_breach": mean,
            "approximate_95_percent_sampling_interval": [max(0, centre - half), min(1, centre + half)],
            "interval_note": "Approximate Wilson binomial sampling interval from rounded simulation fractions; excludes model error, parameter uncertainty and real-world agreement reliability."}


def run(output, *, runs=10000, repetitions=3, warmup=1):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    baseline = out / "baseline-scenarios.json"
    if not baseline.exists():
        baseline.write_bytes((ROOT / "evidence/readiness-v3/scenarios/report.json").read_bytes())
    historical = json.loads(baseline.read_text(encoding="utf-8"))
    spec = load_spec()
    initial_digest, _ = source_digest()
    rows = []
    for case in spec["scenarios"]:
        if case["id"] not in ("D06", "H11"):
            continue
        workflow = run_case(case, spec["defaults"])
        app = Tideway(":memory:", seed=False)
        try:
            business_id = new_business(app, case, spec["defaults"])
            snapshot = app.store.snapshot(business_id)
            derived = app.store.derived(snapshot)
            options = {"basis_dates": derived["likely_dates"], "profiles": derived["profiles"],
                       "blocked": derived["blocked"], "mc_seed": analytics.stable_seed(business_id, snapshot["snapshot_hash"],
                                                                                   snapshot["business"]["default_target_date"]),
                       "mc_runs": 400, "as_of": snapshot["state"]["current_date"]}
            times = []
            result = None
            for iteration in range(warmup + repetitions):
                start = time.perf_counter()
                result = planner.plan_recovery(snapshot["business"], snapshot["policy"], snapshot["records"],
                                                snapshot["business"]["default_target_date"], **options)
                if iteration >= warmup:
                    times.append((time.perf_counter() - start) * 1000)
            old = next(row for row in historical["rows"] if row["id"] == case["id"])
            row = {"id": case["id"], "historical_observation": {
                "risk_after_400_runs": old["after"]["probability_reserve_breach"],
                "executed_cost_minor": old["executed_cost_minor"], "trace": old["trace"]},
                   "current_workflow": workflow,
                   "selected_executed_plan_fresh_draws": risk_followup(snapshot, workflow.get("executed_actions", []), runs),
                   "planner_timing": {"scope": "planner only, including candidate screening, search Monte Carlo and independent finalist validation; excludes workflow approvals, database and baseline simulation",
                                      "warmups_discarded": warmup, "repetitions": repetitions,
                                      "durations_ms": times, "median_ms": statistics.median(times),
                                      "search": result["search"]}}
            if case["id"] == "H11":
                end = planner.horizon_end(snapshot["business"], snapshot["business"]["default_target_date"],
                                          snapshot["policy"]["lookahead_days"])
                maximal = [max(planner._deferral_options(snapshot["business"], snapshot["policy"], bill, end, {})[0],
                               key=lambda action: (action["days"], action["amount_minor"]))
                           for bill in snapshot["records"]["bills"]]
                row["maximal_permitted_deferral_check"] = {
                    "actions": maximal, "risk": risk_followup(snapshot, maximal, runs),
                    "dominance_argument": "For this fixed ledger, every open obligation is an ordinary reschedulable bill, discounts are disabled, there are no other executable cash-generating actions, all six full-amount fourteen-day deferrals fit the daily cap and horizon. Moving each outflow later by its largest permitted amount never lowers any daily balance relative to a shorter/partial deferral. Thus maximal deferral weakly dominates every available timing bundle on every shared receipt-date path. Its residual risk cannot be removed by selecting a different permitted combination.",
                    "scope": "A model-conditional structural argument for this disclosed synthetic ledger and policy. It does not prove model calibration or guaranteed real-world risk."}
            rows.append(row)
            print(f"{case['id']}: selected follow-up risk={row['selected_executed_plan_fresh_draws']['mean_probability_breach']:.4f}; planner median={statistics.median(times):.1f} ms", flush=True)
        finally:
            app.store.close()
    final_digest, _ = source_digest()
    report = {"version": "planner-risk-remediation-v5", "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "source_tree_sha256": final_digest, "source_unchanged_during_run": initial_digest == final_digest,
              "evaluation_script_sha256": sha(__file__), "fixture_sha256": sha(FIXTURE),
              "historical_baseline": {"path": baseline.name, "sha256": sha(baseline),
                                      "original_run_at_utc": historical["run_at_utc"],
                                      "comparison_note": "Immutable recorded outcomes, not a rerun of old source. Changes in model draw alignment and final-estimate sampling are included; do not attribute the entire difference solely to candidate selection. Timings across those runs are not a controlled speed comparison."},
              "machine": {"python": platform.python_version(), "platform": platform.platform()},
              "rows": rows,
              "limits": {"record_groups": planner.MAX_GROUPS, "search_monte_carlo_candidates": planner.ROBUST_CANDIDATES,
                         "independent_finalists": planner.VALIDATION_FINALISTS, "search_runs": 400, "finalist_runs": 1200},
              "limitations": ["Known disclosed synthetic cases reused after inspecting failures; not fresh held-out performance.",
                              "Receipt timing is uncertain; accepted early-payment agreements are fixed in the sandbox simulation. Their real-world reliability is not measured.",
                              "Fresh seeds reduce Monte Carlo sampling noise, not TidePay model error or unmodelled business risks.",
                              "Below-target estimates are not guarantees; above-target approvals still require exact bound residual-risk acknowledgement from each approver.",
                              "No real money, genuine counterparties, model inference or external services tested."]}
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/readiness-v5/planner")
    parser.add_argument("--runs", type=int, default=10000)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    args = parser.parse_args()
    if not 100 <= args.runs <= 100000 or not 1 <= args.repetitions <= 100 or not 0 <= args.warmup <= 10:
        parser.error("runs must be 100–100000, repetitions 1–100 and warmup 0–10")
    result = run(args.out, runs=args.runs, repetitions=args.repetitions, warmup=args.warmup)
    raise SystemExit(0 if result["source_unchanged_during_run"] and all(row["current_workflow"]["safety_pass"] for row in result["rows"]) else 1)
