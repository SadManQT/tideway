"""Leakage guards and exact scoring contracts, independent of winning metrics."""
from __future__ import annotations

import copy
import csv
import json
import math
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tideway.ml import evaluation_v2 as ev
from tideway.ml import model as tp
from tideway.ml.synth import generate
from tideway.ml.train import prior_eval


class TidePayEvaluationTests(unittest.TestCase):
    def test_global_splits_purge_unavailable_payment_labels(self):
        examples = ev.make_examples(generate(3), ev.DEFAULTS["train_end"], ev.DEFAULTS["validation_end"])
        splits = {row["split"] for row in examples}
        self.assertEqual(splits, {"train", "validation", "test", "purged_train", "purged_validation"})
        for row in examples:
            if row["split"] == "train":
                self.assertLess(row["issue_date"], "2025-03-01")
                self.assertLess(row["paid_date"], "2025-03-01")
            elif row["split"] == "validation":
                self.assertGreaterEqual(row["issue_date"], "2025-03-01")
                self.assertLess(row["issue_date"], "2025-07-01")
                self.assertLess(row["paid_date"], "2025-07-01")
            elif row["split"] == "test":
                self.assertGreaterEqual(row["issue_date"], "2025-07-01")
        self.assertEqual(len({r["id"] for r in examples}), len(examples))

    def test_unsettled_and_future_labels_do_not_enter_earlier_features(self):
        invoices = [
            {"customer": "c", "issue_date": date(2024, 1, 1), "due_date": date(2024, 1, 31),
             "paid_date": date(2024, 2, 10), "amount": 100, "terms": 30, "delay": 10},
            {"customer": "c", "issue_date": date(2024, 2, 1), "due_date": date(2024, 3, 2),
             "paid_date": date(2024, 3, 12), "amount": 100, "terms": 30, "delay": 10},
            {"customer": "c", "issue_date": date(2024, 3, 20), "due_date": date(2024, 4, 19),
             "paid_date": date(2024, 4, 29), "amount": 100, "terms": 30, "delay": 10}]
        original = tp.dataset({"invoices": invoices})
        modified = copy.deepcopy(invoices)
        modified[0]["delay"] = 70
        modified[2]["delay"] = 80
        changed = tp.dataset({"invoices": modified})
        self.assertEqual(original[0][0], changed[0][0])  # own target not an input
        self.assertEqual(original[1][0], changed[1][0])  # first invoice not yet paid
        self.assertNotEqual(original[2][0], changed[2][0])  # now-known past label can enter online history

    def test_fitted_statistics_ignore_all_nontraining_targets(self):
        examples = ev.make_examples(generate(2), ev.DEFAULTS["train_end"], ev.DEFAULTS["validation_end"])
        train = [r for r in examples if r["split"] == "train"]
        expected = ev.fit_statistics(train)
        poisoned = copy.deepcopy(examples)
        for row in poisoned:
            if row["split"] != "train":
                row["delay"] = 9999
                row["y"] = 4
                row["x"] = [999] * len(tp.FEATURES)
        actual = ev.fit_statistics([r for r in poisoned if r["split"] == "train"])
        self.assertEqual(expected[0].to_json(), actual[0].to_json())
        self.assertEqual(expected[1:], actual[1:])
        with self.assertRaises(ValueError):
            ev.fit_statistics(examples)

    def test_historical_prior_uses_training_delay_mean_on_rerun(self):
        # Predictions must stay at training mean 0, even when every test label is 30.
        result = prior_eval([0, 0], [0, 0], [([], 3), ([], 3)], [30, 30])
        self.assertEqual(result["mae_days"], 30)

    def test_metrics_use_summed_multiclass_brier_and_signed_lateness(self):
        row = {"probabilities": [0.2] * 5, "y": 0, "delay": -3, "expected_delay_days": 2}
        result = ev.metrics([row])
        self.assertEqual(result["n"], 1)
        self.assertEqual(result["mae_days"], 5)
        self.assertAlmostEqual(result["brier_sum"], 0.8)
        self.assertAlmostEqual(result["log_loss"], math.log(5))
        with self.assertRaises(ValueError):
            ev.metrics([{**row, "probabilities": [0.3] * 5}])

    def test_reliability_boundaries_counts_and_empty_bins(self):
        rows = [{"probabilities": [1, 0, 0, 0, 0], "delay": 0},
                {"probabilities": [0, 0, 1, 0, 0], "delay": 8},
                {"probabilities": [0.9, 0, 0.1, 0, 0], "delay": 7}]
        bins = ev.reliability(rows)
        self.assertEqual([b["n"] for b in bins], [1, 1, 0, 0, 0, 0, 0, 0, 0, 1])
        self.assertEqual(sum(b["observed_events"] for b in bins), 1)
        self.assertIsNone(bins[2]["observed_rate"])
        self.assertGreater(bins[9]["observed_wilson_95"][0], 0)
        self.assertLessEqual(bins[9]["observed_wilson_95"][1], 1)

    def test_business_bootstrap_is_paired_and_deterministic(self):
        rows = [{"id": str(b), "business": b, "probabilities": [0.2] * 5,
                 "y": b % 5, "delay": b, "expected_delay_days": 2} for b in range(5)]
        data = {"prior": rows, "federated": copy.deepcopy(rows)}
        first = ev.cluster_intervals(data, repetitions=30, seed=42)
        self.assertEqual(first, ev.cluster_intervals(data, repetitions=30, seed=42))
        for interval in first["federated_minus_comparator_95"]["prior"].values():
            self.assertEqual(interval, [0.0, 0.0])

    def test_small_end_to_end_keeps_same_ids_and_production_model_unchanged(self):
        model_path = ev.ROOT / "tideway/ml/tidepay_model.json"
        before = model_path.read_bytes()
        config = {"businesses": 3, "rounds": 1, "bootstrap_repetitions": 10}
        with tempfile.TemporaryDirectory() as folder:
            report = ev.run(folder, config)
            self.assertTrue(report["provenance"]["same_test_ids_for_all_models"])
            self.assertEqual(len({v["n"] for v in report["results"].values()}), 1)
            with (Path(folder) / "predictions.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            ids = {name: [r["id"] for r in rows if r["split"] == "test" and r["model"] == name]
                   for name in ev.MODEL_NAMES}
            for cohort in ids.values():
                self.assertEqual(cohort, ids["prior"])
            for split in ("train", "validation", "test"):
                self.assertEqual(sum(report["balance"][split]["class_counts"]), report["balance"][split]["n"])
            stats = report["fitted_training_statistics"]
            self.assertNotEqual(stats["local_by_business"]["0"]["mean"], stats["global"]["mean"])
            hashes = json.loads((Path(folder) / "artifact_sha256.json").read_text())
            for name, expected in hashes.items():
                import hashlib
                self.assertEqual(hashlib.sha256((Path(folder) / name).read_bytes()).hexdigest(), expected)
        self.assertEqual(before, model_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
