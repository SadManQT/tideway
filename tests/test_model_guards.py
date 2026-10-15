"""Regression coverage for the TideLM plan validation boundary."""
import json
import unittest

from tideway.copilot import run_plan, validate_plan
from tideway.domain import ValidationError
from tideway.service import Tideway
from tideway.tidelm import TideLM


BUSINESS = "shapla-services"


def model(reply):
    return TideLM(generator=lambda _system, _user: json.dumps(reply))


class ModelPlanGuards(unittest.TestCase):
    def setUp(self):
        self.app = Tideway(":memory:")

    def ask(self, plan):
        return model(plan).ask(self.app, BUSINESS, None, "run this scenario", "owner")

    def test_shallow_extra_expense_is_a_safe_refusal(self):
        plan = {"intent": "what_if", "calls": [{"tool": "what_if", "args": {"extra_expense": 5}}]}

        reply = self.ask(plan)

        self.assertEqual(reply["results"], [])
        self.assertIn("I couldn't do that safely", reply["text"])
        self.assertIn("extra_expense must be an object", reply["text"])

    def test_malformed_argument_shapes_are_validation_errors(self):
        bad_plans = (
            {"tool": "project_cash", "args": {"scenario": "unknown"}},
            {"tool": "what_if", "args": {"customer_delays": []}},
            {"tool": "what_if", "args": {"customer_delays": {"Nila Traders": "5"}}},
            {"tool": "what_if", "args": {"customer_delays": {"Nila Traders": 91}}},
            {"tool": "what_if", "args": {"extra_expense": {"amount": 0, "date": "2026-10-15"}}},
            {"tool": "what_if", "args": {"extra_expense": {"amount": 5}}},
            {"tool": "what_if", "args": {"extra_expense": {"amount": 5, "date": "2026-10-15", "note": "x"}}},
            {"tool": "propose_plan", "args": {"max_discount_pct": 10.1}},
            {"tool": "credit_check", "args": {"customer": "Nila Traders", "amount": "500", "terms_days": 30}},
            {"tool": "credit_check", "args": {"customer": "Nila Traders", "amount": 500, "terms_days": 181}},
            {"tool": "draft_reminders", "args": {"customers": "Nila Traders"}},
        )
        for call in bad_plans:
            with self.subTest(call=call):
                with self.assertRaises(ValidationError):
                    validate_plan({"intent": "test", "calls": [call]})

    def test_malformed_plan_cannot_reach_tool_execution(self):
        plan = {"intent": "what_if", "calls": [{"tool": "what_if", "args": {"extra_expense": 5}}]}

        with self.assertRaises(ValidationError):
            run_plan(self.app, BUSINESS, None, plan, "agent:test")

    def test_valid_nested_arguments_still_execute(self):
        plan = {"intent": "what_if", "calls": [{"tool": "what_if", "args": {
            "customer_delays": {},
            "extra_expense": {"amount": 5, "date": "2026-10-15"},
            "drop_invoice_customer": None,
        }}]}

        reply = self.ask(plan)

        self.assertEqual([item["tool"] for item in reply["results"]], ["what_if"])
        self.assertIn("Nothing was saved", reply["text"])


if __name__ == "__main__":
    unittest.main()
