"""The viewing-only survey generator stays deterministic and separate from evidence."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_demo_surveys import (
    SECURITY_CASES,
    SECURITY_CSV_HEADERS,
    SME_CSV_HEADERS,
    SME_TASKS,
    build_dataset,
    validate_dataset,
    write_dataset,
)


ROOT = Path(__file__).resolve().parents[1]


class DemoSurveyData(unittest.TestCase):
    def test_dataset_has_two_complete_fictional_cohorts(self):
        dataset = build_dataset()
        validate_dataset(dataset)
        self.assertEqual(dataset["evidence_status"], "synthetic_viewing_only_not_observed")
        self.assertEqual(len(dataset["cohorts"]["sme"]["participants"]), 20)
        self.assertEqual(len(dataset["cohorts"]["security"]["participants"]), 20)
        self.assertEqual(dataset["canonical_evidence"]["real_sme_participants"], 0)
        self.assertEqual(dataset["canonical_evidence"]["real_external_security_reviewers"], 0)

    def test_sme_rows_cover_tasks_model_boundaries_and_complete_sus(self):
        participants = build_dataset()["cohorts"]["sme"]["participants"]
        self.assertEqual({item["id"] for item in participants}, {f"SME-{number:02d}" for number in range(1, 21)})
        for participant in participants:
            self.assertEqual(set(participant["tasks"]), set(SME_TASKS))
            self.assertEqual(len(participant["sus_responses"]), 10)
            self.assertTrue(all(1 <= value <= 5 for value in participant["sus_responses"]))
            t3 = participant["tasks"]["T3"]
            if participant["model_status"] == "available":
                self.assertIn(t3["status"], {"completed", "assisted", "failed"})
            elif participant["model_status"] == "unavailable":
                self.assertEqual(t3["status"], "unavailable_model")
                self.assertIsNone(t3["seconds"])
            else:
                self.assertEqual(t3["status"], "not_attempted")
                self.assertIsNone(t3["seconds"])

    def test_security_rows_cover_all_cases_and_have_mixed_reactions(self):
        participants = build_dataset()["cohorts"]["security"]["participants"]
        self.assertEqual({item["id"] for item in participants}, {f"SEC-P{number:02d}" for number in range(1, 21)})
        for participant in participants:
            self.assertEqual(set(participant["cases"]), set(SECURITY_CASES))
            self.assertTrue(all(item["safe_final_action"] for item in participant["cases"].values()))
            self.assertTrue(all(item["seconds"] > 0 for item in participant["cases"].values()))
        self.assertGreater(sum(item["overall_behavior"]["prompted_cases"] for item in participants), 0)
        self.assertGreater(sum(item["overall_behavior"]["initially_trusted_cases"] for item in participants), 0)

    def test_checked_in_outputs_match_generator_and_keep_canonical_status_empty(self):
        checked_in = ROOT / "demo-data"
        self.assertEqual(
            json.loads((checked_in / "synthetic-surveys.json").read_text(encoding="utf-8")),
            build_dataset(),
        )
        with (checked_in / "sme-survey.csv").open(encoding="utf-8", newline="") as handle:
            checked_in_sme_rows = list(csv.DictReader(handle))
        self.assertEqual(len(checked_in_sme_rows), 20)
        self.assertEqual(list(checked_in_sme_rows[0]), SME_CSV_HEADERS)
        with (checked_in / "security-survey.csv").open(encoding="utf-8", newline="") as handle:
            checked_in_security_rows = list(csv.DictReader(handle))
        self.assertEqual(len(checked_in_security_rows), 20)
        self.assertEqual(list(checked_in_security_rows[0]), SECURITY_CSV_HEADERS)

        with tempfile.TemporaryDirectory() as temporary:
            paths = write_dataset(Path(temporary))
            generated = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(generated, build_dataset())
            with paths["sme_csv"].open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
                self.assertEqual(list(rows[0]), SME_CSV_HEADERS)
            self.assertEqual(len(rows), 20)
            with paths["security_csv"].open(encoding="utf-8", newline="") as handle:
                security_rows = list(csv.DictReader(handle))
                self.assertEqual(list(security_rows[0]), SECURITY_CSV_HEADERS)
            self.assertEqual(len(security_rows), 20)

        canonical = json.loads((ROOT / "evidence/readiness-v3/user-study-status.json").read_text(encoding="utf-8"))
        self.assertEqual(canonical["consented_participants"], 0)
        self.assertEqual(canonical["status"], "pending_no_consented_participants")


if __name__ == "__main__":
    unittest.main()
