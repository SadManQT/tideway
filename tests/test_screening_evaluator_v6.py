"""Protocol/arithmetic tests: invented data and fake pipelines, never holdouts/models."""

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/evaluate_screening_v6.py"
SPEC = importlib.util.spec_from_file_location("screening_evaluator_v6", MODULE_PATH)
evaluator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluator)


def dummy_case(label="benign", review="none", identifier="arithmetic-only"):
    return {"id": identifier, "text": "invented test record", "label": label,
            "attack_intent": label == "malicious", "language": "test",
            "category": "arithmetic", "review_signal": review}


def dummy_result(label="benign", *, rules=None, combined=None, categories=None,
                 errors=None, raw='{"label":"benign","categories":[],"reason":"test"}'):
    encoded = raw.encode("utf-8")
    return {"label": label, "categories": categories or [], "reason": "invented test reason",
            "rule_flags": rules or [], "combined_flags": combined or [],
            "warning_required": label in {"attack", "review", "uncertain"} or bool(combined),
            "human_review_required": True, "trusted": False, "attempt_count": 1,
            "raw_output": raw, "raw_output_sha256": hashlib.sha256(encoded).hexdigest(),
            "raw_output_bytes": len(encoded), "raw_output_truncated": False,
            "errors": errors or [], "elapsed_ms": 1.25,
            "model_identity": {"model": "inert-test-double", "purpose": "classifier"}}


class FakeClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def screen(self, text, *, enabled=None):
        self.calls.append((text, enabled))
        return self.result


