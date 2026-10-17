"""Arithmetic/protocol tests using invented booleans, never the holdout labels."""

import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/evaluate_screening_v5.py"
SPEC = importlib.util.spec_from_file_location("screening_evaluator_v5", MODULE_PATH)
evaluator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluator)


class ScreeningEvaluatorArithmeticTests(unittest.TestCase):
    def test_confusion_matrix_and_rates(self):
        result = evaluator.confusion_counts([
            (True, True), (True, True), (False, True),
            (True, False), (False, False), (False, False), (True, None),
        ])
        self.assertEqual({key: result[key] for key in ("tp", "fp", "fn", "tn", "errors", "total", "scored")},
                         {"tp": 2, "fp": 1, "fn": 1, "tn": 2, "errors": 1, "total": 7, "scored": 6})
        self.assertAlmostEqual(result["precision"], 2 / 3)
        self.assertAlmostEqual(result["recall"], 2 / 3)
        self.assertAlmostEqual(result["false_positive_rate"], 1 / 3)
        self.assertAlmostEqual(result["coverage"], 6 / 7)
        self.assertAlmostEqual(result["f1"], 2 / 3)

    def test_zero_denominators_remain_undefined(self):
        empty = evaluator.confusion_counts([])
        for key in ("precision", "recall", "specificity", "false_positive_rate",
                    "accuracy_on_scored_cases", "f1", "coverage"):
            self.assertIsNone(empty[key])
        all_negative = evaluator.confusion_counts([(False, False)])
        self.assertIsNone(all_negative["precision"])
        self.assertIsNone(all_negative["recall"])
        self.assertEqual(all_negative["specificity"], 1.0)

    def test_review_flags_do_not_imply_attack(self):
        dummy_case = {"id": "arithmetic-only", "text": "ordinary record", "label": "benign",
                      "language": "test", "category": "test", "review_signal": "payment_details"}
        record = evaluator.case_record(dummy_case,
                                       lambda _text: ["payment_detail_change", "hidden_characters"], None)
        self.assertFalse(record["predicted_attack"])
        self.assertTrue(record["predicted_payment_review"])
        self.assertTrue(record["predicted_generic_review"])
        self.assertEqual(record["unclassified_flags"], [])

    def test_unknown_flags_are_preserved_without_intent_inference(self):
        dummy_case = {"id": "arithmetic-only", "text": "ordinary record", "label": "benign",
                      "language": "test", "category": "test", "review_signal": "none"}
        record = evaluator.case_record(dummy_case, lambda _text: ["future_warning", "future_warning"], None)
        self.assertEqual(record["raw_flags"], ["future_warning", "future_warning"])
        self.assertEqual(record["unclassified_flags"], ["future_warning"])
        self.assertFalse(record["predicted_attack"])

    def test_scanner_errors_are_unscored_and_case_is_retained(self):
        dummy_case = {"id": "arithmetic-only", "text": "ordinary record", "label": "malicious",
                      "language": "test", "category": "test", "review_signal": "none"}
        record = evaluator.case_record(dummy_case, None, "deliberate import failure")
        self.assertEqual(record["case"], dummy_case)
        self.assertIsNone(record["predicted_attack"])
        metrics = evaluator.summarize_records([record])
        self.assertEqual(metrics["attack"]["errors"], 1)
        self.assertEqual(metrics["attack"]["fn"], 0)
        self.assertEqual(metrics["per_language"]["test"]["total"], 1)
        self.assertEqual(metrics["per_category"]["test"]["total"], 1)

    def test_exclusive_writes_and_started_marker_refuse_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = evaluator.evidence_paths(root)
            evaluator.assert_unstarted(paths)
            evaluator.write_new_json(paths["start"], {"test": True})
            with self.assertRaises(FileExistsError):
                evaluator.write_new_json(paths["start"], {"test": False})
            with self.assertRaises(evaluator.EvidenceError):
                evaluator.assert_unstarted(paths)

    def test_partial_output_directory_also_blocks_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = evaluator.evidence_paths(Path(folder))
            paths["run"].mkdir(parents=True)
            with self.assertRaises(evaluator.EvidenceError):
                evaluator.assert_unstarted(paths)

    def test_source_manifest_covers_resources_and_ignores_generated_bytecode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = root / "tideway"
            package.mkdir()
            (package / "dummy.py").write_text("# inert test file\n", encoding="utf-8")
            (package / "dummy.json").write_text("{}\n", encoding="utf-8")
            cache = package / "__pycache__"
            cache.mkdir()
            (cache / "dummy.pyc").write_bytes(b"generated")
            manifest = evaluator.implementation_manifest(root)
            self.assertEqual(set(manifest), {"tideway/dummy.py", "tideway/dummy.json"})
            initial_hash = manifest["tideway/dummy.json"]
            (package / "dummy.json").write_text('{"changed":true}\n', encoding="utf-8")
            self.assertNotEqual(evaluator.implementation_manifest(root)["tideway/dummy.json"], initial_hash)


if __name__ == "__main__":
    unittest.main()
