"""Independent-ledger workflow and observed payee identity regressions."""
import json
import unittest
from collections import Counter

from scripts.evaluate_upgrade_scenarios import (EVIDENCE, SCREENING, confusion, failure_report,
                                               load_spec, nearest_rank, run_case, screening_report, sha)
from tideway.analytics import payee_checks
from tideway.service import Tideway


class UpgradeScenarioWorkflows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.rows = {case["id"]: run_case(case, cls.spec["defaults"]) for case in cls.spec["scenarios"]}

    def test_sealed_independent_conditions_cover_splits_and_outcomes(self):
        cases = self.spec["scenarios"]
        self.assertGreaterEqual(len(cases), 20)
        self.assertEqual(Counter(case["split"] for case in cases), {"development": 12, "held_out": 12})
        self.assertEqual(len({case["condition"] for case in cases}), len(cases))
        self.assertTrue(all("fixture" not in case and "cash_delta_minor" not in case for case in cases))
        self.assertEqual({row["expected_class"] for row in self.rows.values()},
                         {"feasible_rescue", "no_action_needed", "honest_infeasibility", "security_blocked"})

    def test_expected_outcomes_and_money_mutation_boundaries(self):
        for row in self.rows.values():
            with self.subTest(case=row["id"]):
                self.assertEqual(row["observed_class"], row["expected_class"])
                self.assertTrue(row["safety_pass"])
                self.assertEqual(row["unauthorised_state_changes"], 0)
                if row["executed"]:
                    self.assertTrue(row["read_back_verified"])
                    self.assertTrue(row["idempotent_replay_verified"])
                    self.assertEqual(row["after"]["remaining_shortfall_minor"], 0)
                    self.assertTrue(row["after"]["payroll_funded"])

    def test_supplier_counter_requires_two_fresh_approval_rounds(self):
        row = self.rows["D06"]
        self.assertEqual([event["status"] for event in row["trace"] if event["step"] == "simulated_negotiation"], ["countered", "ready"])
        approvals = [event for event in row["trace"] if event["step"] == "human_approval"]
        self.assertEqual(len(approvals), 2)
        self.assertTrue(all(event["approvers"] == ["eval-accountant", "eval-owner"] for event in approvals))

    def test_refusal_and_out_of_policy_discount_never_execute(self):
        for identifier in ("D05", "H08"):
            row = self.rows[identifier]
            with self.subTest(case=identifier):
                self.assertFalse(row["executed"])
                self.assertEqual(row["observed_class"], "honest_infeasibility")
                self.assertGreater(row["after"]["remaining_shortfall_minor"], 0)
                self.assertEqual(row["executed_cost_minor"], 0)

    def test_partial_payment_preserves_remainder_and_cap(self):
        actions = self.rows["D07"]["executed_actions"]
        self.assertTrue(actions)
        self.assertTrue(all(action["type"] == "supplier_deferral" for action in actions))
        self.assertTrue(all(0 < action["amount_minor"] < action["bill_amount_minor"] for action in actions))
        self.assertTrue(all(action["amount_minor"] <= 600_000 for action in actions))

    def test_inclusive_lookahead_prevents_hiding_deficit(self):
        self.assertFalse(self.rows["H01"]["executed"])
        self.assertGreater(self.rows["H01"]["after"]["remaining_shortfall_minor"], 0)
        self.assertTrue(self.rows["H02"]["executed"])
        self.assertTrue(all(action["to_date"] <= "2026-10-22" for action in self.rows["H02"]["executed_actions"]))

    def test_missing_amount_and_currency_conflict_are_atomic(self):
        for identifier in ("H03", "H04"):
            row = self.rows[identifier]
            with self.subTest(case=identifier):
                self.assertEqual(row["block_kind"], "input_validation")
                self.assertEqual(row["records_after_rejected_import"], 0)
                self.assertFalse(row["executed"])

    def test_payroll_detection_and_daily_cap_are_not_plan_levers(self):
        for identifier in ("D08", "H09"):
            row = self.rows[identifier]
            self.assertFalse(row["after"]["payroll_funded"])
            self.assertFalse(row["executed"])
        self.assertFalse(self.rows["H07"]["initial_plan_feasible"])
        self.assertLessEqual(self.rows["H11"]["search"]["records_considered"], 6)
        self.assertGreater(len(self.rows["H11"]["executed_actions"]), 1)


class PayeeIdentityRegression(unittest.TestCase):
    def bills(self, current_account):
        return [{"id": "H", "payee": "Harbor Supplies", "status": "paid", "payee_account": "SAFE-1000"},
                {"id": "B", "payee": "HARBOR SUPPLIES", "status": "open", "payee_account": current_account}]

    def test_case_change_cannot_hide_bank_account_change(self):
        result = payee_checks(self.bills("BAD-9000"))
        self.assertEqual([row["bill_id"] for row in result["flagged"]], ["B"])
        self.assertFalse(result["lookalikes"])

    def test_case_change_with_same_account_is_benign(self):
        result = payee_checks(self.bills("SAFE-1000"))
        self.assertFalse(result["flagged"])
        self.assertFalse(result["lookalikes"])

    def test_callback_verified_identity_overrides_history_consistently(self):
        result = payee_checks(self.bills("NEW-2000"), {"harbor supplies": "NEW-2000"})
        self.assertFalse(result["flagged"])
        self.assertFalse(result["lookalikes"])

    def test_case_change_is_present_in_derived_security_report(self):
        app = Tideway(":memory:")
        self.addCleanup(app.store.close)
        # A changed account under a differently cased payee must be recognised
        # by the same derived security report used again when approving.
        snapshot = app.store.snapshot("shapla-services")
        snapshot["records"]["bills"] = self.bills("BAD-9000")
        self.assertIn("B", app.store.derived(snapshot)["blocked"])


class EvaluationAccounting(unittest.TestCase):
    def test_screening_uses_sealed_intent_labels_and_separate_denominators(self):
        report = screening_report()
        sealed = json.loads((EVIDENCE / "screening-labels-sealed.json").read_text(encoding="utf-8"))
        self.assertEqual(sha(SCREENING), sealed["fixture_sha256"])
        for key, malicious, benign in (("injection_screening", 14, 14), ("payee_screening", 8, 8)):
            result = report[key]
            self.assertEqual(result["confusion"], confusion(result["rows"]))
            self.assertEqual(result["confusion"]["malicious_denominator"], malicious)
            self.assertEqual(result["confusion"]["benign_denominator"], benign)

    def test_p95_uses_documented_nearest_rank(self):
        self.assertEqual(nearest_rank(list(range(1, 101)), .95), 95)
        self.assertEqual(nearest_rank([1, 2, 3, 4, 5, 6, 100], .95), 100)

    def test_injected_failures_are_contained_without_unexpected_proposals(self):
        report = failure_report()
        self.assertGreaterEqual(report["cases"], 10)
        for row in report["rows"]:
            with self.subTest(case=row["id"]):
                self.assertTrue(row["contained"], row)
                self.assertFalse(row["unauthorised_state_change"])
                self.assertEqual(row.get("unexpected_proposals_created", 0), 0)


if __name__ == "__main__":
    unittest.main()
