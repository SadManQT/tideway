"""Residual-risk consent must be explicit, bound and independently given by each human."""
import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tideway import security
from tideway.domain import ValidationError, canonical_json
from tideway.server import Application
from tideway.store import Store, json_hash


BUSINESS = "shapla-services"


class RiskAcknowledgement(unittest.TestCase):
    def setUp(self):
        self.app = Application(":memory:")
        self.addCleanup(self.app.store.close)
        self.owner = self.app.store.verify_pin("nadia", "2468")
        self.accountant = self.app.store.verify_pin("imran", "1357")
        self.plan = self.app.tideway.propose(BUSINESS, None, "agent:test")
        # A real feasible cheaper alternative leaves substantially greater risk.
        self.bundle = next(bundle for bundle in self.plan["bundles"]
                           if bundle["feasible"] and bundle["probability_breach_after"] > self.plan["risk_target"])
        self.assertTrue(self.bundle["dual_approval_required"])

    def consent(self, plan=None, bundle=None):
        plan, bundle = plan or self.plan, bundle or self.bundle
        return {"acknowledged": True, "plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"],
                "bundle_id": bundle["bundle_id"], "probability_breach_after": bundle["probability_breach_after"],
                "risk_target": plan["risk_target"]}

    def approve(self, acknowledgement=None, operator=None, pin=None, plan=None, bundle=None):
        plan, bundle, operator = plan or self.plan, bundle or self.bundle, operator or self.accountant
        return self.app.post("/api/plan/approve", {
            "business_id": BUSINESS, "plan_id": plan["plan_id"], "bundle_id": bundle["bundle_id"],
            "pin": pin or ("2468" if operator["id"] == "nadia" else "1357"), "review_ms": 9000,
            "confirm_amount_minor": bundle["exposure_minor"], "risk_acknowledgement": acknowledgement}, operator, None)

    def counts(self):
        with self.app.store.connect() as db:
            return tuple(db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                         for name in ("approvals", "mandates", "audit"))

    def test_omitted_consent_is_atomic_at_api_and_store_boundary(self):
        before = self.counts()
        snapshot = self.app.store.snapshot(BUSINESS)["snapshot_hash"]
        with self.assertRaisesRegex(ValidationError, "Explicitly acknowledge"):
            self.approve()
        with self.assertRaisesRegex(ValidationError, "Explicitly acknowledge"):
            self.app.store.approve(BUSINESS, self.plan["plan_id"], self.bundle["bundle_id"],
                                   self.accountant, "1357", "operator:imran", 9000)
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.app.store.snapshot(BUSINESS)["snapshot_hash"], snapshot)

    def test_wrong_boolean_identity_hash_risk_target_and_extra_fields_are_refused(self):
        valid = self.consent()
        malformed = [True, "yes", [], {**valid, "acknowledged": False}, {**valid, "acknowledged": 1},
                     {**valid, "plan_id": "0" * 32}, {**valid, "plan_hash": "0" * 64},
                     {**valid, "bundle_id": "recommended"}, {**valid, "risk_target": .99},
                     {**valid, "probability_breach_after": .05}, {**valid, "probability_breach_after": True},
                     {**valid, "probability_breach_after": float("nan")},
                     {**valid, "probability_breach_after": float("inf")}, {**valid, "extra": "ignored?"}]
        before = self.counts()
        for acknowledgement in malformed:
            with self.subTest(acknowledgement=acknowledgement), self.assertRaises(ValidationError):
                self.approve(acknowledgement)
            self.assertEqual(self.counts(), before)

    def test_each_dual_approver_must_acknowledge_and_signed_receipt_retains_consent(self):
        acknowledgement = self.consent()
        first = self.approve(acknowledgement)
        self.assertEqual(first["status"], "awaiting_second_approval")
        saved = self.app.store.plan(BUSINESS, self.plan["plan_id"])["approvals"]
        self.assertEqual(saved[0]["risk_acknowledgement"], acknowledgement)
        before = self.counts()
        with self.assertRaises(ValidationError):
            self.approve(operator=self.owner)
        self.assertEqual(self.counts(), before)
        second = self.approve(acknowledgement, self.owner)
        mandate = second["mandate"]
        self.assertEqual(second["status"], "mandate_issued")
        self.assertTrue(self.app.store.verify_mandate_document(mandate)["signature_valid"])
        self.assertEqual({entry["operator_id"] for entry in mandate["approvals"]}, {"nadia", "imran"})
        self.assertTrue(all(entry["risk_acknowledgement"] == acknowledgement for entry in mandate["approvals"]))
        forged = copy.deepcopy(mandate)
        forged["approvals"][0]["risk_acknowledgement"]["probability_breach_after"] = .01
        self.assertFalse(self.app.store.verify_mandate_document(forged)["signature_valid"])
        self.assertEqual(self.app.tideway.negotiate(BUSINESS, mandate["mandate_id"], "agent:test")["status"], "ready")
        receipt = self.app.store.execute(BUSINESS, mandate["mandate_id"], "risk-consent-once", self.owner, "operator:nadia")
        self.assertTrue(receipt["risk"]["acknowledgement_required"])
        self.assertEqual(receipt["risk"]["probability_breach_after"], self.bundle["probability_breach_after"])
        self.assertTrue(all(entry["risk_acknowledgement"] == acknowledgement for entry in receipt["approvals"]))
        replay = self.app.store.execute(BUSINESS, mandate["mandate_id"], "risk-consent-once", self.owner, "operator:nadia")
        self.assertEqual(receipt["receipt_id"], replay["receipt_id"])
        evidence = self.app.store.evidence(BUSINESS)
        self.assertTrue(evidence["hash_chain_valid"])
        for entry in evidence["entries"]:
            if entry["action"] in ("plan.approve", "mandate.issue", "mandate.execute"):
                self.assertTrue(entry["details"]["risk"]["acknowledgement_required"])
                self.assertTrue(all(item["risk_acknowledgement"] == acknowledgement for item in entry["details"]["approvals"]))

    def test_consent_does_not_replace_pin_or_distinct_people(self):
        before = self.counts()
        with self.assertRaises(ValidationError):
            self.approve(self.consent(), pin="9999")
        self.assertEqual(self.counts(), before)
        self.approve(self.consent())
        with self.assertRaisesRegex(ValidationError, "different person"):
            self.approve(self.consent())

    def test_below_target_bundle_keeps_ordinary_approval_without_checkbox(self):
        safe = next(bundle for bundle in self.plan["bundles"]
                    if bundle["feasible"] and bundle["probability_breach_after"] <= self.plan["risk_target"])
        first = self.approve(bundle=safe)
        self.assertEqual(first["status"], "awaiting_second_approval")
        second = self.approve(operator=self.owner, bundle=safe)
        self.assertFalse(second["mandate"]["risk"]["acknowledgement_required"])
        self.assertTrue(all(item["risk_acknowledgement"] is None for item in second["mandate"]["approvals"]))

    def test_display_flag_cannot_suppress_server_probability_comparison(self):
        payload = {key: value for key, value in self.plan.items()
                   if key not in ("plan_id", "plan_hash", "status", "approvals", "audit_id", "audit_hash")}
        payload["bundles"] = copy.deepcopy(payload["bundles"])
        next(item for item in payload["bundles"] if item["bundle_id"] == self.bundle["bundle_id"])["risk_target_met"] = True
        with self.app.store.connect() as db:
            db.execute("UPDATE plans SET payload=?,plan_hash=? WHERE id=?", (canonical_json(payload), json_hash(payload), self.plan["plan_id"]))
        with self.assertRaisesRegex(ValidationError, "Explicitly acknowledge"):
            self.approve()

    def test_superseded_or_stale_plan_consent_cannot_be_reused(self):
        old_consent = self.consent()
        fresh = self.app.tideway.propose(BUSINESS, None, "agent:test")
        bundle = next(item for item in fresh["bundles"] if item["bundle_id"] == self.bundle["bundle_id"])
        with self.assertRaises(ValidationError):
            self.approve(old_consent, plan=fresh, bundle=bundle)
        self.app.store.set_policy(BUSINESS, {"lookahead_days": 9}, self.owner, "operator:nadia")
        with self.assertRaises(ValidationError):
            self.approve(self.consent(fresh, bundle), plan=fresh, bundle=bundle)
        self.assertFalse(self.app.store.live_mandates(BUSINESS))

    def test_legacy_pending_approval_cannot_supply_unacknowledged_second_person(self):
        with self.app.store.connect() as db:
            db.execute("INSERT INTO approvals(id,business_id,plan_id,bundle_id,operator_id,role,created_at) "
                       "VALUES (?,?,?,?,?,?,?)", ("legacy", BUSINESS, self.plan["plan_id"], self.bundle["bundle_id"],
                                                 "imran", "accountant", "2026-10-15T00:00:00+00:00"))
        before = self.counts()
        with self.assertRaisesRegex(ValidationError, "Create a fresh plan"):
            self.approve(self.consent(), self.owner)
        self.assertEqual(self.counts(), before)

    def test_authentic_legacy_mandate_without_risk_consent_cannot_execute(self):
        acknowledgement = self.consent()
        self.approve(acknowledgement)
        mandate = self.approve(acknowledgement, self.owner)["mandate"]
        self.app.tideway.negotiate(BUSINESS, mandate["mandate_id"], "agent:test")
        for approval in mandate["approvals"]:
            approval.pop("risk_acknowledgement")
        mandate.pop("signature")
        mandate["signature"] = security.sign(self.app.store.key, mandate)
        with self.app.store.connect() as db:
            db.execute("UPDATE mandates SET document=? WHERE id=?", (canonical_json(mandate), mandate["mandate_id"]))
        before = self.app.store.snapshot(BUSINESS)["state"]["state_hash"]
        with self.assertRaisesRegex(ValidationError, "Explicitly acknowledge"):
            self.app.store.execute(BUSINESS, mandate["mandate_id"], "legacy-risk", self.owner, "operator:nadia")
        self.assertEqual(self.app.store.snapshot(BUSINESS)["state"]["state_hash"], before)

    def test_risk_metadata_requires_finite_numeric_probabilities(self):
        for bad in (None, True, "0.36", -1, 1.1, float("nan"), float("inf")):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                Store.risk_acknowledgement_terms(self.plan, {**self.bundle, "probability_breach_after": bad})


class RiskSchemaMigration(unittest.TestCase):
    def test_existing_workspace_approval_rows_are_preserved_without_invented_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.sqlite3"
            from contextlib import closing
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE approvals (id TEXT PRIMARY KEY,business_id TEXT,plan_id TEXT,bundle_id TEXT,"
                           "operator_id TEXT,role TEXT,review_ms INTEGER,created_at TEXT,UNIQUE(plan_id,bundle_id,operator_id))")
                db.execute("INSERT INTO approvals(id,operator_id) VALUES ('old','person')")
            store = Store(path)
            try:
                with store.connect() as db:
                    row = db.execute("SELECT * FROM approvals WHERE id='old'").fetchone()
                    self.assertEqual(row["operator_id"], "person")
                    self.assertIsNone(row["risk_acknowledgement"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
