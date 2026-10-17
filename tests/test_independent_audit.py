"""Regressions for independently reproduced release and financial defects."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

import run
from tideway import analytics, security
from tideway.domain import ValidationError
from tideway.financing import compare
from tideway.store import Store


class SigningKeyIntegrity(unittest.TestCase):
    def test_existing_invalid_key_is_preserved_and_rejected(self):
        for value in (b"truncated", b"", b"g" * 64, b" " * 64, b"\xff" * 64):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "signing.key"
                path.write_bytes(value)
                with self.assertRaisesRegex(ValidationError, "signing key"):
                    security.load_key(path)
                self.assertEqual(path.read_bytes(), value)

    def test_concurrent_first_start_uses_one_persistent_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new" / "signing.key"
            with ThreadPoolExecutor(max_workers=8) as pool:
                keys = list(pool.map(lambda _: security.load_key(path), range(24)))
            self.assertEqual(len(set(keys)), 1)
            self.assertEqual(security.load_key(path), keys[0])
            self.assertEqual(path.read_bytes(), keys[0].hex().encode("ascii"))
            self.assertEqual([p.name for p in path.parent.iterdir()], [path.name])

    def test_malformed_signatures_are_rejected_without_exception(self):
        for signature in ("\u00e9" * 64, "g" * 64, " " * 64, "0" * 63, None, True, []):
            with self.subTest(signature=signature):
                self.assertFalse(security.verify(b"k" * 32, {"signature": signature}))
        document = {"amount_minor": 50}
        document["signature"] = security.sign(b"k" * 32, document)
        self.assertTrue(security.verify(b"k" * 32, document))
        document["amount_minor"] = 51
        self.assertFalse(security.verify(b"k" * 32, document))


class StartupConfiguration(unittest.TestCase):
    def test_dotenv_honours_structured_plans_without_overriding_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / ".env").write_text(
                'TIDEWAY_LOCAL_STRUCTURED_PLANS="1"\nTIDEWAY_SEMANTIC_SCREENING=1\nTIDEWAY_PORT=9999\nUNRELATED_AUDIT_SETTING=bad\n', encoding="utf-8")
            with patch.object(run, "ROOT", Path(directory)), patch.dict(os.environ, {"TIDEWAY_PORT": "8789"}, clear=True):
                run.load_env()
                self.assertEqual(os.environ["TIDEWAY_LOCAL_STRUCTURED_PLANS"], "1")
                self.assertEqual(os.environ["TIDEWAY_SEMANTIC_SCREENING"], "1")
                self.assertEqual(os.environ["TIDEWAY_PORT"], "8789")
                self.assertNotIn("UNRELATED_AUDIT_SETTING", os.environ)


def invoice(identifier, paid=None):
    return {"id": identifier, "customer": "Client", "issue_date": "2026-09-01", "due_date": "2026-10-01",
            "paid_date": paid, "status": "paid" if paid else "confirmed", "amount_minor": 300_000,
            "expected_collection_date": "2026-11-01", "currency": "USD", "risk_flags": []}


class FinancialSnapshotIntegrity(unittest.TestCase):
    def test_profiles_use_only_history_known_at_snapshot_date(self):
        rows = [invoice("today", "2026-10-15"), invoice("future", "2026-10-30"), invoice("open")]
        profile = analytics.customer_profiles(rows, "2026-10-15")
        self.assertEqual(profile["history_observations"], 1)
        self.assertEqual(profile["customers"]["Client"]["mean_days_late"], 14)
        self.assertEqual(analytics.customer_profiles(rows, "2026-10-30")["history_observations"], 2)

    def test_empirical_fallback_cannot_sample_future_payments(self):
        future = [invoice("future", "2026-10-30")]
        before = analytics._delay_sampler([], "2026-10-15")
        after = analytics._delay_sampler(future, "2026-10-15")
        a, b = random.Random(7), random.Random(7)
        self.assertEqual([before(a, "Client", 0) for _ in range(100)],
                         [after(b, "Client", 0) for _ in range(100)])

    def test_snapshot_profiles_and_model_history_share_cutoff(self):
        rows = [invoice("future", "2026-10-30"), invoice("open")]
        result = Store.derived({"records": {"invoices": rows, "bills": []}, "counterparties": {},
                                "state": {"current_date": "2026-10-15"}})
        self.assertEqual(result["profiles"]["history_observations"], 0)
        self.assertEqual(result["predictions"]["open"]["history_used"], 0)
        self.assertEqual(result["profiles"]["customers"]["Client"]["days_overdue"], 14)

    def test_internal_backtest_excludes_labels_not_yet_available(self):
        rows = [invoice(str(i), "2026-10-30") for i in range(8)]
        result = analytics.backtest(rows, as_of="2026-10-15")
        self.assertFalse(result["available"])
        self.assertEqual(result["n"], 0)

    def test_collected_or_unissued_invoice_cannot_back_mock_advance(self):
        business = {"business_id": "test", "currency": "USD", "opening_date": "2026-10-01", "opening_cash_minor": 100_000}
        policy = {"reserve_floor_minor": 20_000, "lookahead_days": 14}
        records = {"invoices": [invoice("committed")], "bills": [], "transactions": []}
        adjustment = {"kind": "invoice_early_payment", "invoice_id": "committed", "face_minor": 300_000,
                      "amount_minor": 294_000, "to_date": "2026-10-02"}
        def check(adjustments=()):
            return compare(business, policy, records, "2026-10-31", 20_000, "2026-10-05",
                           as_of="2026-10-03", adjustments=adjustments)[0]
        self.assertTrue(check()["ledger_requirement_met"])
        self.assertFalse(check([adjustment])["ledger_requirement_met"])
        records["invoices"][0]["issue_date"] = "2026-10-10"
        self.assertFalse(check()["ledger_requirement_met"])


if __name__ == "__main__":
    unittest.main()
