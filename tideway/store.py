"""SQLite persistence and the approval-gated workflow for Tideway.

Every read is scoped to one business and every mutation runs inside a
``BEGIN IMMEDIATE`` transaction.  The sandbox is synthetic: no bank,
payment rail, lender, supplier or customer is connected to this store.

Workflow: plan (agent proposal) -> approvals (one or two humans, PIN
step-up) -> signed mandate -> simulated counterparty negotiation ->
idempotent execution with read-back -> receipt.  Each step re-checks the
snapshot hash so nothing approved on stale data can execute.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import analytics, security
from .constraints import check_plan_constraints
from .domain import (
    OPEN_INVOICE_STATUSES,
    SecurityError,
    ValidationError,
    canonical_json,
    check_new_pin,
    text_value,
    validate_bill,
    validate_business,
    validate_business_id,
    validate_invoice,
    validate_policy,
    validate_transaction,
    validate_username,
    valid_date,
    days_between,
)
from .projection import project, summary


SESSION_HOURS = 8
MANDATE_MINUTES = 15
STANDING_MANDATE_DAYS = 7
MAX_PIN_FAILURES = 5
LOCKOUT_MINUTES = 5
BREAKER_DENIALS = 5          # security denials ...
BREAKER_WINDOW_MINUTES = 10  # ... within this window pause the agent automatically
FAST_APPROVAL_MS = 2000
APPROVER_ROLES = ("owner", "accountant")
ROLES = ("owner", "accountant", "viewer")
INVITE_DAYS = 7
# Illustrative SaaS plans: the sandbox enforces seats; prices are shown, never charged.
PLANS = {
    "demo": {"label": "Demo", "price_usd_month": 0, "seats": 10, "businesses": 3},
    "starter": {"label": "Starter", "price_usd_month": 0, "seats": 3, "businesses": 1},
    "growth": {"label": "Growth", "price_usd_month": 19, "seats": 10, "businesses": 5},
}
BUNDLE_LIVE = ("active", "ready", "countered", "rejected")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _later(**delta):
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat(timespec="seconds")


def _parse_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else datetime.min.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def _expired(value):
    return _parse_time(value) <= datetime.now(timezone.utc)


def json_hash(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _fingerprint(row):
    """Duplicate detection.  Rows with their own ids are distinct even if date, text and amount match."""
    text = " ".join(row["description"].casefold().split())
    return hashlib.sha256(f"{row['date']}|{text}|{row['type']}|{row['amount_minor']}|{row.get('id') or ''}".encode()).hexdigest()


def idempotency_ok(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}", value))


def _entry_digest(previous, business_id, row):
    return hashlib.sha256(f"{previous}|{business_id}|{row['timestamp']}|{row['action']}|{row['actor']}|"
                          f"{row['permission']}|{row['details']}".encode()).hexdigest()


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS businesses (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, currency TEXT NOT NULL,
    opening_cash_minor INTEGER NOT NULL CHECK(opening_cash_minor >= 0),
    opening_date TEXT NOT NULL, default_target_date TEXT NOT NULL,
    country TEXT NOT NULL DEFAULT '', sector TEXT NOT NULL DEFAULT '',
    synthetic INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operators (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('owner','accountant','viewer')),
    pin_salt TEXT NOT NULL, pin_hash TEXT NOT NULL, failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memberships (
    business_id TEXT NOT NULL, operator_id TEXT NOT NULL REFERENCES operators(id),
    role TEXT NOT NULL CHECK(role IN ('owner','accountant','viewer')), created_at TEXT NOT NULL,
    PRIMARY KEY(business_id, operator_id));
CREATE TABLE IF NOT EXISTS invites (
    token_hash TEXT PRIMARY KEY, business_id TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('accountant','viewer','owner')),
    display_name TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
    used_by TEXT, used_at TEXT);
CREATE TABLE IF NOT EXISTS subscriptions (
    business_id TEXT PRIMARY KEY, plan TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT, business_id TEXT NOT NULL, operator_id TEXT NOT NULL, mode TEXT NOT NULL,
    helpful INTEGER NOT NULL CHECK(helpful IN (0,1)), question_sha256 TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS login_failures (
    key TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0, locked_until TEXT);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, operator_id TEXT NOT NULL REFERENCES operators(id),
    created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS transactions (
    business_id TEXT NOT NULL, id TEXT NOT NULL, date TEXT NOT NULL, description TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('income','expense')), amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
    currency TEXT NOT NULL, category TEXT NOT NULL, fingerprint TEXT NOT NULL,
    risk_flags TEXT NOT NULL DEFAULT '[]', source TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(business_id,id), UNIQUE(business_id,fingerprint));
CREATE TABLE IF NOT EXISTS invoices (
    business_id TEXT NOT NULL, id TEXT NOT NULL, customer TEXT NOT NULL, description TEXT NOT NULL,
    issue_date TEXT NOT NULL, due_date TEXT NOT NULL, expected_collection_date TEXT NOT NULL,
    status TEXT NOT NULL, paid_date TEXT, amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
    currency TEXT NOT NULL, risk_flags TEXT NOT NULL DEFAULT '[]', source TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(business_id,id));
CREATE TABLE IF NOT EXISTS bills (
    business_id TEXT NOT NULL, id TEXT NOT NULL, payee TEXT NOT NULL, payee_account TEXT,
    description TEXT NOT NULL, due_date TEXT NOT NULL, amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
    currency TEXT NOT NULL, status TEXT NOT NULL, priority TEXT NOT NULL,
    reschedule_allowed INTEGER NOT NULL DEFAULT 0, rescheduled_date TEXT,
    risk_flags TEXT NOT NULL DEFAULT '[]', source TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(business_id,id));
CREATE TABLE IF NOT EXISTS counterparties (
    business_id TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('supplier','customer')),
    profile_json TEXT NOT NULL DEFAULT '{}', verified_account TEXT, verified_by TEXT, verified_at TEXT,
    PRIMARY KEY(business_id,name,kind));
CREATE TABLE IF NOT EXISTS policies (
    business_id TEXT PRIMARY KEY, policy_json TEXT NOT NULL, version TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sandbox_state (
    business_id TEXT PRIMARY KEY, current_date TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0,
    state_json TEXT NOT NULL, reset_count INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY, business_id TEXT NOT NULL, target_date TEXT NOT NULL, plan_hash TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
    proposed_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY, business_id TEXT NOT NULL, plan_id TEXT NOT NULL, bundle_id TEXT NOT NULL,
    operator_id TEXT NOT NULL, role TEXT NOT NULL, review_ms INTEGER, created_at TEXT NOT NULL,
    risk_acknowledgement TEXT,
    UNIQUE(plan_id,bundle_id,operator_id));
CREATE TABLE IF NOT EXISTS mandates (
    id TEXT PRIMARY KEY, business_id TEXT NOT NULL, plan_id TEXT, bundle_id TEXT, kind TEXT NOT NULL,
    document TEXT NOT NULL, status TEXT NOT NULL, expires_at TEXT NOT NULL, nonce TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL, used_at TEXT);
CREATE TABLE IF NOT EXISTS negotiations (
    id TEXT PRIMARY KEY, business_id TEXT NOT NULL, mandate_id TEXT NOT NULL, action_id TEXT NOT NULL,
    counterparty TEXT NOT NULL, request_json TEXT NOT NULL, response_json TEXT NOT NULL, status TEXT NOT NULL,
    simulated_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY, business_id TEXT NOT NULL, mandate_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
    receipt_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(business_id,idempotency_key));
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY, business_id TEXT NOT NULL, mandate_id TEXT, action_id TEXT NOT NULL,
    record_id TEXT NOT NULL, counterparty TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL,
    reply TEXT, status TEXT NOT NULL, human_present INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, business_id TEXT NOT NULL, timestamp TEXT NOT NULL,
    action TEXT NOT NULL, actor TEXT NOT NULL, permission TEXT NOT NULL, details TEXT NOT NULL,
    previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS audit_business ON audit(business_id,id);
CREATE INDEX IF NOT EXISTS plan_business ON plans(business_id,status,created_at);
CREATE INDEX IF NOT EXISTS mandate_business ON mandates(business_id,status,created_at);
"""


