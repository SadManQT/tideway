"""Frozen deployed TidePay artifact on fresh, unseen synthetic SME cohorts.

No training, calibration, hyperparameter selection or production-model writes.
Features follow the running app: settled history ordered by payment date. The
older training benchmark ordered history by issue date, a documented mismatch.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from . import evaluation_v2 as ev
from . import model as tp
from .synth import generate

ROOT = Path(__file__).resolve().parents[2]
DEPLOYED_PATH = ROOT / "tideway/ml/tidepay_model.json"
AUDITED_PATH = ROOT / "evidence/upgrade-v1/tidepay/federated_model.json"
DEFAULTS = {"seeds": [410281, 598217, 730639, 951313], "businesses_per_seed": 20,
            "generator_start": "2025-11-01", "generator_months": 6,
            "labels_as_of": "2026-10-15", "bootstrap_seed": 284117,
            "bootstrap_repetitions": 1000, "calibration_bins": 10}
MODEL_NAMES = ("deployed", "audited_v2", "historical_training_prior", "customer_history_heuristic")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def historical_prior(artifact):
    """Reconstruct only the shipped artifact's historical training rows.

    Verify exact scaler/bucket statistics before accepting provenance. No fresh
    evaluation examples enter this fit. All historical labels matured before
    the new cohort's first issue date; the report verifies that boundary.
    """
    meta = artifact["meta"]
    businesses = generate(meta["clients"], meta["seed"])
    training, invoices = [], []
    for business in businesses:
        rows = tp.dataset(business)
        cutoff = int(len(rows) * 0.75)
        training.extend(rows[:cutoff])
        invoices.extend(business["invoices"][:cutoff])
    scaler = tp.Softmax()
    scaler.fit_scaler([x for x, _y, _delay in training])
    means = [round(statistics.fmean(d for _x, y, d in training if y == c), 2)
             for c in range(len(tp.BUCKETS))]
    matches = {"training_count": len(training) == meta["train_invoices"],
               "scaler_mean": scaler.mean == artifact["mean"],
               "scaler_std": scaler.std == artifact["std"],
               "bucket_means": means == artifact["bucket_means"]}
    if not all(matches.values()):
        raise ValueError("Cannot establish historical training provenance: " + str(matches))
    counts = Counter(y for _x, y, _delay in training)
    return {"probabilities": [(counts[c] + 1) / (len(training) + len(tp.BUCKETS))
                              for c in range(len(tp.BUCKETS))],
            "expected_delay_days": statistics.fmean(d for _x, _y, d in training),
            "n": len(training), "class_counts": [counts[c] for c in range(len(tp.BUCKETS))],
            "labels_mature_by": max(r["paid_date"] for r in invoices).isoformat(),
            "training_rows_sha256": ev.digest(training), "exact_provenance_matches": matches,
            "source_seed": meta["seed"], "source_clients": meta["clients"],
            "split": "historical first floor(75% of each SME's issue-ordered invoices)"}


def make_cohort(config):
    """Disjoint seed namespaces and all issue windows, including cold starts."""
    seeds = config["seeds"]
    if not seeds or len(set(seeds)) != len(seeds) or 7 in seeds:
        raise ValueError("fresh, distinct nonhistorical seeds required")
    if config["businesses_per_seed"] < 2 or config["generator_months"] < 1:
        raise ValueError("at least two businesses and one month required")
    businesses = []
    for seed in seeds:
        generated = generate(config["businesses_per_seed"], seed,
                             date.fromisoformat(config["generator_start"]), config["generator_months"])
        for business in generated:
            namespace = f"fresh-{seed}-b{business['business']:02d}"
            business["business"] = namespace
            business["cohort_seed"] = seed
            for customer in business["customers"]:
                customer["id"] = f"fresh-{seed}-{customer['id']}"
            for invoice in business["invoices"]:
                invoice["business"] = namespace
                invoice["customer"] = f"fresh-{seed}-{invoice['customer']}"
            businesses.append(business)
    return businesses


def make_examples(businesses, labels_as_of):
    """At issue time, only already paid invoices may contribute a feature.

    Payment-date order is the production API's order. Delays of the current or
    future invoice never enter its inputs. Unascertained labels are retained as
    censored manifest rows, without treating them as on time or scoring them.
    """
    as_of = date.fromisoformat(labels_as_of)
    examples = []
    for business in businesses:
        earlier = []
        for index, invoice in enumerate(business["invoices"]):
            known = [r for r in earlier if r["paid_date"] <= invoice["issue_date"]]
            history = sorted((r for r in known if r["customer"] == invoice["customer"]),
                             key=lambda r: r["paid_date"])
            portfolio = statistics.fmean(r["delay"] for r in known) if known else 5.0
            x = tp.features(history, invoice, portfolio)
            examples.append({"id": f"{business['business']}-i{index:04d}",
                             "business": business["business"], "cohort_seed": business["cohort_seed"],
                             "sector": business["sector"], "customer": invoice["customer"],
                             "issue_date": invoice["issue_date"].isoformat(),
                             "due_date": invoice["due_date"].isoformat(),
                             "paid_date": invoice["paid_date"].isoformat(), "amount": invoice["amount"],
                             "terms": invoice["terms"], "history_n": len(history),
                             "history_latest_paid": max((r["paid_date"].isoformat() for r in history), default=None),
                             "portfolio_n": len(known), "portfolio_mean": portfolio, "x": x,
                             "y": tp.bucket_of(invoice["delay"]), "delay": invoice["delay"],
                             "split": "test" if invoice["paid_date"] <= as_of else "censored"})
            earlier.append(invoice)
    return examples


def predict(examples, deployed, audited, prior):
    predictions = {name: [] for name in MODEL_NAMES}
    for example in examples:
        if example["split"] != "test":
            continue
        forecast = example["x"][2] * 10
        chosen = tp.bucket_of(round(forecast))
        outputs = {"historical_training_prior": (prior["probabilities"], prior["expected_delay_days"]),
                   "customer_history_heuristic": ([0.6 if c == chosen else 0.1 for c in range(5)], forecast)}
        for name, model in (("deployed", deployed), ("audited_v2", audited)):
            probabilities = model.proba(example["x"])
            # This is the expected-delay precision returned by predict_for.
            outputs[name] = (probabilities, round(model.expected_delay(probabilities), 1))
        for name, (probabilities, expected) in outputs.items():
            predictions[name].append({k: example[k] for k in
                                      ("id", "business", "cohort_seed", "sector", "customer", "y", "delay")}
                                     | {"probabilities": probabilities, "expected_delay_days": expected,
                                        "likely_delay_days": max(0, round(expected))})
    return predictions


def intervals(predictions, repetitions, seed):
    """Reuse paired cluster bootstrap with deployed as the reference model."""
    renamed = {("federated" if name == "deployed" else name): rows
               for name, rows in predictions.items()}
    result = ev.cluster_intervals(renamed, repetitions, seed)
    if "metrics_95" in result:
        result["metrics_95"]["deployed"] = result["metrics_95"].pop("federated")
        result["deployed_minus_comparator_95"] = result.pop("federated_minus_comparator_95")
    return result


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def reliability_svg(path, by_model):
    """Standalone static plot with all nonempty-bin Ns and descriptive bars."""
    items = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="850" viewBox="0 0 1000 850">',
             '<rect width="1000" height="850" fill="white"/>',
             '<g font-family="Arial,sans-serif" fill="#172033">',
             '<text x="45" y="30" font-size="22">Fresh-cohort reliability: invoice more than seven days late</text>',
             '<text x="45" y="53" font-size="13">Ten fixed probability bins; labels show N. Bars are descriptive 95% Wilson intervals.</text>']
    colors = ("#007c78", "#2563eb", "#64748b", "#b45309")
    for index, (name, bins) in enumerate(by_model.items()):
        left, bottom, size = 90 + (index % 2) * 470, 370 + (index // 2) * 350, 250
        items.append(f'<text x="{left}" y="{bottom-size-20}" font-size="17">{name}</text>')
        for tick in range(6):
            share = tick / 5
            x, y = left + share * size, bottom - share * size
            items += [f'<path d="M{left},{y} H{left+size}" stroke="#e2e8f0"/>',
                      f'<text x="{left-28}" y="{y+4}" font-size="11">{share:.1f}</text>',
                      f'<text x="{x-8}" y="{bottom+18}" font-size="11">{share:.1f}</text>']
        items += [f'<path d="M{left},{bottom-size} V{bottom} H{left+size}" fill="none" stroke="#475569"/>',
                  f'<path d="M{left},{bottom} L{left+size},{bottom-size}" stroke="#94a3b8" stroke-dasharray="5,5"/>',
                  f'<text x="{left+38}" y="{bottom+40}" font-size="12">Mean predicted probability</text>',
                  f'<text transform="translate({left-45},{bottom-40}) rotate(-90)" font-size="12">Observed event rate</text>']
        for bucket in bins:
            if not bucket["n"]:
                continue
            x = left + bucket["mean_predicted"] * size
            y = bottom - bucket["observed_rate"] * size
            low, high = bucket["observed_wilson_95"]
            items += [f'<path d="M{x:.2f},{bottom-high*size:.2f} V{bottom-low*size:.2f}" stroke="{colors[index]}"/>',
                      f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{colors[index]}"/>',
                      f'<text x="{x+5:.2f}" y="{y-7:.2f}" font-size="10">{bucket["n"]}</text>']
    items += ['<text x="45" y="800" font-size="13">Synthetic new SMEs; correlated invoices. Wilson bars do not account for customer/business clustering.</text>',
              '<text x="45" y="822" font-size="13">All empty and nonempty bin counts: reliability.csv. Paired SME-cluster metric intervals: report.json.</text>', '</g></svg>']
    path.write_text("\n".join(items) + "\n", encoding="utf-8")


def run(output, config=None):
    config = DEFAULTS | (config or {})
    if config["bootstrap_repetitions"] < 0:
        raise ValueError("bootstrap repetitions must not be negative")
    deployed_bytes, audited_bytes = DEPLOYED_PATH.read_bytes(), AUDITED_PATH.read_bytes()
    deployed_json, audited_json = json.loads(deployed_bytes), json.loads(audited_bytes)
    deployed, audited = tp.Softmax.from_json(deployed_json), tp.Softmax.from_json(audited_json)
    prior = historical_prior(deployed_json)
    if prior["labels_mature_by"] >= config["generator_start"]:
        raise ValueError("fresh evaluation must follow historical training label maturity")
    businesses = make_cohort(config)
    examples = make_examples(businesses, config["labels_as_of"])
    predictions = predict(examples, deployed, audited, prior)
    reference_ids = [r["id"] for r in predictions["deployed"]]
    if not reference_ids:
        raise ValueError("no matured examples available")
    if not all([r["id"] for r in rows] == reference_ids for rows in predictions.values()):
        raise ValueError("model cohorts differ")
    by_id = {r["id"]: r for r in examples}
    selectors = {f"sector:{s}": lambda r, s=s: r["sector"] == s for s in sorted({b["sector"] for b in businesses})}
    selectors |= {f"cohort_seed:{s}": lambda r, s=s: r["cohort_seed"] == s for s in config["seeds"]}
    selectors |= {"history:none": lambda r: by_id[r["id"]]["history_n"] == 0,
                  "history:available": lambda r: by_id[r["id"]]["history_n"] > 0,
                  "terms:up_to_30_days": lambda r: by_id[r["id"]]["terms"] <= 30,
                  "terms:over_30_days": lambda r: by_id[r["id"]]["terms"] > 30,
                  "size:at_least_1.5x_history": lambda r: by_id[r["id"]]["x"][9] >= math.log(1.5)}
    results = {name: ev.metrics(rows) | {"likely_day_mae": statistics.fmean(
        abs(row["likely_delay_days"] - row["delay"]) for row in rows)} for name, rows in predictions.items()}
    subgroups = {name: {model: ev.metrics([r for r in rows if match(r)])
                        for model, rows in predictions.items()} for name, match in selectors.items()}
    balances = {}
    for split in ("test", "censored"):
        rows = [r for r in examples if r["split"] == split]
        balances[split] = {"n": len(rows), "businesses": len({r["business"] for r in rows}),
                           "class_counts": [sum(r["y"] == c for r in rows) for c in range(5)],
                           "issue_min": min((r["issue_date"] for r in rows), default=None),
                           "issue_max": max((r["issue_date"] for r in rows), default=None),
                           "paid_max": max((r["paid_date"] for r in rows), default=None)}
    source_names = ["tideway/ml/model.py", "tideway/ml/synth.py", "tideway/ml/evaluation_v2.py",
                    "tideway/ml/deployed_evaluation.py", "scripts/evaluate_deployed_tidepay.py", "tideway/analytics.py"]
    report = {"version": "deployed-tidepay-fresh-cohorts-v1", "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "config": config, "machine": {"python": sys.version, "platform": platform.platform()},
              "artifacts": {"deployed": {"path": str(DEPLOYED_PATH.relative_to(ROOT)), "sha256": hashlib.sha256(deployed_bytes).hexdigest(), "meta": deployed_json["meta"]},
                            "audited_v2": {"path": str(AUDITED_PATH.relative_to(ROOT)), "sha256": hashlib.sha256(audited_bytes).hexdigest(), "meta": audited_json["meta"],
                                           "training_policy": "7745 matured training labels before 2025-03-01; seed7, 40 SMEs; no new fitting"}},
              "provenance": {"source_sha256": {p: sha256(ROOT / p) for p in source_names},
                             "raw_dataset_sha256": ev.digest(businesses), "features_and_splits_sha256": ev.digest(examples),
                             "test_ids_sha256": ev.digest(reference_ids), "same_test_ids_for_all_models": True,
                             "split_ids_sha256": {s: ev.digest([r["id"] for r in examples if r["split"] == s]) for s in balances},
                             "fitting_on_fresh_examples": False, "artifact_bytes_unchanged": True},
              "historical_prior_statistics": prior, "balance": balances, "results": results,
              "intervals": intervals(predictions, config["bootstrap_repetitions"], config["bootstrap_seed"]),
              "subgroups": subgroups, "reliability": {name: ev.reliability(rows, config["calibration_bins"]) for name, rows in predictions.items()},
              "definitions": {"population": "new synthetic SMEs and customers; four fresh seeds, all issue dates including cold starts; no overlap with seed7 training cohort",
                              "features": "production issue-time snapshot: paid_date <= issue_date, same-customer history sorted by payment date, current invoice excluded",
                              "online_history": "earlier test invoice labels may enter later features only once actually settled; weights/scaler/calibration stay frozen",
                              "mae_days": "mean absolute error of expected delay; deployed/audited expected values rounded to 0.1 day as in predict_for",
                              "likely_day_mae": "MAE of max(0,round(expected_delay_days)); actual likely-scenario day forecast",
                              "probability_scores": "full precision model probabilities before API's four-decimal display rounding; no renormalization or calibration",
                              "log_loss": "mean natural -ln(max(p_true,1e-15))", "brier_sum": "mean sum of five squared class errors; range 0..2, not divided by five",
                              "heuristic": "issue-time credibility customer mean for days; fixed 0.6/0.1 smoothed bucket probabilities, unchanged from earlier benchmark",
                              "labels": "only invoices whose paid_date <= labels_as_of are scored; censored examples remain visible in manifest",
                              "freeze": "existing shipped and audited artifacts fixed before fresh-seed generation; no tuning, training, calibration or selection on these rows"},
              "limitations": ["Synthetic same-generator-family evaluation; no real SME outcomes, causal evidence, lending validation or real-world calibrated cash-risk estimate.",
                              "Fresh seeded cohorts are a stronger independent regression/evaluation set, not an independently administered blind trial.",
                              "Retrospective synthetic issue dates do not establish a prospective real-time deployment trial; artifacts were trained in October 2026.",
                              "Model was trained on histories ordered by issue date; production sorts by payment date. This evaluation follows production and explicitly covers that mismatch.",
                              "Production can forecast later than issue time. Only issuance snapshots are evaluated here; overdue conditional forecasts are not validated.",
                              "All eventually observed outcomes come from the generator; real unpaid/defaulted and missing-data processes are absent.",
                              "Fresh cohort receives no prior fitting; historical prior was reconstructed from verified original training rows. Audited v2 uses fewer matured labels, so model comparisons do not isolate chronology as a causal factor.",
                              "No local-only/pooled model is newly fitted; those earlier benchmark scores must not be copied onto this different test cohort.",
                              "Business-cluster intervals capture resampling of these synthetic SMEs, not full generator, user, geography or model-selection uncertainty.",
                              "Reliability Wilson bars are descriptive; within-SME/customer correlations violate independent binomial assumptions.",
                              "The simulator's payment tail and festival assumptions remain illustrative; four seeds cannot characterize all plausible shifts."]}
    if DEPLOYED_PATH.read_bytes() != deployed_bytes or AUDITED_PATH.read_bytes() != audited_bytes:
        raise RuntimeError("frozen artifact changed during evaluation")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (output / "raw_dataset.jsonl").write_text("\n".join(ev.canonical(b).decode() for b in businesses) + "\n", encoding="utf-8")
    manifest = [{k: v for k, v in row.items() if k != "x"} | {"features_json": json.dumps(row["x"])} for row in examples]
    write_csv(output / "split_manifest.csv", manifest)
    flattened = []
    for model, rows in predictions.items():
        for row in rows:
            flattened.append({"model": model, **{k: v for k, v in row.items() if k != "probabilities"},
                              **{f"p_{c}": p for c, p in enumerate(row["probabilities"])},
                              "p_late_over_7d": sum(row["probabilities"][2:])})
    write_csv(output / "predictions.csv", flattened)
    reliability = []
    for model, bins in report["reliability"].items():
        for bucket in bins:
            bounds = bucket["observed_wilson_95"]
            reliability.append({"model": model, **{k: v for k, v in bucket.items() if k != "observed_wilson_95"},
                                "wilson_low": bounds[0] if bounds else None, "wilson_high": bounds[1] if bounds else None})
    write_csv(output / "reliability.csv", reliability)
    reliability_svg(output / "reliability.svg", report["reliability"])
    write_csv(output / "per_business.csv", [{"business": b["business"], "sector": b["sector"], "model": name,
              **ev.metrics([r for r in rows if r["business"] == b["business"]])} for b in businesses for name, rows in predictions.items()])
    lines = ["# Exact deployed TidePay: fresh synthetic cohorts", "", "Frozen artifacts; no fitting or tuning on the new test cohort.", "",
             f"Scored {balances['test']['n']} invoices from {balances['test']['businesses']} new synthetic SMEs across {len(config['seeds'])} seeds; {balances['censored']['n']} unascertained labels excluded and disclosed.", "",
             f"Deployed artifact SHA-256: `{report['artifacts']['deployed']['sha256']}`.", "",
             "| Model | MAE days | Log loss | Sum Brier | Likely-day MAE | N |", "|---|---:|---:|---:|---:|---:|"]
    for name, result in results.items():
        lines.append(f"| {name} | {result['mae_days']:.4f} | {result['log_loss']:.4f} | {result['brier_sum']:.4f} | {result['likely_day_mae']:.4f} | {result['n']} |")
    lines += ["", "All models use identical examples and production payment-date-ordered issue-time features. Raw probability scores precede display rounding; day forecasts match app precision. The audited v2 artifact is diagnostic and is not deployed.", "",
              "Cold-start/history and cohort/sector/terms/size results, paired business-cluster bootstrap intervals, full reliability counts (including empty bins), frozen training-prior provenance and all hashes are in report.json. [Reliability plot](reliability.svg).", "",
              "## Limitations", ""] + [f"- {item}" for item in report["limitations"]]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files = sorted(p for p in output.iterdir() if p.is_file() and p.name != "artifact_sha256.json")
    (output / "artifact_sha256.json").write_text(json.dumps({p.name: sha256(p) for p in files}, indent=2) + "\n", encoding="utf-8")
    return report
