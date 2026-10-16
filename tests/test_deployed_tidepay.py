"""Deployed-artifact contracts and leakage boundaries, independent of scores."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from tideway import analytics
from tideway.ml import deployed_evaluation as de
from tideway.ml import model as tp


class DeployedTidePayTests(unittest.TestCase):
    def test_historical_prior_matches_exact_shipped_training_statistics(self):
        artifact = json.loads(de.DEPLOYED_PATH.read_bytes())
        prior = de.historical_prior(artifact)
        self.assertEqual(prior["n"], artifact["meta"]["train_invoices"])
        self.assertTrue(all(prior["exact_provenance_matches"].values()))
        self.assertLess(prior["labels_mature_by"], de.DEFAULTS["generator_start"])
        artifact["mean"][0] += 0.01
        with self.assertRaisesRegex(ValueError, "provenance"):
            de.historical_prior(artifact)

    def test_fresh_ids_and_seeds_do_not_overlap_historical_cohort(self):
        cohort = de.make_cohort(de.DEFAULTS | {"seeds": [410281, 598217], "businesses_per_seed": 2})
        self.assertEqual(len({b["business"] for b in cohort}), 4)
        customers = [c["id"] for b in cohort for c in b["customers"]]
        self.assertEqual(len(customers), len(set(customers)))
        self.assertTrue(all(c.startswith("fresh-") for c in customers))
        for seeds in ([7], [410281, 410281], []):
            with self.assertRaises(ValueError):
                de.make_cohort(de.DEFAULTS | {"seeds": seeds})

    @staticmethod
    def reversed_payment_business():
        # First-issued invoice pays second: production sorts by payment date.
        invoices = []
        for issued, paid, terms, delay in ((1, 20, 10, 9), (2, 10, 5, 3), (25, 40, 10, 5)):
            issue = date(2026, 1, issued)
            invoices.append({"customer": "fresh-c", "issue_date": issue,
                             "due_date": issue + timedelta(days=terms),
                             "paid_date": date(2026, 1, 1) + timedelta(days=paid - 1),
                             "terms": terms, "amount": 10000, "delay": delay})
        return {"business": "fresh-b", "cohort_seed": 410281, "sector": "services", "invoices": invoices}

    def test_features_equal_production_including_payment_date_history_order(self):
        business = self.reversed_payment_business()
        examples = de.make_examples([business], "2026-10-15")
        last = examples[-1]
        self.assertEqual(last["history_n"], 2)
        self.assertEqual(last["x"][6], 0.9)  # last settled delay=9, rather than last-issued delay=3
        model = tp.load(de.DEPLOYED_PATH)
        runtime_rows = []
        for index, invoice in enumerate(business["invoices"]):
            runtime_rows.append({"id": str(index), "customer": invoice["customer"],
                                 "issue_date": invoice["issue_date"].isoformat(),
                                 "due_date": invoice["due_date"].isoformat(),
                                 "paid_date": invoice["paid_date"].isoformat(),
                                 "amount_minor": invoice["amount"] * 100,
                                 "status": "paid" if index < 2 else "confirmed"})
        with patch.object(analytics, "tidepay_model", return_value=model):
            actual = analytics.tidepay_predictions(runtime_rows, last["issue_date"])["2"]
        raw = model.proba(last["x"])
        self.assertEqual(actual["probabilities"], [round(p, 4) for p in raw])
        self.assertEqual(actual["expected_delay_days"], round(model.expected_delay(raw), 1))
        self.assertEqual(actual["history_used"], last["history_n"])

    def test_own_and_unsettled_targets_cannot_enter_earlier_features(self):
        business = self.reversed_payment_business()
        original = de.make_examples([business], "2026-10-15")
        poisoned = copy.deepcopy(business)
        poisoned["invoices"][0]["delay"] = 80
        poisoned["invoices"][2]["delay"] = 90
        changed = de.make_examples([poisoned], "2026-10-15")
        self.assertEqual(original[0]["x"], changed[0]["x"])  # own outcome
        self.assertEqual(original[1]["x"], changed[1]["x"])  # first invoice still unsettled
        self.assertNotEqual(original[2]["x"], changed[2]["x"])  # previously observed outcome
        for row in original:
            if row["history_latest_paid"]:
                self.assertLessEqual(row["history_latest_paid"], row["issue_date"])

    def test_unascertained_labels_are_censored_without_becoming_on_time(self):
        business = self.reversed_payment_business()
        examples = de.make_examples([business], "2026-01-25")
        self.assertEqual(examples[-1]["split"], "censored")
        model = tp.load(de.DEPLOYED_PATH)
        prior = {"probabilities": [0.2] * 5, "expected_delay_days": 5.0}
        predictions = de.predict(examples, model, model, prior)
        self.assertEqual({len(rows) for rows in predictions.values()}, {2})
        self.assertTrue(all(examples[-1]["id"] not in {r["id"] for r in rows}
                            for rows in predictions.values()))

    def test_small_run_never_trains_or_changes_artifacts_and_recomputes_scores(self):
        before = {path: path.read_bytes() for path in (de.DEPLOYED_PATH, de.AUDITED_PATH)}
        config = {"seeds": [410281], "businesses_per_seed": 2, "bootstrap_repetitions": 10}
        with tempfile.TemporaryDirectory() as folder, patch.object(tp.Softmax, "sgd", side_effect=AssertionError("training forbidden")):
            report = de.run(folder, config)
            self.assertFalse(report["provenance"]["fitting_on_fresh_examples"])
            self.assertTrue(report["provenance"]["same_test_ids_for_all_models"])
            with (Path(folder) / "predictions.csv").open(newline="") as handle:
                csv_rows = list(csv.DictReader(handle))
            ids = {name: [r["id"] for r in csv_rows if r["model"] == name] for name in de.MODEL_NAMES}
            self.assertTrue(all(group == ids["deployed"] for group in ids.values()))
            for model in de.MODEL_NAMES:
                rows = [r for r in csv_rows if r["model"] == model]
                mae = sum(abs(float(r["expected_delay_days"]) - int(r["delay"])) for r in rows) / len(rows)
                self.assertAlmostEqual(mae, report["results"][model]["mae_days"])
                self.assertEqual(sum(b["n"] for b in report["reliability"][model]), len(rows))
                self.assertEqual(len(report["reliability"][model]), 10)
            self.assertGreater(report["subgroups"]["history:none"]["deployed"]["n"], 0)
            hashes = json.loads((Path(folder) / "artifact_sha256.json").read_text())
            for name, expected in hashes.items():
                self.assertEqual(hashlib.sha256((Path(folder) / name).read_bytes()).hexdigest(), expected)
        for path, contents in before.items():
            self.assertEqual(path.read_bytes(), contents)


if __name__ == "__main__":
    unittest.main()
