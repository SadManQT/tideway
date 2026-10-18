"""Validation for the non-evidence SME user-study scenario templates."""
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "evidence" / "readiness-v3" / "user-study-scenarios.json"


class UserStudyScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        cls.scenarios = {scenario["id"]: scenario for scenario in cls.spec["scenarios"]}

    def test_spec_has_five_unique_scenario_ids(self):
        scenarios = self.spec["scenarios"]
        ids = [scenario["id"] for scenario in scenarios]

        self.assertEqual(len(scenarios), 5)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {"P1", "P2", "P3", "P4", "P5"})

    def test_spec_explicitly_labels_examples_as_non_evidence(self):
        self.assertEqual(
            self.spec["evidence_status"],
            "illustrative_examples_only_not_observed_results",
        )
        disclaimer = self.spec["evidence_disclaimer"].lower()
        label = self.spec["non_evidence_label"].lower()
        self.assertIn("illustrative", disclaimer)
        self.assertIn("not observed", disclaimer)
        self.assertIn("example/template", label)
        self.assertIn("not an observed result", label)

        for scenario in self.spec["scenarios"]:
            example = scenario["illustrative_example"]
            self.assertIn("illustrative", example["label"].lower())
            self.assertIn("not an observed result", example["label"].lower())
            self.assertFalse(example["observed"])
            self.assertEqual(scenario["status"], "not_observed")
            self.assertTrue(scenario["pending"])

    def test_spec_has_no_participant_rows_or_identity_data(self):
        self.assertEqual(self.spec["participant_count"], 0)
        self.assertEqual(self.spec["participant_rows"], [])
        self.assertEqual(self.spec["observed_results"], [])
        self.assertFalse(self.spec["privacy"]["collect_free_text"])
        self.assertFalse(self.spec["privacy"]["collect_identity_data"])
        self.assertFalse(self.spec["privacy"]["participant_rows_in_this_spec"])
        self.assertEqual(self.spec["privacy"]["new_csv_columns"], [])

        forbidden_keys = {"participant_id", "email", "phone", "full_name", "contact_details"}

        def visit(value):
            if isinstance(value, dict):
                self.assertTrue(forbidden_keys.isdisjoint(value), value.keys())
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(self.spec)

    def test_required_protocol_and_scenario_fields(self):
        self.assertEqual(self.spec["scenario_status"], "not_observed")
        self.assertEqual(self.spec["study_status"], "pending")
        self.assertEqual(self.spec["user_study_status"], "pending_no_consented_participants")

        protocol = self.spec["observer_protocol"]
        for field in ("acceptance_criteria", "assistance_rule", "timing_rule", "structured_observer_fields"):
            self.assertIn(field, protocol)
        self.assertTrue(protocol["acceptance_criteria"])
        self.assertIn("60 seconds", protocol["assistance_rule"])
        for field in ("start", "stop", "exclude", "csv_field", "interruption"):
            self.assertIn(field, protocol["timing_rule"])

        expected = {
            "P1": {"role": "owner", "task": "T1", "outcome": "assisted", "seconds": 92},
            "P2": {"role": "accountant", "task": "T3", "outcome": "completed", "seconds": 75},
            "P3": {"role": "owner", "task": "T2", "outcome": "assisted", "seconds": 140},
            "P4": {"role": "owner", "task": "T4", "outcome": "completed", "seconds": 110},
            "P5": {"role": "bookkeeper", "task": "T5", "outcome": "completed", "seconds": 55},
        }
        for scenario_id, required in expected.items():
            with self.subTest(scenario_id=scenario_id):
                scenario = self.scenarios[scenario_id]
                for field in (
                    "id",
                    "status",
                    "pending",
                    "role",
                    "title",
                    "task_ids",
                    "persona",
                    "dialogue",
                    "acceptance_criteria",
                    "learning_points",
                    "illustrative_example",
                ):
                    self.assertIn(field, scenario)
                self.assertEqual(scenario["role"], required["role"])
                self.assertEqual(scenario["task_ids"], [required["task"]])
                self.assertTrue(scenario["persona"]["label"])
                self.assertTrue(scenario["dialogue"]["moderator_read_aloud"])
                self.assertTrue(scenario["acceptance_criteria"])
                self.assertTrue(scenario["learning_points"])
                example = scenario["illustrative_example"]
                self.assertEqual(example["example_outcome"], required["outcome"])
                self.assertEqual(example["example_seconds"], required["seconds"])
                self.assertEqual(example["time_unit"], "seconds")

    def test_mapping_covers_existing_csv_tasks_without_new_fields(self):
        mapping = self.spec["task_mapping"]
        self.assertEqual(set(mapping), {"T1", "T2", "T3", "T4", "T5"})
        for task_id, entry in mapping.items():
            with self.subTest(task_id=task_id):
                self.assertEqual(entry["csv_status_field"], f"{task_id.lower()}_status")
                self.assertEqual(entry["csv_seconds_field"], f"{task_id.lower()}_seconds")
                self.assertIn("study_prompt", entry)
                self.assertIn("mapping_note", entry)
        self.assertEqual(mapping["T1"]["scenario_id"], "P1")
        self.assertEqual(mapping["T2"]["scenario_id"], "P3")
        self.assertEqual(mapping["T3"]["scenario_id"], "P2")
        self.assertEqual(mapping["T4"]["scenario_id"], "P4")
        self.assertEqual(mapping["T5"]["scenario_id"], "P5")

    def test_p5_keeps_interruption_time_separate_from_active_time(self):
        scenario = self.scenarios["P5"]

        self.assertTrue(scenario["timing"]["active_time_only"])
        self.assertTrue(scenario["timing"]["interruption_time_separate"])
        self.assertIsNone(scenario["timing"]["interruption_seconds_example"])
        self.assertEqual(scenario["illustrative_example"]["example_seconds_kind"], "active_task_time")
        self.assertIsNone(scenario["illustrative_example"]["interruption_seconds"])
        self.assertIn("t5_seconds", scenario["timing"]["interruption_note"])


if __name__ == "__main__":
    unittest.main()
