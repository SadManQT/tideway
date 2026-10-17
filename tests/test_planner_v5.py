"""Risk-aware search must improve coverage without bypassing consent or caps."""
import copy
import unittest
from unittest.mock import patch

from scripts.evaluate_upgrade_scenarios import _approve, load_spec, new_business
from tideway import analytics, planner
from tideway.domain import ValidationError
from tideway.service import Tideway


class PlannerRiskCoverage(unittest.TestCase):
    def setUp(self):
        self.spec = load_spec()
        self.app = Tideway(":memory:", seed=False)
        self.addCleanup(self.app.store.close)

    def business(self, identifier):
        case = next(case for case in self.spec["scenarios"] if case["id"] == identifier)
        business_id = new_business(self.app, case, self.spec["defaults"])
        snapshot = self.app.store.snapshot(business_id)
        return business_id, snapshot, self.app.store.derived(snapshot)

    def test_risk_diverse_shortlist_includes_plans_beyond_forty_cheapest(self):
        business_id, snapshot, _ = self.business("H11")
        select = planner._robust_candidates
        observed = {}

        def inspect(feasible, *args):
            chosen, metadata = select(feasible, *args)
            identity = lambda item: tuple(sorted(action["action_id"] for action in item["chosen"]))
            cheapest = {identity(item) for item in feasible[:planner.ROBUST_CANDIDATES]}
            observed["new_plans"] = sum(identity(item) not in cheapest for item in chosen)
            return chosen, metadata

        with patch.object(planner, "_robust_candidates", side_effect=inspect):
            plan = self.app.propose(business_id, None, "agent:test")
        self.assertGreater(observed["new_plans"], 0)
        self.assertEqual(plan["search"]["robustness_checked"], 40)
        self.assertLessEqual(plan["search"]["independent_finalists_checked"], 4)
        self.assertEqual(plan["search"]["validation_runs_each"], 1200)
        for bundle in plan["bundles"]:
            self.assertTrue(bundle["risk_evaluation"]["independent_of_search"])
            self.assertNotEqual(bundle["risk_evaluation"]["validation_seed"],
                                analytics.stable_seed(business_id, snapshot["snapshot_hash"], plan["target_date"]))
            self.assertEqual(bundle["risk_target_met"], bundle["probability_breach_after"] <= .10)
        # No assertion forces this structurally constrained case below 10%.
        self.assertEqual(self.app.store.snapshot(business_id)["snapshot_hash"], snapshot["snapshot_hash"])

    def test_customer_draws_stay_aligned_when_another_invoice_becomes_fixed(self):
        business_id, snapshot, _ = self.business("D06")
        records = copy.deepcopy(snapshot["records"])
        first = records["invoices"][0]
        first["customer"] = "A customer"
        records["invoices"].append({**first, "id": "second", "customer": "B customer"})
        predictions = {first["id"]: {"probabilities": [1, 0, 0, 0, 0]},
                       "second": {"probabilities": [0, 1, 0, 0, 0]}}
        draws = []

        def sample(probabilities, uniform):
            if probabilities[1] == 1:
                draws.append(uniform)
            return 0

        with patch.object(analytics, "tidepay_predictions", return_value=predictions), \
                patch.object(analytics, "delay_quantile", side_effect=sample):
            args = (snapshot["business"], snapshot["policy"], records, snapshot["business"]["default_target_date"])
            analytics.monte_carlo(*args, runs=8, seed=9)
            before = draws[:]
            draws.clear()
            adjustment = {"kind": "invoice_early_payment", "invoice_id": first["id"],
                          "face_minor": first["amount_minor"], "amount_minor": first["amount_minor"] - 100,
                          "to_date": "2026-10-03"}
            analytics.monte_carlo(*args, adjustments=[adjustment], runs=8, seed=9)
        self.assertEqual(len(before), 8)
        self.assertEqual(before, draws)

    def test_optional_as_of_matches_explicit_opening_date_for_large_search(self):
        _, snapshot, derived = self.business("H11")
        args = (snapshot["business"], snapshot["policy"], snapshot["records"],
                snapshot["business"]["default_target_date"])
        options = {"profiles": derived["profiles"], "basis_dates": derived["likely_dates"],
                   "mc_runs": 20, "mc_seed": 7}
        implicit = planner.plan_recovery(*args, **options)
        explicit = planner.plan_recovery(*args, **options, as_of=snapshot["business"]["opening_date"])
        self.assertEqual(implicit, explicit)

    def test_counter_repair_keeps_terms_and_requires_new_approvals_and_consent(self):
        business_id, snapshot, _ = self.business("D06")
        plan = self.app.propose(business_id, None, "agent:test")
        original, _ = _approve(self.app, business_id, plan)
        self.assertEqual(self.app.negotiate(business_id, original["mandate_id"], "agent:test")["status"], "countered")
        repaired = self.app.accept_counter(business_id, original["mandate_id"], "agent:test")
        best = repaired["bundles"][0]
        self.assertEqual(repaired["search"]["source"], "counter-offer repair")
        self.assertTrue(best["risk_target_met"])
        fixed = next(action for action in best["actions"] if action["type"] == "supplier_deferral")
        self.assertEqual((fixed["days"], fixed["to_date"]), (7, "2026-10-12"))
        self.assertTrue(any(action["type"] == "early_payment_offer" for action in best["actions"]))
        self.assertFalse(repaired["approvals"])
        owner = self.app.store.verify_pin("eval-owner", "893741")
        with self.assertRaises(ValidationError):
            self.app.store.execute(business_id, original["mandate_id"], "obsolete", owner, "operator:eval-owner")
        mandate, approvals = _approve(self.app, business_id, repaired)
        self.assertEqual(approvals, ["eval-accountant", "eval-owner"])
        with self.assertRaises(ValidationError):
            self.app.store.execute(business_id, mandate["mandate_id"], "no-consent", owner, "operator:eval-owner")
        # The newly added customer's counter-offer also requires a new plan;
        # approval of the supplier's old mandate never authorises this action.
        reply = self.app.negotiate(business_id, mandate["mandate_id"], "agent:test")
        self.assertEqual(reply["status"], "countered")
        final = self.app.accept_counter(business_id, mandate["mandate_id"], "agent:test")
        self.assertFalse(final["approvals"])
        final_mandate, _ = _approve(self.app, business_id, final)
        self.assertEqual(self.app.negotiate(business_id, final_mandate["mandate_id"], "agent:test")["status"], "ready")
        receipt = self.app.store.execute(business_id, final_mandate["mandate_id"], "approved-once", owner, "operator:eval-owner")
        self.assertTrue(receipt["read_back"]["verified"])
        self.assertTrue(self.app.store.evidence(business_id)["hash_chain_valid"])

    def test_locked_counter_terms_cannot_bypass_daily_exposure_cap(self):
        business_id, snapshot, derived = self.business("D06")
        plan = self.app.propose(business_id, None, "agent:test")
        fixed = copy.deepcopy(plan["bundles"][0]["actions"])
        policy = {**snapshot["policy"], "daily_cap_minor": fixed[0]["amount_minor"] - 1}
        result = planner.plan_recovery(snapshot["business"], policy, snapshot["records"], plan["target_date"],
                                       basis_dates=derived["likely_dates"], required_actions=fixed)
        self.assertFalse(result["bundles"])
        self.assertEqual(self.app.store.snapshot(business_id)["snapshot_hash"], snapshot["snapshot_hash"])

    def test_locked_counter_terms_cannot_reintroduce_a_security_blocked_record(self):
        _, snapshot, derived = self.business("D06")
        plan = self.app.propose(snapshot["business"]["business_id"], None, "agent:test")
        with self.assertRaisesRegex(ValidationError, "security-blocked"):
            planner.plan_recovery(snapshot["business"], snapshot["policy"], snapshot["records"], plan["target_date"],
                                  basis_dates=derived["likely_dates"], required_actions=plan["bundles"][0]["actions"],
                                  blocked={"B1": "Changed bank account"})

    def test_optimistic_search_cannot_override_independent_risk_estimate(self):
        _, snapshot, derived = self.business("D06")

        def simulate(*args, **kwargs):
            probability = .0 if kwargs["seed"] == 42 else .30
            return {"probability_breach": probability, "futures_short_of_20": round(probability * 20)}

        with patch.object(analytics, "monte_carlo", side_effect=simulate):
            result = planner.plan_recovery(snapshot["business"], snapshot["policy"], snapshot["records"],
                                           snapshot["business"]["default_target_date"],
                                           basis_dates=derived["likely_dates"], mc_seed=42, mc_runs=400)
        self.assertTrue(result["bundles"])
        for bundle in result["bundles"]:
            self.assertEqual(bundle["probability_breach_after"], .30)
            self.assertEqual(bundle["risk_evaluation"]["search_probability_breach"], .0)
            self.assertFalse(bundle["risk_target_met"])

    def test_counter_repair_respects_owners_zero_discount_constraint(self):
        business_id, _, _ = self.business("D06")
        plan = self.app.propose(business_id, None, "agent:test", max_discount_bps=0)
        mandate, _ = _approve(self.app, business_id, plan)
        self.assertEqual(self.app.negotiate(business_id, mandate["mandate_id"], "agent:test")["status"], "countered")
        revised = self.app.accept_counter(business_id, mandate["mandate_id"], "agent:test")
        self.assertTrue(all(action["type"] == "supplier_deferral" for action in revised["bundles"][0]["actions"]))
        self.assertFalse(revised["bundles"][0]["risk_target_met"])
        self.assertIn("explicit residual-risk acknowledgement", revised["explanation"])


if __name__ == "__main__":
    unittest.main()
