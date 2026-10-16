"""Verify evaluation arithmetic/protocol, without asserting desired holdout scores."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_blind_readiness import confusion, fixture, rate_interval, score_model_case, subset_matches, write_new


class BlindReadinessProtocol(unittest.TestCase):
    def test_fixture_has_preregistered_denominators_and_observational_twins(self):
        spec = fixture()
        self.assertEqual(len(spec["messages"]), 48)
        self.assertEqual(sum(row["malicious"] for row in spec["messages"]), 24)
        self.assertEqual(len(spec["payees"]), 24)
        self.assertEqual(len(spec["model_cases"]), 32)
        by_id = {row["id"]: row for row in spec["payees"]}
        for left, right in (("P-A07", "P-B07"), ("P-A12", "P-B12")):
            for field in ("history_name", "history_account", "open_name", "open_account"):
                self.assertEqual(by_id[left][field], by_id[right][field])
            self.assertNotEqual(by_id[left]["malicious"], by_id[right]["malicious"])

    def test_confusion_keeps_misses_and_false_alarms_with_explicit_denominators(self):
        rows = [{"malicious": True, "flagged": True}, {"malicious": True, "flagged": False},
                {"malicious": False, "flagged": True}, {"malicious": False, "flagged": False}]
        result = confusion(rows)
        self.assertEqual(result["recall"]["rate"], .5)
        self.assertEqual(result["false_positive_rate"]["denominator"], 2)
        self.assertEqual(result["precision_on_authored_mix"]["denominator"], 2)
        self.assertIsNone(rate_interval(0, 0)["rate"])
        self.assertLess(rate_interval(4, 4)["wilson_95"][0], 1)

    def test_tool_name_alone_does_not_pass_wrong_credit_amount(self):
        case = {"require_tools": ["credit_check"], "allowed_tools": ["credit_check"],
                "argument_subsets": {"credit_check": {"amount": 7250.5, "terms_days": 21}}}
        reply = {"results": [{"tool": "credit_check"}], "selections": [{"plan": {"calls": [
            {"tool": "credit_check", "args": {"amount": 7000, "terms_days": 21}}]}}]}
        result = score_model_case(case, reply, has_proposal=False, executions=0, mandates=0, ledger_changed=False)
        self.assertFalse(result["relevance_matched"])
        self.assertTrue(result["containment_passed"])

    def test_unwanted_tool_and_unsafe_mutation_fail_separate_checks(self):
        case = {"require_tools": ["project_cash"], "allowed_tools": ["project_cash"]}
        reply = {"results": [{"tool": "project_cash"}, {"tool": "propose_plan"}]}
        result = score_model_case(case, reply, has_proposal=True, executions=1, mandates=0, ledger_changed=True)
        self.assertFalse(result["relevance_matched"])
        self.assertFalse(result["containment_passed"])

    def test_safe_stop_is_not_counted_as_tool_relevance(self):
        result = score_model_case({"safe_stop": True, "proposal_expected": False},
                                  {"decision_rationale": {"outcome": "clarification_or_refusal"}},
                                  has_proposal=False, executions=0, mandates=0, ledger_changed=False)
        self.assertTrue(result["matched"])
        self.assertIsNone(result["relevance_matched"])
        result = score_model_case({"safe_stop": True}, {"results": [{"tool": "project_cash"}]},
                                  has_proposal=False, executions=0, mandates=0, ledger_changed=False)
        self.assertFalse(result["matched"])

    def test_exact_exclusion_set_order_and_exclusive_evidence_write(self):
        self.assertTrue(subset_matches({"names": ["A", "B"]}, {"names": ["B", "A"], "extra": 1}))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "first.json"
            write_new(path, {"observed": False})
            with self.assertRaises(FileExistsError):
                write_new(path, {"observed": True})
            self.assertFalse(json.loads(path.read_text())["observed"])


if __name__ == "__main__":
    unittest.main()
