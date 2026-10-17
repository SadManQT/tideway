"""Audited, chronological TidePay benchmark; does not replace the shipped model.

No optional packages are needed. Fitted statistics use matured training labels
only. Histories are observational features rebuilt as of each invoice's issue
date, so previously settled validation/test invoices can enter later histories.
This is an online-feature evaluation of existing SMEs, not unseen businesses.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import random
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from . import model as tp
from .synth import generate

ROOT = Path(__file__).resolve().parents[2]
MODEL_NAMES = ("prior", "heuristic_v1", "local_only", "federated", "centralised")
DEFAULTS = {"seed": 7, "businesses": 40, "rounds": 25, "local_epochs": 1,
            "learning_rate": 0.05, "train_end": "2025-03-01", "validation_end": "2025-07-01",
            "generator_start": "2024-01-01", "generator_months": 22,
            "bootstrap_seed": 1701, "bootstrap_repetitions": 1000, "calibration_bins": 10}
# Fixed before evaluation; used only for classes absent from a local training set.
EMPTY_CLASS_MEANS = [0.0, 4.0, 11.5, 23.0, 45.0]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def make_examples(businesses, train_end, validation_end):
    """Global time boundaries, with labels available before the next period.

    Unmatured labels are purged, not moved into a later split. Their invoices can
    still enter an observational history once actually paid, as in deployment.
    """
    train_end, validation_end = date.fromisoformat(train_end), date.fromisoformat(validation_end)
    if train_end >= validation_end:
        raise ValueError("train_end must precede validation_end")
    examples = []
    for business in businesses:
        invoices = sorted(business["invoices"], key=lambda r: (r["issue_date"], r["customer"]))
        rows = tp.dataset({**business, "invoices": invoices})
        for index, (invoice, (x, y, delay)) in enumerate(zip(invoices, rows)):
            if invoice["issue_date"] < train_end:
                split = "train" if invoice["paid_date"] < train_end else "purged_train"
            elif invoice["issue_date"] < validation_end:
                split = "validation" if invoice["paid_date"] < validation_end else "purged_validation"
            else:
                split = "test"
            examples.append({"id": f"b{business['business']:02d}-i{index:04d}",
                             "business": business["business"], "sector": business["sector"],
                             "customer": invoice["customer"], "issue_date": invoice["issue_date"].isoformat(),
                             "due_date": invoice["due_date"].isoformat(),
                             "paid_date": invoice["paid_date"].isoformat(), "amount": invoice["amount"],
                             "terms": invoice["terms"], "split": split, "x": x, "y": y, "delay": delay})
    return examples


def fit_statistics(rows):
    if not rows:
        raise ValueError("a training cohort is empty")
    if any(row["split"] != "train" for row in rows):
        raise ValueError("fitted statistics accept training examples only")
    scaler = tp.Softmax()
    scaler.fit_scaler([row["x"] for row in rows])
    class_counts = Counter(row["y"] for row in rows)
    scaler.bucket_means = [statistics.fmean(r["delay"] for r in rows if r["y"] == c)
                           if class_counts[c] else EMPTY_CLASS_MEANS[c] for c in range(len(tp.BUCKETS))]
    priors = [(class_counts[c] + 1) / (len(rows) + len(tp.BUCKETS)) for c in range(len(tp.BUCKETS))]
    return scaler, priors, statistics.fmean(row["delay"] for row in rows)


def metrics(predictions):
    """Brier is sum over 5 classes, then mean over N (range 0..2)."""
    if not predictions:
        return {"n": 0}
    sums = {"mae_days": 0.0, "log_loss": 0.0, "brier_sum": 0.0, "accuracy": 0.0}
    scores = []
    for row in predictions:
        p, y = row["probabilities"], row["y"]
        if len(p) != len(tp.BUCKETS) or any(not math.isfinite(v) or v < 0 for v in p) or abs(sum(p) - 1) > 1e-8:
            raise ValueError("invalid probability distribution")
        sums["mae_days"] += abs(row["expected_delay_days"] - row["delay"])
        sums["log_loss"] -= math.log(max(p[y], 1e-15))
        sums["brier_sum"] += sum((v - (c == y)) ** 2 for c, v in enumerate(p))
        sums["accuracy"] += max(range(len(p)), key=p.__getitem__) == y
        scores.append((sum(p[2:]), row["delay"] > 7))
    return {"n": len(predictions), **{k: v / len(predictions) for k, v in sums.items()},
            "auc_late_over_7d": tp.auc(scores)}


def wilson(successes, n):
    if not n:
        return None
    z = 1.959963984540054
    p = successes / n
    middle = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [max(0.0, middle - half), min(1.0, middle + half)]


def reliability(predictions, bins=10):
    if bins < 1:
        raise ValueError("bins must be positive")
    grouped = [[] for _ in range(bins)]
    for row in predictions:
        p = sum(row["probabilities"][2:])
        grouped[min(bins - 1, int(p * bins))].append((p, row["delay"] > 7))
    result = []
    for i, rows in enumerate(grouped):
        n, observed = len(rows), sum(y for _p, y in rows)
        result.append({"bin": i, "lower_inclusive": i / bins, "upper": (i + 1) / bins,
                       "upper_inclusive": i == bins - 1, "n": n, "observed_events": observed,
                       "mean_predicted": statistics.fmean(p for p, _y in rows) if n else None,
                       "observed_rate": observed / n if n else None,
                       "observed_wilson_95": wilson(observed, n)})
    return result


def quantile(values, p):
    values = sorted(values)
    place = (len(values) - 1) * p
    lower = int(place)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (place - lower)


def cluster_intervals(predictions_by_model, repetitions=1000, seed=1701):
    """Paired percentile bootstrap over businesses, retaining within-SME rows."""
    names = list(predictions_by_model)
    sums = {}
    for name, rows in predictions_by_model.items():
        by_business = defaultdict(list)
        for row in rows:
            by_business[row["business"]].append(row)
        sums[name] = {b: metrics(group) for b, group in by_business.items()}
    businesses = sorted(sums[names[0]])
    if len(businesses) < 2 or not repetitions:
        return {"clusters": len(businesses), "reason": "fewer than two businesses or bootstrap disabled"}
    if any(set(sums[name]) != set(businesses) for name in names):
        raise ValueError("bootstrap model cohorts differ")
    rng = random.Random(seed)
    keys = ("mae_days", "log_loss", "brier_sum")
    samples = {name: {key: [] for key in keys} for name in names}
    differences = {name: {key: [] for key in keys} for name in names if name != "federated"}
    for _ in range(repetitions):
        drawn = [rng.choice(businesses) for _ in businesses]
        values = {}
        for name in names:
            n = sum(sums[name][b]["n"] for b in drawn)
            values[name] = {key: sum(sums[name][b][key] * sums[name][b]["n"] for b in drawn) / n for key in keys}
            for key in keys:
                samples[name][key].append(values[name][key])
        if "federated" in values:
            for name in differences:
                for key in keys:
                    differences[name][key].append(values["federated"][key] - values[name][key])
    interval = lambda series: [quantile(series, 0.025), quantile(series, 0.975)]
    return {"clusters": len(businesses), "repetitions": repetitions, "seed": seed,
            "method": "95% percentile paired business-cluster bootstrap; invoice-weighted means",
            "metrics_95": {name: {k: interval(v) for k, v in group.items()} for name, group in samples.items()},
            "federated_minus_comparator_95": {name: {k: interval(v) for k, v in group.items()}
                                               for name, group in differences.items()}}


def train_and_predict(examples, config):
    train = [r for r in examples if r["split"] == "train"]
    scaler, priors, prior_mean = fit_statistics(train)
    clients = sorted({r["business"] for r in examples})
    train_by_business = {b: [r for r in train if r["business"] == b] for b in clients}
    scaled = lambda rows, model: [(model.scale(r["x"]), r["y"]) for r in rows]
    local_models = {}
    local_statistics = {}
    for b in clients:
        local, local_prior, local_mean = fit_statistics(train_by_business[b])
        local.sgd(scaled(train_by_business[b], local), epochs=config["rounds"],
                  lr=config["learning_rate"], seed=config["seed"] * 1000 + b)
        local_models[b] = local
        local_statistics[str(b)] = {"n": len(train_by_business[b]), "mean": local.mean, "std": local.std,
                                    "bucket_means": local.bucket_means, "priors": local_prior,
                                    "delay_mean": local_mean}
    federation_log = []
    fed = tp.federated_train([scaled(train_by_business[b], scaler) for b in clients], scaler,
                             rounds=config["rounds"], local_epochs=config["local_epochs"],
                             lr=config["learning_rate"], seed=config["seed"], log=federation_log)
    fed.bucket_means = scaler.bucket_means[:]
    central = tp.Softmax()
    central.mean, central.std, central.bucket_means = scaler.mean[:], scaler.std[:], scaler.bucket_means[:]
    central.sgd(scaled(train, scaler), epochs=config["rounds"], lr=config["learning_rate"], seed=config["seed"])
    predictions = {split: {name: [] for name in MODEL_NAMES} for split in ("validation", "test")}
    for row in examples:
        if row["split"] not in predictions:
            continue
        expected = row["x"][2] * 10
        chosen = tp.bucket_of(round(expected))
        all_p = {"prior": (priors, prior_mean),
                 "heuristic_v1": ([0.6 if c == chosen else 0.1 for c in range(len(tp.BUCKETS))], expected)}
        for name, model in (("local_only", local_models[row["business"]]), ("federated", fed), ("centralised", central)):
            probabilities = model.proba(row["x"])
            all_p[name] = (probabilities, model.expected_delay(probabilities))
        for name, (p, expected) in all_p.items():
            predictions[row["split"]][name].append({k: row[k] for k in ("id", "business", "sector", "customer", "y", "delay")}
                                                   | {"probabilities": p, "expected_delay_days": expected})
    stats = {"global": {"n": len(train), "mean": scaler.mean, "std": scaler.std,
                         "bucket_means": scaler.bucket_means, "priors": priors, "delay_mean": prior_mean},
             "local_by_business": local_statistics}
    return predictions, fed, stats, federation_log


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def calibration_svg(path, data):
    """Standalone scientific SVG; standard-library fallback without matplotlib."""
    colors = ("#64748b", "#d97706", "#7c3aed", "#007c78", "#2563eb")
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="850" viewBox="0 0 1200 850">',
           '<rect width="1200" height="850" fill="white"/>',
           '<g font-family="Arial,sans-serif" fill="#172033">',
           '<text x="45" y="30" font-size="22">TidePay v2 reliability: payment more than seven days late</text>',
           '<text x="45" y="55" font-size="13">Ten equal-width probability bins. Point labels show N; bars show descriptive 95% Wilson intervals.</text>']
    for index, name in enumerate(MODEL_NAMES):
        col, row = index % 3, index // 3
        x0, y0, size = 70 + col * 390, 340 + row * 370, 235
        svg.append(f'<text x="{x0}" y="{y0-size-20}" font-size="17">{escape(name)}</text>')
        for tick in range(6):
            t = tick / 5
            x, y = x0 + t * size, y0 - t * size
            svg.append(f'<path d="M{x0},{y} H{x0+size}" stroke="#e2e8f0"/>')
            svg.append(f'<text x="{x0-27}" y="{y+4}" font-size="11">{t:.1f}</text>')
            svg.append(f'<text x="{x-7}" y="{y0+18}" font-size="11">{t:.1f}</text>')
        svg.append(f'<path d="M{x0},{y0-size} V{y0} H{x0+size}" fill="none" stroke="#475569"/>')
        svg.append(f'<path d="M{x0},{y0} L{x0+size},{y0-size}" stroke="#94a3b8" stroke-dasharray="5,5"/>')
        svg.append(f'<text x="{x0+50}" y="{y0+40}" font-size="12">Mean predicted probability</text>')
        svg.append(f'<text transform="translate({x0-43},{y0-45}) rotate(-90)" font-size="12">Observed event rate</text>')
        points = []
        for bucket in data[name]:
            if not bucket["n"]:
                continue
            x, y = x0 + bucket["mean_predicted"] * size, y0 - bucket["observed_rate"] * size
            low, high = bucket["observed_wilson_95"]
            points.append(f"{x:.2f},{y:.2f}")
            svg.append(f'<path d="M{x:.2f},{y0-high*size:.2f} V{y0-low*size:.2f}" stroke="{colors[index]}"/>')
            svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{colors[index]}"/>')
            svg.append(f'<text x="{x+4:.2f}" y="{y-7:.2f}" font-size="10">{bucket["n"]}</text>')
        svg.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[index]}"/>')
    svg.extend(['<text x="70" y="795" font-size="13">Synthetic existing SMEs; correlated invoices. Wilson bars are descriptive and do not model clustering.</text>',
                '<text x="70" y="818" font-size="13">Business-cluster bootstrap metric intervals and all empty/nonempty bins are in report.json and reliability.csv.</text>', '</g></svg>'])
    path.write_text("\n".join(svg) + "\n", encoding="utf-8")


def run(output, config=None):
    started = time.perf_counter()
    config = DEFAULTS | (config or {})
    if config["local_epochs"] != 1:
        raise ValueError("This fixed comparison uses one local epoch per federation round")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    businesses = generate(config["businesses"], config["seed"], start=date.fromisoformat(config["generator_start"]),
                          months=config["generator_months"])
    examples = make_examples(businesses, config["train_end"], config["validation_end"])
    predictions, fed, fitted, federation_log = train_and_predict(examples, config)
    test = predictions["test"]
    reference_ids = [r["id"] for r in test["prior"]]
    assert all([r["id"] for r in rows] == reference_ids for rows in test.values())
    balance = {}
    for split in ("train", "validation", "test", "purged_train", "purged_validation"):
        rows = [r for r in examples if r["split"] == split]
        balance[split] = {"n": len(rows), "businesses": len({r["business"] for r in rows}),
                          "class_counts": [sum(r["y"] == c for r in rows) for c in range(len(tp.BUCKETS))],
                          "late_over_7d": sum(r["delay"] > 7 for r in rows),
                          "issue_min": min((r["issue_date"] for r in rows), default=None),
                          "issue_max": max((r["issue_date"] for r in rows), default=None),
                          "paid_max": max((r["paid_date"] for r in rows), default=None)}
    train_counts = Counter(r["business"] for r in examples if r["split"] == "train")
    median_train = statistics.median(train_counts.values())
    selectors = {f"sector:{sector}": lambda r, s=sector: r["sector"] == s for sector in sorted({r["sector"] for r in examples})}
    selectors |= {"training_size:below_median": lambda r: train_counts[r["business"]] < median_train,
                  "training_size:at_or_above_median": lambda r: train_counts[r["business"]] >= median_train}
    example_by_id = {r["id"]: r for r in examples}
    selectors |= {"history:none": lambda r: example_by_id[r["id"]]["x"][0] == 0,
                  "history:available": lambda r: example_by_id[r["id"]]["x"][0] == 1}
    selectors |= {"terms:up_to_30_days": lambda r: example_by_id[r["id"]]["terms"] <= 30,
                  "terms:over_30_days": lambda r: example_by_id[r["id"]]["terms"] > 30,
                  "invoice_size:at_least_1.5x_history": lambda r: example_by_id[r["id"]]["x"][9] >= math.log(1.5),
                  "invoice_size:below_1.5x_history": lambda r: example_by_id[r["id"]]["x"][9] < math.log(1.5)}
    subgroups = {}
    for name, matches in selectors.items():
        subset = {model: [r for r in rows if matches(r)] for model, rows in test.items()}
        subgroups[name] = {"results": {model: metrics(rows) for model, rows in subset.items()},
                           "intervals": cluster_intervals(subset, config["bootstrap_repetitions"], config["bootstrap_seed"])}
    by_business = []
    for b in sorted(train_counts):
        models = {name: [r for r in rows if r["business"] == b] for name, rows in test.items()}
        by_business.append({"business": b, "sector": next(r["sector"] for r in examples if r["business"] == b),
                            "train_n": train_counts[b], "results": {name: metrics(rows) for name, rows in models.items()},
                            "test_class_counts": [sum(r["y"] == c for r in models["prior"]) for c in range(len(tp.BUCKETS))]})
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False).stdout.strip() or None
    except FileNotFoundError:
        head = None
    source_files = ["tideway/ml/model.py", "tideway/ml/synth.py", "tideway/ml/evaluation_v2.py", "scripts/evaluate_tidepay_v2.py"]
    source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_files}
    split_ids = {split: [r["id"] for r in examples if r["split"] == split] for split in balance}
    report = {"version": "tidepay-evaluation-v2", "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "config": config, "machine": {"python": sys.version, "platform": platform.platform(),
                                             "machine": platform.machine(), "processor": platform.processor(),
                                             "logical_cpus": __import__("os").cpu_count()},
              "provenance": {"git_head": head, "source_sha256": source_hashes,
                             "dataset_sha256": digest(businesses), "features_and_splits_sha256": digest(examples),
                             "split_ids_sha256": {s: digest(ids) for s, ids in split_ids.items()},
                             "same_test_ids_for_all_models": True, "same_test_ids_sha256": digest(reference_ids)},
              "definitions": {"mae_days": "mean absolute error of expected lateness in days over N invoices; early payments have negative lateness",
                              "log_loss": "mean -ln(max(p[observed class], 1e-15)) over N; natural logarithm",
                              "brier_sum": "mean over N of sum over all five classes of (p_c - 1[y=c])^2; NOT divided by five; range 0..2",
                              "accuracy": "fraction of N whose highest-probability class matches observed class; first class wins ties",
                              "reliability": "event delay > 7 days; 10 equal-width bins [k/10,(k+1)/10), final bin includes 1; no empty-bin interpolation",
                              "expected_delay": "softmax models: probability-weighted training bucket means; prior: raw training delay mean; heuristic: issue-time credibility mean (probability baseline separately fixed at 0.6/0.1)",
                              "split": "common global issue-date windows; purge train/validation invoices whose payment label is not known strictly before next period",
                              "features": "only prior invoices settled by issue date; rolling observable history may include earlier validation/test invoices; no refitting from them",
                              "calibration": "none fitted; validation retained separately for diagnostics; no validation-based tuning or model selection"},
              "balance": balance, "results": {name: metrics(rows) for name, rows in test.items()},
              "validation_results": {name: metrics(rows) for name, rows in predictions["validation"].items()},
              "intervals": cluster_intervals(test, config["bootstrap_repetitions"], config["bootstrap_seed"]),
              "per_business": by_business, "subgroups": subgroups, "smaller_business_threshold_train_n": median_train,
              "reliability": {name: reliability(rows, config["calibration_bins"]) for name, rows in test.items()},
              "fitted_training_statistics": fitted, "federation_sample": federation_log[:2],
              "historical_audit": ["Historical train.prior_eval computes mean_delay from test delays for prior MAE: test-label leakage; v2 uses training delay mean.",
                                   "Historical split uses each business's invoice index at 75%, without a common global cutoff or payment-label maturity purge.",
                                   "Historical scaler and bucket means were training-row-only, but training rows could carry labels unavailable when early held-out invoices were issued.",
                                   "Historical local-only model shared pooled training scaling and bucket means; v2 local models fit those from their own matured training rows.",
                                   "Issue-time feature history filters paid_date <= issue_date. Latent personality and current invoice delay/paid_date are not features.",
                                   "Bucket means represent training observations (including any >90-day synthetic tail in final class); frozen empty-class means are used only when a local class is absent."],
              "limitations": ["Synthetic histories from the same generator family and same 40 businesses, not real-world or unseen-business validation.",
                              "One seed/cohort; cluster intervals capture business resampling, not generator, hyperparameter or deployment uncertainty.",
                              "Test invoices all have eventually observed synthetic labels; there is no real-world censoring model.",
                              "Purging unmatured labels selects faster-settling invoices near each cutoff; gaps and class balances are reported rather than silently treating unpaid invoices as on-time.",
                              "No cold-start customer exists in this final test; history:none has N=0 and establishes no performance for new customers.",
                              "The fixed heuristic's probability mass is arbitrary and coarse; its raw expected delay can differ from its smoothed class distribution's mean.",
                              "Local, FedAvg and centralised optimisers have different update paths. Same rows/information/policy does not imply identical compute or convergence.",
                              "FedAvg is a single-process simulation holding raw client data, pooled train scaling, reproducible predictable masks; no cryptographic privacy guarantee.",
                              "Small subgroups and within-customer correlations limit precision; per-business rows have no claimed inferential interval.",
                              "Wilson reliability bars are descriptive binomial intervals; correlated invoices violate the independence assumption.",
                              "Historic evidence and the shipped production model remain unchanged; v2 is an audit benchmark, not a deployed calibration update."],
              "elapsed_seconds": round(time.perf_counter() - started, 3)}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (output / "federated_model.json").write_text(json.dumps(fed.to_json({"evaluation": report["version"], "dataset_sha256": digest(businesses)}), indent=2) + "\n", encoding="utf-8")
    manifest = [{k: r[k] for k in ("id", "business", "sector", "customer", "issue_date", "due_date", "paid_date", "split", "y", "delay")}
                for r in examples]
    write_csv(output / "split_manifest.csv", manifest)
    flat_predictions = []
    for split, models in predictions.items():
        for model, rows in models.items():
            for row in rows:
                flat_predictions.append({"split": split, "model": model, **{k: row[k] for k in ("id", "business", "sector", "customer", "y", "delay", "expected_delay_days")},
                                         **{f"p_{i}": p for i, p in enumerate(row["probabilities"])},
                                         "p_late_over_7d": sum(row["probabilities"][2:])})
    write_csv(output / "predictions.csv", flat_predictions)
    reliability_rows = []
    for model, bins in report["reliability"].items():
        for b in bins:
            bounds = b["observed_wilson_95"]
            reliability_rows.append({"model": model, **{k: v for k, v in b.items() if k != "observed_wilson_95"},
                                     "wilson_low": bounds[0] if bounds else None, "wilson_high": bounds[1] if bounds else None})
    write_csv(output / "reliability.csv", reliability_rows)
    business_rows = [{"business": group["business"], "sector": group["sector"], "train_n": group["train_n"], "model": name, **result}
                     for group in by_business for name, result in group["results"].items()]
    write_csv(output / "per_business.csv", business_rows)
    calibration_svg(output / "reliability.svg", report["reliability"])
    lines = ["# TidePay v2 chronological synthetic evaluation", "", "This audit benchmark leaves historical raw observations and the shipped model unchanged.", "",
             f"Training: {balance['train']['n']}; validation: {balance['validation']['n']}; final test: {balance['test']['n']} invoices from {balance['test']['businesses']} existing synthetic SMEs.",
             f"Global cutoffs: {config['train_end']} / {config['validation_end']}; purged immature train/validation labels: {balance['purged_train']['n']} / {balance['purged_validation']['n']}.", "",
             "| Model | MAE days | Log loss | Brier (sum of 5 classes) | Accuracy | N |", "|---|---:|---:|---:|---:|---:|"]
    for name, result in report["results"].items():
        lines.append(f"| {name} | {result['mae_days']:.4f} | {result['log_loss']:.4f} | {result['brier_sum']:.4f} | {result['accuracy']:.4f} | {result['n']} |")
    lines += ["", "The heuristic preserves its original raw credibility-mean day forecast and fixed smoothed class probabilities. A better day forecast can coexist with worse probability scores.", "",
              "## Paired business-cluster bootstrap", "", "95% percentile intervals for federated minus comparator (negative favours federated):", "",
              "| Comparator | MAE difference interval | Log loss difference interval | Brier difference interval |", "|---|---:|---:|---:|"]
    for name, intervals in report["intervals"].get("federated_minus_comparator_95", {}).items():
        cells = [f"[{intervals[k][0]:.4f}, {intervals[k][1]:.4f}]" for k in ("mae_days", "log_loss", "brier_sum")]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "See report.json for class balance, all per-business/sector/history/size subgroups, validation diagnostics, definitions, fitted statistics, seeds and hashes.", "",
              "[Reliability plot](reliability.svg) uses event delay >7 days, 10 equal-width bins, counts and descriptive Wilson bars. Correlation limits their interpretation. [CSV](reliability.csv).", "",
              "## Historical audit", ""] + [f"- {finding}" for finding in report["historical_audit"]]
    lines += ["", "## Limitations", ""] + [f"- {finding}" for finding in report["limitations"]]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files = sorted(p for p in output.iterdir() if p.is_file() and p.name != "artifact_sha256.json")
    (output / "artifact_sha256.json").write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}, indent=2) + "\n", encoding="utf-8")
    return report
