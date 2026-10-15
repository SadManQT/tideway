"""Train and evaluate TidePay. Run: python -m tideway.ml.train

Compares, on the same held-out (chronologically later) invoices:
  * prior: the overall bucket frequencies (no model);
  * heuristic: Tideway v1's customer-average rule (credibility-weighted mean);
  * local-only: each SME trains alone on its own small history;
  * federated: single-process FedAvg simulation with illustrative masking (no privacy guarantee);
  * centralised: one model on pooled data (an upper bound that needs data sharing).
Writes the federated model to tideway/ml/tidepay_model.json and a report to evidence/ml/.
"""
from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path

from . import model as tp
from .synth import generate

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = Path(__file__).with_name("tidepay_model.json")


def heuristic_eval(rows, delays, bucket_means):
    """Customer-average rule as a probabilistic baseline (smoothed one-hot on its bucket)."""
    loss, correct, errors, scores = 0.0, 0, [], []
    for (x, y), delay in zip(rows, delays):
        predicted = x[2] * 10  # prior_mean feature (credibility-weighted customer average)
        bucket = tp.bucket_of(round(predicted))
        probs = [0.6 if c == bucket else 0.1 for c in range(len(tp.BUCKETS))]
        loss -= math.log(probs[y])
        correct += bucket == y
        errors.append(abs(predicted - delay))
        scores.append((predicted, delay > 7))
    return {"log_loss": round(loss / len(rows), 4), "accuracy": round(correct / len(rows), 4),
            "mae_days": round(statistics.fmean(errors), 2), "auc_late_over_7d": tp.auc(scores), "n": len(rows)}


def prior_eval(train_y, rows, delays):
    counts = [train_y.count(c) + 1 for c in range(len(tp.BUCKETS))]
    probs = [c / sum(counts) for c in counts]
    mean_delay = statistics.fmean(delays)
    loss = -statistics.fmean(math.log(probs[y]) for _x, y in rows)
    top = max(range(len(probs)), key=probs.__getitem__)
    return {"log_loss": round(loss, 4), "accuracy": round(sum(1 for _x, y in rows if y == top) / len(rows), 4),
            "mae_days": round(statistics.fmean(abs(mean_delay - d) for d in delays), 2), "auc_late_over_7d": 0.5,
            "n": len(rows)}


