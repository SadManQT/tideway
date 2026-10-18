"""Check the cash threshold against exhaustive integer amounts and fresh paths."""
import math
import random
import unittest

from tideway.analytics import liquidity_gap, monte_carlo
from tideway.service import Tideway
from scripts.evaluate_upgrade_scenarios import load_spec, new_business


class LiquidityGap(unittest.TestCase):
    def test_matches_exhaustive_small_integer_thresholds(self):
        rng = random.Random(613)
        for _ in range(50):
            minimums = [rng.randrange(-20, 30) for _ in range(rng.randrange(1, 40))]
            reserve = rng.randrange(0, 20)
            target = rng.choice((0, .1, .25, .5))
            allowed = math.floor(len(minimums) * target)
            expected = next(amount for amount in range(60)
                            if sum(value + amount < reserve for value in minimums) <= allowed)
            result = liquidity_gap(minimums, reserve, target)
            self.assertEqual(result["additional_cash_minor"], expected)
            self.assertLessEqual(result["sample_breaches_after"], allowed)
            if expected:
                self.assertGreater(result["breaches_with_one_minor_less"], allowed)
            self.assertFalse(result["executable"])
            self.assertFalse(result["funding_confirmed"])

    def test_empty_or_invalid_inputs_are_rejected(self):
        for args in (([], 1), ([True], 1), ([1], -1), ([1], 1, float("nan")), ([1], 1, 1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                liquidity_gap(*args)

    def test_decimal_target_at_integer_boundary_is_not_rounded_down(self):
        result = liquidity_gap([0] * 29 + [100] * 71, 100, .29)
        self.assertEqual(result["additional_cash_minor"], 0)
        self.assertEqual(result["sample_breaches_after"], 29)

    def test_cash_only_counterfactual_does_not_mutate_h11_ledger(self):
        spec = load_spec()
        case = next(c for c in spec["scenarios"] if c["id"] == "H11")
        app = Tideway(":memory:", seed=False)
        try:
            identifier = new_business(app, case, spec["defaults"])
            snapshot = app.store.snapshot(identifier)
            from tideway import planner
            end = planner.horizon_end(snapshot["business"], snapshot["business"]["default_target_date"], snapshot["policy"]["lookahead_days"])
            actions = [max(planner._deferral_options(snapshot["business"], snapshot["policy"], bill, end, {})[0],
                           key=lambda action: (action["days"], action["amount_minor"])) for bill in snapshot["records"]["bills"]]
            def simulate(business, seed):
                return monte_carlo(business, snapshot["policy"], snapshot["records"], business["default_target_date"],
                                   [a["adjustment"] for a in actions], runs=1000, seed=seed,
                                   lookahead_days=snapshot["policy"]["lookahead_days"], as_of=snapshot["state"]["current_date"])
            baseline = simulate(snapshot["business"], 70279)
            amount = baseline["liquidity_gap"]["additional_cash_minor"]
            self.assertGreater(baseline["probability_breach"], .1)
            self.assertGreater(amount, 0)
            hypothetical = {**snapshot["business"], "opening_cash_minor": snapshot["business"]["opening_cash_minor"] + amount}
            fresh = simulate(hypothetical, 82613)
            self.assertLessEqual(fresh["probability_breach"], .1)
            self.assertEqual(app.store.snapshot(identifier)["snapshot_hash"], snapshot["snapshot_hash"])
        finally:
            app.store.close()


if __name__ == "__main__":
    unittest.main()