class ScreeningEvaluatorProtocolTests(unittest.TestCase):
    def test_confusion_matrix_and_rates(self):
        result = evaluator.confusion_counts([
            (True, True), (True, True), (False, True),
            (True, False), (False, False), (False, False), (True, None),
        ])
        self.assertEqual({key: result[key] for key in ("tp", "fp", "fn", "tn", "unscored", "total", "scored")},
                         {"tp": 2, "fp": 1, "fn": 1, "tn": 2, "unscored": 1, "total": 7, "scored": 6})
        self.assertAlmostEqual(result["precision"], 2 / 3)
        self.assertAlmostEqual(result["recall"], 2 / 3)
        self.assertAlmostEqual(result["false_positive_rate"], 1 / 3)
        self.assertAlmostEqual(result["coverage"], 6 / 7)

    def test_zero_denominators_remain_undefined(self):
        empty = evaluator.confusion_counts([])
        for key in ("precision", "recall", "specificity", "false_positive_rate",
                    "accuracy_on_scored_cases", "f1", "coverage"):
            self.assertIsNone(empty[key])

    def test_uncertainty_is_not_dropped_from_primary_attack_denominator(self):
        result = dummy_result("uncertain", errors=["deliberate_test_error"])
        records = [evaluator.case_record(dummy_case("malicious"), FakeClient(result), None),
                   evaluator.case_record(dummy_case("benign"), FakeClient(result), None)]
        metrics = evaluator.summarize_records(records)
        primary = metrics["semantic_attack"]
        self.assertEqual((primary["fn"], primary["tn"], primary["total"]), (1, 1, 2))
        self.assertEqual(primary["recall"], 0)
        self.assertEqual(primary["accuracy_on_scored_cases"], 0.5)
        self.assertEqual(primary["decision_coverage"], 0)
        self.assertEqual(primary["selective_metrics"]["unscored"], 2)
        self.assertEqual(metrics["combined_warning"]["tp"], 1)
        self.assertEqual(metrics["combined_warning"]["fp"], 1)

    def test_review_is_separate_from_attack_intent(self):
        result = dummy_result("review", rules=["payment_detail_change", "hidden_characters"],
                              combined=["payment_detail_change", "hidden_characters"],
                              categories=["payment_detail_change"])
        record = evaluator.case_record(dummy_case(review="payment_details"), FakeClient(result), None)
        self.assertFalse(record["rule_attack_detected"])
        self.assertFalse(record["semantic_attack_detected"])
        self.assertTrue(record["predicted_payment_review"])
        self.assertTrue(record["predicted_generic_review"])
        self.assertTrue(record["combined_warning"])

    def test_actual_screen_api_is_called_once_with_enabled_true(self):
        raw = ' {"label":"attack"}\n<literal text>\u200b'
        client = FakeClient(dummy_result("attack", raw=raw))
        record = evaluator.case_record(dummy_case("malicious"), client, None,
                                       runtime_status={"runtime": "inert"}, source_seal_sha256="test-source")
        self.assertEqual(client.calls, [("invented test record", True)])
        self.assertEqual(record["model_attempt"]["raw_output"], raw)
        self.assertEqual(record["model_attempt"]["elapsed_ms"], 1.25)
        self.assertEqual(record["model_attempt"]["execution_source_seal_sha256"], "test-source")

    def test_contract_violation_preserves_raw_evidence(self):
        result = dummy_result()
        result["trusted"] = True
        record = evaluator.case_record(dummy_case(), FakeClient(result), None)
        self.assertIsNotNone(record["pipeline_error"])
        self.assertEqual(record["model_attempt"]["raw_output"], result["raw_output"])
        self.assertEqual(record["scope"]["financial_authority"], "none")

    def test_bad_raw_hash_is_recorded_without_retry(self):
        result = dummy_result(rules=["instruction_override"])
        result["raw_output_sha256"] = "0" * 64
        client = FakeClient(result)
        record = evaluator.case_record(dummy_case(), client, None)
        self.assertEqual(len(client.calls), 1)
        self.assertIsNotNone(record["pipeline_error"])
        self.assertTrue(record["rule_attack_detected"])
        self.assertEqual(record["pipeline_result"]["raw_output_sha256"], "0" * 64)

    def test_typed_evidence_keeps_literal_data(self):
        @dataclass
        class DummyAttempt:
            raw_generation: str
            error: str | None
        normalized = evaluator.json_compatible(DummyAttempt("literal\nraw", "test error"))
        self.assertEqual(normalized, {"raw_generation": "literal\nraw", "error": "test error"})
        with self.assertRaises(ValueError):
            evaluator.json_compatible(float("nan"))

    def test_initialization_failure_keeps_case_and_primary_denominator(self):
        record = evaluator.case_record(dummy_case("malicious"), None, "deliberate init failure")
        metrics = evaluator.summarize_records([record])
        self.assertEqual(metrics["semantic_attack"]["fn"], 1)
        self.assertEqual(metrics["semantic_attack"]["total"], 1)
        self.assertEqual(metrics["pipeline_exception_cases"], 1)

    def test_no_generation_error_retains_zero_attempt_evidence(self):
        result = dummy_result("uncertain", errors=["deliberate_unavailable"], raw="")
        result.update({"attempt_count": 0, "raw_output_sha256": None})
        record = evaluator.case_record(dummy_case("malicious"), FakeClient(result), None)
        self.assertIsNone(record["pipeline_error"])
        self.assertEqual(record["model_attempt"]["attempt_count"], 0)
        self.assertFalse(record["semantic_attack_detected"])

    def test_exclusive_writes_and_partial_directory_block_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = evaluator.evidence_paths(Path(folder))
            evaluator.write_new_json(paths["start"], {"test": True})
            with self.assertRaises(FileExistsError):
                evaluator.write_new_json(paths["start"], {"test": False})
            with self.assertRaises(evaluator.EvidenceError):
                evaluator.assert_unstarted(paths)
        with tempfile.TemporaryDirectory() as folder:
            paths = evaluator.evidence_paths(Path(folder))
            paths["run"].mkdir(parents=True)
            with self.assertRaises(evaluator.EvidenceError):
                evaluator.assert_unstarted(paths)

    def test_source_manifest_covers_resources_not_bytecode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = root / "tideway"
            package.mkdir()
            (package / "inert.py").write_text("# inert test file\n", encoding="utf-8")
            (package / "data.json").write_text("{}\n", encoding="utf-8")
            cache = package / "__pycache__"
            cache.mkdir()
            (cache / "inert.pyc").write_bytes(b"generated")
            self.assertEqual(set(evaluator.implementation_manifest(root)),
                             {"tideway/inert.py", "tideway/data.json"})

    def test_external_artifact_change_is_measurable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "inert-model.bin"
            path.write_bytes(b"first inert bytes")
            config = {"artifact_paths": {"model_file": str(path)}}
            initial = evaluator.artifact_manifest(config)
            path.write_bytes(b"changed inert bytes")
            self.assertNotEqual(initial, evaluator.artifact_manifest(config))

    def test_complete_fake_run_starts_before_pipeline_and_cannot_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = evaluator.evidence_paths(root)
            cases = [dummy_case("malicious", identifier="dummy-positive"),
                     dummy_case("benign", identifier="dummy-negative")]
            evaluator.write_new_json(paths["fixture"], {"provenance": "independently_authored_synthetic", "cases": cases})
            evaluator.write_new_json(paths["author"], {
                "fixture_path": evaluator.FIXTURE_REL.as_posix(),
                "fixture_sha256": evaluator.sha256_file(paths["fixture"]),
                "counts": evaluator.case_counts(cases),
            })
            (root / "tideway").mkdir()
            (root / "tideway/inert.py").write_text("# never imported\n", encoding="utf-8")
            (root / "scripts").mkdir()
            (root / "scripts/evaluate_screening_v6.py").write_bytes(MODULE_PATH.read_bytes())
            artifact = root / "inert.bin"
            artifact.write_bytes(b"not a model or executable")
            config = {"base_url": "http://127.0.0.1:1/v1", "served_model_id": "inert-test",
                      "artifact_paths": {"model_file": str(artifact)}, "scope": evaluator.CLASSIFIER_SCOPE}
            evaluator.seal_execution_source(root, config)
            outer = self

            class FakeActualClient:
                def status(self):
                    outer.assertTrue(paths["start"].exists())
                    return {"model": "inert-test"}

                def screen(self, text, *, enabled=None):
                    outer.assertTrue(paths["start"].exists())
                    outer.assertTrue(enabled)
                    return dummy_result("uncertain")

            with mock.patch.object(evaluator.importlib, "import_module", return_value=SimpleNamespace(TideLM=FakeActualClient)), \
                 mock.patch.dict(evaluator.os.environ, {}, clear=False):
                result_path = evaluator.run_evaluation(root)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["completed_case_count"], 2)
            self.assertEqual(result["metrics"]["semantic_attack"]["total"], 2)
            self.assertEqual(len(paths["attempts"].read_text(encoding="utf-8").splitlines()), 4)
            with self.assertRaises(evaluator.EvidenceError):
                evaluator.run_evaluation(root)


if __name__ == "__main__":
    unittest.main()