def main(seed=7, rounds=25):
    started = time.time()
    businesses = generate(n_businesses=40, seed=seed)
    clients = []
    for business in businesses:
        rows = tp.dataset(business)
        cut = int(len(rows) * 0.75)
        clients.append({"train": rows[:cut], "test": rows[cut:], "sector": business["sector"]})
    all_train = [r for c in clients for r in c["train"]]
    all_test = [r for c in clients for r in c["test"]]
    scaler = tp.Softmax()
    scaler.fit_scaler([x for x, _y, _d in all_train])  # in deployment: computed from securely summed moments
    bucket_means = []
    for index in range(len(tp.BUCKETS)):
        values = [d for _x, y, d in all_train if y == index]
        bucket_means.append(round(statistics.fmean(values), 2) if values else tp.BUCKETS[index][0])

    def scaled(rows):
        return [(scaler.scale(x), y) for x, y, _d in rows]

    test_scaled, test_delays = scaled(all_test), [d for _x, _y, d in all_test]
    results = {"prior": prior_eval([y for _x, y, _d in all_train], test_scaled, test_delays),
               "heuristic_v1": heuristic_eval([(x, y) for x, y, _d in all_test], test_delays, bucket_means)}

    # Local-only: each SME alone, evaluated on its own later invoices.
    local_rows, local_delays, local_models = [], [], []
    for index, client in enumerate(clients):
        model = tp.Softmax()
        model.mean, model.std, model.bucket_means = scaler.mean, scaler.std, bucket_means
        model.sgd(scaled(client["train"]), epochs=rounds, lr=0.05, seed=index)
        local_models.append(model)
        local_rows.extend((model, z, y) for z, y in scaled(client["test"]))
        local_delays.extend(d for _x, _y, d in client["test"])
    loss = correct = 0
    errors, scores = [], []
    for (model, z, y), delay in zip(local_rows, local_delays):
        probs = model.proba_scaled(z)
        loss -= math.log(max(probs[y], 1e-9))
        correct += max(range(len(probs)), key=probs.__getitem__) == y
        errors.append(abs(model.expected_delay(probs) - delay))
        scores.append((sum(probs[2:]), delay > 7))
    results["local_only"] = {"log_loss": round(loss / len(local_rows), 4), "accuracy": round(correct / len(local_rows), 4),
                             "mae_days": round(statistics.fmean(errors), 2), "auc_late_over_7d": tp.auc(scores),
                             "n": len(local_rows)}

    secure_log = []
    federated = tp.federated_train([scaled(c["train"]) for c in clients], scaler, rounds=rounds, seed=seed, log=secure_log)
    federated.bucket_means = bucket_means
    results["federated"] = tp.evaluate(federated, test_scaled, test_delays)

    central = tp.Softmax()
    central.mean, central.std, central.bucket_means = scaler.mean, scaler.std, bucket_means
    central.sgd(scaled(all_train), epochs=rounds, lr=0.05, seed=seed)
    results["centralised"] = tp.evaluate(central, test_scaled, test_delays)

    thin = [i for i, c in enumerate(clients) if len(c["train"]) < statistics.median(len(c["train"]) for c in clients)]
    thin_rows = [r for i in thin for r in clients[i]["test"]]
    results["federated_on_smaller_half_of_smes"] = tp.evaluate(federated, scaled(thin_rows), [d for _x, _y, d in thin_rows])
    thin_local = []
    for i in thin:
        for z, y in scaled(clients[i]["test"]):
            thin_local.append((local_models[i], z, y))
    thin_delays = [d for i in thin for _x, _y, d in clients[i]["test"]]
    errors = [abs(m.expected_delay(m.proba_scaled(z)) - d) for (m, z, _y), d in zip(thin_local, thin_delays)]
    results["local_only_on_smaller_half_of_smes"] = {"mae_days": round(statistics.fmean(errors), 2), "n": len(errors)}

    meta = {"trained_at": time.strftime("%Y-%m-%d %H:%M"), "seed": seed, "rounds": rounds, "clients": len(clients),
            "train_invoices": len(all_train), "test_invoices": len(all_test), "method": "Single-process FedAvg simulation + illustrative pairwise masks",
            "data": "synthetic SME invoice histories (tideway/ml/synth.py); no real customer data"}
    MODEL_PATH.write_text(json.dumps(federated.to_json(meta), indent=1))
    out = ROOT / "evidence" / "ml"
    out.mkdir(parents=True, exist_ok=True)
    report = {"meta": meta, "results": results, "secure_aggregation_sample": secure_log[:2],
              "elapsed_seconds": round(time.time() - started, 1)}
    (out / "tidepay_report.json").write_text(json.dumps(report, indent=1))
    lines = ["# TidePay evaluation (synthetic held-out invoices)", "",
             f"{meta['clients']} SMEs, {meta['train_invoices']} training and {meta['test_invoices']} later test invoices. {meta['data']}.", "",
             "| Model | Log loss (lower better) | Accuracy | MAE days | AUC (>7 days late) |", "|---|---|---|---|---|"]
    for name in ("prior", "heuristic_v1", "local_only", "federated", "centralised"):
        r = results[name]
        lines.append(f"| {name} | {r['log_loss']} | {r['accuracy']} | {r['mae_days']} | {r['auc_late_over_7d']} |")
    lines += ["", f"Smaller half of SMEs: local-only MAE {results['local_only_on_smaller_half_of_smes']['mae_days']} days vs "
              f"federated {results['federated_on_smaller_half_of_smes']['mae_days']} days.", "",
              "Simulation only: one process holds all client data, pools training features for scaling, and generates predictable masks. Mask cancellation is demonstrated; cryptographic privacy and distributed deployment are not implemented.",
              "Results are on synthetic data and show the method works as designed, not real-world accuracy."]
    (out / "tidepay_report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nsaved {MODEL_PATH.relative_to(ROOT)} in {report['elapsed_seconds']}s")


if __name__ == "__main__":
    main()
