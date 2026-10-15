"""Focused regression tests for audit-chain witness integrity."""
import json
import tempfile
import unittest
from pathlib import Path

from tideway.store import Store


class AuditWitnessIntegrityTests(unittest.TestCase):
    business_id = "audit-witness-test"

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.db_path = root / "audit.sqlite3"
        self.witness_path = root / "audit.witness.json"
        self.store = Store(self.db_path, witness_path=self.witness_path)
        self.store.create_business(
            {
                "business_id": self.business_id,
                "name": "Audit Witness Test",
                "currency": "BDT",
                "opening_cash": "1000",
                "opening_date": "2026-10-01",
                "default_target_date": "2026-10-31",
                "country": "BD",
                "sector": "Test",
            },
            {"reserve_floor": "100", "action_limit": "100"},
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def _cosign(self):
        result = self.store.witness_cosign(self.business_id)
        self.assertTrue(result["cosigned"])

    def test_first_time_without_witness_remains_valid(self):
        evidence = self.store.evidence(self.business_id)

        self.assertTrue(evidence["hash_chain_valid"])
        self.assertEqual(evidence["witness"], {"present": False})

    def test_valid_witness_is_consistent(self):
        self._cosign()

        evidence = self.store.evidence(self.business_id)

        self.assertTrue(evidence["hash_chain_valid"])
        self.assertTrue(evidence["witness"]["present"])
        self.assertTrue(evidence["witness"]["signature_valid"])
        self.assertTrue(evidence["witness"]["consistent"])

    def test_tampered_witness_signature_invalidates_hash_chain(self):
        self._cosign()
        witness = json.loads(self.witness_path.read_text())
        witness[self.business_id]["signature"] = "0" * 64
        self.witness_path.write_text(json.dumps(witness))

        evidence = self.store.evidence(self.business_id)

        self.assertFalse(evidence["hash_chain_valid"])
        self.assertFalse(evidence["witness"]["signature_valid"])
        self.assertFalse(evidence["witness"]["consistent"])
        self.assertIn("signature", evidence["witness"]["problem"].lower())

    def test_deleted_witness_invalidates_evidence(self):
        self._cosign()
        self.witness_path.unlink()

        evidence = self.store.evidence(self.business_id)

        self.assertFalse(evidence["hash_chain_valid"])
        self.assertFalse(evidence["witness"]["present"])
        self.assertFalse(evidence["witness"]["consistent"])
        self.assertIn("missing", evidence["witness"]["problem"].lower())

    def test_truncated_audit_chain_invalidates_witness(self):
        self._cosign()
        with self.store.connect() as db:
            db.execute(
                "DELETE FROM audit WHERE business_id=? AND id=(SELECT MAX(id) FROM audit WHERE business_id=?)",
                (self.business_id, self.business_id),
            )

        evidence = self.store.evidence(self.business_id)

        self.assertFalse(evidence["hash_chain_valid"])
        self.assertTrue(evidence["witness"]["present"])
        self.assertTrue(evidence["witness"]["signature_valid"])
        self.assertFalse(evidence["witness"]["consistent"])
        self.assertIn("truncated", evidence["witness"]["problem"])


if __name__ == "__main__":
    unittest.main()
