"""Loopback-only HTTP API and static UI for the Tideway sandbox."""
from __future__ import annotations

import csv
import io
import json
import re
import secrets
import sys
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import selftest
from .agent import Agent
from .domain import SecurityError, ValidationError, canonical_json, validate_business_id
from .security import RateLimiter
from .service import Tideway
from .tidelm import TideLM, TideLMUnavailable, confirm as confirm_inbox
from .vision import TideVision, TideVisionUnavailable


ROOT = Path(__file__).resolve().parent.parent
STATIC = {"/": "index.html", "/index.html": "index.html", "/styles.css": "styles.css", "/app.js": "app.js",
          "/favicon.svg": "favicon.svg", "/guide": "guide.html", "/guide.html": "guide.html",
          "/guide.css": "guide.css", "/guide.js": "guide.js",
          "/benchmarks/tidepay.json": "../evidence/upgrade-v1/tidepay/report.json",
          "/benchmarks/tidepay-reliability.svg": "../evidence/upgrade-v1/tidepay/reliability.svg"}
CONTENT_TYPES = {"html": "text/html", "css": "text/css", "js": "text/javascript", "svg": "image/svg+xml", "json": "application/json"}
COOKIE = "tideway_session"


def csv_cell(value):
    """Prevent spreadsheets from treating imported text as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


class Application:
    def __init__(self, db_path, key="", model="gpt-5-mini", seed=True, transport=None):
        self.tideway = Tideway(db_path, seed=seed)
        self.store = self.tideway.store
        self.agent = Agent(self.tideway, key, model, **({"transport": transport} if transport else {}))
        self.csrf = secrets.token_urlsafe(32)
        self.post_limiter = RateLimiter(capacity=120, refill_per_second=2)
        self.login_limiter = RateLimiter(capacity=10, refill_per_second=0.2)
        self.selftest_cache = None
        self.tidelm = TideLM()
        self.vision = TideVision()

    # ---- helpers ---------------------------------------------------------------

    @staticmethod
    def fields(body, allowed, required=()):
        if not isinstance(body, dict):
            raise ValidationError("Request must be a JSON object.")
        unexpected = sorted(set(body) - set(allowed))
        if unexpected:
            raise ValidationError(f"Unexpected field(s): {', '.join(unexpected)}.")
        missing = [name for name in required if name not in body]
        if missing:
            raise ValidationError(f"Missing field(s): {', '.join(missing)}.")

    @staticmethod
    def require(operator, *roles):
        if operator is None:
            raise PermissionError("Sign in first.")
        if roles and operator["role"] not in roles:
            raise PermissionError(f"This action needs the {' or '.join(roles)} role.")
        return operator

    def scoped(self, operator, business_id):
        """Tenant isolation: the operator must be a member, and acts with their role in this business."""
        role = self.store.membership_role(operator["id"], business_id)
        if role is None:
            raise PermissionError("You are not a member of this business.")
        return {**operator, "role": role}

    def config(self, operator):
        return {**self.tideway.config(operator), "csrf_token": self.csrf, "operator": operator,
                "ai_configured": bool(self.agent.key), "ai_model": self.agent.model if self.agent.key else None,
                "tidelm": self.tidelm.status(), "vision": self.vision.status()}

    def bundle_for(self, business_id, plan_id, bundle_id):
        plan = self.store.plan(business_id, plan_id)
        bundle = next((item for item in plan["bundles"] if item["bundle_id"] == bundle_id), None)
        if not bundle:
            raise ValidationError("Bundle was not found in this plan.")
        return bundle

    # ---- GET -------------------------------------------------------------------

    def get(self, path, query, operator):
        one = lambda name, default=None: query.get(name, [default])[0]  # noqa: E731
        if path == "/api/config":
            return self.config(operator)
        if path == "/api/session":
            return {"operator": operator}
        self.require(operator)
        business_id = validate_business_id(one("business_id", ""))
        operator = self.scoped(operator, business_id)
        if path == "/api/team":
            return self.store.team(business_id)
        if path == "/api/feedback":
            return self.store.feedback_summary(business_id)
        if path == "/api/network":
            return self.tideway.network(business_id, one("target_date"))
        if path == "/api/dashboard":
            return self.tideway.dashboard(business_id, one("target_date"))
        if path == "/api/plan":
            return self.store.plan(business_id, one("plan_id", ""))
        if path == "/api/mandate":
            return self.store.mandate(business_id, one("mandate_id", ""))
        if path == "/api/audit":
            return self.store.evidence(business_id)
        if path == "/api/execution":
            return self.store.execution_by_key(business_id, one("idempotency_key", ""))
        raise LookupError(path)

    def export(self, query, operator):
        self.require(operator)
        kind = query.get("kind", ["evidence"])[0]
        business_id = validate_business_id(query.get("business_id", [""])[0])
        self.scoped(operator, business_id)
        if kind == "evidence":
            return canonical_json(self.store.evidence(business_id)), "application/json", f"tideway-{business_id}-evidence.json"
        if kind == "bank-pack":
            from .copilot import bank_pack, bank_pack_html
            return (bank_pack_html(bank_pack(self.tideway, business_id, query.get("target_date", [None])[0])), "text/html",
                    f"tideway-{business_id}-bank-pack.html")
        if kind == "iso20022":
            return self.tideway.iso20022(business_id), "application/xml", f"tideway-{business_id}-pain001-draft.xml"
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        if kind == "records":
            records = self.store.records(business_id)
            writer.writerow(["record_type", "id", "date", "description", "amount_minor", "currency", "type", "category",
                             "customer", "payee", "payee_account", "issue_date", "due_date", "expected_collection_date",
                             "paid_date", "status", "priority", "reschedule_allowed", "risk_flags", "source"])
            for row in records["transactions"]:
                writer.writerow(["transaction", row["id"], row["date"], csv_cell(row["description"]), row["amount_minor"],
                                 row["currency"], row["type"], csv_cell(row["category"]), "", "", "", "", "", "", "", "", "", "",
                                 "|".join(row["risk_flags"]), row["source"]])
            for row in records["invoices"]:
                writer.writerow(["invoice", row["id"], row["issue_date"], csv_cell(row["description"]), row["amount_minor"],
                                 row["currency"], "", "", csv_cell(row["customer"]), "", "", row["issue_date"], row["due_date"],
                                 row["expected_collection_date"], row["paid_date"] or "", row["status"], "", "",
                                 "|".join(row["risk_flags"]), row["source"]])
            for row in records["bills"]:
                writer.writerow(["bill", row["id"], "", csv_cell(row["description"]), row["amount_minor"], row["currency"], "", "",
                                 "", csv_cell(row["payee"]), csv_cell(row["payee_account"] or ""), "", row["due_date"], "", "",
                                 row["status"], row["priority"], str(row["reschedule_allowed"]).lower(),
                                 "|".join(row["risk_flags"]), row["source"]])
            return "﻿" + stream.getvalue(), "text/csv", f"tideway-{business_id}-records.csv"
        if kind == "receipts":
            writer.writerow(["receipt_id", "mandate_id", "plan_id", "bundle_id", "idempotency_key", "executed_by", "human_present",
                             "exposure_minor", "cash_moved_minor", "actions_json", "state_before_hash", "state_after_hash",
                             "read_back_verified", "audit_hash"])
            for receipt in self.store.executions(business_id):
                writer.writerow([receipt["receipt_id"], receipt["mandate_id"], receipt["plan_id"], receipt["bundle_id"],
                                 receipt["idempotency_key"], receipt["executed_by"], receipt["human_present"],
                                 receipt["exposure_minor"], receipt["cash_moved_minor"], canonical_json(receipt["actions"]),
                                 receipt["state_before"]["state_hash"], receipt["state_after"]["state_hash"],
                                 receipt["read_back"]["verified"], receipt["audit_hash"]])
            return "﻿" + stream.getvalue(), "text/csv", f"tideway-{business_id}-receipts.csv"
        raise ValidationError("Unsupported export kind.")

    # ---- POST ------------------------------------------------------------------

    def post(self, path, body, operator, session_token, client="local"):
        actor = f"operator:{operator['id']}" if operator else "anonymous"
        if path == "/api/session/login":
            self.fields(body, ("operator_id", "pin"), ("operator_id", "pin"))
            if not isinstance(body["operator_id"], str) or not isinstance(body["pin"], str):
                raise ValidationError("Operator and PIN must be text.")
            token, who = self.store.login(body["operator_id"], body["pin"], client)
            return {"operator": who, "_set_session": token}
        if path == "/api/signup":
            business, who = self.tideway.signup(body)
            token, who = self.store.login(who["id"], body["pin"], client)
            return {"operator": who, "business_id": business["business_id"], "_set_session": token}
        if path == "/api/team/join":
            self.fields(body, ("code", "username", "name", "pin"), ("code",))
            joined = self.store.accept_invite(body["code"], operator, body.get("username"), body.get("name"), body.get("pin"))
            if operator is None:
                token, who = self.store.login(joined["operator"]["id"], body.get("pin"), client)
                return {"operator": who, "business_id": joined["business_id"], "_set_session": token}
            return {"operator": operator, "business_id": joined["business_id"]}
        if path == "/api/session/logout":
            self.store.logout(session_token)
            return {"operator": None, "_clear_session": True}
        self.require(operator)
        business_id = validate_business_id(body.get("business_id", "")) if "business_id" in body else None
        if business_id:
            operator = self.scoped(operator, business_id)
        if path == "/api/feedback":
            self.fields(body, ("business_id", "mode", "helpful", "question", "comment"), ("business_id", "mode", "helpful", "question"))
            return self.store.add_feedback(business_id, operator, body["mode"], body["helpful"], body["question"], body.get("comment", ""))
        if path == "/api/team/invite":
            self.fields(body, ("business_id", "role", "name"), ("business_id", "role", "name"))
            return self.store.create_invite(business_id, operator, body["role"], body["name"])
        if path == "/api/team/remove":
            self.fields(body, ("business_id", "operator_id"), ("business_id", "operator_id"))
            if not isinstance(body["operator_id"], str):
                raise ValidationError("operator_id must be text.")
            return self.store.remove_member(business_id, operator, body["operator_id"])
        if path == "/api/agent/run":
            self.fields(body, ("business_id", "target_date"), ("business_id",))
            self.require(operator, "owner", "accountant")
            return self.agent.rescue_run(business_id, body.get("target_date"), "agent:local")
        if path == "/api/demo/payment-delay":
            self.fields(body, ("business_id", "invoice_id", "collection_date", "expected_snapshot", "request_id", "pin", "target_date"),
                        ("business_id", "invoice_id", "collection_date", "expected_snapshot", "request_id", "pin"))
            self.require(operator, "owner")
            return self.tideway.apply_demo_delay(business_id, body["invoice_id"], body["collection_date"],
                                                body["expected_snapshot"], body["request_id"], operator,
                                                body["pin"], actor, body.get("target_date"))
        if path == "/api/chat":
            self.fields(body, ("business_id", "target_date", "message", "history", "consent"), ("business_id", "message"))
            history = body.get("history", [])
            if not isinstance(history, list) or len(history) > 20 or not isinstance(body.get("consent", False), bool):
                raise ValidationError("Invalid chat request.")
            return self.agent.chat(business_id, body.get("target_date"), body["message"], history, body.get("consent", False),
                                   "agent:llm" if body.get("consent") and self.agent.key else "agent:local", operator["role"],
                                   operator["name"])
        if path == "/api/copilot/ask":
            self.fields(body, ("business_id", "target_date", "message"), ("business_id", "message"))
            return self.tidelm.ask(self.tideway, business_id, body.get("target_date"), body["message"], operator["role"],
                                   name=operator["name"])
        if path == "/api/inbox/extract":
            self.fields(body, ("business_id", "text"), ("business_id", "text"))
            self.require(operator, "owner", "accountant")
            return self.tidelm.extract(self.tideway, business_id, body["text"])
        if path == "/api/inbox/photo":
            self.fields(body, ("business_id", "image"), ("business_id", "image"))
            self.require(operator, "owner", "accountant")
            return self.vision.read(self.tideway, business_id, body["image"])
        if path == "/api/inbox/confirm":
            self.fields(body, ("business_id", "records"), ("business_id", "records"))
            self.require(operator, "owner", "accountant")
            return confirm_inbox(self.tideway, business_id, body["records"], actor)
        if path == "/api/plan/propose":
            self.fields(body, ("business_id", "target_date"), ("business_id",))
            self.require(operator, "owner", "accountant")
            return self.tideway.propose(business_id, body.get("target_date"), actor, proposed_by="agent")
        if path == "/api/plan/approve":
            self.fields(body, ("business_id", "plan_id", "bundle_id", "pin", "review_ms", "confirm_amount_minor"),
                        ("business_id", "plan_id", "bundle_id", "pin"))
            bundle = self.bundle_for(business_id, body["plan_id"], body["bundle_id"])
            if bundle.get("dual_approval_required") and body.get("confirm_amount_minor") != bundle["exposure_minor"]:
                raise ValidationError("High-value bundle: type the total exposure exactly to confirm you read it.")
            return self.store.approve(business_id, body["plan_id"], body["bundle_id"], operator, body["pin"], actor,
                                      body.get("review_ms"))
        if path == "/api/mandate/negotiate":
            self.fields(body, ("business_id", "mandate_id"), ("business_id", "mandate_id"))
            self.require(operator, "owner", "accountant")
            return self.tideway.negotiate(business_id, body["mandate_id"], "agent:local")
        if path == "/api/mandate/simulate":
            self.fields(body, ("business_id", "mandate_id", "action_id", "accept"), ("business_id", "mandate_id", "action_id", "accept"))
            return self.tideway.simulate_decision(business_id, body["mandate_id"], body["action_id"], body["accept"], operator, actor)
        if path == "/api/mandate/counter":
            self.fields(body, ("business_id", "mandate_id"), ("business_id", "mandate_id"))
            self.require(operator, "owner", "accountant")
            return self.tideway.accept_counter(business_id, body["mandate_id"], actor)
        if path == "/api/mandate/replan":
            self.fields(body, ("business_id", "mandate_id"), ("business_id", "mandate_id"))
            self.require(operator, "owner", "accountant")
            return self.tideway.replan_without(business_id, body["mandate_id"], actor)
        if path == "/api/mandate/execute":
            self.fields(body, ("business_id", "mandate_id", "idempotency_key"), ("business_id", "mandate_id", "idempotency_key"))
            return self.store.execute(business_id, body["mandate_id"], body["idempotency_key"], operator, actor)
        if path == "/api/mandate/cancel":
            self.fields(body, ("business_id", "mandate_id"), ("business_id", "mandate_id"))
            return self.store.cancel_mandate(business_id, body["mandate_id"], operator, actor)
        if path == "/api/mandate/verify":
            self.fields(body, ("document",), ("document",))
            return self.store.verify_mandate_document(body["document"])
        if path == "/api/reminder/send":
            self.fields(body, ("business_id", "target_date", "action_id"), ("business_id", "action_id"))
            return self.tideway.send_reminder(business_id, body.get("target_date"), body["action_id"], operator, actor)
        if path == "/api/policy":
            self.fields(body, ("business_id", "changes", "pin"), ("business_id", "changes"))
            changes = body["changes"]
            if not isinstance(changes, dict) or not changes:
                raise ValidationError("changes must be a non-empty object.")
            if changes != {"agent_paused": True}:
                self.store.verify_pin(operator["id"], body.get("pin") or "")
            return self.store.set_policy(business_id, changes, operator, actor)
        if path == "/api/payee/verify":
            self.fields(body, ("business_id", "payee", "account", "method", "pin"), ("business_id", "payee", "account", "method", "pin"))
            self.store.verify_pin(operator["id"], body["pin"])
            return self.store.verify_payee(business_id, body["payee"], body["account"], operator, actor, body["method"])
        if path == "/api/import":
            self.fields(body, ("business_id", "csv", "replace_demo"), ("business_id", "csv"))
            self.require(operator, "owner", "accountant")
            if not isinstance(body.get("replace_demo", False), bool):
                raise ValidationError("replace_demo must be true or false.")
            return self.tideway.import_csv(business_id, body["csv"], actor, body.get("replace_demo", False))
        if path == "/api/whatif":
            self.fields(body, ("business_id", "target_date", "changes"), ("business_id", "changes"))
            return self.tideway.what_if(business_id, body.get("target_date"), body["changes"])
        if path == "/api/sandbox/reset":
            self.fields(body, ("business_id",), ("business_id",))
            return self.store.reset_sandbox(business_id, operator, actor)
        if path == "/api/audit/drill":
            self.fields(body, ("business_id",), ("business_id",))
            return self.store.tamper_drill(business_id)
        if path == "/api/selftest":
            self.fields(body, ())
            self.require(operator, "owner", "accountant")
            self.selftest_cache = selftest.run()
            return self.selftest_cache
        raise LookupError(path)


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Tideway/3.0"

        def trusted_host(self):
            port = self.server.server_port
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def session(self):
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            token = cookie[COOKIE].value if COOKIE in cookie else None
            return token, app.store.session_operator(token)

        def reply(self, status, body, content_type="application/json; charset=utf-8", filename=None, cookie=None):
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
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                                        "connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; "
                                                        "frame-ancestors 'none'")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def fail(self, exc, business_id=None, operator=None, path=""):
            message = str(exc)
            code = exc.code if isinstance(exc, SecurityError) else "validation_error"
            if business_id and operator:  # anonymous callers must not be able to fill the audit log or trip the breaker
                app.store.reject(business_id, "api.rejected", f"operator:{operator['id']}", message, {"path": path},
                                 security_relevant=isinstance(exc, SecurityError))
            self.reply(400, {"error": message, "code": code})

        def do_GET(self):
            if not self.trusted_host():
                return self.reply(403, {"error": "Untrusted host. Open the loopback address printed by the server."})
            parsed = urlsplit(self.path)
            if parsed.path in STATIC:
                name = STATIC[parsed.path]
                return self.reply(200, (ROOT / "web" / name).read_bytes(), CONTENT_TYPES[name.rsplit(".", 1)[1]] + "; charset=utf-8")
            _token, operator = self.session()
            query = parse_qs(parsed.query)
            try:
                if parsed.path == "/api/export":
                    body, content_type, filename = app.export(query, operator)
                    return self.reply(200, body, content_type + "; charset=utf-8", filename)
                return self.reply(200, app.get(parsed.path, query, operator))
            except PermissionError as exc:
                self.reply(401 if operator is None else 403, {"error": str(exc)})
            except LookupError:
                self.reply(404, {"error": "Not found."})
            except ValidationError as exc:
                self.fail(exc)
            except Exception as exc:  # never leak internals
                print(f"GET {parsed.path} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                self.reply(500, {"error": "Internal error. Check the server console."})

        def do_POST(self):
            if not self.trusted_host():
                return self.reply(403, {"error": "Untrusted host."})
            port = self.server.server_port
            origin = self.headers.get("Origin")
            if origin is not None and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return self.reply(403, {"error": "Cross-origin writes are not allowed."})
            if not secrets.compare_digest(self.headers.get("X-Tideway-Token", "").encode("utf-8", "surrogateescape"),
                                          app.csrf.encode()):
                return self.reply(403, {"error": "Missing or invalid CSRF token. Refresh the page."})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self.reply(415, {"error": "Use application/json."})
            path = urlsplit(self.path).path
            token, operator = self.session()
            limiter = app.login_limiter if path in ("/api/session/login", "/api/signup", "/api/team/join") else app.post_limiter
            if not limiter.allow(token or self.client_address[0]):
                return self.reply(429, {"error": "Too many requests. Slow down and try again shortly."})
            business_id = None
            try:
                raw_length = self.headers.get("Content-Length", "0").strip()
                if not raw_length.isascii() or not raw_length.isdigit():
                    return self.reply(400, {"error": "Invalid Content-Length.", "code": "validation_error"})
                length = int(raw_length)
                if not 0 < length <= 2_000_000:
                    return self.reply(413, {"error": "Request body must be 1 byte to 2 MB."})
                body = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid number")))
                if not isinstance(body, dict):
                    raise ValidationError("Request must be a JSON object.")
                candidate = body.get("business_id")
                if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", candidate):
                    business_id = candidate if any(item["id"] == candidate for item in app.store.list_businesses()) else None
                result = app.post(path, body, operator, token, self.client_address[0])
                cookie = None
                if isinstance(result, dict) and "_set_session" in result:
                    cookie = f"{COOKIE}={result.pop('_set_session')}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800"
                elif isinstance(result, dict) and result.pop("_clear_session", False):
                    cookie = f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
                return self.reply(200, result, cookie=cookie)
            except PermissionError as exc:
                self.reply(401 if operator is None else 403, {"error": str(exc)})
            except LookupError:
                self.reply(404, {"error": "Not found."})
            except (TideLMUnavailable, TideVisionUnavailable) as exc:
                self.reply(503, {"error": str(exc), "code": "tidelm_unavailable" if isinstance(exc, TideLMUnavailable)
                                 else "vision_unavailable"})
            except RecursionError:
                self.reply(400, {"error": "JSON is nested too deeply.", "code": "validation_error"})
            except (ValidationError, ValueError, UnicodeDecodeError) as exc:
                self.fail(exc, business_id, operator, path)
            except Exception as exc:
                print(f"POST {path} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                self.reply(500, {"error": "Internal error. Check the server console."})

        def log_message(self, fmt, *args):
            print(f"[{self.log_date_time_string()}] {fmt % args}", flush=True)

    return Handler


def serve(db_path, port=8787, key="", model="gpt-5-mini", seed=True, host="127.0.0.1"):
    app = Application(db_path, key, model, seed)
    server = ThreadingHTTPServer((host, port), make_handler(app))
    model_status = app.tidelm.status()
    if model_status["available"] and model_status.get("backend") != "local-compatible":
        import threading
        def warm_model():
            try:
                app.tidelm.warm()
            except Exception:
                app.tidelm._warm_error = "TideLM warm-up failed. Check model files, available memory and MLX installation."
                print(app.tidelm._warm_error, flush=True)
        threading.Thread(target=warm_model, name="tidelm-warmup", daemon=True).start()
        print("TideLM: loading the on-device model in the background…", flush=True)
    elif model_status["available"]:
        print("Local compatible model configured; its results are not the TideLM v2 benchmark.", flush=True)
    display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    print(f"Tideway is ready: http://{display_host}:{server.server_port}", flush=True)
    print("Demo sign-in (synthetic sandbox): owner Nadia PIN 2468 · accountant Imran PIN 1357 · viewer Guest PIN 0000", flush=True)
    print("AI provider connected (consent required per message)." if key else
          "Local agent mode (no network). Set OPENAI_API_KEY in .env to try the optional LLM mode.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Tideway stopped.")
    finally:
        server.server_close()
