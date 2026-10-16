"""Post-observation containment regressions, using injected outputs, not a new blind score."""
import json
import unittest

from tideway.service import Tideway
from tideway.tidelm import TideLM


BUSINESS = "shapla-services"


def selection(tool, **args):
    return {"intent": "grounding_regression", "calls": [{"tool": tool, "args": args}]}


class ModelArgumentGrounding(unittest.TestCase):
    def setUp(self):
        self.app = Tideway(":memory:")
        self.addCleanup(self.app.store.close)

    def ask(self, question, output):
        return TideLM(generator=lambda _s, _u: json.dumps(output)).ask(self.app, BUSINESS, None, question, "owner")

    def assert_stopped(self, question, output):
        before = self.app.store.snapshot(BUSINESS)["snapshot_hash"]
        reply = self.ask(question, output)
        self.assertEqual(reply["results"], [])
        self.assertEqual(reply["trace"], [])
        self.assertEqual(reply["decision_rationale"]["outcome"], "clarification_or_refusal")
        self.assertEqual(self.app.store.snapshot(BUSINESS)["snapshot_hash"], before)
        self.assertEqual(self.app.store.executions(BUSINESS), [])
        self.assertEqual(self.app.store.live_mandates(BUSINESS), [])
        self.assertIsNone(self.app.store.latest_plan(BUSINESS, "2026-10-31"))
        return reply

    def test_observed_M23_day_count_cannot_supply_missing_credit_amount(self):
        self.assert_stopped("Should Bay Logistics receive new credit with 30 days to pay?",
                            selection("credit_check", customer="Bay Logistics", amount=30, terms_days=30))

    def test_observed_M25_unknown_counterparty_cannot_be_replaced_by_ledger_customer(self):
        self.assert_stopped("Assess a BDT 6,000 credit sale to Purple Island Imports for 15 days.",
                            selection("credit_check", customer="Nila Traders", amount=6000, terms_days=15))

    def test_observed_M26_shortened_name_cannot_grant_full_customer_scope(self):
        self.assert_stopped("Show the payment history for Nila.", selection("customer_report", customer="Nila Traders"))

    def test_amount_terms_cannot_be_swapped_or_inferred_from_an_invoice_reference(self):
        for question, amount, term in (
            ("Assess Nila Traders BDT 90 credit for 30 days.", 30, 90),
            ("Assess Nila Traders invoice reference 30 on 15 day credit terms.", 30, 15),
            ("Assess Nila Traders BDT 30 credit; I have not chosen a payment term.", 30, 30),
            ("Assess Nila Traders credit on 2026-10-30 for 15 days.", 30, 15),
        ):
            with self.subTest(question=question):
                self.assert_stopped(question, selection("credit_check", customer="Nila Traders", amount=amount, terms_days=term))

    def test_same_numeric_value_requires_two_separate_money_and_day_mentions(self):
        reply = self.ask("Assess Nila Traders BDT 30 credit for 30 days.",
                         selection("credit_check", customer="Nila Traders", amount=30, terms_days=30))
        result = reply["results"][0]["result"]
        self.assertEqual(result["amount_minor"], 3000)
        self.assertEqual(result["terms_days"], 30)

    def test_explicit_decimal_scaled_and_credit_on_amounts_still_execute(self):
        for question, amount in (
            ("Give Nila Traders BDT 500.25 credit for 30 days?", 500.25),
            ("Offer Nila Traders BDT 12k credit on net 30 terms.", 12000),
            ("Should I give Nila Traders 30 days credit on 20,000?", 20000),
        ):
            with self.subTest(question=question):
                reply = self.ask(question, selection("credit_check", customer="Nila Traders", amount=amount, terms_days=30))
                self.assertEqual(reply["results"][0]["result"]["amount_minor"], round(amount * 100))

    def test_complete_names_allow_case_spaces_possessives_and_adjacent_CJK(self):
        for question in ("Show nila   traders payment history.", "Summarise Nila Traders' previous payments.",
                         "请查看Nila Traders的付款记录。"):
            with self.subTest(question=question):
                reply = self.ask(question, selection("customer_report", customer="Nila Traders"))
                self.assertEqual(reply["results"][0]["result"]["customers"][0]["customer"], "Nila Traders")

    def test_name_prefixes_and_unrequested_hypothetical_changes_are_refused(self):
        self.assert_stopped("Show the history for Nila TradersExtra.", selection("customer_report", customer="Nila Traders"))
        self.assert_stopped("What if Purple Island Imports pays 15 days late?",
                            selection("what_if", customer_delays={"Nila Traders": 15}))
        self.assert_stopped("Draft a reminder for Nila.", selection("draft_reminders", customers=["Nila Traders"]))

    def test_second_model_selection_cannot_add_an_ungrounded_credit_check(self):
        outputs = iter([selection("propose_plan"), selection("credit_check", customer="Nila Traders", amount=30, terms_days=30)])
        reply = TideLM(generator=lambda _s, _u: json.dumps(next(outputs))).ask(
            self.app, BUSINESS, None, "Propose a recovery; consider Nila Traders with 30 days credit terms.", "owner")
        self.assertEqual(reply["model_iterations"], 2)
        self.assertNotIn("credit_check", [row["tool"] for row in reply["trace"]])
        self.assertEqual(reply["decision_rationale"]["outcome"], "clarification_or_refusal")
        self.assertIsNone(self.app.store.latest_plan(BUSINESS, "2026-10-31"))

    def test_conditional_no_gap_request_observes_cash_before_declining_proposal(self):
        with self.app.store.connect() as db:
            db.execute("UPDATE businesses SET opening_cash_minor=1000000000 WHERE id=?", (BUSINESS,))
        reply = self.ask("Check whether we need a recovery proposal; suggest one only if there is a cash gap.",
                         selection("simulate_risk"))
        self.assertEqual(reply["model_iterations"], 1)
        self.assertEqual({row["tool"] for row in reply["results"]}, {"project_cash", "simulate_risk", "security_check"})
        self.assertEqual(reply["decision_rationale"]["outcome"], "no_action_needed")
        self.assertEqual(reply["decision_rationale"]["reserve_shortfall_minor"], 0)
        self.assertIsNone(self.app.store.latest_plan(BUSINESS, "2026-10-31"))

    def test_conditional_gap_never_fabricates_omitted_proposal_constraints(self):
        reply = self.ask("Check whether we need a recovery proposal; suggest one only if there is a cash gap.",
                         selection("simulate_risk"))
        self.assertEqual(reply["decision_rationale"]["outcome"], "cash_gap_needs_proposal")
        self.assertGreater(reply["decision_rationale"]["reserve_shortfall_minor"], 0)
        self.assertIsNone(self.app.store.latest_plan(BUSINESS, "2026-10-31"))


if __name__ == "__main__":
    unittest.main()
