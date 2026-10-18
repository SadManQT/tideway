import unittest

from tideway.agent import Agent, Pseudonyms, grounding_check
from tideway.service import Tideway


BUSINESS = "shapla-services"


class AgentPrivacyRegressionTests(unittest.TestCase):
    def setUp(self):
        self.app = Tideway(":memory:")
        self.addCleanup(self.app.store.close)

    def test_privacy_preview_scrubs_exact_case_variants_but_not_name_substrings(self):
        aliases = Pseudonyms(self.app.store.snapshot(BUSINESS)["records"])
        expected = aliases.forward["Nila Traders"]
        agent = Agent(self.app)

        for message in ("How is Nila Traders doing?", "How is nila traders doing?",
                        "How is NILA TRADERS doing?"):
            with self.subTest(message=message):
                content = agent.privacy_preview(BUSINESS, None, message)["initial_payload"]["input"][-1]["content"]
                self.assertEqual(content, f"How is {expected} doing?")

        content = agent.privacy_preview(BUSINESS, None, "Nila TradersExtra is unrelated.")["initial_payload"]["input"][-1]["content"]
        self.assertIn("Nila TradersExtra", content)
        self.assertNotIn(expected, content)

    def test_scrubbing_keeps_aliases_and_existing_account_contact_protection(self):
        aliases = Pseudonyms(self.app.store.snapshot(BUSINESS)["records"])
        expected = aliases.forward["Nila Traders"]
        existing_alias = next(alias for alias in aliases.backward if alias != expected)
        value = aliases.scrub(f"NILA TRADERS {existing_alias} AC-2201-4471 owner@example.com +8801712345678")

        self.assertEqual(value.count(expected), 1)
        self.assertEqual(value.count(existing_alias), 1)
        self.assertNotIn("AC-2201-4471", value)
        self.assertNotIn("owner@example.com", value)
        self.assertNotIn("+8801712345678", value)
        self.assertEqual(aliases.restore(aliases.scrub("Nila Traders")), "Nila Traders")


class GroundingCheckRegressionTests(unittest.TestCase):
    def test_small_unsupported_money_is_not_exempt(self):
        self.assertEqual(grounding_check("You need 30 dollars.", {}), ["30"])

    def test_day_count_and_calendar_date_remain_exempt(self):
        self.assertEqual(grounding_check("The delay is 30 days; the target date is 2026-10-31.", {}), [])

    def test_minor_unit_conversion_remains_supported(self):
        self.assertEqual(grounding_check("Cash falls to BDT 42,000.", [{"minimum_cash_minor": -4_200_000}]), [])


if __name__ == "__main__":
    unittest.main()
