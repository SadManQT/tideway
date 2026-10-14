"""Replies in the reader's language: detection, complete phrasebook, numbers identical across languages."""
import json
import string
import unittest

from tideway import i18n
from tideway.ml.tidelm_data import T
from tideway.service import Tideway
from tideway.tidelm import TideLM


def fields(template):
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


class Phrasebook(unittest.TestCase):
    def test_every_message_has_every_language_with_the_same_placeholders(self):
        for key, table in {**i18n.M, **i18n.SUGGESTIONS}.items():
            self.assertEqual(set(table), set(i18n.LANGUAGES), key)
            english = table["en"]
            for lang, text in table.items():
                if isinstance(english, str):
                    self.assertEqual(fields(text), fields(english), f"{key}/{lang}")
                else:
                    self.assertEqual(set(text), set(english), f"{key}/{lang}")

    def test_detects_the_language_of_every_training_template(self):
        for key, languages in T.items():
            for lang, templates in languages.items():
                for template in templates:
                    text = template.format(a="Nila Traders", b="Bay Logistics", days=10, days2=15, value=5000, terms=30,
                                           pct=2, d="2026-10-20")
                    if key in ("exclude", "discount", "safe"):  # fragments are appended to a plan request
                        text = T["plan"].get(lang, T["plan"]["en"])[0] + text
                    expected = "en" if lang in ("hinglish", "banglish") else lang
                    self.assertEqual(i18n.detect(text), expected, text)

    def test_dates_follow_the_reader(self):
        self.assertEqual(i18n.day("zh", "2026-10-31"), "10月31日")
        self.assertEqual(i18n.day("es", "2026-11-03"), "3 nov")
        self.assertEqual(i18n.day("en", "2026-10-31"), "31 Oct")


class LocalisedAnswers(unittest.TestCase):
    def test_same_numbers_in_every_language(self):
        app = Tideway(":memory:")
        plan = {"intent": "what_if", "calls": [{"tool": "what_if", "args": {"customer_delays": {"Bay Logistics": 20},
                                                                            "extra_expense": None, "drop_invoice_customer": None}}]}
        model = TideLM(generator=lambda _s, _u: json.dumps(plan))
        replies = {lang: model.ask(app, "shapla-services", None, question, "owner") for lang, question in (
            ("en", "What if Bay Logistics pays 20 days late?"), ("zh", "如果Bay Logistics晚20天付款会怎样？"),
            ("es", "¿Qué pasa si Bay Logistics paga 20 días tarde?"))}
        for lang, reply in replies.items():
            self.assertEqual(reply["lang"], lang)
            for figure in ("-BDT 57,000", "BDT 15,000", "BDT 77,000"):
                self.assertIn(figure, reply["text"], lang)
        self.assertIn("在这种情况下", replies["zh"]["text"])
        self.assertIn("Con ese cambio", replies["es"]["text"])


if __name__ == "__main__":
    unittest.main()
