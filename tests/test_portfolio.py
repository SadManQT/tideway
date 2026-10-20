"""Portfolio radar: synthetic-only lender early warning (tideway/portfolio.py)."""
import ast
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tideway import analytics, portfolio
from tideway.domain import ValidationError
from tideway.fixtures import fixtures

ROOT = Path(__file__).resolve().parents[1]


class PortfolioRadarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = portfolio.radar()

    def test_same_seed_gives_identical_output_and_other_seed_differs(self):
        first = portfolio.generate_portfolio(12, 3)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(portfolio.generate_portfolio(12, 3), sort_keys=True))
        self.assertNotEqual(json.dumps(first, sort_keys=True), json.dumps(portfolio.generate_portfolio(12, 4), sort_keys=True))
        portfolio.clear_cache()
        again = portfolio.radar()
        self.assertEqual(json.dumps(self.base, sort_keys=True), json.dumps(again, sort_keys=True))
        small = dict(n=15, runs=80, seed=11)
        stressed = portfolio.radar({"customer_delay_days": 10}, **small)
        portfolio.clear_cache()
        self.assertEqual(stressed, portfolio.radar({"customer_delay_days": 10}, **small))

    def test_output_is_json_and_labelled_synthetic(self):
        json.dumps(self.base)
        self.assertTrue(self.base["synthetic"])
        self.assertIn("SYNTHETIC", self.base["label"])
        self.assertEqual(self.base["security"], {"tenant_data_read": False, "store_access": False,
                                                 "executable_actions": False, "credit_decision": False})
        tenant_ids = {item["business"]["business_id"] for item in fixtures()}
        self.assertEqual(len(self.base["smes"]), portfolio.DEFAULT_SIZE)
        for row in self.base["smes"]:
            self.assertTrue(row["synthetic"])
            self.assertTrue(row["sme_id"].startswith("pf-sme-"))
            self.assertNotIn(row["sme_id"], tenant_ids)
            self.assertFalse(row["intervention"]["executable"])
            self.assertTrue(row["intervention"]["advisory_only"])
        self.assertEqual([row["rank"] for row in self.base["smes"]], list(range(1, portfolio.DEFAULT_SIZE + 1)))

    def test_input_validation(self):
        bad_shocks = ({"customer_delay_days": 61}, {"customer_delay_days": -1}, {"customer_delay_days": True},
                      {"customer_delay_days": "15"}, {"customer_delay_days": 5, "sector": "crypto"},
                      {"customer_delay_days": 5, "business_id": "shapla-services"}, "15", [15])
        for shock in bad_shocks:
            with self.subTest(shock=shock), self.assertRaises(ValidationError):
                portfolio.radar(shock)
        for kwargs in ({"n": 5}, {"n": 201}, {"seed": -1}, {"runs": 10}, {"runs": 5000}, {"seed": 1.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                portfolio.radar(**kwargs)
        for query in ({"shock_days": ["abc"]}, {"shock_days": ["61"]}, {"shock_days": ["-5"]}, {"shock_days": ["1", "2"]},
                      {"sector": ["<script>"]}, {"business_id": ["shapla-services"]}, {"shock_days": ["999"]}):
            with self.subTest(query=query), self.assertRaises(ValidationError):
                portfolio.radar_from_query(query)
        result = portfolio.radar_from_query({"shock_days": ["0"], "sector": ["retail"]})
        self.assertIsNone(result["shock"])
        stressed = portfolio.radar_from_query({"shock_days": ["15"], "sector": ["retail"]})
        self.assertEqual((stressed["shock"]["customer_delay_days"], stressed["shock"]["sector"]), (15, "retail"))

    def test_module_never_touches_the_store(self):
        tree = ast.parse((ROOT / "tideway" / "portfolio.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[-1])
            elif isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[-1] for alias in node.names)
        self.assertFalse(imported & {"store", "service", "server", "sqlite3", "event_store", "agent", "copilot"}, imported)
        code = ("import sys; from tideway import portfolio; portfolio.radar(n=10, runs=50); "
                "print([m for m in ('tideway.store','tideway.service','tideway.server','sqlite3') if m in sys.modules])")
        output = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertEqual(output.stdout.strip(), "[]")

    def test_tier_thresholds(self):
        cases = ((1.0, "red"), (0.5, "red"), (0.4999, "amber"), (0.15, "amber"), (0.1499, "green"), (0.0, "green"))
        for probability, tier in cases:
            self.assertEqual(portfolio.tier_for(probability), tier)
        for row in self.base["smes"]:
            self.assertEqual(row["tier"], portfolio.tier_for(row["breach_probability"]))
            self.assertEqual(row["intervention"]["code"] == "no_action", row["tier"] == "green")
            self.assertLessEqual(row["p_breach_14d"], row["p_breach_30d"])
            self.assertLessEqual(row["p_breach_30d"], row["breach_probability"])
        summary = self.base["summary"]
        self.assertEqual(sum(summary["tiers"].values()), portfolio.DEFAULT_SIZE)
        self.assertGreater(summary["tiers"]["green"], 0)
        self.assertGreater(summary["tiers"]["red"], 0)

    def test_currencies_are_never_summed_together(self):
        totals = {}
        for row in self.base["smes"]:
            totals[row["currency"]] = totals.get(row["currency"], 0) + row["expected_shortfall_minor"]
        self.assertEqual(self.base["summary"]["expected_shortfall_by_currency_minor"], dict(sorted(totals.items())))
        self.assertGreaterEqual(len(totals), 3)

    def test_matches_the_app_monte_carlo_at_zero_shock(self):
        checked = 0
        for sme in portfolio.generate_portfolio(60, portfolio.DEFAULT_SEED):
            prep = portfolio._prepare(sme)
            mine = len(portfolio._simulate(prep, 150, 17)["breach_days"]) / 150
            if 0 < mine < 1:
                reference = analytics.monte_carlo(sme["business"], sme["policy"], sme["records"], portfolio.TARGET_DATE,
                                                  runs=150, seed=17)
                self.assertEqual(round(mine, 4), reference["probability_breach"], sme["sme_id"])
                checked += 1
            if checked == 3:
                break
        self.assertEqual(checked, 3)

    def test_shock_never_reduces_breach_probability(self):
        small = dict(n=20, runs=100, seed=5)
        previous = None
        for days in (0, 5, 15, 30, 60):
            result = portfolio.radar({"customer_delay_days": days}, **small)
            rows = {row["sme_id"]: row for row in result["smes"]}
            if days:
                mean_after = result["shock"]["summary_after"]["mean_breach_probability"]
                for row in rows.values():
                    self.assertGreaterEqual(row["stressed"]["breach_probability"], row["breach_probability"])
                migration = result["shock"]["migration"]
                self.assertEqual(sum(sum(after.values()) for after in migration.values()), 20)
                self.assertEqual(migration["red"]["green"] + migration["red"]["amber"] + migration["amber"]["green"], 0)
            else:
                mean_after = result["summary"]["mean_breach_probability"]
                self.assertIsNone(result["shock"])
            if previous is not None:
                self.assertGreaterEqual(mean_after, previous)
            previous = mean_after
        sector = portfolio.radar({"customer_delay_days": 30, "sector": "retail"}, **small)
        for row in sector["smes"]:
            self.assertEqual(row["stressed"]["in_scope"], row["sector"] == "retail")
            if row["sector"] != "retail":
                self.assertEqual(row["stressed"]["breach_probability"], row["breach_probability"])

    def test_backtest_metrics_are_bounded_and_seeded(self):
        result = self.base["backtest"]
        for block in ("radar", "baseline_scheduled_projection", "baseline_cash_to_payroll"):
            for key, value in result[block].items():
                if key in ("auc", "brier", "red_precision", "red_recall") and value is not None:
                    self.assertGreaterEqual(value, 0.0, (block, key))
                    self.assertLessEqual(value, 1.0, (block, key))
        self.assertEqual(result["n"], portfolio.DEFAULT_SIZE)
        self.assertTrue(0 <= result["prevalence"] <= 1)
        self.assertIsNotNone(result["radar"]["auc"])
        detailed = portfolio.backtest(include_rows=True)
        self.assertEqual(detailed["radar"], result["radar"])
        other = portfolio.backtest(outcome_seed=12345)
        self.assertEqual(other["outcome_seed"], 12345)
        self.assertNotEqual(other["outcome_seed"], result["outcome_seed"])

    def test_performance_bound(self):
        portfolio.clear_cache()
        started = time.perf_counter()
        portfolio.radar({"customer_delay_days": 15})       # cold: generation, baseline and stressed runs
        elapsed = time.perf_counter() - started
        # Measured ~2.4 s on the build PC (target < 3 s); a looser bound keeps slower CI machines green.
        self.assertLess(elapsed, 8.0)
        started = time.perf_counter()
        portfolio.radar({"customer_delay_days": 15})
        self.assertLess(time.perf_counter() - started, 0.5)  # deterministic result is cached


if __name__ == "__main__":
    unittest.main()
