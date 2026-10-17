"""Scoring and one-shot protocol tests; injected answers are not quality evidence."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_screening_v7 import score_records, start_run, verify_author_seal
from scripts.evaluate_screening_v6 import case_record
from tideway.semantic_screening import semantic_classify


class ScreeningEvidence(unittest.TestCase):
    def test_attack_review_and_unavailable_are_scored_on_separate_denominators(self):
        rows = []
        for i, (attack, review, label) in enumerate(((True, False, "uncertain"), (False, True, "review"),
                                                  (False, False, "benign"), (True, True, "attack"))):
            class Client:
                def screen(self, text, enabled=True):
                    categories = ["payment_detail_change"] if label == "review" else ["payment_redirect"] if label == "attack" else []
                    return semantic_classify(text, lambda *_: json.dumps({"label": label, "categories": categories, "reason": "Test only"}))
            case = {"id": str(i), "language": "en", "category": "test", "label": "malicious" if attack else "benign",
                    "review_signal": "payment_details" if review else "none", "text": "Invoice total 400."}
            rows.append(case_record(case, Client(), None))
        metrics = score_records(rows)
        self.assertEqual(metrics["semantic_attack"]["fn"], 1)
        self.assertEqual(metrics["semantic_attack"]["fp"], 0)
        self.assertEqual(metrics["combined_warning"]["tp"], 3)
        self.assertEqual(metrics["combined_warning"]["tn"], 1)
        self.assertEqual(metrics["combined_attack"]["fn"], 1)
        self.assertEqual(metrics["legitimate_payment_review"]["tp"], 1)
        self.assertEqual(metrics["legitimate_payment_review"]["fn"], 0)
        self.assertEqual(metrics["legitimate_payment_review"]["total"], 2)

    def test_started_or_partial_run_cannot_be_silently_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "run"
            start_run(p, {"scope": "test"})
            with self.assertRaises(FileExistsError):
                start_run(p, {"scope": "retry"})
            self.assertEqual(json.loads((p / "started.json").read_text())["scope"], "test")

    def test_fresh_evaluation_requires_matching_independent_author_seal(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "fixture.json"
            p.write_text('{"cases":[]}', encoding="utf-8")
            seal = Path(folder) / "seal.json"
            seal.write_text('{"fixture_sha256":"wrong"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_author_seal(p, seal)

    def test_author_seal_sha256_field_is_verified_without_changing_the_seal(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "fixture.json"
            p.write_bytes(b'{"cases":[]}\n')
            seal = Path(folder) / "seal.json"
            value = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            seal.write_text(json.dumps(value))
            before = seal.read_bytes()
            self.assertEqual(verify_author_seal(p, seal), value)
            self.assertEqual(seal.read_bytes(), before)
