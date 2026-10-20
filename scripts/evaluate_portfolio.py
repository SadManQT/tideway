"""Evaluate the synthetic portfolio radar and write evidence/portfolio/portfolio-report.json.

Measures: radar timings on this machine, the default portfolio summary, macro-shock
tier migration, Monte Carlo run-count stability, and a backtest of the radar's
breach probability against realised futures drawn with independent seeds, versus
two simple baselines.  Everything is synthetic; nothing reads a tenant workspace.

    python scripts/evaluate_portfolio.py [--portfolios 10] [--bootstrap 1000]
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tideway import portfolio  # noqa: E402
from tideway.ml.model import auc  # noqa: E402


def timed(callable_):
    started = time.perf_counter()
    result = callable_()
    return result, round((time.perf_counter() - started) * 1000, 1)


def timings(repeats):
    cold, cold_shock, cold_sector, warm_shock, cached = [], [], [], [], []
    for _ in range(repeats):
        portfolio.clear_cache()
        cold.append(timed(portfolio.radar)[1])
        warm_shock.append(timed(lambda: portfolio.radar({"customer_delay_days": 15}))[1])
        cached.append(timed(lambda: portfolio.radar({"customer_delay_days": 15}))[1])
        portfolio.clear_cache()
        cold_shock.append(timed(lambda: portfolio.radar({"customer_delay_days": 30}))[1])  # worst case: all sectors
        cold_sector.append(timed(lambda: portfolio.radar({"customer_delay_days": 30, "sector": "retail"}))[1])
    summary = lambda values: {"median_ms": statistics.median(values), "max_ms": max(values), "samples_ms": values}  # noqa: E731
    return {"repeats": repeats, "smes": portfolio.DEFAULT_SIZE, "runs_per_sme": portfolio.DEFAULT_RUNS,
            "target": "whole radar call under 3,000 ms on the build PC",
            "cold_baseline_radar": summary(cold),
            "cold_radar_with_all_sector_shock_including_baseline": summary(cold_shock),
            "sector_shock_with_baseline_cached": summary(cold_sector),
            "shock_with_baseline_cached": summary(warm_shock),
            "repeated_identical_call_cached": summary(cached)}


def shocks():
    base = portfolio.radar()
    result = []
    for shock in ({"customer_delay_days": 5}, {"customer_delay_days": 15}, {"customer_delay_days": 30},
                  {"customer_delay_days": 30, "sector": "retail"}, {"customer_delay_days": 30, "sector": "manufacturing"}):
        stressed = portfolio.radar(shock)["shock"]
        result.append({"shock": {**{"sector": "all"}, **shock}, "migration_before_to_after": stressed["migration"],
                       "newly_at_risk": len(stressed["newly_at_risk"]),
                       "newly_at_risk_ids": [row["sme_id"] for row in stressed["newly_at_risk"]],
                       "tiers_before": base["summary"]["tiers"], "tiers_after": stressed["summary_after"]["tiers"],
                       "mean_breach_probability_before": base["summary"]["mean_breach_probability"],
                       "mean_breach_probability_after": stressed["summary_after"]["mean_breach_probability"],
                       "expected_shortfall_after_by_currency_minor": stressed["summary_after"]["expected_shortfall_by_currency_minor"]})
    return result


def run_stability(reference_runs=2000):
    small = portfolio.radar()
    large = portfolio.radar(runs=reference_runs)
    a = {row["sme_id"]: row for row in small["smes"]}
    b = {row["sme_id"]: row for row in large["smes"]}
    differences = [abs(a[key]["breach_probability"] - b[key]["breach_probability"]) for key in a]
    return {"default_runs": portfolio.DEFAULT_RUNS, "reference_runs": reference_runs,
            "mean_abs_probability_difference": round(statistics.fmean(differences), 4),
            "max_abs_probability_difference": round(max(differences), 4),
            "tier_agreement": round(sum(a[key]["tier"] == b[key]["tier"] for key in a) / len(a), 4),
            "tiers_default_runs": small["summary"]["tiers"], "tiers_reference_runs": large["summary"]["tiers"]}


def bootstrap(rows, resamples, seed):
    rng = random.Random(seed)
    outcomes = [1 if row["breached"] else 0 for row in rows]
    stats = {"radar_auc": [], "scheduled_auc": [], "cash_ratio_auc": [], "auc_gain_vs_scheduled": [],
             "radar_brier": [], "scheduled_brier": []}
    n = len(rows)
    for _ in range(resamples):
        index = [int(rng.random() * n) for _ in range(n)]
        y = [outcomes[i] for i in index]
        if not 0 < sum(y) < n:
            continue
        radar_auc = auc([(rows[i]["p"], outcomes[i]) for i in index])
        scheduled_auc = auc([(rows[i]["scheduled_score"], outcomes[i]) for i in index])
        stats["radar_auc"].append(radar_auc)
        stats["scheduled_auc"].append(scheduled_auc)
        stats["cash_ratio_auc"].append(auc([(rows[i]["cash_ratio_score"], outcomes[i]) for i in index]))
        stats["auc_gain_vs_scheduled"].append(radar_auc - scheduled_auc)
        stats["radar_brier"].append(statistics.fmean((rows[i]["p"] - outcomes[i]) ** 2 for i in index))
        stats["scheduled_brier"].append(statistics.fmean(((1.0 if rows[i]["scheduled_breach"] else 0.0) - outcomes[i]) ** 2
                                                         for i in index))
    interval = {}
    for key, values in stats.items():
        values.sort()
        interval[key] = {"low_2_5": round(values[int(0.025 * (len(values) - 1))], 4),
                         "high_97_5": round(values[int(0.975 * (len(values) - 1))], 4)}
    return {"resamples_used": len(stats["radar_auc"]), "seed": seed, "percentile_95_intervals": interval}


def calibration(rows):
    bins = []
    for low, high in ((0, 0.05), (0.05, 0.15), (0.15, 0.5), (0.5, 0.9), (0.9, 1.01)):
        members = [row for row in rows if low <= row["p"] < high]
        if members:
            bins.append({"predicted_range": [low, min(high, 1.0)], "n": len(members),
                         "mean_predicted": round(statistics.fmean(row["p"] for row in members), 4),
                         "observed_breach_rate": round(statistics.fmean(1 if row["breached"] else 0 for row in members), 4)})
    return bins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolios", type=int, default=10, help="independent synthetic portfolios for the pooled backtest")
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", default=str(ROOT / "evidence" / "portfolio" / "portfolio-report.json"))
    args = parser.parse_args()

    timing = timings(args.repeats)
    base = portfolio.radar()
    default_backtest = {key: value for key, value in base["backtest"].items() if key != "method"}

    pooled, per_portfolio = [], []
    portfolio_seeds = list(range(1, args.portfolios + 1))
    started = time.perf_counter()
    for seed in portfolio_seeds:
        result = portfolio.backtest(seed=seed, include_rows=True)
        rows = result.pop("rows")
        pooled.extend(rows)
        per_portfolio.append({"seed": seed, "outcome_seed": result["outcome_seed"], "n": result["n"],
                              "breached": result["breached"], "radar_auc": result["radar"]["auc"],
                              "scheduled_auc": result["baseline_scheduled_projection"]["auc"],
                              "cash_ratio_auc": result["baseline_cash_to_payroll"]["auc"],
                              "radar_brier": result["radar"]["brier"]})
    pooled_metrics = portfolio.backtest_metrics(pooled)
    backtest_seconds = round(time.perf_counter() - started, 2)

    report = {
        "synthetic": True,
        "label": portfolio.LABEL,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "processor": platform.processor()},
        "config": {"version": portfolio.PORTFOLIO_VERSION, "default_seed": portfolio.DEFAULT_SEED,
                   "smes": portfolio.DEFAULT_SIZE, "runs_per_sme": portfolio.DEFAULT_RUNS,
                   "opening_date": portfolio.OPENING_DATE, "horizon_days": portfolio.HORIZON_DAYS,
                   "thresholds": base["thresholds"], "markets": base["generated"]["markets"],
                   "sectors": base["generated"]["sectors"], "max_shock_days": portfolio.MAX_SHOCK_DAYS,
                   "unexpected_expense_chance_in_realised_futures": portfolio.UNEXPECTED_EXPENSE_CHANCE},
        "timings": timing,
        "portfolio_summary": base["summary"],
        "top_10": [{key: row[key] for key in ("rank", "sme_id", "name", "sector", "currency", "breach_probability",
                                               "p_breach_14d", "days_to_breach", "tier")} | {
                    "driver": row["top_driver"]["name"], "intervention": row["intervention"]["code"]}
                   for row in base["smes"][:10]],
        "shock_migration": shocks(),
        "monte_carlo_run_stability": run_stability(),
        "backtest_default_portfolio": default_backtest,
        "backtest_pooled": {"portfolio_seeds": portfolio_seeds, "smes": len(pooled),
                            "method": portfolio.BACKTEST_METHOD, "metrics": pooled_metrics,
                            "bootstrap": bootstrap(pooled, args.bootstrap, 20261020),
                            "calibration_bins": calibration(pooled),
                            "per_portfolio": per_portfolio, "seconds": backtest_seconds},
        "security": base["security"],
        "limits": base["limits"] + [
            "Realised futures come from the same generative family TidePay was trained on (in-distribution), "
            "which flatters the radar relative to real data.",
            "The scheduled-projection baseline ignores lateness by construction; a stronger baseline (e.g. a "
            "deterministic TidePay 'likely' projection) was not evaluated."],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    pm = pooled_metrics
    print(f"Wrote {out}")
    print(f"Cold radar {timing['cold_baseline_radar']['median_ms']} ms; cold with shock "
          f"{timing['cold_radar_with_all_sector_shock_including_baseline']['median_ms']} ms")
    print(f"Pooled backtest n={pm['n']} breached={pm['breached']}: radar AUC {pm['radar']['auc']} Brier {pm['radar']['brier']}"
          f" | scheduled AUC {pm['baseline_scheduled_projection']['auc']} Brier {pm['baseline_scheduled_projection']['brier']}"
          f" | cash ratio AUC {pm['baseline_cash_to_payroll']['auc']}")


if __name__ == "__main__":
    main()
