"""SQLite persistence for the Probaho sandbox and legacy FinMate demo.

Every Probaho read takes a business id and every mutation runs in a
``BEGIN IMMEDIATE`` transaction.  The sandbox is synthetic: no bank,
payments, lender or external side effect is connected to this store.
"""
from __future__ import annotations

import hashlib
import re
import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .finance import (
    MAX_AMOUNT_MINOR,
    PROBAHO_CURRENCY,
    ValidationError,
    project_cash,
    validate_bill,
    validate_business,
    validate_business_id,
    validate_invoice,
    validate_policy,
    validate_probaho_transaction,
    validate_transaction,
    valid_date,
)


LEGACY_BUSINESS_ID = "legacy-personal"
SHAPLA_BUSINESS_ID = "shapla-services"
SEED_TARGET_DATE = "2026-10-31"
FIXTURE_VERSION = "probaho-synthetic-v3"
LOCAL_OPERATOR = "local demo operator; not authenticated multiuser"


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _future(seconds=300):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def _parse_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else datetime.min.replace(tzinfo=timezone.utc)
    except (AttributeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


class Store:
    def __init__(self, path):
        self.path = Path(path) if str(path) != ":memory:" else Path(".")
        self._memory = str(path) == ":memory:"
        self._memory_uri = f"file:finmate_{id(self)}?mode=memory&cache=shared" if self._memory else None
        self._memory_keepalive = None
        if self._memory:
            self._memory_keepalive = sqlite3.connect(self._memory_uri, uri=True, timeout=10)
            self._memory_keepalive.execute("PRAGMA foreign_keys=ON")
        if not self._memory:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            # Old FinMate databases can have a transactions table without a
            # business_id column.  Create/migrate columns first; indexes that
            # reference new columns are deliberately created afterwards.
            self._create_schema(db)
            self._migrate_old_schema(db)
            self._create_indexes(db)
            db.execute(
                "INSERT OR IGNORE INTO businesses "
                "(id,name,currency,opening_cash_minor,opening_date,default_target_date,synthetic,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (LEGACY_BUSINESS_ID, "Legacy Personal Demo", PROBAHO_CURRENCY, 0,
                 "2026-01-01", "2026-10-31", 1, utc_now()),
            )

    def _create_schema(self, db):
        db.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS businesses (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                currency TEXT NOT NULL CHECK(currency='BDT'),
                opening_cash_minor INTEGER NOT NULL CHECK(opening_cash_minor >= 0),
                opening_date TEXT NOT NULL,
                default_target_date TEXT NOT NULL,
                synthetic INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT NOT NULL,
                business_id TEXT NOT NULL,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('income','expense')),
                amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                currency TEXT NOT NULL DEFAULT 'BDT' CHECK(currency='BDT'),
                category TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(business_id,id),
                UNIQUE(business_id, fingerprint)
            );
            CREATE TABLE IF NOT EXISTS invoices (
                business_id TEXT NOT NULL,
                id TEXT NOT NULL,
                customer TEXT NOT NULL,
                description TEXT NOT NULL,
                issue_date TEXT NOT NULL,
                due_date TEXT NOT NULL,
                expected_collection_date TEXT NOT NULL,
                status TEXT NOT NULL,
                amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                currency TEXT NOT NULL CHECK(currency='BDT'),
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(business_id,id)
            );
            CREATE TABLE IF NOT EXISTS bills (
                business_id TEXT NOT NULL,
                id TEXT NOT NULL,
                payee TEXT NOT NULL,
                description TEXT NOT NULL,
                due_date TEXT NOT NULL,
                amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                currency TEXT NOT NULL CHECK(currency='BDT'),
                status TEXT NOT NULL,
                priority TEXT NOT NULL,
                reschedule_allowed INTEGER NOT NULL DEFAULT 0,
                rescheduled_date TEXT,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(business_id,id)
            );
            CREATE TABLE IF NOT EXISTS policies (
                business_id TEXT PRIMARY KEY,
                currency TEXT NOT NULL CHECK(currency='BDT'),
                reserve_floor_minor INTEGER NOT NULL CHECK(reserve_floor_minor >= 0),
                payroll_priority INTEGER NOT NULL,
                action_limit_minor INTEGER NOT NULL CHECK(action_limit_minor >= 0),
                version TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sandbox_state (
                business_id TEXT PRIMARY KEY,
                balance_minor INTEGER NOT NULL,
                current_date TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 0,
                state_json TEXT NOT NULL,
                reset_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY,
                business_id TEXT NOT NULL,
                target_date TEXT NOT NULL,
                plan_hash TEXT NOT NULL,
                payload TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                state_version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                business_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                payee TEXT,
                amount_minor INTEGER NOT NULL,
                currency TEXT NOT NULL CHECK(currency='BDT'),
                target_date TEXT NOT NULL,
                plan_hash TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL DEFAULT '',
                expiry TEXT NOT NULL,
                nonce TEXT NOT NULL UNIQUE,
                state_version INTEGER NOT NULL,
                balance_minor INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                used_at TEXT
            );
            CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY,
                business_id TEXT NOT NULL,
                approval_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                action_id TEXT NOT NULL,
                payee TEXT,
                amount_minor INTEGER NOT NULL,
                currency TEXT NOT NULL CHECK(currency='BDT'),
                target_date TEXT NOT NULL,
                receipt_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(business_id,idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS supplier_consents (
                id TEXT PRIMARY KEY,
                business_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                plan_hash TEXT NOT NULL,
                bill_id TEXT NOT NULL,
                payee TEXT NOT NULL,
                amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                original_due_date TEXT NOT NULL,
                new_due_date TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('accepted','rejected','revoked')),
                synthetic INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                business_id TEXT NOT NULL,
                invoice_id TEXT NOT NULL,
                payee TEXT NOT NULL,
                body TEXT NOT NULL,
                target_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id TEXT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                permission TEXT NOT NULL,
                details TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                entry_hash TEXT NOT NULL
                ,chain_version TEXT NOT NULL DEFAULT 'business-v2'
            );
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS drafts (
                id TEXT PRIMARY KEY, month TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS budgets (
                month TEXT PRIMARY KEY, draft_id TEXT NOT NULL, payload TEXT NOT NULL,
                approved_at TEXT NOT NULL
            );
            """
        )

    def _create_indexes(self, db):
        """Create indexes only after old tables have their new columns."""
        db.executescript(
            """
            CREATE INDEX IF NOT EXISTS transaction_business_date ON transactions(business_id,date);
            CREATE INDEX IF NOT EXISTS invoice_business_due ON invoices(business_id,due_date);
            CREATE INDEX IF NOT EXISTS bill_business_due ON bills(business_id,due_date);
            CREATE INDEX IF NOT EXISTS plan_business_status ON plans(business_id,status,created_at,id);
            CREATE INDEX IF NOT EXISTS approval_business_status ON approvals(business_id,status,created_at,id);
            CREATE INDEX IF NOT EXISTS consent_business_action ON supplier_consents(business_id,plan_id,action_id,created_at,id);
            CREATE INDEX IF NOT EXISTS execution_business_key ON executions(business_id,idempotency_key);
            """
        )

    def _migrate_old_schema(self, db):
        """Make a pre-Probaho local DB readable without weakening new scope checks."""
        columns = {row[1] for row in db.execute("PRAGMA table_info(transactions)")}
        if "business_id" not in columns:
            db.execute("ALTER TABLE transactions ADD COLUMN business_id TEXT")
        if "currency" not in columns:
            db.execute("ALTER TABLE transactions ADD COLUMN currency TEXT NOT NULL DEFAULT 'BDT'")
        if "created_at" not in columns:
            db.execute("ALTER TABLE transactions ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        db.execute("UPDATE transactions SET business_id=? WHERE business_id IS NULL OR business_id=''", (LEGACY_BUSINESS_ID,))
        db.execute("UPDATE transactions SET currency='BDT' WHERE currency IS NULL OR currency=''" )
        audit_columns = {row[1] for row in db.execute("PRAGMA table_info(audit)")}
        if "business_id" not in audit_columns:
            db.execute("ALTER TABLE audit ADD COLUMN business_id TEXT")
        if "chain_version" not in audit_columns:
            db.execute("ALTER TABLE audit ADD COLUMN chain_version TEXT NOT NULL DEFAULT 'legacy-global-v1'")
        plan_columns = {row[1] for row in db.execute("PRAGMA table_info(plans)")}
        if plan_columns and "snapshot_hash" not in plan_columns:
            db.execute("ALTER TABLE plans ADD COLUMN snapshot_hash TEXT NOT NULL DEFAULT ''")
        approval_columns = {row[1] for row in db.execute("PRAGMA table_info(approvals)")}
        if approval_columns and "snapshot_hash" not in approval_columns:
            db.execute("ALTER TABLE approvals ADD COLUMN snapshot_hash TEXT NOT NULL DEFAULT ''")
        # Some very early local databases did not have an executions table or
        # the new consent table.  CREATE TABLE IF NOT EXISTS above covers the
        # absent-table case; these defaults make old rows safe to read.
        if plan_columns:
            db.execute("UPDATE plans SET snapshot_hash='' WHERE snapshot_hash IS NULL")
        if approval_columns:
            db.execute("UPDATE approvals SET snapshot_hash='' WHERE snapshot_hash IS NULL")

    @contextmanager
    def connect(self):
        if self._memory:
            db = sqlite3.connect(self._memory_uri, uri=True, timeout=10)
        else:
            db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _audit(db, action, permission, details, business_id=None):
        business_id = business_id or LEGACY_BUSINESS_ID
        timestamp = utc_now()
        serialized = json.dumps(details, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        previous = db.execute("SELECT entry_hash FROM audit WHERE business_id=? AND chain_version='business-v2' ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
        previous_hash = previous[0] if previous else "0" * 64
        # The business scope is part of the digest.  A filtered export can
        # therefore be verified independently without relying on another
        # business' entries in a global chain.
        scope = business_id or ""
        digest = hashlib.sha256(f"{previous_hash}|{scope}|{timestamp}|{action}|{permission}|{serialized}".encode()).hexdigest()
        cursor = db.execute(
            "INSERT INTO audit(business_id,timestamp,action,permission,details,previous_hash,entry_hash,chain_version) VALUES (?,?,?,?,?,?,?,?)",
            (business_id, timestamp, action, permission, serialized, previous_hash, digest, "business-v2"),
        )
        return {"receipt": cursor.lastrowid, "hash": digest, "audit_receipt": cursor.lastrowid, "audit_hash": digest}

    def audit(self, action, permission, details, business_id=None):
        business_id = business_id or (details.get("business_id") if isinstance(details, dict) else None) or LEGACY_BUSINESS_ID
        validate_business_id(business_id)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return self._audit(db, action, permission, details, business_id)

    def _reject(self, action, reason, business_id=None, details=None):
        payload = {"reason": str(reason)}
        if details:
            payload.update(details)
        try:
            self.audit(action, "denied", payload, business_id)
        except Exception:
            pass

    @staticmethod
    def _json_hash(value):
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _state_payload(state):
        return {
            "business_id": state.get("business_id"),
            "balance_minor": state.get("balance_minor", 0),
            "current_date": state.get("current_date"),
            "version": state.get("version", 0),
            "rescheduled_bills": state.get("rescheduled_bills", {}),
            "accepted_actions": state.get("accepted_actions", []),
            "collected_invoices": state.get("collected_invoices", []),
        }

    @classmethod
    def _state_hash(cls, state):
        return cls._json_hash(cls._state_payload(state))

    @staticmethod
    def _stable_rows(rows, excluded=("created_at", "updated_at")):
        result = []
        for row in rows:
            result.append({key: value for key, value in sorted(dict(row).items()) if key not in excluded})
        return result

    @classmethod
    def _snapshot_hash(cls, business, policy, transactions, invoices, bills, state):
        payload = {
            "business": {key: business.get(key) for key in (
                "business_id", "id", "name", "currency", "opening_cash_minor",
                "opening_date", "default_target_date", "synthetic") if key in business},
            "policy": {key: policy.get(key) for key in (
                "business_id", "currency", "reserve_floor_minor", "payroll_priority",
                "action_limit_minor", "version") if key in policy},
            "transactions": cls._stable_rows(transactions),
            "invoices": cls._stable_rows(invoices),
            "bills": cls._stable_rows(bills),
            "sandbox": cls._state_payload(state),
        }
        return cls._json_hash(payload)

    @staticmethod
    def _public_state(state):
        return {
            "business_id": state.get("business_id"),
            "cash_minor": state.get("balance_minor", 0),
            "balance_minor": state.get("balance_minor", 0),
            "current_date": state.get("current_date"),
            "version": state.get("version", 0),
            "reset_count": state.get("reset_count", 0),
            "rescheduled_bills": state.get("rescheduled_bills", {}),
            "scheduled_actions": Store._accepted_actions(state, state.get("current_date")),
            "accepted_actions": state.get("accepted_actions", []),
            "collected_invoices": state.get("collected_invoices", []),
            "state_hash": state.get("state_hash") or Store._state_hash(state),
        }

    def _invalidate_pending_locked(self, db, business_id, reason="snapshot changed"):
        now = utc_now()
        db.execute("UPDATE approvals SET status='invalidated',used_at=? WHERE business_id=? AND status='pending'", (now, business_id))
        db.execute("UPDATE plans SET status='invalidated' WHERE business_id=? AND status IN ('pending','approved')", (business_id,))
        return reason

    def _bump_state_locked(self, db, business_id, invalidate=True):
        row = db.execute("SELECT version FROM sandbox_state WHERE business_id=?", (business_id,)).fetchone()
        if not row:
            return 0
        version = int(row["version"]) + 1
        db.execute("UPDATE sandbox_state SET version=?,updated_at=? WHERE business_id=?", (version, utc_now(), business_id))
        if invalidate:
            self._invalidate_pending_locked(db, business_id)
        return version

    def _business_row(self, db, business_id):
        business_id = validate_business_id(business_id)
        row = db.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone()
        if not row:
            raise ValidationError("Business was not found or is not in this local sandbox.")
        if row["currency"] != PROBAHO_CURRENCY:
            raise ValidationError("Business currency must be BDT.")
        return row

    def ensure_business(self, raw):
        business = validate_business(raw)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM businesses WHERE id=?", (business["business_id"],)).fetchone()
            if existing and (existing["currency"] != business["currency"] or
                             existing["opening_cash_minor"] != business["opening_cash_minor"]):
                raise ValidationError("Business already exists with different immutable opening data.")
            db.execute(
                "INSERT OR IGNORE INTO businesses(id,name,currency,opening_cash_minor,opening_date,default_target_date,synthetic,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (business["business_id"], business["name"], business["currency"], business["opening_cash_minor"],
                 business["opening_date"], business["default_target_date"], int(business["synthetic"]), utc_now()),
            )
            row = db.execute("SELECT * FROM businesses WHERE id=?", (business["business_id"],)).fetchone()
            return dict(row)

    def set_policy(self, business_id, raw):
        """Validate and atomically replace one business policy."""
        business_id = validate_business_id(business_id)
        if not isinstance(raw, dict):
            raise ValidationError("Policy must be an object.")
        policy = validate_policy(raw, business_id)
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                self._business_row(db, business_id)
                previous_row = db.execute("SELECT * FROM policies WHERE business_id=?", (business_id,)).fetchone()
                previous = dict(previous_row) if previous_row else None
                if previous:
                    previous["payroll_priority"] = bool(previous["payroll_priority"])
                    same = all(previous.get(key) == policy.get(key) for key in (
                        "currency", "reserve_floor_minor", "payroll_priority", "action_limit_minor"))
                    if same:
                        return {**previous, "business_id": business_id, "changed": False}
                state_row = db.execute("SELECT state_json FROM sandbox_state WHERE business_id=?", (business_id,)).fetchone()
                accepted_amounts = []
                if state_row:
                    accepted_amounts = [item.get("amount_minor", 0) for item in json.loads(state_row["state_json"]).get("rescheduled_bills", {}).values()]
                if any(isinstance(amount, int) and amount > policy["action_limit_minor"] for amount in accepted_amounts):
                    raise ValidationError("Action limit cannot be lowered below an accepted sandbox schedule; reset the sandbox first.")
                db.execute("INSERT OR REPLACE INTO policies(business_id,currency,reserve_floor_minor,payroll_priority,action_limit_minor,version,updated_at) VALUES (?,?,?,?,?,?,?)",
                           (business_id, policy["currency"], policy["reserve_floor_minor"], int(policy["payroll_priority"]),
                            policy["action_limit_minor"], policy["version"], utc_now()))
                business = self._business_row(db, business_id)
                db.execute("INSERT OR IGNORE INTO sandbox_state(business_id,balance_minor,current_date,version,state_json,reset_count,updated_at) VALUES (?,?,?,?,?,?,?)",
                           (business_id, business["opening_cash_minor"], business["opening_date"], 0,
                            json.dumps({"rescheduled_bills": {}, "accepted_actions": [], "collected_invoices": []}, sort_keys=True), 0, utc_now()))
                version = self._bump_state_locked(db, business_id, invalidate=True)
                details = {"business_id": business_id, "policy_version": policy["version"],
                           "policy": policy, "previous_policy": previous, "state_version": version,
                           "operator": "local demo operator"}
                receipt = self._audit(db, "policy.update", "human_approval", details, business_id)
            return {**policy, "business_id": business_id, "changed": True, "state_version": version, **receipt}
        except ValidationError as exc:
            self._reject("policy.update_rejected", exc, business_id)
            raise

    def get_business(self, business_id):
        with self.connect() as db:
            row = self._business_row(db, business_id)
            result = dict(row)
            result["synthetic"] = bool(result["synthetic"])
            return result

    def list_businesses(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM businesses ORDER BY id")]

    # Small read aliases make the scoped domain surface explicit for callers
    # outside the HTTP handler while keeping the older ``rows`` API intact.
    def businesses(self):
        return self.list_businesses()

    def get_policy(self, business_id):
        with self.connect() as db:
            self._business_row(db, business_id)
            row = db.execute("SELECT * FROM policies WHERE business_id=?", (business_id,)).fetchone()
            if not row:
                raise ValidationError("A policy is not configured for this business.")
            result = dict(row)
            result["payroll_priority"] = bool(result["payroll_priority"])
            return result

    def policy(self, business_id):
        return self.get_policy(business_id)

    def get_sandbox_state(self, business_id):
        with self.connect() as db:
            business = self._business_row(db, business_id)
            row = db.execute("SELECT * FROM sandbox_state WHERE business_id=?", (business_id,)).fetchone()
            if not row:
                raise ValidationError("Sandbox state is not configured for this business.")
            state = json.loads(row["state_json"])
            result = {"business_id": business_id, "balance_minor": row["balance_minor"],
                      "cash_minor": row["balance_minor"], "current_date": row["current_date"],
                      "version": row["version"], "reset_count": row["reset_count"],
                      "updated_at": row["updated_at"], **state}
            result["business_id"] = business_id
            result["balance_minor"] = row["balance_minor"]
            result["cash_minor"] = row["balance_minor"]
            result["version"] = row["version"]
            result["state_hash"] = self._state_hash(result)
            result["scheduled_actions"] = self._accepted_actions(result, result.get("current_date"))
            return result

    def sandbox(self, business_id):
        return self.get_sandbox_state(business_id)

    def _snapshot_db(self, db, business_id):
        business = dict(self._business_row(db, business_id))
        business["synthetic"] = bool(business["synthetic"])
        policy = db.execute("SELECT * FROM policies WHERE business_id=?", (business_id,)).fetchone()
        if not policy:
            raise ValidationError("A policy is not configured for this business.")
        policy = dict(policy)
        policy["payroll_priority"] = bool(policy["payroll_priority"])
        transactions = [dict(row) for row in db.execute("SELECT * FROM transactions WHERE business_id=? ORDER BY date,id", (business_id,))]
        invoices = [dict(row) for row in db.execute("SELECT * FROM invoices WHERE business_id=? ORDER BY due_date,id", (business_id,))]
        bills = [dict(row) for row in db.execute("SELECT * FROM bills WHERE business_id=? ORDER BY due_date,id", (business_id,))]
        for record in transactions + invoices + bills:
            record["synthetic"] = record.get("source") == "demo"
        for bill in bills:
            bill["reschedule_allowed"] = bool(bill["reschedule_allowed"])
            bill["reschedulable"] = bill["reschedule_allowed"]
        sandbox = db.execute("SELECT * FROM sandbox_state WHERE business_id=?", (business_id,)).fetchone()
        if not sandbox:
            raise ValidationError("Sandbox state is not configured for this business.")
        state = {"business_id": business_id, "balance_minor": sandbox["balance_minor"],
                 "cash_minor": sandbox["balance_minor"], "current_date": sandbox["current_date"],
                 "version": sandbox["version"], "reset_count": sandbox["reset_count"], **json.loads(sandbox["state_json"])}
        state["business_id"] = business_id
        state["balance_minor"] = sandbox["balance_minor"]
        state["cash_minor"] = sandbox["balance_minor"]
        state["version"] = sandbox["version"]
        state["state_hash"] = self._state_hash(state)
        state["scheduled_actions"] = self._accepted_actions(state, state.get("current_date"))
        return business, policy, transactions, invoices, bills, state

    def snapshot(self, business_id):
        with self.connect() as db:
            db.execute("BEGIN")
            business, policy, transactions, invoices, bills, sandbox = self._snapshot_db(db, business_id)
            return {"business": business, "policy": policy, "transactions": transactions,
                    "invoices": invoices, "bills": bills, "sandbox": sandbox,
                    "snapshot_hash": self._snapshot_hash(business, policy, transactions, invoices, bills, sandbox)}

    def rows(self, business_id=None):
        with self.connect() as db:
            if business_id is None:
                # Legacy compatibility only; never expose all business rows
                # through an unscoped call.
                return [dict(r) for r in db.execute("SELECT * FROM transactions WHERE business_id=? ORDER BY date DESC,id DESC", (LEGACY_BUSINESS_ID,))]
            self._business_row(db, business_id)
            return [dict(r) for r in db.execute("SELECT * FROM transactions WHERE business_id=? ORDER BY date DESC,id DESC", (business_id,))]

    def transactions(self, business_id):
        return self.rows(business_id)

    def invoices(self, business_id):
        with self.connect() as db:
            self._business_row(db, business_id)
            return [dict(r) for r in db.execute("SELECT * FROM invoices WHERE business_id=? ORDER BY due_date,id", (business_id,))]

    def list_invoices(self, business_id):
        return self.invoices(business_id)

    def bills(self, business_id):
        with self.connect() as db:
            self._business_row(db, business_id)
            result = [dict(r) for r in db.execute("SELECT * FROM bills WHERE business_id=? ORDER BY due_date,id", (business_id,))]
            for bill in result:
                bill["reschedule_allowed"] = bool(bill["reschedule_allowed"])
                bill["reschedulable"] = bill["reschedule_allowed"]
            return result

    def list_bills(self, business_id):
        return self.bills(business_id)

    def records(self, business_id, limit=None):
        validate_business_id(business_id)
        if limit is not None and (not isinstance(limit, int) or not 1 <= limit <= 5000):
            raise ValidationError("Record limit must be between 1 and 5,000.")
        with self.connect() as db:
            self._business_row(db, business_id)
            suffix = " LIMIT ?" if limit is not None else ""
            args = (business_id, limit) if limit is not None else (business_id,)
            transactions = [dict(r) for r in db.execute(f"SELECT * FROM transactions WHERE business_id=? ORDER BY date DESC,id DESC{suffix}", args)]
            invoices = [dict(r) for r in db.execute(f"SELECT * FROM invoices WHERE business_id=? ORDER BY due_date DESC,id DESC{suffix}", args)]
            bills = [dict(r) for r in db.execute(f"SELECT * FROM bills WHERE business_id=? ORDER BY due_date DESC,id DESC{suffix}", args)]
            for record in transactions + invoices + bills:
                record["synthetic"] = record.get("source") == "demo"
            for bill in bills:
                bill["reschedule_allowed"] = bool(bill["reschedule_allowed"])
                bill["reschedulable"] = bill["reschedule_allowed"]
            return {"transactions": transactions, "invoices": invoices, "bills": bills}

    @staticmethod
    def _import_record_fields(kind, row):
        fields = {
            "transaction": ("id", "business_id", "date", "description", "type", "amount_minor", "currency", "category"),
            "invoice": ("id", "business_id", "customer", "description", "issue_date", "due_date",
                         "expected_collection_date", "status", "amount_minor", "currency"),
            "bill": ("id", "business_id", "payee", "description", "due_date", "amount_minor", "currency",
                      "status", "priority", "reschedule_allowed", "rescheduled_date"),
        }[kind]
        result = {key: row.get(key) for key in fields}
        if kind == "bill":
            result["reschedule_allowed"] = bool(result["reschedule_allowed"])
        return result

    @classmethod
    def _same_import_record(cls, kind, existing, incoming, ignore_id=False):
        left = cls._import_record_fields(kind, dict(existing))
        right = cls._import_record_fields(kind, incoming)
        if kind == "transaction" and (ignore_id or not incoming.get("id")):
            left.pop("id", None)
            right.pop("id", None)
        return left == right

    def import_combined(self, business_id, records, source="csv", replace_demo=False):
        business_id = validate_business_id(business_id)
        if not isinstance(records, dict):
            raise ValidationError("Validated import records are required.")
        # Validate once more at the persistence boundary; callers cannot use
        # this method to bypass business/currency validation.
        transactions = [validate_probaho_transaction(row, business_id) for row in (records.get("transactions", []) or [])]
        invoices = [validate_invoice(row, business_id) for row in (records.get("invoices", []) or [])]
        bills = [validate_bill(row, business_id) for row in (records.get("bills", []) or [])]
        if not any((transactions, invoices, bills)):
            raise ValidationError("At least one transaction, invoice or bill is required.")
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                self._business_row(db, business_id)
                removed = {"transactions": 0, "invoices": 0, "bills": 0}
                state_row = db.execute("SELECT state_json FROM sandbox_state WHERE business_id=?", (business_id,)).fetchone()
                scheduled_ids = set()
                if state_row:
                    scheduled_ids = set((json.loads(state_row["state_json"]).get("rescheduled_bills") or {}).keys())
                if replace_demo and scheduled_ids:
                    placeholders = ",".join("?" for _ in scheduled_ids)
                    params = [business_id, *sorted(scheduled_ids)]
                    scheduled_demo = db.execute(
                        f"SELECT id FROM bills WHERE business_id=? AND source='demo' AND id IN ({placeholders})", params
                    ).fetchall()
                    if scheduled_demo:
                        raise ValidationError("Reset the sandbox before replacing a demo record with an accepted schedule.")
                duplicate_indexes = {"transactions": set(), "invoices": set(), "bills": set()}
                # Check every existing identity before deleting demo rows or
                # inserting any new row.  INSERT OR IGNORE must never hide a
                # financial conflict.
                for index, row in enumerate(transactions):
                    existing = None
                    matched_by_fingerprint = False
                    if row.get("id"):
                        existing = db.execute("SELECT * FROM transactions WHERE business_id=? AND id=?", (business_id, row["id"])).fetchone()
                    if existing is None:
                        normalized = " ".join(row["description"].casefold().split())
                        fingerprint = hashlib.sha256(f"{row['date']}|{normalized}|{row['type']}|{row['amount_minor']}".encode()).hexdigest()
                        existing = db.execute("SELECT * FROM transactions WHERE business_id=? AND fingerprint=?", (business_id, fingerprint)).fetchone()
                        matched_by_fingerprint = existing is not None
                    if existing is not None:
                        if not self._same_import_record("transaction", existing, row, matched_by_fingerprint):
                            raise ValidationError(f"Transaction {row.get('id') or row['date']} conflicts with an existing record.")
                        if not (replace_demo and existing["source"] == "demo"):
                            duplicate_indexes["transactions"].add(index)
                for kind, collection, table in (("invoice", invoices, "invoices"), ("bill", bills, "bills")):
                    for index, row in enumerate(collection):
                        existing = db.execute(f"SELECT * FROM {table} WHERE business_id=? AND id=?", (business_id, row["id"])).fetchone()
                        if existing is not None:
                            if not self._same_import_record(kind, existing, row):
                                label = "Invoice" if kind == "invoice" else "Bill"
                                raise ValidationError(f"{label} {row['id']} conflicts with an existing record.")
                            if not (replace_demo and existing["source"] == "demo"):
                                duplicate_indexes[table].add(index)
                if replace_demo:
                    for table in ("transactions", "invoices", "bills"):
                        removed[table] = db.execute(f"DELETE FROM {table} WHERE business_id=? AND source='demo'", (business_id,)).rowcount
                added = {"transactions": 0, "invoices": 0, "bills": 0}
                duplicate = {"transactions": 0, "invoices": 0, "bills": 0}
                for index, row in enumerate(transactions):
                    if index in duplicate_indexes["transactions"]:
                        duplicate["transactions"] += 1
                        continue
                    normalized = " ".join(row["description"].casefold().split())
                    fingerprint = row.get("fingerprint") or hashlib.sha256(
                        f"{row['date']}|{normalized}|{row['type']}|{row['amount_minor']}".encode()).hexdigest()
                    cursor = db.execute(
                        "INSERT OR IGNORE INTO transactions(id,business_id,date,description,type,amount_minor,currency,category,fingerprint,source,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (row.get("id") or uuid.uuid4().hex, business_id, row["date"], row["description"], row["type"],
                         row["amount_minor"], PROBAHO_CURRENCY, row["category"], fingerprint, source, utc_now()),
                    )
                    added["transactions"] += cursor.rowcount
                duplicate["transactions"] = len(transactions) - added["transactions"]
                for index, row in enumerate(invoices):
                    if index in duplicate_indexes["invoices"]:
                        duplicate["invoices"] += 1
                        continue
                    cursor = db.execute(
                        "INSERT OR IGNORE INTO invoices(business_id,id,customer,description,issue_date,due_date,expected_collection_date,status,amount_minor,currency,source,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (business_id, row["id"], row["customer"], row["description"], row["issue_date"], row["due_date"],
                         row["expected_collection_date"], row["status"], row["amount_minor"], PROBAHO_CURRENCY, source, utc_now()),
                    )
                    added["invoices"] += cursor.rowcount
                for index, row in enumerate(bills):
                    if index in duplicate_indexes["bills"]:
                        duplicate["bills"] += 1
                        continue
                    cursor = db.execute(
                        "INSERT OR IGNORE INTO bills(business_id,id,payee,description,due_date,amount_minor,currency,status,priority,reschedule_allowed,rescheduled_date,source,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (business_id, row["id"], row["payee"], row["description"], row["due_date"], row["amount_minor"],
                         PROBAHO_CURRENCY, row["status"], row["priority"], int(row["reschedule_allowed"]), row.get("rescheduled_date"), source, utc_now()),
                    )
                    added["bills"] += cursor.rowcount
                result = {"business_id": business_id, "added": added, "duplicates_skipped": duplicate,
                          "source": source, "sample_records_removed": removed,
                          "total_added": sum(added.values()), "total_removed": sum(removed.values())}
                mutated = result["total_added"] + result["total_removed"] > 0
                if mutated:
                    result["state_version"] = self._bump_state_locked(db, business_id, invalidate=True)
                else:
                    current = db.execute("SELECT version FROM sandbox_state WHERE business_id=?", (business_id,)).fetchone()
                    result["state_version"] = current["version"] if current else None
                result["mutated"] = mutated
                result["fingerprints"] = [
                    hashlib.sha256(f"{row['date']}|{' '.join(row['description'].casefold().split())}|{row['type']}|{row['amount_minor']}".encode()).hexdigest()
                    for row in transactions
                ]
                result["policy_version"] = (db.execute("SELECT version FROM policies WHERE business_id=?", (business_id,)).fetchone() or {"version": None})["version"]
                result.update(self._audit(db, "ledger.import", "user_write", result, business_id))
            return result
        except ValidationError as exc:
            self._reject("ledger.import_rejected", exc, business_id)
            raise
        except sqlite3.IntegrityError as exc:
            self._reject("ledger.import_rejected", str(exc), business_id)
            raise ValidationError("Import could not be committed atomically; no records were written.") from None

    def import_rows(self, rows, source="csv", replace_demo=False, business_id=None):
        """Compatibility transaction-only import used by the old FinMate UI."""
        if not isinstance(rows, list) or not rows:
            raise ValidationError("At least one transaction is required.")
        if not isinstance(rows[0], dict):
            raise ValidationError("Each transaction must be an object.")
        business_id = business_id or rows[0].get("business_id") or LEGACY_BUSINESS_ID
        validate_business_id(business_id)
        normalized = []
        for raw in rows:
            try:
                if not isinstance(raw, dict):
                    raise ValidationError("Each transaction must be an object.")
                if "fingerprint" in raw and "amount_minor" in raw and raw.get("currency", "BDT") == "BDT":
                    item = dict(raw)
                    item["business_id"] = business_id
                    item.setdefault("source", source)
                else:
                    item = validate_transaction({**raw, "business_id": business_id})
                item = validate_probaho_transaction({**item, "business_id": business_id}, business_id)
                item["fingerprint"] = raw.get("fingerprint") or hashlib.sha256(
                    f"{item['date']}|{' '.join(item['description'].casefold().split())}|{item['type']}|{item['amount_minor']}".encode()).hexdigest()
                normalized.append(item)
            except ValidationError:
                raise
        records = {"transactions": normalized, "invoices": [], "bills": []}
        result = self.import_combined(business_id, records, source, replace_demo)
        # Preserve the integer-shaped receipt used by FinMate's transaction
        # import API.  The combined Probaho endpoint keeps per-record-type
        # dictionaries.
        result["added_by_type"] = result["added"]
        result["duplicates_by_type"] = result["duplicates_skipped"]
        result["removed_by_type"] = result["sample_records_removed"]
        result["added"] = result["added"]["transactions"]
        result["duplicates_skipped"] = result["duplicates_skipped"]["transactions"]
        result["sample_records_removed"] = result["sample_records_removed"]["transactions"]
        return result

    def _seed_business(self, db, business, policy):
        db.execute(
            "INSERT OR IGNORE INTO businesses(id,name,currency,opening_cash_minor,opening_date,default_target_date,synthetic,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (business["business_id"], business["name"], business["currency"], business["opening_cash_minor"],
             business["opening_date"], business["default_target_date"], 1, utc_now()),
        )
        db.execute(
            "INSERT OR REPLACE INTO policies(business_id,currency,reserve_floor_minor,payroll_priority,action_limit_minor,version,updated_at) VALUES (?,?,?,?,?,?,?)",
            (business["business_id"], PROBAHO_CURRENCY, policy["reserve_floor_minor"], int(policy["payroll_priority"]),
             policy["action_limit_minor"], policy["version"], utc_now()),
        )
        state = {"rescheduled_bills": {}, "accepted_actions": [], "collected_invoices": []}
        db.execute(
            "INSERT OR IGNORE INTO sandbox_state(business_id,balance_minor,current_date,version,state_json,reset_count,updated_at) VALUES (?,?,?,?,?,?,?)",
            (business["business_id"], business["opening_cash_minor"], business["opening_date"], 0, json.dumps(state, sort_keys=True), 0, utc_now()),
        )

    def seed_probaho(self):
        fixtures = [
            {
                "business": {"business_id": SHAPLA_BUSINESS_ID, "name": "Shapla Services", "currency": "BDT",
                              "opening_cash_minor": 12_000_000, "opening_date": "2026-10-01",
                              "default_target_date": SEED_TARGET_DATE, "synthetic": True},
                "policy": {"business_id": SHAPLA_BUSINESS_ID, "currency": "BDT", "reserve_floor_minor": 2_000_000,
                           "payroll_priority": True, "action_limit_minor": 5_000_000, "version": "probaho-policy-v2"},
                "transactions": [{"id": "txn-payroll-oct", "date": SEED_TARGET_DATE, "description": "October payroll",
                                  "type": "expense", "amount_minor": 8_000_000, "currency": "BDT", "category": "Payroll"}],
                "invoices": [{"id": "inv-shapla-001", "customer": "Nila Traders", "description": "October service receivable",
                              "issue_date": "2026-10-01", "due_date": SEED_TARGET_DATE, "expected_collection_date": SEED_TARGET_DATE,
                              "status": "confirmed", "amount_minor": 2_000_000, "currency": "BDT"}],
                "bills": [{"id": "bill-supplier-001", "payee": "Rahman Supplies", "description": "Supplier materials bill",
                           "due_date": SEED_TARGET_DATE, "amount_minor": 7_000_000, "currency": "BDT", "status": "open",
                           "priority": "high", "reschedule_allowed": True}],
                "fixture": "shapla-services-v2",
            },
            {
                "business": {"business_id": "meghna-traders", "name": "Meghna Traders", "currency": "BDT",
                              "opening_cash_minor": 3_000_000, "opening_date": "2026-10-01",
                              "default_target_date": SEED_TARGET_DATE, "synthetic": True},
                "policy": {"business_id": "meghna-traders", "currency": "BDT", "reserve_floor_minor": 1_500_000,
                           "payroll_priority": True, "action_limit_minor": 1_000_000, "version": "probaho-policy-v2"},
                "transactions": [{"id": "txn-meghna-payroll", "date": SEED_TARGET_DATE, "description": "October payroll",
                                  "type": "expense", "amount_minor": 2_000_000, "currency": "BDT", "category": "Payroll"}],
                "invoices": [{"id": "inv-meghna-late", "customer": "Delta Retail", "description": "Late customer receivable",
                              "issue_date": "2026-10-01", "due_date": SEED_TARGET_DATE, "expected_collection_date": SEED_TARGET_DATE,
                              "status": "confirmed", "amount_minor": 1_500_000, "currency": "BDT"}],
                "bills": [{"id": "bill-meghna-critical", "payee": "Meghna Wholesale", "description": "Critical supplier settlement",
                           "due_date": SEED_TARGET_DATE, "amount_minor": 2_500_000, "currency": "BDT", "status": "open",
                           "priority": "critical", "reschedule_allowed": False}],
                "fixture": "meghna-late-receivable-v1",
            },
            {
                "business": {"business_id": "padma-designs", "name": "Padma Designs", "currency": "BDT",
                              "opening_cash_minor": 10_000_000, "opening_date": "2026-10-01",
                              "default_target_date": SEED_TARGET_DATE, "synthetic": True},
                "policy": {"business_id": "padma-designs", "currency": "BDT", "reserve_floor_minor": 2_000_000,
                           "payroll_priority": True, "action_limit_minor": 2_000_000, "version": "probaho-policy-v2"},
                "transactions": [{"id": "txn-padma-receipt", "date": "2026-10-15", "description": "Design project receipt",
                                  "type": "income", "amount_minor": 4_000_000, "currency": "BDT", "category": "Income"},
                                 {"id": "txn-padma-payroll", "date": SEED_TARGET_DATE, "description": "October payroll",
                                  "type": "expense", "amount_minor": 2_000_000, "currency": "BDT", "category": "Payroll"}],
                "invoices": [{"id": "inv-padma-001", "customer": "Northstar Studio", "description": "Design retainer",
                              "issue_date": "2026-10-01", "due_date": "2026-10-20", "expected_collection_date": "2026-10-20",
                              "status": "collected", "amount_minor": 1_000_000, "currency": "BDT"}],
                "bills": [{"id": "bill-padma-001", "payee": "Paper House", "description": "Materials bill",
                           "due_date": "2026-10-25", "amount_minor": 1_000_000, "currency": "BDT", "status": "open",
                           "priority": "normal", "reschedule_allowed": True}],
                "fixture": "padma-healthy-v1",
            },
        ]
        # Synthetic history is intentionally before each business' opening
        # date.  It exercises scoped ledger reads and exports without changing
        # the forecast-period Shapla arithmetic.  These are fictional records,
        # not pilot or customer data.
        history_dates = ("2026-08-05", "2026-08-12", "2026-08-19", "2026-08-26", "2026-09-02",
                         "2026-09-09", "2026-09-16", "2026-09-23", "2026-09-28", "2026-09-30")
        for fixture in fixtures:
            business_id = fixture["business"]["business_id"]
            slug = business_id.split("-")[0]
            for index, day in enumerate(history_dates):
                fixture["transactions"].append({
                    "id": f"txn-{slug}-history-{index + 1:02d}", "date": day,
                    "description": f"{fixture['business']['name']} fictional history {index + 1:02d}",
                    "type": "income" if index % 2 == 0 else "expense",
                    "amount_minor": 125_000 + index * 5_000, "currency": "BDT",
                    "category": "Income" if index % 2 == 0 else "Utilities"})
            for index, day in enumerate(history_dates[:5]):
                fixture["invoices"].append({
                    "id": f"inv-{slug}-history-{index + 1:02d}",
                    "customer": f"Fictional customer {slug} {index + 1:02d}",
                    "description": f"Settled fictional receivable {index + 1:02d}",
                    "issue_date": day, "due_date": day,
                    "expected_collection_date": day, "status": "collected",
                    "amount_minor": 90_000 + index * 2_000, "currency": "BDT"})
                fixture["bills"].append({
                    "id": f"bill-{slug}-history-{index + 1:02d}",
                    "payee": f"Fictional supplier {slug} {index + 1:02d}",
                    "description": f"Settled fictional supplier bill {index + 1:02d}",
                    "due_date": day, "amount_minor": 70_000 + index * 3_000,
                    "currency": "BDT", "status": "paid", "priority": "normal",
                    "reschedule_allowed": False})
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for fixture in fixtures:
                business = validate_business(fixture["business"])
                policy = validate_policy(fixture["policy"], business["business_id"])
                self._seed_business(db, business, policy)
                for raw in fixture["transactions"]:
                    row = validate_probaho_transaction({**raw, "business_id": business["business_id"], "source": "demo"}, business["business_id"])
                    fingerprint = hashlib.sha256(f"{row['date']}|{row['description'].casefold()}|{row['type']}|{row['amount_minor']}".encode()).hexdigest()
                    db.execute("INSERT OR IGNORE INTO transactions(id,business_id,date,description,type,amount_minor,currency,category,fingerprint,source,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                               (row["id"], business["business_id"], row["date"], row["description"], row["type"], row["amount_minor"], PROBAHO_CURRENCY, row["category"], fingerprint, "demo", utc_now()))
                for raw in fixture["invoices"]:
                    row = validate_invoice({**raw, "business_id": business["business_id"], "source": "demo"}, business["business_id"])
                    db.execute("INSERT OR IGNORE INTO invoices(business_id,id,customer,description,issue_date,due_date,expected_collection_date,status,amount_minor,currency,source,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                               (business["business_id"], row["id"], row["customer"], row["description"], row["issue_date"], row["due_date"], row["expected_collection_date"], row["status"], row["amount_minor"], PROBAHO_CURRENCY, "demo", utc_now()))
                for raw in fixture["bills"]:
                    row = validate_bill({**raw, "business_id": business["business_id"], "source": "demo"}, business["business_id"])
                    db.execute("INSERT OR IGNORE INTO bills(business_id,id,payee,description,due_date,amount_minor,currency,status,priority,reschedule_allowed,rescheduled_date,source,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (business["business_id"], row["id"], row["payee"], row["description"], row["due_date"], row["amount_minor"], PROBAHO_CURRENCY, row["status"], row["priority"], int(row["reschedule_allowed"]), None, "demo", utc_now()))
                self._audit(db, "probaho.seed", "system_seed", {"business_id": business["business_id"], "fixture": fixture["fixture"], "fixture_version": FIXTURE_VERSION, "history_records": 20}, business["business_id"])
            db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES ('initial_seed',?)", (FIXTURE_VERSION,))

    def seed_demo(self):
        with self.connect() as db:
            seeded = db.execute("SELECT value FROM metadata WHERE key='initial_seed'").fetchone()
            if seeded:
                return
            count = db.execute("SELECT COUNT(*) FROM transactions WHERE business_id IS NULL OR business_id=?", (LEGACY_BUSINESS_ID,)).fetchone()[0]
        if count:
            # An old local DB already has personal records.  Keep that demo
            # isolated and do not silently mix it into the SME fixture.
            self.import_rows(demo_rows(), "demo", business_id=LEGACY_BUSINESS_ID)
            marker = "legacy"
        else:
            self.seed_probaho()
            marker = FIXTURE_VERSION
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES ('initial_seed',?)", (marker,))

    # ---- plan, approval and sandbox -------------------------------------------------

    @staticmethod
    def _action_fingerprint(action):
        return Store._json_hash(action)

    @staticmethod
    def _accepted_actions(state, target_date):
        actions = []
        for bill_id, item in sorted((state.get("rescheduled_bills") or {}).items()):
            actions.append({
                "action_id": item.get("action_id", f"accepted-{bill_id}"),
                "type": "supplier_reschedule",
                "business_id": state.get("business_id"),
                "bill_id": bill_id,
                "payee": item.get("payee"),
                "amount_minor": item.get("amount_minor", 0),
                "currency": PROBAHO_CURRENCY,
                "date": item.get("action_date", target_date),
                "reschedule_to": item.get("reschedule_to"),
            })
        return actions

    @staticmethod
    def _projection_kwargs(business, policy, transactions, invoices, bills, target_date, actions, scenario):
        return {
            "opening_cash_minor": business["opening_cash_minor"],
            "opening_date": business["opening_date"],
            "transactions": transactions,
            "invoices": invoices,
            "bills": bills,
            "policy": policy,
            "target_date": target_date,
            "scenario": scenario,
            "approved_actions": actions,
            "business_id": business["id"],
        }

    def _projection_pair(self, business, policy, transactions, invoices, bills, state, target_date, extra_action=None):
        before_actions = self._accepted_actions(state, target_date)
        after_actions = before_actions + ([extra_action] if extra_action else [])
        before = project_cash(**self._projection_kwargs(business, policy, transactions, invoices, bills, target_date,
                                                        before_actions, "approved_recovery"))
        after = project_cash(**self._projection_kwargs(business, policy, transactions, invoices, bills, target_date,
                                                       after_actions, "approved_recovery"))
        return before, after

    def create_plan(self, business_id, payload):
        business_id = validate_business_id(business_id)
        if not isinstance(payload, dict) or payload.get("business_id") != business_id:
            raise ValidationError("Plan business scope is invalid.")
        plan_hash = payload.get("plan_hash")
        if not isinstance(plan_hash, str) or len(plan_hash) != 64:
            raise ValidationError("Plan hash is invalid.")
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            business, policy, transactions, invoices, bills, state = self._snapshot_db(db, business_id)
            snapshot_hash = self._snapshot_hash(business, policy, transactions, invoices, bills, state)
            if payload.get("snapshot_hash") != snapshot_hash:
                raise ValidationError("The comparison snapshot is stale; compare the current records again.")
            payload = dict(payload)
            if payload.get("policy_version") is None:
                payload["policy_version"] = policy["version"]
            if self._payload_hash(payload) != plan_hash:
                raise ValidationError("Plan hash is invalid for this comparison payload.")
            db.execute("INSERT INTO plans(id,business_id,target_date,plan_hash,snapshot_hash,payload,status,state_version,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       (identifier, business_id, payload["target_date"], plan_hash, snapshot_hash,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True), "pending", state["version"], utc_now()))
            receipt = self._audit(db, "plan.compare", "agent_propose", {
                "plan_id": identifier, "plan_hash": plan_hash, "snapshot_hash": snapshot_hash,
                "target_date": payload["target_date"], "policy_version": policy["version"],
                "actions": payload.get("plans", []),
                "action_fingerprints": {item.get("action_id"): self._action_fingerprint(item)
                                        for item in payload.get("plans", []) if isinstance(item, dict) and item.get("action_id")},
                "operator": "local demo operator",
            }, business_id)
        return {"plan_id": identifier, "id": identifier, "status": "pending", "created_at": utc_now(), **payload, **receipt}

    def get_plan(self, business_id, plan_id):
        validate_business_id(business_id)
        if not isinstance(plan_id, str) or len(plan_id) != 32:
            raise ValidationError("A valid plan_id is required.")
        with self.connect() as db:
            row = db.execute("SELECT * FROM plans WHERE business_id=? AND id=?", (business_id, plan_id)).fetchone()
            if not row:
                raise ValidationError("Plan was not found for this business.")
            result = json.loads(row["payload"])
            result.update({"plan_id": row["id"], "id": row["id"], "status": row["status"], "created_at": row["created_at"], "state_version": row["state_version"], "snapshot_hash": row["snapshot_hash"]})
            return result

    def pending_plan(self, business_id, target_date=None):
        with self.connect() as db:
            self._business_row(db, business_id)
            if target_date is not None:
                target_date = valid_date(target_date, "target_date")
                row = db.execute("SELECT * FROM plans WHERE business_id=? AND target_date=? AND status IN ('pending','approved') ORDER BY rowid DESC LIMIT 1", (business_id, target_date)).fetchone()
            else:
                row = db.execute("SELECT * FROM plans WHERE business_id=? AND status IN ('pending','approved') ORDER BY rowid DESC LIMIT 1", (business_id,)).fetchone()
            if not row:
                return None
            result = json.loads(row["payload"])
            result.update({"plan_id": row["id"], "id": row["id"], "status": row["status"], "created_at": row["created_at"], "state_version": row["state_version"], "snapshot_hash": row["snapshot_hash"]})
            return result

    def pending_approvals(self, business_id, target_date=None):
        with self.connect() as db:
            self._business_row(db, business_id)
            params = [business_id]
            clause = "business_id=? AND status='pending'"
            if target_date is not None:
                target_date = valid_date(target_date, "target_date")
                clause += " AND target_date=?"
                params.append(target_date)
            rows = db.execute(f"SELECT * FROM approvals WHERE {clause} ORDER BY rowid DESC", tuple(params)).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                if _parse_time(row["expiry"]) <= datetime.now(timezone.utc):
                    item["status"] = "expired"
                    item["expired"] = True
                    continue
                plan = db.execute("SELECT payload FROM plans WHERE business_id=? AND id=?", (business_id, row["plan_id"])).fetchone()
                action = None
                if plan:
                    payload = json.loads(plan["payload"])
                    action = next((candidate for candidate in payload.get("plans", [])
                                   if candidate.get("action_id") == row["action_id"]), None)
                item["action"] = action
                consent = db.execute("SELECT status,id FROM supplier_consents WHERE business_id=? AND plan_id=? AND action_id=? ORDER BY rowid DESC LIMIT 1",
                                     (business_id, row["plan_id"], row["action_id"])).fetchone()
                item["consent_status"] = consent["status"] if consent else None
                item["consent_id"] = consent["id"] if consent else None
                result.append(item)
            return result

    @staticmethod
    def _payload_hash(payload):
        body = dict(payload)
        body.pop("plan_hash", None)
        return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _validate_plan_action(self, db, business_id, payload, action_id, require_recovery=True):
        business, policy, transactions, invoices, bills, state = self._snapshot_db(db, business_id)
        current_snapshot = self._snapshot_hash(business, policy, transactions, invoices, bills, state)
        if payload.get("business_id") != business_id:
            raise ValidationError("Plan belongs to another business.")
        valid_date(payload.get("target_date", ""), "target_date")
        if self._payload_hash(payload) != payload.get("plan_hash"):
            raise ValidationError("Plan changed since comparison; generate a new comparison.")
        if payload.get("snapshot_hash") != current_snapshot:
            raise ValidationError("The comparison snapshot is stale; generate a new comparison.")
        if payload.get("policy_version") not in (None, policy["version"]):
            raise ValidationError("Policy changed since comparison; generate a new comparison.")
        wanted_action = str(action_id).replace("_", "-")
        action = next((item for item in payload.get("plans", [])
                       if item.get("action_id") == action_id or str(item.get("action_id", "")).replace("_", "-") == wanted_action), None)
        if not action:
            raise ValidationError("Action was not found in this plan.")
        if action.get("business_id") not in (None, "", business_id):
            raise ValidationError("Action belongs to another business.")
        if not action.get("executable") or action.get("mock"):
            raise ValidationError("This plan option is not executable in the local sandbox.")
        amount = action.get("amount_minor")
        if not isinstance(amount, int) or amount < 0:
            raise ValidationError("Action amount must be an integer minor-unit value.")
        if amount > policy["action_limit_minor"]:
            raise ValidationError("Action amount exceeds the policy action limit.")
        if action.get("currency") != PROBAHO_CURRENCY:
            raise ValidationError("Action currency must be BDT.")
        if action.get("date") != payload.get("target_date"):
            raise ValidationError("Action date does not match the approved target date.")
        if action.get("type") == "collection_reminder":
            invoice = next((row for row in invoices if row["id"] == action.get("invoice_id")), None)
            if not invoice or invoice["customer"] != action.get("payee") or invoice["amount_minor"] != amount:
                raise ValidationError("Invoice/payee/amount changed; the reminder needs new approval.")
            if invoice["expected_collection_date"] != action.get("original_expected_collection_date"):
                raise ValidationError("Invoice collection date changed; the reminder needs new approval.")
            if invoice["status"] not in ("confirmed", "overdue"):
                raise ValidationError("This invoice is not eligible for a reminder.")
            return business, policy, transactions, invoices, bills, state, action
        if action.get("type") in ("supplier_reschedule", "reschedule"):
            bill = next((row for row in bills if row["id"] == action.get("bill_id")), None)
            if not bill:
                raise ValidationError("Supplier bill was not found for this business.")
            if bill["payee"] != action.get("payee"):
                raise ValidationError("Payee changed; the action needs new approval.")
            if bill["status"] in ("paid", "cancelled"):
                raise ValidationError("This supplier bill is no longer open.")
            if not bill["reschedule_allowed"]:
                raise ValidationError("This supplier bill is not reschedulable.")
            if action.get("bill_id") in (state.get("rescheduled_bills") or {}):
                raise ValidationError("This supplier bill already has an accepted sandbox reschedule; generate a new plan after reset.")
            if bill["priority"] == "payroll":
                raise ValidationError("Payroll-priority bills cannot be rescheduled.")
            if action.get("original_due_date") != bill["due_date"]:
                raise ValidationError("Supplier bill date changed; the action needs new approval.")
            if action.get("original_amount_minor") != bill["amount_minor"]:
                raise ValidationError("Supplier bill amount changed; the action needs new approval.")
            if amount <= 0 or amount > bill["amount_minor"]:
                raise ValidationError("Reschedule amount is outside the supplier bill amount.")
            to_date = action.get("reschedule_to", action.get("new_due_date"))
            if not isinstance(to_date, str) or valid_date(to_date, "reschedule_to") <= payload["target_date"]:
                raise ValidationError("A reschedule date must be after the target date.")
            recovery = project_cash(opening_cash_minor=business["opening_cash_minor"],
                                    opening_date=business["opening_date"], transactions=transactions,
                                    invoices=invoices, bills=bills, policy=policy,
                                    target_date=payload["target_date"], scenario="approved_recovery",
                                    approved_actions=self._accepted_actions(state, payload["target_date"]) + [action], business_id=business_id)
            base = project_cash(opening_cash_minor=business["opening_cash_minor"],
                                opening_date=business["opening_date"], transactions=transactions,
                                invoices=invoices, bills=bills, policy=policy,
                                target_date=payload["target_date"], scenario="base", business_id=business_id)
            if recovery.get("payroll_outflow_minor", 0) < base.get("payroll_outflow_minor", 0) and policy["payroll_priority"]:
                raise ValidationError("The recovery plan would violate the payroll constraint.")
            minimum_cash = recovery.get("minimum_cash_minor", recovery.get("closing_cash_minor", 0))
            if require_recovery and (minimum_cash < policy["reserve_floor_minor"] or recovery.get("closing_cash_minor", 0) < policy["reserve_floor_minor"]):
                raise ValidationError("The recovery plan would violate the reserve floor.")
            return business, policy, transactions, invoices, bills, state, action
        raise ValidationError("Unsupported action type.")

    def approve_plan(self, business_id, plan_id, action_id):
        business_id = validate_business_id(business_id)
        if not isinstance(plan_id, str) or len(plan_id) != 32:
            raise ValidationError("A valid plan_id is required.")
        if not isinstance(action_id, str) or not action_id or len(action_id) > 120:
            raise ValidationError("A valid action_id is required.")
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT * FROM plans WHERE business_id=? AND id=?", (business_id, plan_id)).fetchone()
                if not row:
                    raise ValidationError("Plan was not found for this business.")
                if row["status"] not in ("pending", "approved"):
                    raise ValidationError("This plan is no longer pending.")
                payload = json.loads(row["payload"])
                if row["plan_hash"] != payload.get("plan_hash"):
                    raise ValidationError("Plan hash is stale; generate a new comparison.")
                if row["snapshot_hash"] != payload.get("snapshot_hash"):
                    raise ValidationError("Plan snapshot is stale; generate a new comparison.")
                business, policy, transactions, invoices, bills, state, action = self._validate_plan_action(db, business_id, payload, action_id)
                existing = db.execute("SELECT id FROM approvals WHERE business_id=? AND plan_id=? AND action_id=? AND status='pending' ORDER BY rowid DESC LIMIT 1",
                                     (business_id, plan_id, action_id)).fetchone()
                if existing:
                    raise ValidationError("This action already has a pending approval.")
                # A supplier can accept after the human approves.  Consent is
                # intentionally checked only at execution, never fabricated
                # by approval.
                approval_id = uuid.uuid4().hex
                nonce = secrets.token_urlsafe(24)
                expiry = _future(300)
                snapshot_hash = self._snapshot_hash(business, policy, transactions, invoices, bills, state)
                db.execute("INSERT INTO approvals(id,business_id,plan_id,action_id,payee,amount_minor,currency,target_date,plan_hash,snapshot_hash,expiry,nonce,state_version,balance_minor,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (approval_id, business_id, plan_id, action_id, action.get("payee"), action.get("amount_minor", 0), PROBAHO_CURRENCY,
                             payload["target_date"], payload["plan_hash"], snapshot_hash, expiry, nonce, state["version"], state["balance_minor"], "pending", utc_now()))
                db.execute("UPDATE plans SET status='approved' WHERE id=? AND business_id=?", (plan_id, business_id))
                details = {"plan_id": plan_id, "action_id": action_id, "amount_minor": action.get("amount_minor", 0),
                           "currency": PROBAHO_CURRENCY, "target_date": payload["target_date"], "expiry": expiry,
                           "nonce": nonce, "plan_hash": payload["plan_hash"], "snapshot_hash": snapshot_hash,
                           "policy_version": policy["version"], "action": action,
                           "action_fingerprint": self._action_fingerprint(action), "operator": "local demo operator"}
                receipt = self._audit(db, "plan.approve", "human_approval", details, business_id)
            return {"approval_id": approval_id, "id": approval_id, "business_id": business_id, "plan_id": plan_id,
                    "action_id": action_id, "payee": action.get("payee"), "amount_minor": action.get("amount_minor", 0),
                    "currency": PROBAHO_CURRENCY, "target_date": payload["target_date"],
                    "plan_hash": payload["plan_hash"], "snapshot_hash": snapshot_hash, "expiry": expiry, "expires_at": expiry,
                    "nonce": nonce, "status": "pending", "permission": "human_approval",
                    "action": action, "receipt": receipt, **receipt}
        except ValidationError as exc:
            self._reject("plan.approve_rejected", exc, business_id, {"plan_id": plan_id, "action_id": action_id})
            raise

    def record_supplier_consent(self, business_id, plan_id, action_id, accepted):
        business_id = validate_business_id(business_id)
        if not isinstance(plan_id, str) or len(plan_id) != 32:
            raise ValidationError("A valid plan_id is required.")
        if not isinstance(action_id, str) or not action_id or len(action_id) > 120:
            raise ValidationError("A valid action_id is required.")
        if not isinstance(accepted, bool):
            raise ValidationError("accepted must be true or false.")
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                self._business_row(db, business_id)
                plan_row = db.execute("SELECT * FROM plans WHERE business_id=? AND id=?", (business_id, plan_id)).fetchone()
                if not plan_row:
                    raise ValidationError("Plan was not found for this business.")
                if plan_row["status"] not in ("pending", "approved"):
                    raise ValidationError("Consent can only be recorded for a pending or approved plan.")
                payload = json.loads(plan_row["payload"])
                business, policy, transactions, invoices, bills, state = self._snapshot_db(db, business_id)
                current_snapshot = self._snapshot_hash(business, policy, transactions, invoices, bills, state)
                if plan_row["snapshot_hash"] != payload.get("snapshot_hash") or plan_row["snapshot_hash"] != current_snapshot:
                    raise ValidationError("The plan snapshot is stale; compare current records before consent.")
                if self._payload_hash(payload) != payload.get("plan_hash"):
                    raise ValidationError("The plan hash is invalid; compare current records before consent.")
                action = next((item for item in payload.get("plans", [])
                               if item.get("action_id") == action_id or str(item.get("action_id", "")).replace("_", "-") == str(action_id).replace("_", "-")), None)
                if not action or action.get("type") not in ("supplier_reschedule", "reschedule"):
                    raise ValidationError("Supplier consent requires a supplier reschedule action.")
                bill = db.execute("SELECT * FROM bills WHERE business_id=? AND id=?", (business_id, action.get("bill_id"))).fetchone()
                if not bill:
                    raise ValidationError("Supplier bill was not found for this business.")
                amount = action.get("amount_minor")
                new_due = action.get("reschedule_to", action.get("new_due_date"))
                if not isinstance(amount, int) or amount <= 0:
                    raise ValidationError("Supplier consent amount must be a positive integer minor-unit value.")
                if bill["payee"] != action.get("payee") or bill["amount_minor"] < amount or bill["due_date"] != action.get("original_due_date"):
                    raise ValidationError("Supplier bill changed; consent cannot bind to this action.")
                valid_date(new_due, "reschedule_to")
                latest = db.execute("SELECT * FROM supplier_consents WHERE business_id=? AND plan_id=? AND action_id=? ORDER BY rowid DESC LIMIT 1",
                                    (business_id, plan_id, action_id)).fetchone()
                if not accepted:
                    db.execute("UPDATE supplier_consents SET status='revoked',updated_at=? WHERE business_id=? AND plan_id=? AND action_id=? AND status='accepted'",
                               (utc_now(), business_id, plan_id, action_id))
                    status = "revoked" if latest and latest["status"] == "accepted" else "rejected"
                else:
                    status = "accepted"
                consent_id = uuid.uuid4().hex
                now = utc_now()
                db.execute("INSERT INTO supplier_consents(id,business_id,plan_id,action_id,plan_hash,bill_id,payee,amount_minor,original_due_date,new_due_date,status,synthetic,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (consent_id, business_id, plan_id, action_id, plan_row["plan_hash"], action["bill_id"], action["payee"], amount,
                            action["original_due_date"], new_due, status, 1, now, now))
                details = {"consent_id": consent_id, "plan_id": plan_id, "action_id": action_id,
                           "plan_hash": plan_row["plan_hash"], "bill_id": action["bill_id"], "payee": action["payee"],
                           "amount_minor": amount, "original_due_date": action["original_due_date"], "new_due_date": new_due,
                           "status": status, "accepted": accepted, "synthetic": True,
                           "action": action, "action_fingerprint": self._action_fingerprint(action),
                           "operator": "local demo operator", "note": "Manual simulation only; not real supplier acceptance."}
                audit = self._audit(db, "supplier.consent", "human_approval", details, business_id)
            return {"consent_id": consent_id, "status": status, "synthetic": True, "audit": audit, **audit,
                    "business_id": business_id, "plan_id": plan_id, "action_id": action_id,
                    "note": "Manual simulation only; not real supplier acceptance."}
        except ValidationError as exc:
            self._reject("supplier.consent_rejected", exc, business_id, {"plan_id": plan_id, "action_id": action_id})
            raise

    def cancel_approval(self, business_id, approval_id):
        business_id = validate_business_id(business_id)
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT * FROM approvals WHERE business_id=? AND id=?", (business_id, approval_id)).fetchone()
                if not row:
                    raise ValidationError("Approval was not found for this business.")
                if row["status"] != "pending":
                    if row["status"] == "used":
                        raise ValidationError("Executed approvals cannot be cancelled or reversed.")
                    raise ValidationError("Only a pending approval can be cancelled.")
                db.execute("UPDATE approvals SET status='cancelled',used_at=? WHERE business_id=? AND id=? AND status='pending'", (utc_now(), business_id, approval_id))
                db.execute("UPDATE plans SET status='cancelled' WHERE business_id=? AND id=? AND status IN ('pending','approved')", (business_id, row["plan_id"]))
                db.execute("UPDATE supplier_consents SET status='revoked',updated_at=? WHERE business_id=? AND plan_id=? AND action_id=? AND status='accepted'",
                           (utc_now(), business_id, row["plan_id"], row["action_id"]))
                details = {"approval_id": approval_id, "plan_id": row["plan_id"], "action_id": row["action_id"], "operator": "local demo operator"}
                audit = self._audit(db, "plan.cancel", "human_approval", details, business_id)
            return {"approval_id": approval_id, "status": "cancelled", "synthetic": True, **audit}
        except ValidationError as exc:
            self._reject("plan.cancel_rejected", exc, business_id, {"approval_id": approval_id})
            raise

    def execute_plan(self, business_id, approval_id, idempotency_key):
        business_id = validate_business_id(business_id)
        try:
            if not isinstance(approval_id, str) or len(approval_id) != 32:
                raise ValidationError("A valid approval_id is required; direct execution is not allowed.")
            if not isinstance(idempotency_key, str) or not re_fullmatch_idempotency(idempotency_key):
                raise ValidationError("idempotency_key must contain 1-120 safe characters.")
        except ValidationError as exc:
            self._reject("plan.execute_rejected", exc, business_id, {"approval_id": approval_id})
            raise
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                prior = db.execute("SELECT receipt_json FROM executions WHERE business_id=? AND idempotency_key=?", (business_id, idempotency_key)).fetchone()
                if prior:
                    result = json.loads(prior[0])
                    if result.get("approval_id") != approval_id:
                        raise ValidationError("Idempotency key is already bound to a different approval.")
                    return result
                approval = db.execute("SELECT * FROM approvals WHERE business_id=? AND id=?", (business_id, approval_id)).fetchone()
                if not approval:
                    raise ValidationError("Approval was not found for this business.")
                if approval["status"] != "pending":
                    if approval["status"] == "used":
                        raise ValidationError("This approval was already executed; retry with its original idempotency key.")
                    raise ValidationError("This approval has already been used or invalidated.")
                nonce_count = db.execute("SELECT COUNT(*) FROM approvals WHERE nonce=?", (approval["nonce"],)).fetchone()[0]
                if not approval["nonce"] or nonce_count != 1:
                    raise ValidationError("Approval nonce is invalid or has already been consumed.")
                if _parse_time(approval["expiry"]) <= datetime.now(timezone.utc):
                    db.execute("UPDATE approvals SET status='expired' WHERE id=?", (approval_id,))
                    raise ValidationError("Approval has expired; compare and approve the current action again.")
                plan_row = db.execute("SELECT * FROM plans WHERE business_id=? AND id=?", (business_id, approval["plan_id"])).fetchone()
                if not plan_row:
                    raise ValidationError("The approved plan is no longer available.")
                payload = json.loads(plan_row["payload"])
                if approval["plan_hash"] != plan_row["plan_hash"] or self._payload_hash(payload) != approval["plan_hash"]:
                    raise ValidationError("Plan hash changed after approval; approval is invalid.")
                if plan_row["snapshot_hash"] != payload.get("snapshot_hash") or approval["snapshot_hash"] != plan_row["snapshot_hash"]:
                    raise ValidationError("Plan snapshot changed after approval; approval is invalid.")
                business, policy, transactions, invoices, bills, state = self._snapshot_db(db, business_id)
                current_snapshot = self._snapshot_hash(business, policy, transactions, invoices, bills, state)
                if approval["snapshot_hash"] != current_snapshot or payload.get("snapshot_hash") != current_snapshot:
                    raise ValidationError("The approved snapshot is stale; compare and approve the current action again.")
                if state["version"] != approval["state_version"] or state["balance_minor"] != approval["balance_minor"]:
                    raise ValidationError("Sandbox state or current balance is stale; compare and approve again.")
                business, policy, transactions, invoices, bills, state, action = self._validate_plan_action(db, business_id, payload, approval["action_id"])
                if action.get("payee") != approval["payee"] or action.get("amount_minor", 0) != approval["amount_minor"]:
                    raise ValidationError("Approved payee or amount changed; approval is invalid.")
                action_type = action.get("type")
                state_json = {"rescheduled_bills": {}, "accepted_actions": [], "collected_invoices": []}
                raw_state = db.execute("SELECT state_json FROM sandbox_state WHERE business_id=?", (business_id,)).fetchone()
                if raw_state:
                    state_json.update(json.loads(raw_state[0]))
                projection_before, projection_after = self._projection_pair(business, policy, transactions, invoices, bills, state,
                                                                            payload["target_date"], action)
                consent_row = None
                if action_type in ("supplier_reschedule", "reschedule"):
                    consent_row = db.execute("SELECT * FROM supplier_consents WHERE business_id=? AND plan_id=? AND action_id=? AND plan_hash=? AND bill_id=? AND payee=? AND amount_minor=? AND original_due_date=? AND new_due_date=? ORDER BY rowid DESC LIMIT 1",
                                             (business_id, approval["plan_id"], approval["action_id"], approval["plan_hash"], action["bill_id"], action["payee"], action["amount_minor"], action["original_due_date"], action.get("reschedule_to", action.get("new_due_date")))).fetchone()
                    if not consent_row or consent_row["status"] != "accepted":
                        raise ValidationError("Matching accepted supplier consent is required before execution.")
                    if action["bill_id"] in state_json.get("rescheduled_bills", {}):
                        raise ValidationError("This supplier bill already has an accepted sandbox reschedule; use a new plan after reset.")
                receipt_id = uuid.uuid4().hex
                if action_type == "supplier_reschedule":
                    state_json.setdefault("rescheduled_bills", {})[action["bill_id"]] = {
                        "amount_minor": action["amount_minor"], "reschedule_to": action["reschedule_to"], "payee": action["payee"],
                        "action_id": action["action_id"], "action_date": action.get("date"), "plan_hash": approval["plan_hash"],
                        "consent_id": consent_row["id"] if consent_row else None}
                elif action_type == "collection_reminder":
                    reminder_id = uuid.uuid4().hex
                    db.execute("INSERT INTO reminders(id,business_id,invoice_id,payee,body,target_date,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
                               (reminder_id, business_id, action["invoice_id"], action["payee"],
                                "Synthetic reminder draft; sending is not connected.", action["date"], "draft", utc_now()))
                    state_json.setdefault("accepted_actions", []).append({"action_id": action["action_id"], "reminder_id": reminder_id})
                else:
                    raise ValidationError("Only sandbox reminder and supplier actions can execute.")
                after_version = state["version"] + 1
                db.execute("UPDATE sandbox_state SET version=?,state_json=?,updated_at=? WHERE business_id=?",
                           (after_version, json.dumps(state_json, ensure_ascii=False, sort_keys=True), utc_now(), business_id))
                after_row = db.execute("SELECT * FROM sandbox_state WHERE business_id=?", (business_id,)).fetchone()
                state_after = {"business_id": business_id, "balance_minor": after_row["balance_minor"], "cash_minor": after_row["balance_minor"],
                               "current_date": after_row["current_date"], "version": after_row["version"], "reset_count": after_row["reset_count"],
                               **json.loads(after_row["state_json"])}
                state_after["state_hash"] = self._state_hash(state_after)
                recorded_after_state = self._public_state(state_after)
                read_back = {
                    "source": "post-mutation SELECT in the atomic transaction",
                    "recorded_after_state": recorded_after_state,
                    "verified": bool(recorded_after_state["version"] == after_version and
                                     recorded_after_state["business_id"] == business_id and
                                     json.loads(after_row["state_json"]) == state_json),
                }
                db.execute("UPDATE approvals SET status='used',used_at=? WHERE id=? AND status='pending'", (utc_now(), approval_id))
                if db.execute("SELECT changes()").fetchone()[0] != 1:
                    raise ValidationError("Approval was consumed by another request.")
                receipt = {"receipt_id": receipt_id, "execution_id": receipt_id, "business_id": business_id, "approval_id": approval_id,
                           "plan_id": approval["plan_id"], "plan_hash": approval["plan_hash"], "snapshot_hash": current_snapshot,
                           "idempotency_key": idempotency_key, "status": "executed", "action_id": action["action_id"],
                           "action_type": action_type, "action": action, "payee": action.get("payee"),
                           "amount_minor": action.get("amount_minor", 0), "currency": PROBAHO_CURRENCY,
                            "target_date": action.get("date"), "state_before": self._public_state(state),
                            "state_after": recorded_after_state, "projection_before": projection_before,
                            "projection_after": projection_after, "cash_effect_minor": 0, "synthetic": True,
                           "permission": "sandbox_execute", "operator": "local demo operator",
                           "note": "Schedule change only; no instant money movement occurred.",
                           "action_fingerprint": self._action_fingerprint(action)}
                audit_details = {"execution_id": receipt_id, "approval_id": approval_id, "plan_id": approval["plan_id"],
                                 "plan_hash": approval["plan_hash"], "snapshot_hash": current_snapshot,
                                 "policy_version": policy["version"], "action": action,
                                 "action_fingerprint": receipt["action_fingerprint"], "receipt": receipt}
                audit = self._audit(db, "plan.execute", "sandbox_execute", audit_details, business_id)
                receipt["audit"] = audit
                receipt["read_back"] = read_back
                response = {**receipt, "receipt": dict(receipt)}
                db.execute("INSERT INTO executions(id,business_id,approval_id,idempotency_key,action_id,payee,amount_minor,currency,target_date,receipt_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           (receipt_id, business_id, approval_id, idempotency_key, action["action_id"], action.get("payee"), action.get("amount_minor", 0), PROBAHO_CURRENCY, action.get("date"), json.dumps(response, ensure_ascii=False, sort_keys=True), utc_now()))
                db.execute("UPDATE plans SET status='executed' WHERE id=? AND business_id=?", (approval["plan_id"], business_id))
                db.execute("UPDATE approvals SET status='invalidated',used_at=? WHERE business_id=? AND status='pending' AND id<>?", (utc_now(), business_id, approval_id))
                db.execute("UPDATE plans SET status='invalidated' WHERE business_id=? AND status IN ('pending','approved') AND id<>?", (business_id, approval["plan_id"]))
            return response
        except ValidationError as exc:
            if "expired" in str(exc).lower() and isinstance(approval_id, str):
                try:
                    with self.connect() as db:
                        db.execute("BEGIN IMMEDIATE")
                        db.execute("UPDATE approvals SET status='expired' WHERE business_id=? AND id=? AND status='pending'", (business_id, approval_id))
                except Exception:
                    pass
            self._reject("plan.execute_rejected", exc, business_id, {"approval_id": approval_id, "idempotency_key": idempotency_key})
            raise

    def reset_sandbox(self, business_id):
        business_id = validate_business_id(business_id)
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                business, _, _, _, _, state = self._snapshot_db(db, business_id)
                fresh = {"rescheduled_bills": {}, "accepted_actions": [], "collected_invoices": []}
                db.execute("UPDATE sandbox_state SET balance_minor=?,current_date=?,version=?,state_json=?,reset_count=reset_count+1,updated_at=? WHERE business_id=?",
                           (business["opening_cash_minor"], business["opening_date"], state["version"] + 1, json.dumps(fresh, sort_keys=True), utc_now(), business_id))
                db.execute("UPDATE approvals SET status='invalidated',used_at=? WHERE business_id=? AND status IN ('pending','approved')", (utc_now(), business_id))
                db.execute("UPDATE plans SET status='invalidated' WHERE business_id=? AND status IN ('pending','approved')", (business_id,))
                db.execute("UPDATE supplier_consents SET status='revoked',updated_at=? WHERE business_id=? AND status='accepted'", (utc_now(), business_id))
                receipt = {"business_id": business_id, "balance_minor": business["opening_cash_minor"], "cash_minor": business["opening_cash_minor"],
                           "sandbox_version": state["version"] + 1, "reset": True, "schedule_reset_only": True,
                           "records_preserved": True, "receipts_preserved": True, "synthetic": True,
                           "operator": "local demo operator"}
                receipt.update(self._audit(db, "sandbox.reset", "human_approval", receipt, business_id))
            sandbox_state = self._public_state(self.get_sandbox_state(business_id))
            return {**receipt, "sandbox_state": sandbox_state, "receipt": dict(receipt)}
        except ValidationError as exc:
            self._reject("sandbox.reset_rejected", exc, business_id)
            raise

    def create_reminder_draft(self, business_id, invoice_id, target_date, body="Reminder draft"):
        business_id = validate_business_id(business_id)
        from .finance import valid_date
        target_date = valid_date(target_date, "target_date")
        if not isinstance(invoice_id, str) or not invoice_id:
            raise ValidationError("invoice_id is required.")
        if not isinstance(body, str) or not body.strip() or len(body) > 500:
            raise ValidationError("Reminder body must contain 1-500 characters.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._business_row(db, business_id)
            invoice = db.execute("SELECT * FROM invoices WHERE business_id=? AND id=?", (business_id, invoice_id)).fetchone()
            if not invoice:
                raise ValidationError("Invoice was not found for this business.")
            if invoice["status"] not in ("confirmed", "overdue"):
                raise ValidationError("Only confirmed or overdue invoices can receive reminder drafts.")
            identifier = uuid.uuid4().hex
            db.execute("INSERT INTO reminders(id,business_id,invoice_id,payee,body,target_date,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
                       (identifier, business_id, invoice_id, invoice["customer"], body.strip(), target_date, "draft", utc_now()))
            result = {"reminder_id": identifier, "business_id": business_id, "invoice_id": invoice_id,
                      "payee": invoice["customer"], "target_date": target_date, "status": "draft",
                      "cash_effect_minor": 0, "note": "Reminder draft only; no receivable was collected."}
            result.update(self._audit(db, "reminder.draft", "agent_propose", result, business_id))
            return result

    def executions(self, business_id=None):
        with self.connect() as db:
            if business_id is None:
                # Compatibility callers without a scope may inspect only the
                # isolated legacy business; never return every SME receipt.
                rows = db.execute("SELECT * FROM executions WHERE business_id=? ORDER BY rowid", (LEGACY_BUSINESS_ID,)).fetchall()
            else:
                self._business_row(db, business_id)
                rows = db.execute("SELECT * FROM executions WHERE business_id=? ORDER BY rowid", (business_id,)).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["receipt"] = json.loads(item.pop("receipt_json"))
                result.append(item)
            return result

    def execution_receipt(self, business_id, idempotency_key):
        business_id = validate_business_id(business_id)
        if not isinstance(idempotency_key, str) or not re_fullmatch_idempotency(idempotency_key):
            raise ValidationError("idempotency_key must contain 1-120 safe characters.")
        with self.connect() as db:
            self._business_row(db, business_id)
            row = db.execute("SELECT receipt_json FROM executions WHERE business_id=? AND idempotency_key=?", (business_id, idempotency_key)).fetchone()
            return {"found": bool(row), "receipt": json.loads(row["receipt_json"]) if row else None}

    def consents(self, business_id, plan_id=None, action_id=None):
        business_id = validate_business_id(business_id)
        with self.connect() as db:
            self._business_row(db, business_id)
            clauses = ["business_id=?"]
            params = [business_id]
            if plan_id is not None:
                clauses.append("plan_id=?")
                params.append(plan_id)
            if action_id is not None:
                clauses.append("action_id=?")
                params.append(action_id)
            rows = [dict(row) for row in db.execute(f"SELECT * FROM supplier_consents WHERE {' AND '.join(clauses)} ORDER BY rowid", tuple(params))]
            for row in rows:
                row["synthetic"] = bool(row["synthetic"])
            return rows

    # ---- legacy budget API ----------------------------------------------------------

    def new_draft(self, payload):
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO drafts(id,month,payload,created_at) VALUES (?,?,?,?)",
                       (identifier, payload["month"], json.dumps(payload, ensure_ascii=False), utc_now()))
            receipt = self._audit(db, "budget.draft", "agent_propose", {"draft_id": identifier, "month": payload["month"], "savings_percent": payload["savings_percent"]}, LEGACY_BUSINESS_ID)
        return {"id": identifier, "status": "pending", "payload": payload, **receipt}

    def approve(self, identifier):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM drafts WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise ValidationError("Budget draft was not found.")
            if row["status"] != "pending":
                raise ValidationError("This draft is no longer pending. Generate a new draft to make changes.")
            db.execute("INSERT INTO budgets VALUES (?,?,?,?) ON CONFLICT(month) DO UPDATE SET draft_id=excluded.draft_id,payload=excluded.payload,approved_at=excluded.approved_at",
                       (row["month"], identifier, row["payload"], utc_now()))
            db.execute("UPDATE drafts SET status='approved' WHERE id=?", (identifier,))
            db.execute("UPDATE drafts SET status='superseded' WHERE month=? AND status='pending'", (row["month"],))
            receipt = self._audit(db, "budget.approve", "human_approval", {"draft_id": identifier, "month": row["month"]}, LEGACY_BUSINESS_ID)
        return {"id": identifier, "status": "approved", "payload": json.loads(row["payload"]), **receipt}

    def budget(self, month):
        with self.connect() as db:
            row = db.execute("SELECT * FROM budgets WHERE month=?", (month,)).fetchone()
            return {"id": row["draft_id"], "status": "approved", "payload": json.loads(row["payload"])} if row else None

    def pending(self, month):
        with self.connect() as db:
            row = db.execute("SELECT * FROM drafts WHERE month=? AND status='pending' ORDER BY rowid DESC LIMIT 1", (month,)).fetchone()
            return {"id": row["id"], "status": row["status"], "payload": json.loads(row["payload"])} if row else None

    def evidence(self, business_id=None):
        business_id = business_id or LEGACY_BUSINESS_ID
        with self.connect() as db:
            self._business_row(db, business_id)
            rows = [dict(r) for r in db.execute("SELECT * FROM audit WHERE business_id=? AND chain_version='business-v2' ORDER BY id", (business_id,))]
            legacy_rows = []
            if business_id == LEGACY_BUSINESS_ID:
                legacy_rows = [dict(r) for r in db.execute("SELECT * FROM audit WHERE (business_id=? OR business_id IS NULL) AND chain_version='legacy-global-v1' ORDER BY id", (business_id,))]
        valid = True
        previous = "0" * 64
        for row in rows:
            serialized = row["details"]
            digest = hashlib.sha256(f"{previous}|{business_id}|{row['timestamp']}|{row['action']}|{row['permission']}|{serialized}".encode()).hexdigest()
            valid = valid and row["previous_hash"] == previous and row["entry_hash"] == digest
            previous = row["entry_hash"]
            # Preserve exact canonical bytes so an exported consumer can
            # verify without guessing a JSON serializer's whitespace rules.
            row["details_json"] = serialized
            try:
                row["details"] = json.loads(row["details"])
            except (ValueError, TypeError):
                valid = False
        for row in legacy_rows:
            row["details_json"] = row["details"]
            try:
                row["details"] = json.loads(row["details"])
            except (ValueError, TypeError):
                pass
        return {"project": "Probaho", "track": "Topic E", "environment": "local SQLite sandbox",
                "currency": PROBAHO_CURRENCY, "business_id": business_id, "exported_at": utc_now(),
                "hash_chain_valid": bool(valid), "hash_chain_scope": business_id, "chain_version": "business-v2",
                "self_verifiable": True, "genesis_hash": "0" * 64, "head_hash": previous,
                "hash_algorithm": "sha256(previous_hash|business_id|timestamp|action|permission|details_json) UTF-8",
                "entries": rows, "legacy_entries": legacy_rows,
                "legacy_verification": "not verified; filtered historical global entries are not an independent chain" if legacy_rows else None,
                "operator_scope": LOCAL_OPERATOR,
                "note": "Synthetic local evidence verifies an independent per-business hash chain; it is not third-party certification or real-money capability."}


def re_fullmatch_idempotency(value):
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}", value))


def demo_rows():
    records = []
    templates = [
        (1, "Monthly salary", 45000, "income", "Income"),
        (2, "Apartment rent", 14000, "expense", "Housing"),
        (3, "Shwapno groceries", 1850, "expense", "Groceries"),
        (4, "Internet bill", 1200, "expense", "Utilities"),
        (5, "Spotify subscription", 199, "expense", "Subscriptions"),
        (5, "Netflix subscription", 850, "expense", "Subscriptions"),
        (6, "University course", 2500, "expense", "Education"),
        (6, "Pathao rides", 620, "expense", "Transport"),
        (7, "Freelance project", 8000, "income", "Income"),
        (7, "Coffee with friends", 540, "expense", "Dining"),
        (8, "Electricity bill", 1700, "expense", "Utilities"),
        (9, "Foodpanda dinner", 1250, "expense", "Dining"),
        (9, "Local grocery market", 2100, "expense", "Groceries"),
        (10, "Daraz shopping", 1850, "expense", "Shopping"),
        (10, "Pharmacy medicine", 650, "expense", "Health"),
        (11, "Pathao rides", 420, "expense", "Transport"),
        (12, "Cafe lunch", 780, "expense", "Dining"),
        (15, "Weekly groceries", 1750, "expense", "Groceries"),
        (18, "Restaurant dinner", 950, "expense", "Dining"),
        (20, "Bus pass", 800, "expense", "Transport"),
        (23, "Bookshop purchase", 650, "expense", "Shopping"),
        (26, "Weekly groceries", 1200, "expense", "Groceries"),
    ]
    for month in ("2026-09", "2026-10"):
        for day, description, amount, kind, category in templates:
            if month == "2026-10" and day > 12:
                continue
            records.append(validate_transaction({"date": f"{month}-{day:02d}", "description": description,
                                                 "amount": amount, "type": kind, "category": category}))
    return records
