"""Study metrics and privacy validation; synthetic test rows are not real users."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.user_study import HEADERS, StudyError, _private_csv, blank_row, initialise, summarise, sus_score


class UserStudy(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "study.csv"

    def write(self, rows, headers=None):
        with self.path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers or HEADERS)
            writer.writeheader()
            writer.writerows(rows)

    def participant(self, number, **changes):
        return {**blank_row(f"P{number}"), "consent": "yes", "role": "owner", "language": "en", **changes}

    def test_empty_template_has_zero_participants_and_no_fabricated_averages(self):
        initialise(self.path)
        with self.assertRaises(FileExistsError):
            initialise(self.path)
        report = summarise(self.path)
        self.assertEqual(report["consented_participants"], 0)
        self.assertEqual(report["status"], "pending_no_consented_participants")
        self.assertIsNone(report["sus"]["mean_score"])
        self.assertIsNone(report["tasks"]["t1"]["median_seconds"])
        self.assertIsNone(report["tasks"]["t1"]["unassisted_completion"]["rate"])
        self.write([self.participant(1)])
        report = summarise(self.path)
        self.assertEqual(report["status"], "consented_sessions_no_observations")
        self.assertIsNone(report["sus"]["mean_score"])

    def test_sus_formula_and_invalid_fields(self):
        self.assertEqual(sus_score([5, 1] * 5), 100)
        self.assertEqual(sus_score([1, 5] * 5), 0)
        self.assertEqual(sus_score([3] * 10), 50)
        for responses in ([3] * 9, [6] * 10, [True] * 10, [float("nan")] * 10):
            with self.subTest(responses=responses), self.assertRaises(StudyError):
                sus_score(responses)

    def test_consent_and_identifying_columns(self):
        with self.assertRaisesRegex(StudyError, "evidence/private"):
            _private_csv(self.path)
        self.write([{**blank_row(), "role": "owner"}])
        with self.assertRaisesRegex(StudyError, "prior consent"):
            summarise(self.path)
        self.write([{**blank_row(), "email": "private@example.invalid"}], HEADERS + ["email"])
        with self.assertRaises(StudyError) as error:
            summarise(self.path)
        self.assertNotIn("private@example.invalid", str(error.exception))
        for row in (self.participant(1, participant_id="Alice"), self.participant(1, role="My Shop Owner")):
            self.write([row])
            with self.assertRaises(StudyError):
                summarise(self.path)
        self.write([self.participant(1), self.participant(1)])
        with self.assertRaisesRegex(StudyError, "duplicate"):
            summarise(self.path)

    def test_denominators_separate_assistance_failures_and_unavailable_model(self):
        rows = [self.participant(1, t1_status="completed", t1_seconds="10", model_status="unavailable", t3_status="unavailable_model"),
                self.participant(2, t1_status="assisted", t1_seconds="20", model_status="unavailable", t3_status="unavailable_model"),
                self.participant(3, t1_status="failed", t1_seconds="30", model_status="available", t3_status="completed", t3_seconds="15")]
        self.write(rows)
        report = summarise(self.path)
        self.assertEqual(report["tasks"]["t1"]["attempted_denominator"], 3)
        self.assertEqual(report["tasks"]["t1"]["unassisted_completion"]["numerator"], 1)
        self.assertEqual(report["tasks"]["t1"]["completion_including_assistance"]["numerator"], 2)
        self.assertEqual(report["tasks"]["t1"]["median_seconds"], 20)
        self.assertEqual(report["tasks"]["t3"]["counts"]["unavailable_model"], 2)
        self.assertEqual(report["tasks"]["t3"]["attempted_denominator"], 1)
        self.assertEqual(report["tasks"]["t3"]["counts"]["failed"], 0)

    def test_nonfinite_times_and_invalid_status_combinations(self):
        for value in ("nan", "inf", "-1", "3601", "not a time"):
            self.write([self.participant(1, t1_status="completed", t1_seconds=value)])
            with self.subTest(value=value), self.assertRaises(StudyError):
                summarise(self.path)
        for changes in ({"t1_status": "unavailable_model", "model_status": "unavailable"},
                        {"t3_status": "completed", "model_status": "unavailable"},
                        {"t1_status": "not_attempted", "t1_seconds": "8"}, {"sus3": "6"}):
            self.write([self.participant(1, **changes)])
            with self.subTest(changes=changes), self.assertRaises(StudyError):
                summarise(self.path)

    def test_partial_sus_and_aggregate_only_export(self):
        first = self.participant(1, **{f"sus{number}": "3" for number in range(1, 11)})
        self.write([first, self.participant(2, sus1="5"), self.participant(3)])
        report = summarise(self.path)
        self.assertEqual(report["sus"]["complete_responses"], 1)
        self.assertEqual(report["sus"]["partial_responses_not_scored"], 1)
        self.assertEqual(report["sus"]["missing_responses"], 1)
        self.assertEqual(report["sus"]["mean_score"], 50)
        exported = json.dumps(report)
        for forbidden in ("P1", "P2", "participant_id", "sus1", str(self.path)):
            self.assertNotIn(forbidden, exported)


if __name__ == "__main__":
    unittest.main()
