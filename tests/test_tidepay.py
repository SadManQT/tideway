"""TidePay: the trained model must beat simple baselines and secure aggregation must be exact."""
import json
import unittest
from pathlib import Path

from tideway import analytics
from tideway.ml import model as tp

ROOT = Path(__file__).resolve().parents[1]


class TidePayTests(unittest.TestCase):
    def test_report_shows_federated_beats_baselines(self):
        results = json.loads((ROOT / "evidence" / "ml" / "tidepay_report.json").read_text())["results"]
        fed = results["federated"]
        self.assertLess(fed["log_loss"], results["heuristic_v1"]["log_loss"])
        self.assertLess(fed["log_loss"], results["local_only"]["log_loss"])
        self.assertLess(fed["mae_days"], results["heuristic_v1"]["mae_days"])
        self.assertLess(abs(fed["log_loss"] - results["centralised"]["log_loss"]), 0.05)
        self.assertLess(results["federated_on_smaller_half_of_smes"]["mae_days"],
                        results["local_only_on_smaller_half_of_smes"]["mae_days"])

    def test_secure_aggregation_masks_cancel(self):
        masks = tp.pairwise_masks(5, 12, "seed")
        for column in zip(*masks):
            self.assertAlmostEqual(sum(column), 0.0, places=9)
        self.assertTrue(any(abs(value) > 1 for value in masks[0]))  # illustrative masks are nonzero; this does not establish privacy

    def test_quantile_and_cdf_are_consistent(self):
        probs = [0.1, 0.3, 0.4, 0.15, 0.05]
        for u in (0.05, 0.3, 0.6, 0.9, 0.99):
            days = analytics.delay_quantile(probs, u)
            self.assertGreaterEqual(analytics.delay_cdf(probs, days) + 1e-9, u - 0.08)
        self.assertEqual(analytics.delay_quantile([1, 0, 0, 0, 0], 0.5), 0)

    def test_model_prefers_slow_history(self):
        model = analytics.tidepay_model()
        from datetime import date
        fast = [{"delay": 0, "amount": 10000, "paid_date": "2026-01-01"}] * 6
        slow = [{"delay": 25, "amount": 10000, "paid_date": "2026-01-01"}] * 6
        a = tp.predict_for(model, fast, 10000, 30, date(2026, 10, 15), 6)
        b = tp.predict_for(model, slow, 10000, 30, date(2026, 10, 15), 6)
        self.assertLess(a["expected_delay_days"], b["expected_delay_days"])
        self.assertAlmostEqual(sum(a["probabilities"]), 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
