"""The UI must distinguish installed-weight evidence from an older benchmark."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tideway import service
from tideway.ml.deployed_evaluation import ROOT
from tideway.server import STATIC


class TidePayCardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.folder = self.root / "evidence/readiness-v3/tidepay"
        self.folder.mkdir(parents=True)
        self.model = self.root / "tideway/ml/tidepay_model.json"
        self.model.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "tideway/ml/tidepay_model.json", self.model)
        for name in ("report.json", "artifact_sha256.json"):
            shutil.copyfile(ROOT / "evidence/readiness-v3/tidepay" / name, self.folder / name)

    def test_verified_summary_refers_to_exact_weights_and_preserves_cold_start_caveat(self):
        summary = service.deployed_tidepay_evaluation(self.root)
        report = json.loads((self.folder / "report.json").read_text())
        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "verified")
        self.assertEqual(summary["artifact_sha256"], hashlib.sha256(self.model.read_bytes()).hexdigest())
        self.assertEqual(summary["test_invoices"], report["balance"]["test"]["n"])
        self.assertEqual(summary["results"], report["results"])
        self.assertEqual(summary["cold_start"]["deployed"], report["subgroups"]["history:none"]["deployed"])
        self.assertEqual(summary["cold_start"]["prior"], report["subgroups"]["history:none"]["historical_training_prior"])
        self.assertIn("does not establish real-world accuracy", summary["note"])

    def test_replaced_weights_do_not_inherit_saved_scores(self):
        self.model.write_bytes(self.model.read_bytes() + b"\n")
        summary = service.deployed_tidepay_evaluation(self.root)
        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "artifact_mismatch")
        self.assertNotIn("results", summary)

    def test_missing_corrupt_and_tampered_reports_have_honest_fallback(self):
        report_path = self.folder / "report.json"
        original = report_path.read_bytes()
        for replacement in (None, b"{not json}", original + b"\n"):
            with self.subTest(replacement=replacement is None):
                if replacement is None:
                    report_path.unlink()
                else:
                    report_path.write_bytes(replacement)
                summary = service.deployed_tidepay_evaluation(self.root)
                self.assertFalse(summary["available"])
                self.assertNotIn("results", summary)
                self.assertIn("reason", summary)
                report_path.write_bytes(original)

    def test_cohort_mismatch_is_rejected_even_with_matching_file_manifest(self):
        report = json.loads((self.folder / "report.json").read_text())
        report["results"]["deployed"]["n"] -= 1
        report_bytes = json.dumps(report).encode()
        (self.folder / "report.json").write_bytes(report_bytes)
        (self.folder / "artifact_sha256.json").write_text(json.dumps({"report.json": hashlib.sha256(report_bytes).hexdigest()}))
        summary = service.deployed_tidepay_evaluation(self.root)
        self.assertFalse(summary["available"])
        self.assertNotIn("results", summary)

    def test_historical_cache_cannot_skip_current_artifact_check(self):
        with patch.object(service, "_CARD", {"meta": {}, "results": {}}), \
                patch.object(service, "deployed_tidepay_evaluation", side_effect=[
                    {"available": True, "status": "verified"},
                    {"available": False, "status": "artifact_mismatch"}]) as loader:
            self.assertTrue(service.tidepay_card()["deployed_evaluation"]["available"])
            self.assertFalse(service.tidepay_card()["deployed_evaluation"]["available"])
            self.assertEqual(loader.call_count, 2)

    def test_only_explicit_public_evidence_files_are_mapped(self):
        expected = {"/benchmarks/tidepay-deployed.json": "../evidence/readiness-v3/tidepay/report.json",
                    "/benchmarks/tidepay-deployed-reliability.svg": "../evidence/readiness-v3/tidepay/reliability.svg"}
        for route, relative in expected.items():
            self.assertEqual(STATIC[route], relative)
            self.assertTrue((ROOT / "web" / relative).resolve().is_file())
        self.assertNotIn("/evidence/readiness-v3/tidepay/raw_dataset.jsonl", STATIC)


if __name__ == "__main__":
    unittest.main()