class Store:
    def __init__(self, path, key_path=None, witness_path=None):
        self._memory = str(path) == ":memory:"
        self.path = None if self._memory else Path(path)
        self._uri = f"file:tideway_{id(self)}_{secrets.token_hex(4)}?mode=memory&cache=shared" if self._memory else None
        self._keepalive = sqlite3.connect(self._uri, uri=True) if self._memory else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            key_path = key_path or self.path.with_suffix(".key")
            witness_path = witness_path or self.path.with_suffix(".witness.json")
        self.key = security.load_key(key_path)
        # The witness has its own key and file.  Someone who can rewrite the
        # database (and recompute the chain) still cannot forge a cosigned
        # checkpoint without this second secret.
        self.witness_key = security.load_key(Path(witness_path).with_suffix(".key") if witness_path else None)
        self.witness_path = Path(witness_path) if witness_path else None
        self._witness_memory = {}
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            # Existing local workspaces retain their approvals. A missing acknowledgement
            # is never treated as consent when issuing or executing a risky mandate.
            if "risk_acknowledgement" not in {row["name"] for row in db.execute("PRAGMA table_info(approvals)")}:
                db.execute("ALTER TABLE approvals ADD COLUMN risk_acknowledgement TEXT")

    def close(self):
        """Release the keeper connection used by shared in-memory databases."""
        keepalive, self._keepalive = self._keepalive, None
        if keepalive is not None:
            keepalive.close()

    def __del__(self):
        # Tests and short-lived tools create many in-memory stores. Do not leave
        # their keeper connections for interpreter shutdown to warn about.
        try:
            self.close()
        except Exception:
            pass

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self._uri, uri=True, timeout=10) if self._memory else sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    # ---- audit, witness and circuit breaker ---------------------------------

    @staticmethod
    def _audit(db, business_id, action, actor, permission, details):
        row = {"timestamp": utc_now(), "action": action, "actor": actor, "permission": permission,
               "details": canonical_json(details)}
        previous = db.execute("SELECT entry_hash FROM audit WHERE business_id=? ORDER BY id DESC LIMIT 1",
                              (business_id,)).fetchone()
        previous_hash = previous[0] if previous else "0" * 64
        digest = _entry_digest(previous_hash, business_id, row)
        cursor = db.execute("INSERT INTO audit(business_id,timestamp,action,actor,permission,details,previous_hash,entry_hash) "
                            "VALUES (?,?,?,?,?,?,?,?)",
                            (business_id, row["timestamp"], action, actor, permission, row["details"], previous_hash, digest))
        return {"audit_id": cursor.lastrowid, "audit_hash": digest}

    def audit(self, business_id, action, actor, permission, details):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._business_row(db, business_id)
            return self._audit(db, business_id, action, actor, permission, details)

    def reject(self, business_id, action, actor, reason, details=None, security_relevant=False):
        """Record a denied request and trip the circuit breaker on repeated security denials.

        Never raises: a failed audit must not mask the original error.
        """
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                self._business_row(db, business_id)
                self._audit(db, business_id, action, actor, "denied",
                            {"reason": str(reason)[:300], "security_relevant": security_relevant, **(details or {})})
                if security_relevant:
                    self._maybe_trip_breaker(db, business_id)
        except Exception:
            pass

    def _maybe_trip_breaker(self, db, business_id):
        since = (datetime.now(timezone.utc) - timedelta(minutes=BREAKER_WINDOW_MINUTES)).isoformat(timespec="seconds")
        resumed = db.execute("SELECT MAX(id) FROM audit WHERE business_id=? AND action='policy.update' "
                             "AND details LIKE '%\"resumed\":true%'", (business_id,)).fetchone()[0] or 0
        count = db.execute("SELECT COUNT(*) FROM audit WHERE business_id=? AND permission='denied' AND timestamp>=? AND id>? "
                           "AND details LIKE '%\"security_relevant\":true%'", (business_id, since, resumed)).fetchone()[0]
        policy = self._policy(db, business_id)
        if count >= BREAKER_DENIALS and not policy["agent_paused"]:
            policy = {**policy, "agent_paused": True, "paused_reason": f"Circuit breaker: {count} security denials "
                                                                         f"in {BREAKER_WINDOW_MINUTES} minutes"}
            db.execute("UPDATE policies SET policy_json=?,updated_at=? WHERE business_id=?",
                       (canonical_json(policy), utc_now(), business_id))
            self._bump(db, business_id)
            self._audit(db, business_id, "circuit_breaker.trip", "system", "system_control",
                        {"denials": count, "window_minutes": BREAKER_WINDOW_MINUTES,
                         "effect": "agent paused; pending plans and mandates invalidated; owner must resume with a reason"})

    @staticmethod
    def _witness_marker_key(business_id):
        return f"witness:{business_id}"

    def _witness_read_status(self):
        if self.witness_path is None:
            return dict(self._witness_memory), None
        try:
            data = json.loads(self.witness_path.read_text())
        except FileNotFoundError:
            return {}, "missing"
        except (OSError, TypeError, ValueError):
            return {}, "unreadable"
        if not isinstance(data, dict):
            return {}, "unreadable"
        return data, None

    def _witness_read(self):
        return self._witness_read_status()[0]

    def _witness_write(self, data):
        if self.witness_path is None:
            self._witness_memory = dict(data)
            return
        self.witness_path.write_text(json.dumps(data, sort_keys=True, indent=1))

    def _witness_signature(self, item):
        body = canonical_json({key: item[key] for key in ("business_id", "size", "head_hash", "cosigned_at")})
        return hmac.new(self.witness_key, body.encode(), hashlib.sha256).hexdigest()

    def witness_cosign(self, business_id):
        """Cosign the current chain head only if the previous head is still in place."""
        with self.connect() as db:
            rows = db.execute("SELECT id,entry_hash FROM audit WHERE business_id=? ORDER BY id", (business_id,)).fetchall()
        data = self._witness_read()
        previous = data.get(business_id)
        if previous and (len(rows) < previous["size"] or rows[previous["size"] - 1]["entry_hash"] != previous["head_hash"]):
            return {"cosigned": False, "reason": "The chain no longer contains the previously witnessed head."}
        item = {"business_id": business_id, "size": len(rows), "head_hash": rows[-1]["entry_hash"] if rows else "0" * 64,
                "cosigned_at": utc_now()}
        item["signature"] = self._witness_signature(item)
        data[business_id] = item
        self._witness_write(data)
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES (?,?)",
                       (self._witness_marker_key(business_id), item["cosigned_at"]))
        return {"cosigned": True, **item}

    def evidence(self, business_id):
        with self.connect() as db:
            self._business_row(db, business_id)
            rows = [dict(row) for row in db.execute("SELECT * FROM audit WHERE business_id=? ORDER BY id", (business_id,))]
            expected_witness = db.execute("SELECT 1 FROM metadata WHERE key=?",
                                         (self._witness_marker_key(business_id),)).fetchone() is not None
        valid, previous, first_bad = True, "0" * 64, None
        for index, row in enumerate(rows):
            ok = row["previous_hash"] == previous and row["entry_hash"] == _entry_digest(previous, business_id, row)
            if not ok and first_bad is None:
                first_bad = index + 1
            valid = valid and ok
            previous = row["entry_hash"]
            row["details_json"] = row["details"]
            try:
                row["details"] = json.loads(row["details"])
            except ValueError:
                valid = False
            except TypeError:
                valid = False
        witness_data, _ = self._witness_read_status()
        witnessed = witness_data.get(business_id)
        witness = {"present": bool(witnessed)}
        if witnessed:
            size = witnessed.get("size") if isinstance(witnessed, dict) else None
            head_hash = witnessed.get("head_hash") if isinstance(witnessed, dict) else None
            cosigned_at = witnessed.get("cosigned_at") if isinstance(witnessed, dict) else None
            try:
                signature_ok = isinstance(witnessed, dict) and isinstance(witnessed.get("signature"), str) and \
                    hmac.compare_digest(self._witness_signature(witnessed), witnessed["signature"])
            except (KeyError, TypeError, ValueError):
                signature_ok = False
            size_ok = isinstance(size, int) and not isinstance(size, bool) and size > 0
            in_place = size_ok and len(rows) >= size and rows[size - 1]["entry_hash"] == head_hash
            witness.update({"size": size, "head_hash": head_hash, "cosigned_at": cosigned_at,
                            "signature_valid": signature_ok, "consistent": signature_ok and in_place})
            problems = []
            if not signature_ok:
                problems.append("The witness signature is invalid.")
            if not in_place:
                problems.append(f"Chain has {len(rows)} entries but the witness cosigned {size}; "
                                "entries were truncated or rewritten.")
            if problems:
                valid = False
                witness["problem"] = " ".join(problems)
        elif expected_witness:
            valid = False
            witness.update({"signature_valid": False, "consistent": False,
                            "problem": "The previously recorded witness is missing; the witness file may have been deleted or is unreadable."})
        checkpoint = {"business_id": business_id, "entries": len(rows), "head_hash": previous, "signed_at": utc_now()}
        checkpoint["signature"] = security.sign(self.key, checkpoint)
        return {"project": "Tideway", "track": "FinTechathon 2026 International Track, Topic E",
                "environment": "local SQLite sandbox (synthetic)", "business_id": business_id,
                "exported_at": utc_now(), "hash_chain_valid": valid, "first_invalid_entry": first_bad,
                "genesis_hash": "0" * 64, "head_hash": previous, "checkpoint": checkpoint, "witness": witness,
                "hash_algorithm": "sha256(previous_hash|business_id|timestamp|action|actor|permission|details_json)",
                "entries": rows,
                "note": "Synthetic local evidence. The per-business hash chain, signed checkpoint and separately keyed "
                        "witness make edits and truncation detectable. Tamper-evident, not tamper-proof; not third-party "
                        "certification."}

    def tamper_drill(self, business_id):
        """Flip one byte in an in-memory copy of the chain and show where verification breaks.

        The live database is never modified; this demonstrates tamper evidence safely.
        """
        with self.connect() as db:
            self._business_row(db, business_id)
            rows = [dict(row) for row in db.execute("SELECT * FROM audit WHERE business_id=? ORDER BY id", (business_id,))]
        if len(rows) < 2:
            raise ValidationError("The audit chain is too short for a drill.")
        victim = len(rows) // 2
        original = rows[victim]["details"]
        rows[victim]["details"] = original.replace("0", "1", 1) if "0" in original else original + " "
        previous, broken = "0" * 64, None
        for index, row in enumerate(rows):
            if row["previous_hash"] != previous or row["entry_hash"] != _entry_digest(previous, business_id, row):
                broken = index + 1
                break
            previous = row["entry_hash"]
        return {"entries": len(rows), "edited_entry": victim + 1, "edited_action": rows[victim]["action"],
                "verification_breaks_at": broken, "detected": broken == victim + 1,
                "live_database_modified": False,
                "explanation": f"Changing one character in entry {victim + 1} ({rows[victim]['action']}) makes its hash differ, "
                               "so verification stops exactly there. Every later entry depends on it."}

    # ---- operators and sessions --------------------------------------------

    def ensure_operator(self, operator_id, name, role, pin):
        if role not in ROLES:
            raise ValidationError("Unknown role.")
        salt, digest = security.hash_pin(pin)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO operators(id,name,role,pin_salt,pin_hash,created_at) VALUES (?,?,?,?,?,?)",
                       (operator_id, name, role, salt, digest, utc_now()))

    def operators(self):
        with self.connect() as db:
            return [{"id": row["id"], "name": row["name"], "role": row["role"]}
                    for row in db.execute("SELECT id,name,role FROM operators ORDER BY CASE role WHEN 'owner' THEN 0 "
                                          "WHEN 'accountant' THEN 1 ELSE 2 END,id")]

    def verify_pin(self, operator_id, pin, client=None):
        """Check a PIN.  Wrong PINs count toward a lockout and are committed.

        Sign-in failures are counted per (client, operator), so an anonymous caller guessing PINs
        cannot lock a signed-in operator out of their own step-up checks; step-up failures are
        counted on the operator.
        """
        if not isinstance(operator_id, str) or not isinstance(pin, str):
            raise ValidationError("Operator and PIN must be text.")
        key = f"{client}|{operator_id}"[:200] if client is not None else None
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM operators WHERE id=?", (operator_id,)).fetchone()
            if key is not None:
                counter = db.execute("SELECT failures,locked_until FROM login_failures WHERE key=?", (key,)).fetchone()
                failures, locked_until = (counter[0], counter[1]) if counter else (0, None)
            else:
                failures, locked_until = (row["failed_attempts"], row["locked_until"]) if row else (0, None)
            if locked_until and not _expired(locked_until):
                raise ValidationError("Too many wrong PINs. This sign-in is locked for a few minutes.")
            ok = None
            if row and security.check_pin(pin, row["pin_salt"], row["pin_hash"]):
                ok = {"id": row["id"], "name": row["name"], "role": row["role"]}
                failures, locked = 0, None
            else:
                failures += 1
                locked = _later(minutes=LOCKOUT_MINUTES) if failures >= MAX_PIN_FAILURES else None
                failures = 0 if locked else failures
            if key is not None:
                db.execute("INSERT INTO login_failures(key,failures,locked_until) VALUES (?,?,?) "
                           "ON CONFLICT(key) DO UPDATE SET failures=excluded.failures,locked_until=excluded.locked_until",
                           (key, failures, locked))
            elif row:
                db.execute("UPDATE operators SET failed_attempts=?,locked_until=? WHERE id=?", (failures, locked, operator_id))
        if ok is None:
            raise ValidationError("Unknown operator or wrong PIN.")
        return ok

    def login(self, operator_id, pin, client="local"):
        operator = self.verify_pin(operator_id, pin, client=client)
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (utc_now(),))
            db.execute("INSERT INTO sessions(token_hash,operator_id,created_at,expires_at) VALUES (?,?,?,?)",
                       (security.token_hash(token), operator["id"], utc_now(), _later(hours=SESSION_HOURS)))
        return token, operator

    def session_operator(self, token):
        if not isinstance(token, str) or not token or len(token) > 200:
            return None
        with self.connect() as db:
            row = db.execute("SELECT o.id,o.name,o.role,s.expires_at FROM sessions s JOIN operators o ON o.id=s.operator_id "
                             "WHERE s.token_hash=?", (security.token_hash(token),)).fetchone()
        if not row or _expired(row["expires_at"]):
            return None
        return {"id": row["id"], "name": row["name"], "role": row["role"]}

    def logout(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (security.token_hash(token or ""),))

    # ---- SaaS: workspaces, memberships, invites, plans ----------------------

    def membership_role(self, operator_id, business_id):
        """The operator's role in this business, or None: tenants never see each other's data."""
        with self.connect() as db:
            row = db.execute("SELECT role FROM memberships WHERE business_id=? AND operator_id=?",
                             (business_id, operator_id)).fetchone()
        return row["role"] if row else None

    def businesses_for(self, operator_id):
        with self.connect() as db:
            rows = db.execute("SELECT b.*, m.role FROM businesses b JOIN memberships m ON m.business_id=b.id "
                              "WHERE m.operator_id=? ORDER BY b.rowid", (operator_id,)).fetchall()
        return [{**self._business_dict(row), "role": row["role"]} for row in rows]

    def ensure_membership(self, business_id, operator_id, role):
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO memberships(business_id,operator_id,role,created_at) VALUES (?,?,?,?)",
                       (business_id, operator_id, role, utc_now()))

    def subscription(self, business_id):
        with self.connect() as db:
            row = db.execute("SELECT plan FROM subscriptions WHERE business_id=?", (business_id,)).fetchone()
            seats = db.execute("SELECT COUNT(*) FROM memberships WHERE business_id=?", (business_id,)).fetchone()[0]
            pending = db.execute("SELECT COUNT(*) FROM invites WHERE business_id=? AND used_at IS NULL AND expires_at>?",
                                 (business_id, utc_now())).fetchone()[0]
        plan = row["plan"] if row else "demo"
        return {"plan": plan, **PLANS[plan], "seats_used": seats, "pending_invites": pending}

    def signup(self, business_raw, policy_raw, owner_id, owner_name, pin, plan="starter"):
        """Create a workspace: the business, its owner account and membership, in one transaction."""
        if plan not in ("starter", "growth"):
            raise ValidationError("Choose the Starter or Growth plan.")
        operator_id = validate_username(owner_id)
        name = text_value({"name": owner_name}, "name", limit=80, label="Your name")
        check_new_pin(pin)
        salt, digest = security.hash_pin(pin)
        business = validate_business(business_raw)
        policy = validate_policy({**policy_raw, "business_id": business["business_id"]}, business["business_id"],
                                 business["currency"])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM operators WHERE id=?", (operator_id,)).fetchone():
                raise ValidationError("That username is taken. Choose another.")
            if db.execute("SELECT 1 FROM businesses WHERE id=?", (business["business_id"],)).fetchone():
                raise ValidationError("A business with this id already exists.")
            db.execute("INSERT INTO operators(id,name,role,pin_salt,pin_hash,created_at) VALUES (?,?,?,?,?,?)",
                       (operator_id, name, "owner", salt, digest, utc_now()))
            db.execute("INSERT INTO businesses(id,name,currency,opening_cash_minor,opening_date,default_target_date,country,sector,synthetic,created_at) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (business["business_id"], business["name"], business["currency"], business["opening_cash_minor"],
                        business["opening_date"], business["default_target_date"], business["country"], business["sector"],
                        0, utc_now()))
            db.execute("INSERT INTO policies(business_id,policy_json,version,updated_at) VALUES (?,?,?,?)",
                       (business["business_id"], canonical_json(policy), policy["version"], utc_now()))
            db.execute("INSERT INTO sandbox_state(business_id,current_date,version,state_json,updated_at) VALUES (?,?,?,?,?)",
                       (business["business_id"], business["opening_date"], 0, canonical_json(self._empty_state()), utc_now()))
            db.execute("INSERT INTO memberships(business_id,operator_id,role,created_at) VALUES (?,?,?,?)",
                       (business["business_id"], operator_id, "owner", utc_now()))
            db.execute("INSERT INTO subscriptions(business_id,plan,created_at) VALUES (?,?,?)", (business["business_id"], plan, utc_now()))
            self._audit(db, business["business_id"], "workspace.signup", f"operator:{operator_id}", "human_approval",
                        {"business": business, "plan": plan, "owner": operator_id})
        return business, {"id": operator_id, "name": name, "role": "owner"}

    def create_invite(self, business_id, inviter, role, display_name):
        if inviter["role"] != "owner":
            raise ValidationError("Only the owner can invite people.")
        if role not in ROLES:
            raise ValidationError("Role must be owner, accountant or viewer.")
        name = text_value({"name": display_name}, "name", limit=80, label="Name")
        token = secrets.token_urlsafe(9)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._business_row(db, business_id)
            plan = (db.execute("SELECT plan FROM subscriptions WHERE business_id=?", (business_id,)).fetchone() or {"plan": "demo"})["plan"]
            seats = db.execute("SELECT COUNT(*) FROM memberships WHERE business_id=?", (business_id,)).fetchone()[0]
            pending = db.execute("SELECT COUNT(*) FROM invites WHERE business_id=? AND used_at IS NULL AND expires_at>?",
                                 (business_id, utc_now())).fetchone()[0]
            if seats + pending >= PLANS[plan]["seats"]:
                raise ValidationError(f"The {PLANS[plan]['label']} plan includes {PLANS[plan]['seats']} seats. "
                                      "Remove a member, cancel an invite or upgrade.")
            expires = _later(days=INVITE_DAYS)
            db.execute("INSERT INTO invites(token_hash,business_id,role,display_name,created_by,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
                       (security.token_hash(token), business_id, role, name, inviter["id"], utc_now(), expires))
            receipt = self._audit(db, business_id, "team.invite", f"operator:{inviter['id']}", "human_approval",
                                  {"role": role, "name": name, "expires_at": expires})
        return {"code": token, "role": role, "name": name, "expires_at": expires, **receipt}

    def accept_invite(self, code, operator=None, username=None, name=None, pin=None):
        """Join a business with an invite code: as the signed-in operator, or as a new account."""
        if not isinstance(code, str) or not 8 <= len(code) <= 40:
            raise ValidationError("That invite code is not valid.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            invite = db.execute("SELECT * FROM invites WHERE token_hash=?", (security.token_hash(code.strip()),)).fetchone()
            if not invite or invite["used_at"] or _expired(invite["expires_at"]):
                raise ValidationError("That invite code is not valid, was already used or has expired.")
            if operator is None:
                operator_id = validate_username(username)
                display = text_value({"name": name or invite["display_name"]}, "name", limit=80, label="Your name")
                check_new_pin(pin)
                if db.execute("SELECT 1 FROM operators WHERE id=?", (operator_id,)).fetchone():
                    raise ValidationError("That username is taken. Choose another, or sign in first and then join.")
                salt, digest = security.hash_pin(pin)
                db.execute("INSERT INTO operators(id,name,role,pin_salt,pin_hash,created_at) VALUES (?,?,?,?,?,?)",
                           (operator_id, display, invite["role"], salt, digest, utc_now()))
                operator = {"id": operator_id, "name": display, "role": invite["role"]}
            if db.execute("SELECT 1 FROM memberships WHERE business_id=? AND operator_id=?",
                          (invite["business_id"], operator["id"])).fetchone():
                raise ValidationError("You are already a member of this business.")
            db.execute("INSERT INTO memberships(business_id,operator_id,role,created_at) VALUES (?,?,?,?)",
                       (invite["business_id"], operator["id"], invite["role"], utc_now()))
            db.execute("UPDATE invites SET used_by=?,used_at=? WHERE token_hash=?", (operator["id"], utc_now(), invite["token_hash"]))
            self._audit(db, invite["business_id"], "team.join", f"operator:{operator['id']}", "human_approval",
                        {"role": invite["role"], "invited_by": invite["created_by"]})
        return {"business_id": invite["business_id"], "role": invite["role"], "operator": operator}

    def team(self, business_id):
        with self.connect() as db:
            self._business_row(db, business_id)
            members = [dict(row) for row in db.execute(
                "SELECT o.id, o.name, m.role, m.created_at FROM memberships m JOIN operators o ON o.id=m.operator_id "
                "WHERE m.business_id=? ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'accountant' THEN 1 ELSE 2 END, o.name",
                (business_id,))]
            invites = [dict(row) for row in db.execute(
                "SELECT display_name, role, created_by, expires_at FROM invites WHERE business_id=? AND used_at IS NULL "
                "AND expires_at>? ORDER BY created_at", (business_id, utc_now()))]
        return {"members": members, "pending_invites": invites, "subscription": self.subscription(business_id)}

    def remove_member(self, business_id, owner, operator_id):
        if owner["role"] != "owner":
            raise ValidationError("Only the owner can remove people.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT role FROM memberships WHERE business_id=? AND operator_id=?",
                             (business_id, operator_id)).fetchone()
            if not row:
                raise ValidationError("That person is not a member of this business.")
            owners = db.execute("SELECT COUNT(*) FROM memberships WHERE business_id=? AND role='owner'", (business_id,)).fetchone()[0]
            if row["role"] == "owner" and owners <= 1:
                raise ValidationError("A business must keep at least one owner.")
            db.execute("DELETE FROM memberships WHERE business_id=? AND operator_id=?", (business_id, operator_id))
            return self._audit(db, business_id, "team.remove", f"operator:{owner['id']}", "human_approval",
                               {"operator_id": operator_id, "role": row["role"]})

    # ---- answer feedback (for honest usability evidence) --------------------

    def add_feedback(self, business_id, operator, mode, helpful, question, comment=""):
        """Thumbs up/down on an assistant answer.  Only a hash of the question is kept, never its text."""
        if mode not in ("tidelm", "local", "llm", "small_talk") or not isinstance(helpful, bool):
            raise ValidationError("Feedback needs a mode and helpful=true/false.")
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValidationError("Feedback must refer to a question.")
        note = text_value({"comment": comment or ""}, "comment", required=False, limit=500, label="Comment")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._business_row(db, business_id)
            db.execute("INSERT INTO feedback(business_id,operator_id,mode,helpful,question_sha256,comment,created_at) VALUES (?,?,?,?,?,?,?)",
                       (business_id, operator["id"], mode, int(helpful), hashlib.sha256(question.encode()).hexdigest(), note, utc_now()))
        return self.feedback_summary(business_id)

    def feedback_summary(self, business_id):
        with self.connect() as db:
            rows = db.execute("SELECT mode, SUM(helpful) AS up, COUNT(*) AS total FROM feedback WHERE business_id=? GROUP BY mode",
                              (business_id,)).fetchall()
            comments = [dict(row) for row in db.execute(
                "SELECT mode, helpful, comment, created_at FROM feedback WHERE business_id=? AND comment<>'' ORDER BY id DESC LIMIT 20",
                (business_id,))]
        return {"by_mode": {row["mode"]: {"helpful": row["up"], "total": row["total"]} for row in rows}, "recent_comments": comments}

    # ---- businesses, policy, records ---------------------------------------

    def _business_row(self, db, business_id):
        validate_business_id(business_id)
        row = db.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone()
        if not row:
            raise ValidationError("Business was not found in this sandbox.")
        return row

    @staticmethod
    def _business_dict(row):
        result = dict(row)
        result["business_id"] = result["id"]
        result["synthetic"] = bool(result["synthetic"])
        return result

    def list_businesses(self):
        with self.connect() as db:
            return [self._business_dict(row) for row in db.execute("SELECT * FROM businesses ORDER BY rowid")]

    def get_business(self, business_id):
        with self.connect() as db:
            return self._business_dict(self._business_row(db, business_id))

    def create_business(self, raw, policy_raw, counterparties=(), actor="system"):
        business = validate_business(raw)
        policy = validate_policy({**policy_raw, "business_id": business["business_id"]}, business["business_id"],
                                 business["currency"])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM businesses WHERE id=?", (business["business_id"],)).fetchone():
                raise ValidationError("A business with this id already exists.")
            db.execute("INSERT INTO businesses(id,name,currency,opening_cash_minor,opening_date,default_target_date,country,sector,synthetic,created_at) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (business["business_id"], business["name"], business["currency"], business["opening_cash_minor"],
                        business["opening_date"], business["default_target_date"], business["country"], business["sector"],
                        int(business["synthetic"]), utc_now()))
            db.execute("INSERT INTO policies(business_id,policy_json,version,updated_at) VALUES (?,?,?,?)",
                       (business["business_id"], canonical_json(policy), policy["version"], utc_now()))
            db.execute("INSERT INTO sandbox_state(business_id,current_date,version,state_json,updated_at) VALUES (?,?,?,?,?)",
                       (business["business_id"], business["opening_date"], 0, canonical_json(self._empty_state()), utc_now()))
            for item in counterparties:
                db.execute("INSERT OR REPLACE INTO counterparties(business_id,name,kind,profile_json,verified_account) VALUES (?,?,?,?,?)",
                           (business["business_id"], item["name"], item["kind"], canonical_json(item.get("profile", {})),
                            item.get("verified_account")))
            self._audit(db, business["business_id"], "business.create", actor, "system_seed",
                        {"business": business, "policy_version": policy["version"]})
        return business

    @staticmethod
    def _empty_state():
        return {"adjustments": [], "promises": {}, "executed_exposure": {}}

    def _policy(self, db, business_id):
        row = db.execute("SELECT policy_json FROM policies WHERE business_id=?", (business_id,)).fetchone()
        if not row:
            raise ValidationError("A policy is not configured for this business.")
        return json.loads(row["policy_json"])

    def _records(self, db, business_id):
        def rows(query):
            result = []
            for row in db.execute(query, (business_id,)):
                item = dict(row)
                item["risk_flags"] = json.loads(item.get("risk_flags") or "[]")
                item["synthetic"] = item.get("source") == "demo"
                result.append(item)
            return result
        transactions = rows("SELECT * FROM transactions WHERE business_id=? ORDER BY date,id")
        invoices = rows("SELECT * FROM invoices WHERE business_id=? ORDER BY due_date,id")
        bills = rows("SELECT * FROM bills WHERE business_id=? ORDER BY due_date,id")
        for bill in bills:
            bill["reschedule_allowed"] = bool(bill["reschedule_allowed"])
        return {"transactions": transactions, "invoices": invoices, "bills": bills}

    def _counterparties(self, db, business_id):
        result = {}
        for row in db.execute("SELECT * FROM counterparties WHERE business_id=? ORDER BY kind,name", (business_id,)):
            result[f"{row['kind']}:{row['name']}"] = {
                "name": row["name"], "kind": row["kind"], "profile": json.loads(row["profile_json"]),
                "verified_account": row["verified_account"], "verified_by": row["verified_by"],
                "verified_at": row["verified_at"]}
        return result

    def _state(self, db, business_id):
        row = db.execute("SELECT * FROM sandbox_state WHERE business_id=?", (business_id,)).fetchone()
        if not row:
            raise ValidationError("Sandbox state is not configured for this business.")
        state = {**self._empty_state(), **json.loads(row["state_json"])}
        state.update({"business_id": business_id, "current_date": row["current_date"], "version": row["version"],
                      "reset_count": row["reset_count"]})
        state["state_hash"] = json_hash({key: state[key] for key in ("adjustments", "promises", "executed_exposure", "version")})
        return state

    def _snapshot(self, db, business_id):
        business = self._business_dict(self._business_row(db, business_id))
        policy = self._policy(db, business_id)
        records = self._records(db, business_id)
        counterparties = self._counterparties(db, business_id)
        state = self._state(db, business_id)
        stable = {kind: [{key: value for key, value in row.items() if key not in ("created_at", "synthetic")}
                         for row in rows] for kind, rows in records.items()}
        digest = json_hash({"business": {key: business[key] for key in ("id", "currency", "opening_cash_minor", "opening_date")},
                            "policy": policy, "records": stable,
                            "verified": sorted((key, item["verified_account"] or "") for key, item in counterparties.items()),
                            # Promises-to-pay are excluded: a customer reply must not invalidate approvals.
                            # Execution re-projects with the current promises and blocks if the reserve is breached.
                            "state": json_hash({key: state[key] for key in ("adjustments", "executed_exposure", "version")})})
        return {"business": business, "policy": policy, "records": records, "counterparties": counterparties,
                "state": state, "snapshot_hash": digest}

    def snapshot(self, business_id):
        with self.connect() as db:
            db.execute("BEGIN")
            return self._snapshot(db, business_id)

    def records(self, business_id):
        with self.connect() as db:
            self._business_row(db, business_id)
            return self._records(db, business_id)

    def import_records(self, business_id, parsed, actor, source="csv", replace_demo=False):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            business = self._business_row(db, business_id)
            currency = business["currency"]
            transactions = [validate_transaction(row, business_id, currency) for row in parsed.get("transactions", [])]
            invoices = [validate_invoice(row, business_id, currency) for row in parsed.get("invoices", [])]
            bills = [validate_bill(row, business_id, currency) for row in parsed.get("bills", [])]
            if not (transactions or invoices or bills):
                raise ValidationError("At least one transaction, invoice or bill is required.")
            state = self._state(db, business_id)
            if replace_demo and state["adjustments"]:
                raise ValidationError("Reset the sandbox before replacing demo records that have accepted adjustments.")
            fields = {"transactions": ("date", "description", "type", "amount_minor", "category"),
                      "invoices": ("customer", "description", "issue_date", "due_date", "expected_collection_date",
                                   "status", "paid_date", "amount_minor"),
                      "bills": ("payee", "payee_account", "description", "due_date", "amount_minor", "status",
                                "priority", "rescheduled_date")}
            planned = []
            # Check every identity before deleting or inserting anything, so a
            # conflict rejects the whole file and never half-imports.
            for row in transactions:
                row["fingerprint"] = _fingerprint(row)
                row["id"] = row["id"] or "txn-" + row["fingerprint"][:16]
                existing = (db.execute("SELECT * FROM transactions WHERE business_id=? AND id=?", (business_id, row["id"])).fetchone()
                            or db.execute("SELECT * FROM transactions WHERE business_id=? AND fingerprint=?",
                                          (business_id, row["fingerprint"])).fetchone())
                planned.append(("transactions", row, existing))
            for kind, collection in (("invoices", invoices), ("bills", bills)):
                for row in collection:
                    planned.append((kind, row, db.execute(f"SELECT * FROM {kind} WHERE business_id=? AND id=?",
                                                          (business_id, row["id"])).fetchone()))
            keep = []
            skipped = {"transactions": 0, "invoices": 0, "bills": 0}
            for kind, row, existing in planned:
                if existing is not None:
                    replaceable = replace_demo and existing["source"] == "demo"
                    same = all(existing[field] == row[field] for field in fields[kind])
                    if kind == "bills":
                        same = same and bool(existing["reschedule_allowed"]) == row["reschedule_allowed"]
                    if not same and not replaceable:
                        raise ValidationError(f"{kind[:-1].title()} {row['id']} conflicts with an existing record; nothing was imported.")
                    if same and not replaceable:
                        skipped[kind] += 1
                        continue
                keep.append((kind, row))
            removed = {"transactions": 0, "invoices": 0, "bills": 0}
            if replace_demo:
                for kind in removed:
                    removed[kind] = db.execute(f"DELETE FROM {kind} WHERE business_id=? AND source='demo'", (business_id,)).rowcount
            added = {"transactions": 0, "invoices": 0, "bills": 0}
            now = utc_now()
            for kind, row in keep:
                flags = canonical_json(row["risk_flags"])
                if kind == "transactions":
                    db.execute("INSERT INTO transactions(business_id,id,date,description,type,amount_minor,currency,category,fingerprint,risk_flags,source,created_at) "
                               "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                               (business_id, row["id"], row["date"], row["description"], row["type"], row["amount_minor"],
                                currency, row["category"], row["fingerprint"], flags, source, now))
                elif kind == "invoices":
                    db.execute("INSERT INTO invoices(business_id,id,customer,description,issue_date,due_date,expected_collection_date,status,paid_date,amount_minor,currency,risk_flags,source,created_at) "
                               "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (business_id, row["id"], row["customer"], row["description"], row["issue_date"], row["due_date"],
                                row["expected_collection_date"], row["status"], row["paid_date"], row["amount_minor"],
                                currency, flags, source, now))
                else:
                    db.execute("INSERT INTO bills(business_id,id,payee,payee_account,description,due_date,amount_minor,currency,status,priority,reschedule_allowed,rescheduled_date,risk_flags,source,created_at) "
                               "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (business_id, row["id"], row["payee"], row["payee_account"], row["description"], row["due_date"],
                                row["amount_minor"], currency, row["status"], row["priority"], int(row["reschedule_allowed"]),
                                row["rescheduled_date"], flags, source, now))
                added[kind] += 1
            quarantined = [{"kind": kind[:-1], "id": row["id"], "flags": row["risk_flags"]} for kind, row in keep if row["risk_flags"]]
            result = {"business_id": business_id, "added": added, "duplicates_skipped": skipped,
                      "sample_records_removed": removed, "total_added": sum(added.values()),
                      "total_removed": sum(removed.values()), "quarantined_text": quarantined, "source": source}
            if result["total_added"] or result["total_removed"]:
                result["state_version"] = self._bump(db, business_id)
            result.update(self._audit(db, business_id, "ledger.import", actor, "user_write",
                                      {key: result[key] for key in ("added", "duplicates_skipped", "sample_records_removed",
                                                                    "quarantined_text", "source")}))
            return result

    def apply_demo_delay(self, business_id, invoice_id, collection_date, expected_snapshot, request_id, operator, pin, actor):
        """Explicit, atomic demo-only ledger mutation; never a hypothetical what-if.

        Compare-and-swap plus a durable request receipt handles races and lost
        responses. A retry returns the original receipt without another bump.
        """
        if operator.get("role") != "owner":
            raise ValidationError("Only the owner can apply a synthetic demo change.")
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_id):
            raise ValidationError("Use a request id of 8-80 letters, digits, underscores or hyphens.")
        if not isinstance(expected_snapshot, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_snapshot):
            raise ValidationError("A current snapshot hash is required.")
        if not isinstance(invoice_id, str):
            raise ValidationError("Invoice id must be text.")
        collection_date = valid_date(collection_date, "Collection date")
        self.verify_pin(operator["id"], pin)
        signature = json_hash({"invoice_id": invoice_id, "collection_date": collection_date,
                               "expected_snapshot": expected_snapshot, "operator": operator["id"]})
        key = f"demo-delay:{business_id}:{request_id}"
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            membership = db.execute("SELECT role FROM memberships WHERE business_id=? AND operator_id=?",
                                    (business_id, operator["id"])).fetchone()
            if not membership or membership["role"] != "owner":
                raise ValidationError("An owner membership in this business is required.")
            cached = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
            if cached:
                saved = json.loads(cached["value"])
                if saved["signature"] != signature:
                    raise ValidationError("This request id was already used for another demo change.")
                return {**saved["receipt"], "replayed": True}
            before = self._snapshot(db, business_id)
            if not before["business"]["synthetic"]:
                raise ValidationError("Demo changes are restricted to synthetic demo businesses.")
            if before["policy"]["agent_paused"]:
                raise ValidationError("The agent is paused. The owner must resume before a demo change.")
            if before["snapshot_hash"] != expected_snapshot:
                raise ValidationError("Records changed. Reload before applying a demo change.")
            invoice = next((row for row in before["records"]["invoices"] if row["id"] == invoice_id), None)
            if not invoice or invoice["source"] != "demo" or invoice["status"] not in OPEN_INVOICE_STATUSES:
                raise ValidationError("Select an open invoice from the synthetic demo records.")
            if any(action.get("record_id") == invoice_id for action in before["state"]["adjustments"]):
                raise ValidationError("This invoice already has an executed adjustment. Use a fresh demo database.")
            if not 1 <= days_between(invoice["expected_collection_date"], collection_date) <= 60:
                raise ValidationError("The new collection date must be 1-60 days after the current date.")
            if days_between(before["business"]["opening_date"], collection_date) > 366:
                raise ValidationError("The collection date must be within the supported one-year horizon.")
            updated = validate_invoice({**invoice, "expected_collection_date": collection_date}, business_id,
                                       before["business"]["currency"])
            old_plans = [row[0] for row in db.execute("SELECT id FROM plans WHERE business_id=? AND status IN ('pending','approved')", (business_id,))]
            old_mandates = [row[0] for row in db.execute(f"SELECT id FROM mandates WHERE business_id=? AND kind='bundle' AND status IN {BUNDLE_LIVE}", (business_id,))]
            flags = sorted(set(invoice["risk_flags"]) | set(updated["risk_flags"]))
            db.execute("UPDATE invoices SET expected_collection_date=?,risk_flags=? WHERE business_id=? AND id=?",
                       (updated["expected_collection_date"], canonical_json(flags), business_id, invoice_id))
            # An explicit later collection update supersedes an earlier reminder
            # promise. Otherwise the scheduled scenario would keep the old date.
            old_promise = before["state"]["promises"].get(invoice_id)
            if old_promise is not None:
                state_row = db.execute("SELECT state_json FROM sandbox_state WHERE business_id=?", (business_id,)).fetchone()
                state_data = json.loads(state_row["state_json"])
                state_data.get("promises", {}).pop(invoice_id, None)
                db.execute("UPDATE sandbox_state SET state_json=? WHERE business_id=?", (canonical_json(state_data), business_id))
            version = self._bump(db, business_id)
            after = self._snapshot(db, business_id)
            receipt = {"request_id": request_id, "business_id": business_id, "invoice_id": invoice_id,
                       "customer": invoice["customer"], "old_date": invoice["expected_collection_date"],
                       "new_date": collection_date, "before_snapshot": before["snapshot_hash"],
                       "after_snapshot": after["snapshot_hash"], "state_version": version,
                       "invalidated_plans": old_plans, "invalidated_mandates": old_mandates,
                       "superseded_promise": old_promise, "replayed": False, "before": before, "after": after}
            receipt.update(self._audit(db, business_id, "demo.payment_delay", actor, "human_approval",
                                      {k: v for k, v in receipt.items() if k not in ("before", "after")}))
            db.execute("INSERT INTO metadata(key,value) VALUES (?,?)", (key, canonical_json({"signature": signature, "receipt": receipt})))
            return receipt

    def _bump(self, db, business_id):
        """Advance the sandbox version and invalidate anything approved earlier."""
        row = db.execute("SELECT version FROM sandbox_state WHERE business_id=?", (business_id,)).fetchone()
        version = row["version"] + 1
        db.execute("UPDATE sandbox_state SET version=?,updated_at=? WHERE business_id=?", (version, utc_now(), business_id))
        db.execute("UPDATE plans SET status='invalidated' WHERE business_id=? AND status IN ('pending','approved')", (business_id,))
        db.execute(f"UPDATE mandates SET status='invalidated' WHERE business_id=? AND kind='bundle' AND status IN {BUNDLE_LIVE}",
                   (business_id,))
        return version

    def set_policy(self, business_id, changes, operator, actor):
        pause_only = set(changes) == {"agent_paused"} and changes["agent_paused"] is True
        if operator["role"] != "owner" and not (pause_only and operator["role"] in APPROVER_ROLES):
            raise ValidationError("Only the owner can change policy. Any approver can pause the agent.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            business = self._business_row(db, business_id)
            current = self._policy(db, business_id)
            allowed = {"reserve_floor_minor", "action_limit_minor", "daily_cap_minor", "dual_approval_threshold_minor",
                       "max_deferral_days", "max_discount_bps", "lookahead_days", "autonomy_level", "agent_paused",
                       "resume_reason"}
            unknown = set(changes) - allowed
            if unknown:
                raise ValidationError(f"Unknown policy field(s): {', '.join(sorted(unknown))}.")
            changes = dict(changes)
            reason = changes.pop("resume_reason", None)
            tail = current["version"].rsplit("-v", 1)[-1]
            version_label = f"policy-v{int(tail) + 1 if tail.isdigit() else 2}"
            base = {key: value for key, value in current.items() if key != "paused_reason"}
            policy = validate_policy({**base, **changes, "version": version_label}, business_id, business["currency"])
            resumed = current["agent_paused"] and not policy["agent_paused"]
            if resumed and (not isinstance(reason, str) or len(reason.strip()) < 5):
                raise ValidationError("Resuming a paused agent needs a written reason (at least 5 characters).")
            if {k: v for k, v in policy.items() if k != "version"} == {k: v for k, v in base.items() if k != "version"}:
                return {**current, "changed": False}  # nothing changed: keep plans, mandates and the version
            if policy["agent_paused"] and not current["agent_paused"]:
                policy["paused_reason"] = f"Paused by {operator['name']} ({operator['role']})"
            elif policy["agent_paused"] and current.get("paused_reason"):
                policy["paused_reason"] = current["paused_reason"]
            state = self._state(db, business_id)
            if any(item["kind"] == "bill_deferral" and item["amount_minor"] > policy["action_limit_minor"]
                   for item in state["adjustments"]):
                raise ValidationError("The action limit cannot go below an accepted adjustment; reset the sandbox first.")
            db.execute("UPDATE policies SET policy_json=?,version=?,updated_at=? WHERE business_id=?",
                       (canonical_json(policy), policy["version"], utc_now(), business_id))
            version = self._bump(db, business_id)
            db.execute("UPDATE mandates SET status='revoked' WHERE business_id=? AND kind='standing' AND status='active'", (business_id,))
            standing = None
            if policy["autonomy_level"] == "delegate" and not policy["agent_paused"]:
                standing = self._issue_standing(db, business_id, policy, operator)
            receipt = self._audit(db, business_id, "policy.update", actor, "human_approval",
                                  {"previous": current, "policy": policy, "state_version": version, "resume_reason": reason,
                                   "resumed": resumed,
                                   "standing_mandate": standing["mandate_id"] if standing else None})
            return {**policy, "changed": True, "standing_mandate": standing, **receipt}

    def _issue_standing(self, db, business_id, policy, operator):
        """An 'open' mandate: constraints only, for zero-cash reminders without a human present."""
        document = {"version": security.MANDATE_VERSION, "kind": "standing", "mandate_id": uuid.uuid4().hex,
                    "business_id": business_id,
                    "constraints": {"action.types": ["collection_reminder"], "action.max_per_day": 5,
                                    "payment.amount_range": {"max_minor": 0}, "counterparty.one_reminder_per_invoice": True},
                    "policy_version": policy["version"], "issued_by": operator["id"], "issued_role": operator["role"],
                    "human_present_at_execution": False, "issued_at": utc_now(),
                    "expires_at": _later(days=STANDING_MANDATE_DAYS), "nonce": secrets.token_urlsafe(16)}
        document["signature"] = security.sign(self.key, document)
        db.execute("INSERT INTO mandates(id,business_id,kind,document,status,expires_at,nonce,created_at) VALUES (?,?,?,?,?,?,?,?)",
                   (document["mandate_id"], business_id, "standing", canonical_json(document), "active",
                    document["expires_at"], document["nonce"], utc_now()))
        return document

    def standing_mandate(self, business_id):
        with self.connect() as db:
            row = db.execute("SELECT document FROM mandates WHERE business_id=? AND kind='standing' AND status='active' "
                             "ORDER BY rowid DESC LIMIT 1", (business_id,)).fetchone()
        if not row:
            return None
        document = json.loads(row["document"])
        return None if _expired(document["expires_at"]) else document

    def verify_payee(self, business_id, payee, account, operator, actor, method):
        if operator["role"] != "owner":
            raise ValidationError("Only the owner can verify changed bank details.")
        if method != "callback_number_on_file":
            raise ValidationError("Verification must use a phone number already on file, never one from the request.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._business_row(db, business_id)
            if not all(isinstance(value, str) for value in (payee, account)):
                raise ValidationError("Payee and account must be text.")
            payees = self.derived(self._snapshot(db, business_id))["payees"]
            if not any(item["payee"] == payee and item.get("account") == account
                       for item in payees["flagged"] + payees["lookalikes"]):
                raise ValidationError("Only a changed bank account or a look-alike payee needs verification; "
                                      "this payee and account are not flagged.")
            db.execute("INSERT INTO counterparties(business_id,name,kind,profile_json,verified_account,verified_by,verified_at) "
                       "VALUES (?,?,?,?,?,?,?) ON CONFLICT(business_id,name,kind) DO UPDATE SET "
                       "verified_account=excluded.verified_account,verified_by=excluded.verified_by,verified_at=excluded.verified_at",
                       (business_id, payee, "supplier", "{}", account, operator["id"], utc_now()))
            version = self._bump(db, business_id)
            return {"payee": payee, "verified_account": analytics.mask_account(account), "state_version": version,
                    "separation_of_duties": f"{operator['name']} cannot be the only approver of actions for {payee}.",
                    **self._audit(db, business_id, "payee.verify", actor, "human_approval",
                                  {"payee": payee, "account": analytics.mask_account(account), "method": method})}

    # ---- derived context used by planning and execution checks -------------

    @staticmethod
    def derived(snapshot):
        records = snapshot["records"]
        verified = {item["name"]: item["verified_account"] for item in snapshot["counterparties"].values()
                    if item["kind"] == "supplier" and item["verified_account"]}
        payees = analytics.payee_checks(records["bills"], verified)
        profiles = analytics.customer_profiles(records["invoices"], snapshot["state"]["current_date"])
        predictions = analytics.tidepay_predictions(records["invoices"], snapshot["state"]["current_date"])
        for item in profiles["customers"].values():  # TidePay's view of each customer's open invoices
            own = [p for p in predictions.values() if p["customer"] == item["customer"]]
            item["tidepay_delay_days"] = max((p["likely_delay_days"] for p in own), default=None)
            item["tidepay_p80_delay_days"] = max((p["p80_delay_days"] for p in own), default=None)
        blocked = {item["bill_id"]: item["reason"]
                   for item in payees["flagged"]}
        for item in payees.get("lookalikes", []):
            blocked.setdefault(item["bill_id"], f"Payee name looks like '{item['similar_to']}'; confirm it is not an impostor.")
        return {"profiles": profiles, "payees": payees, "blocked": blocked, "predictions": predictions,
                "likely_dates": analytics.scenario_dates(records["invoices"], profiles, "likely", predictions),
                "stress_dates": analytics.scenario_dates(records["invoices"], profiles, "stress", predictions)}

    # ---- plans, approvals and mandates -------------------------------------

    def create_plan(self, business_id, payload, snapshot_hash, proposed_by, actor, replaces_mandate=None):
        """Store a proposal.  With replaces_mandate, that mandate is cancelled in the same transaction,
        only after every check has passed, so a refused proposal never leaves it cancelled."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            snapshot = self._snapshot(db, business_id)
            if snapshot["policy"]["agent_paused"]:
                raise ValidationError("The agent is paused (kill switch). Resume it to create new proposals.")
            if snapshot["policy"]["autonomy_level"] == "advise" and proposed_by.startswith("agent"):
                raise ValidationError("Autonomy is set to 'advise': the agent may explain but not create proposals.")
            if snapshot["snapshot_hash"] != snapshot_hash:
                raise ValidationError("Records changed while planning; compare again.")
            constraints = check_plan_constraints(payload, snapshot["policy"])
            supersedes = None
            if replaces_mandate is not None:
                old, signed = self._load_bundle_mandate(db, business_id, replaces_mandate)
                parent_row, parent = self._fresh_plan(db, business_id, old["plan_id"], snapshot)
                # A recomputed parent hash cannot rewrite instructions that were
                # already signed. Revalidate the original authority atomically,
                # before cancelling it or saving any successor proposal.
                if (parent_row["plan_hash"] != signed["plan_hash"]
                        or signed["snapshot_hash"] != snapshot_hash
                        or signed["plan_id"] != old["plan_id"]
                        or signed["business_id"] != business_id):
                    raise ValidationError("The parent proposal changed or does not match its signed mandate; create a fresh owner-reviewed proposal.")
                previous_constraints = check_plan_constraints(parent, snapshot["policy"])
                if (constraints["max_discount_bps"] > previous_constraints["max_discount_bps"]
                        or constraints["prefer"] != previous_constraints["prefer"]
                        or not set(parent.get("excluded_counterparties", ())) <= set(payload.get("excluded_counterparties", ()))
                        or payload["target_date"] != parent["target_date"]
                        or payload["business_id"] != business_id or payload["currency"] != parent["currency"]):
                    raise ValidationError("Replacement violates the original owner constraints; create a fresh owner-reviewed proposal.")
                supersedes = {"plan_id": old["plan_id"], "plan_hash": parent_row["plan_hash"],
                              "mandate_id": replaces_mandate}
                db.execute("UPDATE mandates SET status='cancelled' WHERE id=?", (replaces_mandate,))
                db.execute("UPDATE plans SET status='cancelled' WHERE id=? AND status IN ('pending','approved')", (old["plan_id"],))
                self._audit(db, business_id, "mandate.cancel", actor, "agent_propose",
                            {"mandate_id": replaces_mandate, "reason": "replaced by a new proposal"})
            identifier = uuid.uuid4().hex
            body = {**payload, "owner_constraints": constraints,
                    "snapshot_hash": snapshot_hash, "policy_version": snapshot["policy"]["version"]}
            if supersedes is not None:
                body["supersedes"] = supersedes
            plan_hash = json_hash(body)
            db.execute("UPDATE plans SET status='superseded' WHERE business_id=? AND target_date=? AND status='pending'",
                       (business_id, payload["target_date"]))
            db.execute("INSERT INTO plans(id,business_id,target_date,plan_hash,snapshot_hash,payload,status,proposed_by,created_at) "
                       "VALUES (?,?,?,?,?,?,?,?,?)",
                       (identifier, business_id, payload["target_date"], plan_hash, snapshot_hash,
                        canonical_json(body), "pending", proposed_by, utc_now()))
            receipt = self._audit(db, business_id, "plan.propose", actor, "agent_propose",
                                  {"plan_id": identifier, "plan_hash": plan_hash, "snapshot_hash": snapshot_hash,
                                   "owner_constraints": body["owner_constraints"], "supersedes": supersedes,
                                   "bundles": [{"bundle_id": item["bundle_id"], "feasible": item["feasible"],
                                                "actions": [action["action_id"] for action in item["actions"]],
                                                "economic_cost_minor": item["economic_cost_minor"]} for item in payload["bundles"]],
                                   "gap_minor": payload["gap_minor"]})
        return {**body, "plan_id": identifier, "plan_hash": plan_hash, "status": "pending", "approvals": [], **receipt}

    def plan(self, business_id, plan_id):
        if not isinstance(plan_id, str) or not re.fullmatch(r"[0-9a-f]{32}", plan_id):
            raise ValidationError("A valid plan_id is required.")
        with self.connect() as db:
            row = db.execute("SELECT * FROM plans WHERE business_id=? AND id=?", (business_id, plan_id)).fetchone()
            if not row:
                raise ValidationError("Plan was not found for this business.")
            approvals = [self._approval_dict(item) for item in db.execute(
                "SELECT bundle_id,operator_id,role,review_ms,created_at,risk_acknowledgement FROM approvals "
                "WHERE plan_id=? ORDER BY created_at", (plan_id,))]
        return {**json.loads(row["payload"]), "plan_id": row["id"], "plan_hash": row["plan_hash"], "status": row["status"],
                "approvals": approvals}

    def latest_plan(self, business_id, target_date):
        with self.connect() as db:
            row = db.execute("SELECT id FROM plans WHERE business_id=? AND target_date=? AND status IN ('pending','approved') "
                             "ORDER BY rowid DESC LIMIT 1", (business_id, target_date)).fetchone()
        return self.plan(business_id, row["id"]) if row else None

    def _fresh_plan(self, db, business_id, plan_id, snapshot):
        row = db.execute("SELECT * FROM plans WHERE business_id=? AND id=?", (business_id, plan_id)).fetchone()
        if not row:
            raise ValidationError("Plan was not found for this business.")
        if row["status"] not in ("pending", "approved", "executed"):
            raise ValidationError(f"This plan is {row['status']}; compare again.")
        payload = json.loads(row["payload"])
        if json_hash(payload) != row["plan_hash"]:
            raise ValidationError("Plan hash does not match; the stored plan was altered.")
        if row["snapshot_hash"] != snapshot["snapshot_hash"]:
            raise ValidationError("Records, policy or sandbox state changed since this plan; compare again.")
        return row, payload

    def _check_bundle(self, snapshot, derived, bundle):
        """Deterministic checks outside the model: every bound value must trace to a ledger record."""
        policy = snapshot["policy"]
        if policy["agent_paused"]:
            raise ValidationError("The agent is paused (kill switch). Resume it before approving or executing.")
        if not bundle["feasible"]:
            raise ValidationError("This bundle does not restore the reserve floor and cannot be approved.")
        exposure = 0
        bills = {row["id"]: row for row in snapshot["records"]["bills"]}
        invoices = {row["id"]: row for row in snapshot["records"]["invoices"]}
        for action in bundle["actions"]:
            if action["currency"] != snapshot["business"]["currency"]:
                raise ValidationError("Action currency does not match the business.")
            if action["type"] == "supplier_deferral":
                bill = bills.get(action["record_id"])
                if not bill or bill["payee"] != action["counterparty"] or bill["due_date"] != action["from_date"] \
                        or bill["amount_minor"] != action["bill_amount_minor"]:
                    raise ValidationError("The bill changed after planning (payee, amount or due date).")
                if bill["priority"] == "payroll" or not bill["reschedule_allowed"]:
                    raise ValidationError("This bill cannot be deferred.")
                if action["record_id"] in derived["blocked"]:
                    raise ValidationError(derived["blocked"][action["record_id"]])
                if action["days"] > policy["max_deferral_days"] or action["amount_minor"] > bill["amount_minor"]:
                    raise ValidationError("Deferral terms exceed the bill or the policy.")
                exposure += action["amount_minor"]
            elif action["type"] == "early_payment_offer":
                invoice = invoices.get(action["record_id"])
                if not invoice or invoice["customer"] != action["counterparty"] or invoice["amount_minor"] != action["face_minor"] \
                        or invoice["status"] not in OPEN_INVOICE_STATUSES:
                    raise ValidationError("The invoice changed after planning.")
                if action["discount_bps"] > policy["max_discount_bps"] or \
                        action["amount_minor"] != action["face_minor"] - action["face_minor"] * action["discount_bps"] // 10_000:
                    raise ValidationError("Discount terms are outside the policy.")
                exposure += action["face_minor"]
            else:
                raise ValidationError("Only supplier deferrals and early-payment offers can be bundled.")
            if action.get("face_minor", action["amount_minor"]) > policy["action_limit_minor"]:
                raise ValidationError("An action is above the per-action limit.")
        if self._exposure_today(snapshot["business"]["id"]) + exposure > policy["daily_cap_minor"]:
            raise ValidationError("This bundle would exceed the daily exposure cap.")
        return exposure

    def _exposure_today(self, business_id):
        """Exposure executed on the real UTC day.  Receipts survive sandbox resets, so a reset cannot lift the cap."""
        with self.connect() as db:
            rows = db.execute("SELECT receipt_json FROM executions WHERE business_id=? AND created_at LIKE ?",
                              (business_id, utc_now()[:10] + "%")).fetchall()
        return sum(json.loads(row["receipt_json"]).get("exposure_minor", 0) for row in rows)

    @staticmethod
    def _approval_dict(row):
        item = dict(row)
        value = item.get("risk_acknowledgement")
        item["risk_acknowledgement"] = json.loads(value) if value else None
        return item

    @staticmethod
    def risk_acknowledgement_terms(plan, bundle):
        """Return the exact proposal context that a human must acknowledge.

        Risk is compared using the stored probabilities, independently of the
        display flag and rounded percentage. This method does not grant consent.
        """
        probability, target = bundle.get("probability_breach_after"), plan.get("risk_target")
        if any(type(value) not in (int, float) or not 0 <= value <= 1 for value in (probability, target)):
            raise ValidationError("This proposal has no valid simulated risk estimate; create a fresh plan before approving.")
        if probability <= target:
            return None
        return {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"], "bundle_id": bundle["bundle_id"],
                "probability_breach_after": probability, "risk_target": target}

    @staticmethod
    def _validate_risk_acknowledgement(terms, acknowledgement):
        if terms is None:
            if acknowledgement is not None:
                raise ValidationError("Risk acknowledgement does not match this proposal; refresh and review it again.")
            return
        expected = {"acknowledged": True, **terms}
        if not isinstance(acknowledgement, dict) or canonical_json(acknowledgement) != canonical_json(expected):
            raise ValidationError("This bundle exceeds the simulated risk target. Explicitly acknowledge its exact "
                                  "remaining risk before approving; refresh if the proposal changed.")

    def approve(self, business_id, plan_id, bundle_id, operator, pin, actor, review_ms=None, risk_acknowledgement=None):
        if operator["role"] not in APPROVER_ROLES:
            raise ValidationError("Only an owner or accountant can approve; viewers and the agent cannot.")
        self.verify_pin(operator["id"], pin)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            snapshot = self._snapshot(db, business_id)
            derived = self.derived(snapshot)
            row, payload = self._fresh_plan(db, business_id, plan_id, snapshot)
            check_plan_constraints(payload, snapshot["policy"])
            if row["status"] == "executed":
                raise ValidationError("This plan was already executed.")
            bundle = next((item for item in payload["bundles"] if item["bundle_id"] == bundle_id), None)
            if not bundle:
                raise ValidationError("Bundle was not found in this plan.")
            exposure = self._check_bundle(snapshot, derived, bundle)
            risk_terms = self.risk_acknowledgement_terms({**payload, "plan_id": plan_id, "plan_hash": row["plan_hash"]}, bundle)
            self._validate_risk_acknowledgement(risk_terms, risk_acknowledgement)
            for live in db.execute(f"SELECT id,document FROM mandates WHERE business_id=? AND plan_id=? AND kind='bundle' "
                                   f"AND status IN {BUNDLE_LIVE}", (business_id, plan_id)).fetchall():
                if _expired(json.loads(live["document"])["expires_at"]):
                    db.execute("UPDATE mandates SET status='expired' WHERE id=?", (live["id"],))
                else:
                    raise ValidationError("This plan already has a live mandate. Use it, or cancel it first.")
            if db.execute("SELECT 1 FROM approvals WHERE plan_id=? AND bundle_id<>?", (plan_id, bundle_id)).fetchone():
                raise ValidationError("Another bundle of this plan is already being approved.")
            if db.execute("SELECT 1 FROM approvals WHERE plan_id=? AND bundle_id=? AND operator_id=?",
                          (plan_id, bundle_id, operator["id"])).fetchone():
                raise ValidationError("You already approved this bundle. A second approval must come from a different person.")
            if risk_terms is not None:
                # An approval from an older version cannot silently supply the second
                # person's consent to residual risk. Both people must review again.
                for prior in db.execute("SELECT risk_acknowledgement FROM approvals WHERE plan_id=? AND bundle_id=?",
                                        (plan_id, bundle_id)):
                    if not prior[0]:
                        raise ValidationError("An existing approval predates risk acknowledgement. Create a fresh plan "
                                              "so every approver can review its remaining risk.")
                    self._validate_risk_acknowledgement(risk_terms, json.loads(prior[0]) if prior[0] else None)
            review = review_ms if isinstance(review_ms, int) and not isinstance(review_ms, bool) and 0 <= review_ms < 86_400_000 else None
            db.execute("INSERT INTO approvals(id,business_id,plan_id,bundle_id,operator_id,role,review_ms,created_at,risk_acknowledgement) "
                       "VALUES (?,?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, business_id, plan_id, bundle_id, operator["id"],
                       operator["role"], review, utc_now(), canonical_json(risk_acknowledgement) if risk_terms else None))
            approvals = [self._approval_dict(item) for item in db.execute(
                "SELECT operator_id,role,review_ms,created_at,risk_acknowledgement FROM approvals "
                "WHERE plan_id=? AND bundle_id=? ORDER BY created_at",
                (plan_id, bundle_id))]
            policy = snapshot["policy"]
            dual = exposure > policy["dual_approval_threshold_minor"]
            people = {item["operator_id"] for item in approvals}
            satisfied = (len(people) >= 2 and any(item["role"] == "owner" for item in approvals)) if dual else True
            # Separation of duties: whoever verified a payee's bank details cannot be the only approver
            # of actions for that payee; someone else must also approve.
            bills = {bill["id"]: bill for bill in snapshot["records"]["bills"]}
            verifiers = {snapshot["counterparties"].get(f"supplier:{bills[action['record_id']]['payee']}", {}).get("verified_by")
                         for action in bundle["actions"] if action["type"] == "supplier_deferral"} - {None}
            sod = bool(verifiers & people) and not (people - verifiers)
            satisfied = satisfied and not sod
            fast = review is not None and review < FAST_APPROVAL_MS
            db.execute("UPDATE plans SET status='approved' WHERE id=?", (plan_id,))
            details = {"plan_id": plan_id, "bundle_id": bundle_id, "exposure_minor": exposure,
                       "owner_constraints": payload["owner_constraints"],
                       "dual_approval_required": dual, "approvals": approvals, "step_up": "PIN re-entered",
                       "review_ms": review, "fast_approval_flag": fast, "separation_of_duties": sod,
                       "risk": {"probability_breach_after": bundle["probability_breach_after"],
                                "risk_target": payload["risk_target"], "acknowledgement_required": risk_terms is not None}}
            if not satisfied:
                receipt = self._audit(db, business_id, "plan.approve", actor, "human_approval",
                                      {**details, "status": "awaiting_second_approval"})
                message = ("Separation of duties: you verified this payee's bank details, so another approver must also "
                           "approve this bundle." if sod else
                           "Maker-checker: a second person, including the owner, must approve this bundle.")
                return {"status": "awaiting_second_approval", "dual_approval_required": dual, "separation_of_duties": sod,
                        "approvals": approvals, "exposure_minor": exposure, "fast_approval_flag": fast,
                        "message": message, **receipt}
            document = {"version": security.MANDATE_VERSION, "kind": "bundle", "mandate_id": uuid.uuid4().hex,
                        "business_id": business_id, "currency": snapshot["business"]["currency"],
                        "plan_id": plan_id, "bundle_id": bundle_id, "plan_hash": row["plan_hash"],
                        "snapshot_hash": snapshot["snapshot_hash"], "policy_version": policy["version"],
                        "target_date": payload["target_date"], "actions": [bound_terms(action) for action in bundle["actions"]],
                        "owner_constraints": payload["owner_constraints"],
                        "excluded_counterparties": payload.get("excluded_counterparties", []),
                        "constraints": {"payment.allowed_counterparties": sorted({action["counterparty"] for action in bundle["actions"]}),
                                        "payment.budget_minor": exposure, "execution.not_after": _later(minutes=MANDATE_MINUTES),
                                        "consent.required": [action["action_id"] for action in bundle["actions"]]},
                        "exposure_minor": exposure, "approvals": approvals, "dual_approval": dual, "risk": details["risk"],
                        "human_present": True, "issued_at": utc_now(), "expires_at": _later(minutes=MANDATE_MINUTES),
                        "nonce": secrets.token_urlsafe(16)}
            document["signature"] = security.sign(self.key, document)
            db.execute("INSERT INTO mandates(id,business_id,plan_id,bundle_id,kind,document,status,expires_at,nonce,created_at) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (document["mandate_id"], business_id, plan_id, bundle_id, "bundle", canonical_json(document),
                        "active", document["expires_at"], document["nonce"], utc_now()))
            # Approvals are consumed by this mandate (they are kept in its signed document and the audit log),
            # so if it later expires or is invalidated the same people can approve again.
            db.execute("DELETE FROM approvals WHERE plan_id=? AND bundle_id=?", (plan_id, bundle_id))
            receipt = self._audit(db, business_id, "mandate.issue", actor, "human_approval",
                                  {**details, "mandate_id": document["mandate_id"], "signature": document["signature"],
                                   "expires_at": document["expires_at"]})
            return {"status": "mandate_issued", "mandate": document, "approvals": approvals, "fast_approval_flag": fast,
                    "dual_approval_required": dual, "exposure_minor": exposure, **receipt}

    @staticmethod
    def _mandate_id(mandate_id):
        if not isinstance(mandate_id, str) or not re.fullmatch(r"[0-9a-f]{32}", mandate_id):
            raise ValidationError("A valid mandate_id is required.")
        return mandate_id

    def mandate(self, business_id, mandate_id):
        self._mandate_id(mandate_id)
        with self.connect() as db:
            row = db.execute("SELECT * FROM mandates WHERE business_id=? AND id=?", (business_id, mandate_id)).fetchone()
            if not row:
                raise ValidationError("Mandate was not found for this business.")
            negotiations = [self._negotiation_dict(item) for item in db.execute(
                "SELECT * FROM negotiations WHERE mandate_id=? ORDER BY created_at,rowid", (mandate_id,))]
        document = json.loads(row["document"])
        status = row["status"]
        if status in BUNDLE_LIVE and _expired(document["expires_at"]):
            status = "expired"
        return {"mandate": document, "status": status, "used_at": row["used_at"], "negotiations": negotiations}

    def live_mandates(self, business_id):
        with self.connect() as db:
            rows = db.execute(f"SELECT id FROM mandates WHERE business_id=? AND kind='bundle' AND status IN {BUNDLE_LIVE} "
                              "ORDER BY rowid DESC", (business_id,)).fetchall()
        return [item for item in (self.mandate(business_id, row["id"]) for row in rows) if item["status"] != "expired"]

    @staticmethod
    def _negotiation_dict(row):
        item = dict(row)
        item["request"] = json.loads(item.pop("request_json"))
        item["response"] = json.loads(item.pop("response_json"))
        return item

    def verify_mandate_document(self, document):
        valid = isinstance(document, dict) and security.verify(self.key, document)
        return {"signature_valid": valid,
                "message": "Signature matches the server key: the mandate is authentic and unaltered." if valid else
                           "invalid_mandate: the signature does not match. The mandate was altered or not issued by this server."}

    def _load_bundle_mandate(self, db, business_id, mandate_id):
        if not isinstance(mandate_id, str) or not re.fullmatch(r"[0-9a-f]{32}", mandate_id):
            raise ValidationError("A valid mandate_id is required; direct execution without a mandate is not allowed.")
        row = db.execute("SELECT * FROM mandates WHERE business_id=? AND id=? AND kind='bundle'", (business_id, mandate_id)).fetchone()
        if not row:
            raise ValidationError("Mandate was not found for this business.")
        document = json.loads(row["document"])
        if not security.verify(self.key, document):
            raise SecurityError("invalid_mandate", "the signature does not verify; refusing to act.")
        if row["status"] == "used":
            raise ValidationError("This mandate was already used. Its receipt is available with the original idempotency key.")
        if row["status"] not in BUNDLE_LIVE:
            raise ValidationError(f"This mandate is {row['status']}.")
        if _expired(document["expires_at"]):
            db.execute("UPDATE mandates SET status='expired' WHERE id=?", (mandate_id,))
            raise ValidationError("The mandate expired; approve the plan again.")
        return row, document

    def record_negotiation(self, business_id, mandate_id, action, response, simulated_by, actor):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            _row, document = self._load_bundle_mandate(db, business_id, mandate_id)
            snapshot = self._snapshot(db, business_id)
            if snapshot["policy"]["agent_paused"]:
                raise ValidationError("The agent is paused (kill switch); no counterparty requests can be sent.")
            if snapshot["snapshot_hash"] != document["snapshot_hash"]:
                raise ValidationError("Records changed after approval; the mandate is stale.")
            bound = next((item for item in document["actions"] if item["action_id"] == action["action_id"]), None)
            if bound is None or bound != bound_terms(action):
                raise SecurityError("unresolved_constraint", "this request is outside the mandate's scope.")
            identifier = uuid.uuid4().hex
            db.execute("INSERT INTO negotiations(id,business_id,mandate_id,action_id,counterparty,request_json,response_json,status,simulated_by,created_at) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (identifier, business_id, mandate_id, action["action_id"], action["counterparty"],
                        canonical_json({"terms": bound, "message": action.get("message", "")}), canonical_json(response),
                        response["status"], simulated_by, utc_now()))
            latest = {}
            for item in db.execute("SELECT action_id,status FROM negotiations WHERE mandate_id=? ORDER BY created_at,rowid", (mandate_id,)):
                latest[item["action_id"]] = item["status"]
            statuses = [latest.get(item["action_id"]) for item in document["actions"]]
            status = ("rejected" if "rejected" in statuses else "countered" if "countered" in statuses
                      else "ready" if all(value == "accepted" for value in statuses) else "active")
            db.execute("UPDATE mandates SET status=? WHERE id=?", (status, mandate_id))
            receipt = self._audit(db, business_id, "counterparty.response", actor, "sandbox_simulation",
                                  {"mandate_id": mandate_id, "action_id": action["action_id"], "counterparty": action["counterparty"],
                                   "status": response["status"], "counter_terms": response.get("counter_terms"),
                                   "simulated_by": simulated_by})
            return {"negotiation_id": identifier, "mandate_status": status, "response": response, **receipt}

    def cancel_mandate(self, business_id, mandate_id, operator, actor):
        if operator["role"] not in APPROVER_ROLES:
            raise ValidationError("Viewers cannot cancel mandates.")
        self._mandate_id(mandate_id)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM mandates WHERE business_id=? AND id=?", (business_id, mandate_id)).fetchone()
            if not row:
                raise ValidationError("Mandate was not found for this business.")
            if row["status"] == "used":
                raise ValidationError("An executed mandate cannot be cancelled; executed changes are never silently undone.")
            if row["status"] not in BUNDLE_LIVE:
                raise ValidationError(f"This mandate is already {row['status']}.")
            db.execute("UPDATE mandates SET status='cancelled' WHERE id=?", (mandate_id,))
            if row["plan_id"]:
                db.execute("UPDATE plans SET status='cancelled' WHERE id=? AND status IN ('pending','approved')", (row["plan_id"],))
            return {"mandate_id": mandate_id, "status": "cancelled",
                    **self._audit(db, business_id, "mandate.cancel", actor, "human_approval", {"mandate_id": mandate_id})}

    # ---- execution -----------------------------------------------------------

    def _project_likely(self, snapshot, derived, adjustments, target_date):
        policy = snapshot["policy"]
        return project(snapshot["business"], policy, snapshot["records"], target_date,
                       adjustments=adjustments, scenario="likely", invoice_dates=derived["likely_dates"],
                       promises=snapshot["state"]["promises"], lookahead_days=policy["lookahead_days"])

    def execute(self, business_id, mandate_id, idempotency_key, operator, actor):
        if not idempotency_ok(idempotency_key):
            raise ValidationError("idempotency_key must contain 1-120 safe characters.")
        if operator["role"] not in APPROVER_ROLES:
            raise ValidationError("Only an owner or accountant can execute; viewers and the agent cannot.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT * FROM executions WHERE business_id=? AND idempotency_key=?",
                               (business_id, idempotency_key)).fetchone()
            if prior:
                if prior["mandate_id"] != mandate_id:
                    raise SecurityError("idempotency_conflict", "this key already belongs to a different mandate.")
                return {**json.loads(prior["receipt_json"]), "replayed": True}
            _row, document = self._load_bundle_mandate(db, business_id, mandate_id)
            snapshot = self._snapshot(db, business_id)
            derived = self.derived(snapshot)
            if snapshot["policy"]["agent_paused"]:
                raise ValidationError("The agent is paused (kill switch); execution is blocked.")
            if snapshot["snapshot_hash"] != document["snapshot_hash"]:
                raise ValidationError("Records, policy or sandbox state changed after approval; execution blocked.")
            plan_row, payload = self._fresh_plan(db, business_id, document["plan_id"], snapshot)
            check_plan_constraints(payload, snapshot["policy"])
            if (document.get("owner_constraints", payload["owner_constraints"]) != payload["owner_constraints"]
                    or document.get("excluded_counterparties", payload.get("excluded_counterparties", [])) != payload.get("excluded_counterparties", [])):
                raise ValidationError("Signed owner constraints do not match the approved proposal.")
            if plan_row["plan_hash"] != document["plan_hash"]:
                raise ValidationError("The plan hash does not match the mandate.")
            bundle = next(item for item in payload["bundles"] if item["bundle_id"] == document["bundle_id"])
            self._check_bundle(snapshot, derived, bundle)
            risk_terms = self.risk_acknowledgement_terms(
                {**payload, "plan_id": document["plan_id"], "plan_hash": plan_row["plan_hash"]}, bundle)
            if risk_terms is not None:
                if not document.get("approvals"):
                    raise ValidationError("This above-target mandate needs fresh human approval and risk acknowledgement.")
                for approval in document["approvals"]:
                    self._validate_risk_acknowledgement(risk_terms, approval.get("risk_acknowledgement"))
            if [bound_terms(action) for action in bundle["actions"]] != document["actions"]:
                raise SecurityError("unresolved_constraint", "the bundle no longer matches the signed terms.")
            latest = {}
            for item in db.execute("SELECT * FROM negotiations WHERE mandate_id=? ORDER BY created_at,rowid", (mandate_id,)):
                latest[item["action_id"]] = self._negotiation_dict(item)
            for bound in document["actions"]:
                reply = latest.get(bound["action_id"])
                if not reply or reply["status"] != "accepted":
                    raise ValidationError(f"{bound['counterparty']} has not accepted the exact terms; execution blocked.")
                if reply["request"]["terms"] != bound:
                    raise ValidationError("A counterparty accepted different terms from the mandate; execution blocked.")
            actions = {action["action_id"]: action for action in bundle["actions"]}
            adjustments = [actions[bound["action_id"]]["adjustment"] for bound in document["actions"]]
            state = snapshot["state"]
            before = self._project_likely(snapshot, derived, state["adjustments"], document["target_date"])
            after = self._project_likely(snapshot, derived, state["adjustments"] + adjustments, document["target_date"])
            if after["reserve_shortfall_minor"] > 0 or after["payroll_at_risk"]:
                raise ValidationError("After these actions the reserve floor would still be breached; execution blocked.")
            new_state = {"adjustments": state["adjustments"] + [{**item, "mandate_id": mandate_id} for item in adjustments],
                         "promises": state["promises"],
                         "executed_exposure": {**state["executed_exposure"],
                                               state["current_date"]: state["executed_exposure"].get(state["current_date"], 0)
                                               + document["exposure_minor"]}}
            version = state["version"] + 1
            db.execute("UPDATE sandbox_state SET version=?,state_json=?,updated_at=? WHERE business_id=?",
                       (version, canonical_json(new_state), utc_now(), business_id))
            read_back = self._state(db, business_id)
            verified = read_back["version"] == version and read_back["adjustments"] == new_state["adjustments"]
            if not verified:
                raise ValidationError("Read-back did not match the intended state; the transaction was rolled back.")
            db.execute("UPDATE mandates SET status='used',used_at=? WHERE id=?", (utc_now(), mandate_id))
            db.execute("UPDATE plans SET status='executed' WHERE id=?", (document["plan_id"],))
            db.execute("UPDATE plans SET status='invalidated' WHERE business_id=? AND status IN ('pending','approved') AND id<>?",
                       (business_id, document["plan_id"]))
            db.execute(f"UPDATE mandates SET status='invalidated' WHERE business_id=? AND kind='bundle' AND id<>? "
                       f"AND status IN {BUNDLE_LIVE}", (business_id, mandate_id))
            receipt = {"receipt_id": uuid.uuid4().hex, "status": "executed", "business_id": business_id,
                       "currency": snapshot["business"]["currency"],
                       "mandate_id": mandate_id, "mandate_signature": document["signature"], "plan_id": document["plan_id"],
                       "bundle_id": document["bundle_id"], "idempotency_key": idempotency_key,
                       "executed_by": operator["id"], "executed_role": operator["role"], "human_present": True,
                       "approvals": document["approvals"], "actions": document["actions"],
                       "owner_constraints": payload["owner_constraints"],
                       "excluded_counterparties": payload.get("excluded_counterparties", []),
                       "risk": document.get("risk", {"probability_breach_after": bundle["probability_breach_after"],
                                                       "risk_target": payload["risk_target"], "acknowledgement_required": False}),
                       "adjustments": adjustments, "exposure_minor": document["exposure_minor"],
                       "cash_moved_minor": 0, "synthetic": True,
                       "state_before": {"version": state["version"], "state_hash": state["state_hash"]},
                       "state_after": {"version": read_back["version"], "state_hash": read_back["state_hash"]},
                       "projection_before": summary(before), "projection_after": summary(after),
                       "read_back": {"verified": verified, "source": "post-write SELECT inside the same transaction"},
                       "note": "Schedule changes in the synthetic sandbox only. No money moved and no real counterparty was contacted."}
            receipt.update(self._audit(db, business_id, "mandate.execute", actor, "sandbox_execute",
                                       {key: receipt[key] for key in ("receipt_id", "mandate_id", "plan_id", "bundle_id",
                                                                      "idempotency_key", "actions", "exposure_minor",
                                                                      "state_before", "state_after", "executed_by", "risk", "approvals")}))
            db.execute("INSERT INTO executions(id,business_id,mandate_id,idempotency_key,receipt_json,created_at) VALUES (?,?,?,?,?,?)",
                       (receipt["receipt_id"], business_id, mandate_id, idempotency_key, canonical_json(receipt), utc_now()))
        receipt["witness"] = self.witness_cosign(business_id)
        return receipt

    def send_reminder(self, business_id, action, reply, operator, actor, standing_mandate_id=None):
        """Record a reminder (zero cash) and the customer's simulated reply.

        A human approver may do this directly; under 'delegate' autonomy the
        agent may do it alone with a signed standing mandate (human not present).
        """
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            snapshot = self._snapshot(db, business_id)
            policy = snapshot["policy"]
            if policy["agent_paused"]:
                raise ValidationError("The agent is paused (kill switch).")
            invoice = next((row for row in snapshot["records"]["invoices"] if row["id"] == action.get("record_id")), None)
            if not invoice or invoice["status"] not in OPEN_INVOICE_STATUSES or invoice["customer"] != action.get("counterparty"):
                raise ValidationError("Reminders need an open invoice for the same customer.")
            human_present = operator is not None
            if human_present:
                if operator["role"] not in APPROVER_ROLES:
                    raise ValidationError("Viewers cannot send reminders.")
            else:
                standing = db.execute("SELECT * FROM mandates WHERE business_id=? AND id=? AND kind='standing' AND status='active'",
                                      (business_id, standing_mandate_id or "")).fetchone()
                if not standing or policy["autonomy_level"] != "delegate":
                    raise ValidationError("No active standing mandate allows the agent to act alone.")
                document = json.loads(standing["document"])
                if not security.verify(self.key, document) or _expired(document["expires_at"]):
                    raise ValidationError("The standing mandate is invalid or expired.")
                if "collection_reminder" not in document["constraints"]["action.types"]:
                    raise ValidationError("The standing mandate does not cover reminders.")
                # Per business and real UTC day, across re-issued standing mandates and sandbox resets.
                sent_today = db.execute("SELECT COUNT(*) FROM messages WHERE business_id=? AND human_present=0 AND created_at LIKE ?",
                                        (business_id, utc_now()[:10] + "%")).fetchone()[0]
                if sent_today >= document["constraints"]["action.max_per_day"]:
                    raise ValidationError("The standing mandate's daily reminder limit is reached; escalating to a human.")
            if db.execute("SELECT 1 FROM messages WHERE business_id=? AND record_id=? AND kind='reminder' AND status<>'reset'",
                          (business_id, invoice["id"])).fetchone():
                raise ValidationError("A reminder for this invoice was already recorded in the sandbox.")
            message_id = uuid.uuid4().hex
            db.execute("INSERT INTO messages(id,business_id,mandate_id,action_id,record_id,counterparty,kind,body,reply,status,human_present,created_at) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (message_id, business_id, standing_mandate_id, action["action_id"], invoice["id"], invoice["customer"],
                        "reminder", action["message"], canonical_json(reply), "delivered_in_sandbox", int(human_present), utc_now()))
            state = snapshot["state"]
            promises = dict(state["promises"])
            if reply.get("promise_to_pay_date"):
                promises[invoice["id"]] = reply["promise_to_pay_date"]
            new_state = {"adjustments": state["adjustments"], "executed_exposure": state["executed_exposure"], "promises": promises}
            db.execute("UPDATE sandbox_state SET state_json=?,updated_at=? WHERE business_id=?",
                       (canonical_json(new_state), utc_now(), business_id))
            version = state["version"]  # zero-cash: no bump, so approved plans and mandates stay valid
            receipt = {"message_id": message_id, "status": "delivered_in_sandbox", "invoice_id": invoice["id"],
                       "counterparty": invoice["customer"], "human_present": human_present,
                       "standing_mandate_id": standing_mandate_id, "cash_effect_minor": 0,
                       "promise_to_pay_date": reply.get("promise_to_pay_date"), "state_version": version,
                       "note": "Reminder recorded in the sandbox; no cash was recognised."}
            receipt.update(self._audit(db, business_id, "reminder.send", actor,
                                       "sandbox_execute" if human_present else "delegated_execute", receipt))
            return receipt

    def executions(self, business_id):
        with self.connect() as db:
            self._business_row(db, business_id)
            return [json.loads(row["receipt_json"]) for row in
                    db.execute("SELECT receipt_json FROM executions WHERE business_id=? ORDER BY rowid", (business_id,))]

    def execution_by_key(self, business_id, idempotency_key):
        if not idempotency_ok(idempotency_key):
            raise ValidationError("idempotency_key must contain 1-120 safe characters.")
        with self.connect() as db:
            self._business_row(db, business_id)
            row = db.execute("SELECT receipt_json FROM executions WHERE business_id=? AND idempotency_key=?",
                             (business_id, idempotency_key)).fetchone()
        return {"found": bool(row), "receipt": json.loads(row["receipt_json"]) if row else None}

    def messages(self, business_id):
        with self.connect() as db:
            self._business_row(db, business_id)
            result = []
            for row in db.execute("SELECT * FROM messages WHERE business_id=? AND status<>'reset' ORDER BY created_at,rowid",
                                  (business_id,)):
                item = dict(row)
                item["reply"] = json.loads(item["reply"]) if item["reply"] else None
                item["human_present"] = bool(item["human_present"])
                result.append(item)
            return result

    def reset_sandbox(self, business_id, operator, actor):
        if operator["role"] not in APPROVER_ROLES:
            raise ValidationError("Viewers cannot reset the sandbox.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            business = self._business_row(db, business_id)
            db.execute("UPDATE sandbox_state SET current_date=?,state_json=?,reset_count=reset_count+1,updated_at=? WHERE business_id=?",
                       (business["opening_date"], canonical_json(self._empty_state()), utc_now(), business_id))
            # Kept (not deleted) so daily limits still count them; they no longer block a new reminder.
            db.execute("UPDATE messages SET status='reset' WHERE business_id=?", (business_id,))
            version = self._bump(db, business_id)
            receipt = {"business_id": business_id, "sandbox_version": version, "reset": True,
                       "records_preserved": True, "receipts_preserved": True, "audit_preserved": True}
            receipt.update(self._audit(db, business_id, "sandbox.reset", actor, "human_approval", receipt))
            return receipt

    # ---- seeding -------------------------------------------------------------

    def seeded(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key='seed'").fetchone()
        return row["value"] if row else None

    def mark_seeded(self, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES ('seed',?)", (value,))


def bound_terms(action):
    """The exact terms a mandate binds for one action (what you see is what you sign)."""
    keys = ("action_id", "type", "record_id", "counterparty", "amount_minor", "from_date", "to_date", "days", "currency")
    terms = {key: action[key] for key in keys if key in action}
    if action["type"] == "early_payment_offer":
        terms.update({"discount_bps": action["discount_bps"], "face_minor": action["face_minor"]})
    if action["type"] == "supplier_deferral":
        terms["bill_amount_minor"] = action["bill_amount_minor"]
    return terms
