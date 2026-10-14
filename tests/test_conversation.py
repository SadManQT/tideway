"""The conversational layer: small talk, varied context-aware answers and suggestions, no dead ends."""
import unittest

from tideway.agent import Agent
from tideway.conversation import classify
from tideway.service import Tideway

SHAPLA = "shapla-services"


class Conversation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Tideway(":memory:")
        cls.agent = Agent(cls.app)

    def ask(self, message):
        return self.agent.chat(SHAPLA, None, message, actor="agent:local", name="Nadia Rahman")

    def test_classifier_is_multilingual_and_strict(self):
        for text, label in (("hi", "greeting"), ("Good morning!", "greeting"), ("你好", "greeting"), ("hola", "greeting"),
                            ("assalamualaikum", "greeting"), ("thanks a lot", "thanks"), ("谢谢", "thanks"),
                            ("what can you do?", "help"), ("how is my business doing?", "status")):
            self.assertEqual(classify(text), label, text)
        for text in ("hi, can I pay payroll on the 31st?", "What if Nila Traders pays 10 days late?", "thanks for nothing, " * 4):
            self.assertIsNone(classify(text), text)

    def test_answers_differ_by_question(self):
        texts = {self.ask(m)["text"] for m in ("hi", "Can I pay salaries?", "Which customers pay late?",
                                                 "How does Bay Logistics usually pay?", "zzz")}
        self.assertEqual(len(texts), 5)

    def test_greeting_is_a_personal_live_briefing(self):
        text = self.ask("hello")["text"]
        self.assertTrue(text.startswith("Hi Nadia!"))
        self.assertIn("Shapla Services today", text)

    def test_suggestions_follow_the_topic(self):
        reply = self.ask("How does Bay Logistics usually pay?")
        self.assertIn("What if Bay Logistics pays 15 days late?", reply["suggestions"])
        self.assertLessEqual(len(reply["suggestions"]), 3)

    def test_credit_check_in_banglish(self):
        self.assertIn("Credit check for Nila Traders", self.ask("Nila Traders ke 50k credit dibo, 30 din?")["text"])

    def test_unknown_is_never_a_dead_end(self):
        reply = self.ask("zzz")
        self.assertIn("not sure", reply["text"])
        self.assertTrue(reply["suggestions"])

    def test_why_compares_the_alternatives(self):
        self.ask("Find me a rescue plan")
        self.assertIn("too risky", self.ask("why this plan?")["text"])


if __name__ == "__main__":
    unittest.main()
