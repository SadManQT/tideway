"""Loopback-only HTTP service for the local Probaho sandbox."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import mimetypes
import secrets
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .agent import Agent
from .finance import (
    CATEGORIES,
    ValidationError,
    build_budget,
    compare_plans,
    insights,
    month_value,
    parse_combined_csv,
    parse_csv,
    previous_month,
    project_cash,
    recurring_bills,
    summary,
    validate_business_id,
    validate_transaction,
    valid_date,
)
from .store import LEGACY_BUSINESS_ID, SEED_TARGET_DATE, SHAPLA_BUSINESS_ID, Store, demo_rows


ROOT = Path(__file__).resolve().parent.parent
DHAKA = timezone(timedelta(hours=6))


def _plan_hash(payload):
    body = dict(payload)
    body.pop("plan_hash", None)
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _plan_payload_hash(payload):
    body = dict(payload)
    body.pop("plan_hash", None)
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Application:
    def __init__(self, db_path, key="", model="gpt-5-mini", seed=True):
        self.store = Store(db_path)
        if seed:
            self.store.seed_demo()
        elif not any(b["id"] != LEGACY_BUSINESS_ID for b in self.store.list_businesses()):
            # Keep --no-demo useful from the real UI: create an empty local
            # business workspace, not a hidden synthetic fixture. The user
            # can then import combined records before comparing plans.
            self.store.ensure_business({"business_id": "local-workspace", "name": "Local workspace",
                                        "currency": "BDT", "opening_cash_minor": 0,
                                        "opening_date": "2026-10-01", "default_target_date": "2026-10-31",
                                        "synthetic": False})
            self.store.set_policy("local-workspace", {"business_id": "local-workspace", "currency": "BDT",
                                                        "reserve_floor_minor": 0, "action_limit_minor": 0,
                                                        "payroll_priority": True, "version": "probaho-policy-v1"})
        self.agent = Agent(self.store, key, model)
        self.csrf = secrets.token_urlsafe(32)

    def config(self):
        businesses = [b for b in self.store.list_businesses() if b["id"] != LEGACY_BUSINESS_ID]
        scoped_rows = []
        scoped_records = []
        if businesses:
            for business in businesses:
                scoped_rows.extend(self.store.rows(business["id"]))
                records = self.store.records(business["id"])
                scoped_records.extend(records["transactions"] + records["invoices"] + records["bills"])
        else:
            legacy_records = self.store.records(LEGACY_BUSINESS_ID)
            scoped_rows = legacy_records["transactions"]
            scoped_records = legacy_records["transactions"] + legacy_records["invoices"] + legacy_records["bills"]
        months = sorted({r["date"][:7] for r in scoped_rows}, reverse=True)
        if not months:
            months = [datetime.now(DHAKA).strftime("%Y-%m")]
        sample_count = sum(r.get("source") == "demo" for r in scoped_records)
        local_count = len(scoped_records) - sample_count
        dataset = ("probaho_synthetic" if businesses and sample_count and not local_count else
                   "probaho_synthetic_plus_local" if businesses and sample_count else
                   "fictional_sample" if sample_count and not local_count else
                   "mixed_records" if sample_count else "local_records")
        default_business = next((b for b in businesses if b["id"] == SHAPLA_BUSINESS_ID), businesses[0] if businesses else None)
        synthetic_only = bool(businesses) and all(bool(b["synthetic"]) for b in businesses) and not bool(local_count)
        return {
            "name": "Probaho", "product": "Probaho", "version": "2.2.0",
            "track": "Topic E", "currency": "BDT", "months": months, "categories": list(CATEGORIES),
            "csrf_token": self.csrf, "default_business_id": default_business["id"] if default_business else None,
            "default_target_date": default_business["default_target_date"] if default_business else SEED_TARGET_DATE,
            "ai_configured": bool(self.agent.key), "ai_model": self.agent.model,
            "dataset": dataset, "dataset_version": "probaho-synthetic-v3", "synthetic_only": synthetic_only,
            "sample_count": sample_count, "local_count": local_count,
            "businesses": [{"business_id": b["id"], "id": b["id"], "name": b["name"],
                            "currency": b["currency"], "opening_cash_minor": b["opening_cash_minor"],
                            "default_target_date": b["default_target_date"], "synthetic": bool(b["synthetic"])}
                           for b in businesses],
            "permission_tiers": ["agent_read", "agent_propose", "human_approval", "sandbox_execute"],
            "capabilities": ["read_ledger", "project_cash", "compare_plans", "create_reminder_draft",
                             "approval_gated_sandbox", "supplier_consent_simulation", "policy_update", "evidence_export"],
            "operator_scope": "local demo operator; not authenticated multiuser",
        }

    def _business_target(self, business_id=None, target_date=None):
        if business_id is None:
            business_id = SHAPLA_BUSINESS_ID if any(b["id"] == SHAPLA_BUSINESS_ID for b in self.store.list_businesses()) else LEGACY_BUSINESS_ID
        validate_business_id(business_id)
        business = self.store.get_business(business_id)
        target_date = valid_date(target_date or business["default_target_date"], "target_date")
        return business_id, target_date

    def _has_scoped_records(self):
        """Tell compatibility GETs whether a real SME workspace is active.

        ``--no-demo`` creates an empty local workspace so the new UI can load,
        while the old unscoped FinMate export tests still need their isolated
        legacy business until the user imports SME records.
        """
        for business in self.store.list_businesses():
            if business["id"] == LEGACY_BUSINESS_ID:
                continue
            records = self.store.records(business["id"])
            if any(records.values()):
                return True
        return False

    def dashboard(self, business_id=None, target_date=None, month=None):
        if month is None and target_date is None and isinstance(business_id, str) and len(business_id) == 7 and business_id[4] == "-":
            month, business_id = business_id, None
        if business_id is None and month is not None:
            # Compatibility dashboard is strictly the personal legacy demo.
            business_id = LEGACY_BUSINESS_ID
            rows = self.store.rows()
            active = self.store.budget(month)
            selected = [r for r in rows if r["date"].startswith(month)]
            return {"summary": summary(rows, month), "previous": summary(rows, previous_month(month)),
                    "insights": insights(rows, month, active["payload"]["savings_percent"] if active else 20),
                    "recurring": recurring_bills(rows, month), "transactions": selected,
                    "budget": active, "draft": self.store.pending(month)}
        business_id, target_date = self._business_target(business_id, target_date)
        snapshot = self.store.snapshot(business_id)
        accepted = self._accepted_actions(snapshot, target_date)
        common = {"business_id": business_id, "opening_cash_minor": snapshot["business"]["opening_cash_minor"],
                  "opening_date": snapshot["business"]["opening_date"], "transactions": snapshot["transactions"],
                  "invoices": snapshot["invoices"], "bills": snapshot["bills"], "policy": snapshot["policy"],
                  "target_date": target_date}
        base = project_cash(**common, scenario="base")
        late = project_cash(**common, scenario="late_collection")
        recovery = project_cash(**common, scenario="approved_recovery", approved_actions=accepted)
        plans = compare_plans(base, business_id=business_id, target_date=target_date,
                               transactions=snapshot["transactions"], invoices=snapshot["invoices"],
                               bills=snapshot["bills"], policy=snapshot["policy"], accepted_actions=accepted)
        plans = self._shape_plans(plans, snapshot)
        pending_approvals = self.store.pending_approvals(business_id, target_date)
        pending_plan = self.store.pending_plan(business_id, target_date)
        evidence = self.store.evidence(business_id)
        return {
            "business": snapshot["business"], "policy": snapshot["policy"],
            "projection": {"base": base, "late_collection": late, "approved_recovery": recovery},
            "plans": plans.get("plans", []), "plan_proposal": plans,
            "pending_plan": pending_plan,
            "pending_approval": pending_approvals[0] if pending_approvals else None,
            "pending_approvals": pending_approvals,
            "sandbox_state": snapshot["sandbox"], "transactions": snapshot["transactions"],
            "invoices": snapshot["invoices"], "bills": snapshot["bills"],
            "recent_records": self.store.records(business_id),
            "supplier_consents": self.store.consents(business_id),
            "evidence_summary": {"hash_chain_valid": evidence["hash_chain_valid"],
                                  "audit_entries": len(evidence["entries"]),
                                  "source_reference_count": len(base.get("source_references", base.get("sources", []))),
                                  "snapshot_hash": snapshot["snapshot_hash"],
                                  "state_hash": snapshot["sandbox"]["state_hash"]},
        }

    @staticmethod
    def _expect_fields(body, allowed, required=()):
        if not isinstance(body, dict):
            raise ValidationError("Request must be a JSON object.")
        unexpected = sorted(set(body) - set(allowed))
        if unexpected:
            raise ValidationError(f"Unexpected request field(s): {', '.join(unexpected)}.")
        missing = [field for field in required if field not in body]
        if missing:
            raise ValidationError(f"Missing required field(s): {', '.join(missing)}.")

    @staticmethod
    def _accepted_actions(snapshot, target_date):
        result = []
        for bill_id, item in sorted((snapshot["sandbox"].get("rescheduled_bills") or {}).items()):
            result.append({"action_id": item.get("action_id", f"accepted-{bill_id}"), "type": "supplier_reschedule",
                           "business_id": snapshot["business"]["id"], "bill_id": bill_id,
                           "payee": item.get("payee"), "amount_minor": item.get("amount_minor", 0),
                           "currency": "BDT", "date": item.get("action_date", target_date),
                           "reschedule_to": item.get("reschedule_to")})
        return result

    def _shape_plans(self, result, snapshot):
        accepted_bills = set((snapshot["sandbox"].get("rescheduled_bills") or {}).keys())
        raw = result.get("plans", []) if isinstance(result, dict) else []
        shaped = []
        for action in raw:
            if action.get("type") in ("supplier_reschedule", "reschedule") and action.get("bill_id") in accepted_bills:
                # The accepted schedule is already in approved_recovery.  Do
                # not present a duplicate candidate that could overwrite it.
                continue
            item = dict(action)
            item["id"] = item.get("id", item.get("action_id"))
            item["title"] = item.get("title", item.get("label", item.get("action_id", "Recovery action")))
            item["kind"] = item.get("kind", item.get("type", "recovery_action"))
            item["assumption"] = item.get("assumption", item.get("explanation", "Uses the current business-scoped records."))
            item["action"] = dict(action)
            item["labelled_mock"] = bool(item.get("labelled_mock", item.get("mock", item["kind"] == "mock_financing")))
            item["projected"] = item.get("projected", {"closing_cash_minor": item.get("projected_closing_cash_minor"),
                                                          "reserve_shortfall_minor": item.get("projected_reserve_shortfall_minor")})
            item["risks"] = item.get("risks", []) if isinstance(item.get("risks", []), list) else [item["risks"]]
            shaped.append(item)
        result = dict(result)
        result["plans"] = shaped
        result["options"] = shaped
        result["supplier_reschedule"] = next((item for item in shaped if item.get("type") in ("supplier_reschedule", "reschedule")), None)
        result["collection_reminder"] = next((item for item in shaped if item.get("type") == "collection_reminder"), None)
        result["financing_alternatives"] = [item for item in shaped if item.get("type") == "mock_financing"]
        return result

    def _compare(self, business_id, target_date):
        business_id, target_date = self._business_target(business_id, target_date)
        snapshot = self.store.snapshot(business_id)
        common = {"business_id": business_id, "opening_cash_minor": snapshot["business"]["opening_cash_minor"],
                  "opening_date": snapshot["business"]["opening_date"], "transactions": snapshot["transactions"],
                  "invoices": snapshot["invoices"], "bills": snapshot["bills"], "policy": snapshot["policy"],
                  "target_date": target_date}
        base = project_cash(**common, scenario="base")
        late = project_cash(**common, scenario="late_collection")
        result = compare_plans(base, business_id=business_id, target_date=target_date,
                               transactions=snapshot["transactions"], invoices=snapshot["invoices"],
                               bills=snapshot["bills"], policy=snapshot["policy"], accepted_actions=self._accepted_actions(snapshot, target_date))
        result["projection"] = {"base": base, "late_collection": late,
                                 "approved_recovery": project_cash(**common, scenario="approved_recovery", approved_actions=self._accepted_actions(snapshot, target_date))}
        result = self._shape_plans(result, snapshot)
        result["snapshot_hash"] = snapshot["snapshot_hash"]
        result["policy_version"] = snapshot["policy"]["version"]
        result["plan_hash"] = _plan_payload_hash(result)
        stored = self.store.create_plan(business_id, result)
        approvals = self.store.pending_approvals(business_id, target_date)
        stored["pending_approval"] = approvals[0] if approvals else None
        stored["sandbox_state"] = snapshot["sandbox"]
        return stored

    def post(self, path, body):
        try:
            if path == "/api/import":
                self._expect_fields(body, ("business_id", "csv", "replace_demo"), ("csv",))
                replace_demo = body.get("replace_demo", False)
                if not isinstance(replace_demo, bool):
                    raise ValidationError("Replace sample data must be true or false.")
                business_id = body.get("business_id")
                if business_id is None:
                    # Legacy transaction-only import remains isolated to the
                    # personal demo business.
                    return self.store.import_rows(parse_csv(body.get("csv")), "csv", replace_demo, LEGACY_BUSINESS_ID)
                business_id = validate_business_id(business_id)
                parsed = parse_combined_csv(body.get("csv"), business_id, allow_legacy=False)
                return self.store.import_combined(business_id, parsed, "csv", replace_demo)
            if path == "/api/transactions":
                # The old personal endpoint remains isolated to the legacy
                # business.  Probaho callers should use the combined import.
                allowed = {"date", "description", "amount", "amount_minor", "type", "category", "currency", "business_id", "replace_demo"}
                self._expect_fields(body, allowed, ("date", "description", "type"))
                replace_demo = body.get("replace_demo", False)
                if not isinstance(replace_demo, bool):
                    raise ValidationError("Replace sample data must be true or false.")
                business_id = body.get("business_id")
                if business_id is None:
                    result = self.store.import_rows([validate_transaction(body)], "manual", replace_demo, LEGACY_BUSINESS_ID)
                else:
                    business_id = validate_business_id(business_id)
                    result = self.store.import_combined(business_id, {"transactions": [body], "invoices": [], "bills": []}, "manual", replace_demo)
                added = result.get("added", 0)
                if isinstance(added, dict):
                    added = added.get("transactions", 0)
                if not added:
                    raise ValidationError("An identical transaction already exists. It was not added twice.")
                return result
            if path == "/api/demo":
                if set(body) - {"business_id", "replace_demo"}:
                    raise ValidationError("Unexpected demo request field.")
                demo_business = body.get("business_id", LEGACY_BUSINESS_ID)
                if demo_business != LEGACY_BUSINESS_ID:
                    raise ValidationError("The legacy personal demo cannot be inserted into an SME business.")
                return self.store.import_rows(demo_rows(), "demo", False, LEGACY_BUSINESS_ID)
            if path == "/api/plan/compare":
                self._expect_fields(body, ("business_id", "target_date"), ("business_id", "target_date"))
                return self._compare(body.get("business_id"), body.get("target_date"))
            if path == "/api/plan/approve":
                self._expect_fields(body, ("business_id", "plan_id", "action_id"), ("business_id", "plan_id", "action_id"))
                business_id = validate_business_id(body.get("business_id", ""))
                return self.store.approve_plan(business_id, body.get("plan_id"), body.get("action_id"))
            if path == "/api/plan/execute":
                self._expect_fields(body, ("business_id", "approval_id", "idempotency_key"), ("business_id", "approval_id", "idempotency_key"))
                business_id = validate_business_id(body.get("business_id", ""))
                return self.store.execute_plan(business_id, body.get("approval_id"), body.get("idempotency_key"))
            if path == "/api/plan/cancel":
                self._expect_fields(body, ("business_id", "approval_id"), ("business_id", "approval_id"))
                business_id = validate_business_id(body.get("business_id", ""))
                return self.store.cancel_approval(business_id, body.get("approval_id"))
            if path == "/api/sandbox/consent":
                self._expect_fields(body, ("business_id", "plan_id", "action_id", "accepted"), ("business_id", "plan_id", "action_id", "accepted"))
                business_id = validate_business_id(body.get("business_id", ""))
                return self.store.record_supplier_consent(business_id, body.get("plan_id"), body.get("action_id"), body.get("accepted"))
            if path == "/api/sandbox/reset":
                self._expect_fields(body, ("business_id",), ("business_id",))
                business_id = validate_business_id(body.get("business_id", ""))
                return self.store.reset_sandbox(business_id)
            if path == "/api/policy":
                self._expect_fields(body, ("business_id", "reserve_floor_minor", "action_limit_minor", "payroll_priority"),
                                    ("business_id", "reserve_floor_minor", "action_limit_minor", "payroll_priority"))
                business_id = validate_business_id(body.get("business_id", ""))
                if not isinstance(body.get("payroll_priority"), bool):
                    raise ValidationError("payroll_priority must be true or false.")
                with self.store.connect() as db:
                    current = db.execute("SELECT version FROM policies WHERE business_id=?", (business_id,)).fetchone()
                version_number = 1
                if current and isinstance(current["version"], str) and current["version"].rsplit("-v", 1)[-1].isdigit():
                    version_number = int(current["version"].rsplit("-v", 1)[-1]) + 1
                policy = {"business_id": business_id, "currency": "BDT",
                          "reserve_floor_minor": body.get("reserve_floor_minor"),
                          "action_limit_minor": body.get("action_limit_minor"),
                          "payroll_priority": body.get("payroll_priority"),
                          "version": f"probaho-policy-v{version_number}"}
                return self.store.set_policy(business_id, policy)
            if path == "/api/budget/approve":
                self._expect_fields(body, ("draft_id",), ("draft_id",))
                identifier = body.get("draft_id")
                if not isinstance(identifier, str) or len(identifier) != 32:
                    raise ValidationError("A valid draft ID is required.")
                return self.store.approve(identifier)
            if path == "/api/budget/draft":
                self._expect_fields(body, ("month", "income", "savings_percent"), ("month",))
                month = month_value(body.get("month", ""))
                income = body.get("income")
                if income is None:
                    income = summary(self.store.rows(), month)["income_minor"] / 100
                return self.store.new_draft(build_budget(self.store.rows(), month, income, body.get("savings_percent", 20)))
            if path == "/api/chat":
                self._expect_fields(body, ("business_id", "target_date", "message", "history", "external_consent", "month"), ("message", "history", "external_consent"))
                history = body.get("history", [])
                consent = body.get("external_consent", False)
                if not isinstance(history, list) or len(history) > 30 or not isinstance(consent, bool):
                    raise ValidationError("Invalid assistant request.")
                business_id = body.get("business_id")
                if business_id is not None:
                    business_id, target_date = self._business_target(business_id, body.get("target_date"))
                    return self.agent.chat(body.get("message"), body.get("month"), history, consent,
                                           business_id, target_date)
                month = month_value(body.get("month", ""))
                return self.agent.chat(body.get("message"), month, history, consent)
            raise ValidationError("Unknown endpoint.")
        except ValidationError as exc:
            self.store._reject("api.rejected", exc, body.get("business_id"), {"path": path})
            raise


def csv_cell(value):
    text = str(value)
    # Prevent spreadsheets interpreting imported descriptions as executable formulae.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Probaho/2.0"

        def trusted_host(self):
            port = self.server.server_port
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def reply(self, status, body, content_type="application/json; charset=utf-8", filename=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_GET(self):
            if not self.trusted_host():
                return self.reply(403, {"error": "Untrusted host. Open the loopback address printed by the server."})
            parsed = urlsplit(self.path)
            path = parsed.path
            try:
                if path in ("/", "/index.html", "/styles.css", "/app.js", "/favicon.svg"):
                    filename = "index.html" if path == "/" else path[1:]
                    static = ROOT / "web" / filename
                    if not static.is_file():
                        return self.reply(404, {"error": "Not found."})
                    content_type = {"html": "text/html", "css": "text/css", "js": "text/javascript", "svg": "image/svg+xml"}[filename.rsplit(".", 1)[-1]]
                    return self.reply(200, static.read_bytes(), content_type + "; charset=utf-8")
                if path == "/api/config":
                    return self.reply(200, app.config())
                query = parse_qs(parsed.query)
                if path == "/api/audit":
                    business_id = query.get("business_id", [None])[0]
                    if business_id is None:
                        business_id = LEGACY_BUSINESS_ID if not app._has_scoped_records() else None
                    if business_id is None:
                        raise ValidationError("business_id is required for SME audit reads.")
                    validate_business_id(business_id)
                    return self.reply(200, app.store.evidence(business_id))
                if path == "/api/execution":
                    business_id = query.get("business_id", [None])[0]
                    if business_id is None:
                        business_id = LEGACY_BUSINESS_ID if not app._has_scoped_records() else None
                    if business_id is None:
                        raise ValidationError("business_id is required for SME execution reads.")
                    idempotency_key = query.get("idempotency_key", [""])[0]
                    validate_business_id(business_id)
                    return self.reply(200, app.store.execution_receipt(business_id, idempotency_key))
                if path == "/api/export":
                    kind = query.get("kind", ["evidence"])[0]
                    business_id = query.get("business_id", [None])[0]
                    if business_id is None:
                        business_id = LEGACY_BUSINESS_ID if not app._has_scoped_records() else None
                    if business_id is None:
                        raise ValidationError("business_id is required for SME exports.")
                    validate_business_id(business_id)
                    if kind == "evidence":
                        return self.reply(200, app.store.evidence(business_id), filename=f"probaho-{business_id}-evidence.json")
                    if kind == "transactions":
                        stream = io.StringIO(newline="")
                        writer = csv.writer(stream)
                        writer.writerow(["record_type", "business_id", "id", "date", "description", "amount", "amount_minor", "type", "currency", "category", "due_date", "status", "customer", "payee", "issue_date", "expected_collection_date", "priority", "reschedule_allowed", "rescheduled_date"])
                        records = app.store.records(business_id)
                        for row in records["transactions"]:
                            writer.writerow(["transaction", row["business_id"], row["id"], row["date"], csv_cell(row["description"]), f"{row['amount_minor']/100:.2f}", row["amount_minor"], row["type"], "BDT", row["category"], "", "", "", "", "", "", "", "", ""])
                        for row in records["invoices"]:
                            writer.writerow(["invoice", row["business_id"], row["id"], row["issue_date"], csv_cell(row["description"]), f"{row['amount_minor']/100:.2f}", row["amount_minor"], "", "BDT", "", row["due_date"], row["status"], csv_cell(row["customer"]), "", row["issue_date"], row["expected_collection_date"], "", "", ""])
                        for row in records["bills"]:
                            writer.writerow(["bill", row["business_id"], row["id"], "", csv_cell(row["description"]), f"{row['amount_minor']/100:.2f}", row["amount_minor"], "", "BDT", "", row["due_date"], row["status"], "", csv_cell(row["payee"]), "", "", row["priority"], str(bool(row["reschedule_allowed"])).lower(), row.get("rescheduled_date") or ""])
                        return self.reply(200, "\ufeff" + stream.getvalue(), "text/csv; charset=utf-8", f"probaho-{business_id}-records.csv")
                    if kind == "results":
                        stream = io.StringIO(newline="")
                        writer = csv.writer(stream)
                        writer.writerow(["result_type", "business_id", "execution_id", "approval_id", "idempotency_key", "action_type", "status", "cash_effect_minor", "action_json", "receipt_json", "synthetic"])
                        for execution in app.store.executions(business_id):
                            receipt = execution["receipt"]
                            writer.writerow(["execution_receipt", execution["business_id"], execution["id"], execution["approval_id"], execution["idempotency_key"], receipt.get("action_type"), receipt.get("status"), receipt.get("cash_effect_minor", 0), json.dumps(receipt.get("action", {}), ensure_ascii=False, sort_keys=True), json.dumps(receipt, ensure_ascii=False, sort_keys=True), bool(receipt.get("synthetic", True))])
                        return self.reply(200, "\ufeff" + stream.getvalue(), "text/csv; charset=utf-8", f"probaho-{business_id}-execution-receipts.csv")
                    raise ValidationError("Unsupported export kind.")
                if path == "/api/dashboard":
                    if query.get("business_id"):
                        return self.reply(200, app.dashboard(query.get("business_id", [None])[0], query.get("target_date", [None])[0]))
                    month = month_value(query.get("month", [""])[0])
                    return self.reply(200, app.dashboard(month=month))
                return self.reply(404, {"error": "Not found."})
            except ValidationError as exc:
                self.reply(400, {"error": str(exc), "code": "validation_error"})
            except Exception as exc:
                print(f"Request failed: {type(exc).__name__}", file=sys.stderr)
                self.reply(500, {"error": "An internal error occurred. Check the local server console."})

        def do_POST(self):
            if not self.trusted_host():
                return self.reply(403, {"error": "Untrusted host."})
            expected = (f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}")
            origin = self.headers.get("Origin")
            if origin is not None and origin not in expected:
                return self.reply(403, {"error": "Cross-origin writes are not allowed."})
            token = self.headers.get("X-FinMate-Token", self.headers.get("X-Probaho-Token", self.headers.get("X-CSRF-Token", "")))
            if not secrets.compare_digest(token, app.csrf):
                return self.reply(403, {"error": "Missing or invalid session token. Refresh the app."})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self.reply(415, {"error": "Use application/json."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 2_000_000:
                    return self.reply(413, {"error": "Request body must be 1 byte to 2 MB."})
                body = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid JSON number")))
                if not isinstance(body, dict):
                    raise ValidationError("Request must be a JSON object.")
                path = urlsplit(self.path).path
                allowed = ("/api/import", "/api/transactions", "/api/demo", "/api/budget/draft", "/api/budget/approve", "/api/chat",
                            "/api/plan/compare", "/api/plan/approve", "/api/plan/execute", "/api/plan/cancel",
                            "/api/sandbox/consent", "/api/sandbox/reset", "/api/policy")
                if path not in allowed:
                    return self.reply(404, {"error": "Not found."})
                return self.reply(200, app.post(path, body))
            except (ValidationError, ValueError, UnicodeDecodeError) as exc:
                self.reply(400, {"error": str(exc), "code": "validation_error"})
            except Exception as exc:
                print(f"Request failed: {type(exc).__name__}", file=sys.stderr)
                self.reply(500, {"error": "An internal error occurred. Check the local server console."})

        def log_message(self, fmt, *args):
            print(f"[{self.log_date_time_string()}] {fmt % args}", flush=True)

    return Handler


def serve(db_path, port=8787, key="", model="gpt-5-mini", seed=True):
    app = Application(db_path, key, model, seed)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    print(f"Probaho is ready: http://127.0.0.1:{server.server_port}", flush=True)
    print("AI connected (consent required per message)." if key else "Local synthetic demo mode. Set OPENAI_API_KEY in .env to enable AI.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Probaho stopped.")
    finally:
        server.server_close()
