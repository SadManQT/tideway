"""Exercise an already-running isolated container through its real HTTP API.

Run with docker exec as the configured non-root image user. This script never
imports Application or changes the database directly. All approvals are
explicitly scripted synthetic demo operators, not genuine human consent.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import platform
import time
from pathlib import Path
from urllib.parse import urlencode

BUSINESS = "shapla-services"
TARGET = "2026-10-31"
REPLAY_KEY = "isolated-container-workflow-v5"
STATE_FILE = Path("/app/data/docker-verification-state.json")


class Client:
    def __init__(self, host="127.0.0.1", port=8787):
        self.host, self.port = host, port
        self.csrf, self.cookie = None, None
        self.calls = []

    def request(self, method, path, body=None, expected=200, csrf=True):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=30)
        headers = {"Host": f"{self.host}:{self.port}"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        payload = None
        if body is not None:
            payload = json.dumps(body, allow_nan=False)
            headers.update({"Content-Type": "application/json", "Origin": f"http://{self.host}:{self.port}"})
            if csrf and self.csrf:
                headers["X-Tideway-Token"] = self.csrf
        try:
            connection.request(method, path, payload, headers)
            response = connection.getresponse()
            raw = response.read()
            self.calls.append({"method": method, "path": path.split("?")[0], "status": response.status})
            if response.status != expected:
                raise AssertionError(f"{method} {path.split('?')[0]} returned {response.status}, expected {expected}: {raw[:500]!r}")
            cookie = response.getheader("Set-Cookie")
            if cookie:
                self.cookie = cookie.split(";", 1)[0]
                assert "HttpOnly" in cookie and "SameSite=Strict" in cookie, "Session cookie lost protection"
            if "application/json" in (response.getheader("Content-Type") or ""):
                return json.loads(raw)
            return raw.decode("utf-8")
        finally:
            connection.close()

    def login(self, operator, pin):
        self.csrf = self.request("GET", "/api/config")["csrf_token"]
        result = self.request("POST", "/api/session/login", {"operator_id": operator, "pin": pin})
        assert result["operator"]["id"] == operator
        return self

    def get(self, route, **query):
        return self.request("GET", route + "?" + urlencode({"business_id": BUSINESS, **query}))

    def post(self, route, body=None, expected=200):
        return self.request("POST", route, {"business_id": BUSINESS, **(body or {})}, expected)


def wait_ready(client):
    deadline = time.monotonic() + 60
    while True:
        try:
            client.request("GET", "/api/config")
            return
        except (OSError, http.client.HTTPException):
            if time.monotonic() >= deadline:
                raise
            time.sleep(.25)


def run(phase, host="127.0.0.1", port=8787):
    anonymous = Client(host, port)
    wait_ready(anonymous)
    uid = os.getuid()
    assert uid == 10001, f"Expected configured non-root uid10001; got {uid}"
    private_paths = [".git", ".env", ".env.local", "submission-team.json", ".opencode", ".claude", ".vscode", "models", "tmp", "dist", "evidence/private", "personal-prep"]
    assert not any((Path("/app") / name).exists() for name in private_paths), "Private/excluded paths leaked into image"
    assert not list(Path("/app").glob("*.key")) and not list(Path("/app").glob("*.sqlite3")), "Host private data leaked into image root"
    for route in ("/guide", "/guide.html", "/guide.css", "/guide.js", "/personal-prep/project-guide/guide.html"):
        anonymous.request("GET", route, expected=404)
    anonymous.request("GET", "/api/dashboard?" + urlencode({"business_id": BUSINESS}), expected=401)
    owner = Client(host, port).login("nadia", "2468")
    checks = {"non_root_runtime": True, "private_paths_excluded": True, "personal_prep_unavailable": True,
              "protected_dashboard_requires_login": True}
    if phase == "workflow":
        owner.request("POST", "/api/session/login", {"operator_id": "nadia", "pin": "2468"}, expected=403, csrf=False)
        checks["csrf_required"] = True
        viewer = Client(host, port).login("guest", "0000")
        viewer.post("/api/plan/propose", {"target_date": TARGET}, expected=403)
        checks["viewer_cannot_create_proposal"] = True
        accountant = Client(host, port).login("imran", "1357")
        plan = owner.post("/api/plan/propose", {"target_date": TARGET})
        above = next((bundle for bundle in plan["bundles"] if bundle["feasible"] and
                      bundle["probability_breach_after"] > plan["risk_target"]), None)
        if above:
            accountant.post("/api/plan/approve", {"plan_id": plan["plan_id"], "bundle_id": above["bundle_id"],
                                                "pin": "1357", "review_ms": 9000,
                                                "confirm_amount_minor": above["exposure_minor"]}, expected=400)
        checks["above_target_requires_acknowledgement"] = above is not None
        approval_trace, negotiation_trace = [], []
        for attempt in range(4):
            bundle = next((bundle for bundle in plan["bundles"] if bundle["feasible"]), None)
            assert bundle is not None, "No feasible proposal for synthetic container smoke"
            consent = {}
            if bundle["probability_breach_after"] > plan["risk_target"]:
                consent = {"risk_acknowledgement": {"acknowledged": True, "plan_id": plan["plan_id"],
                            "plan_hash": plan["plan_hash"], "bundle_id": bundle["bundle_id"],
                            "probability_breach_after": bundle["probability_breach_after"], "risk_target": plan["risk_target"]}}
            approval = None
            for operator_id, pin, client in (("imran", "1357", accountant), ("nadia", "2468", owner)):
                approval = client.post("/api/plan/approve", {"plan_id": plan["plan_id"], "bundle_id": bundle["bundle_id"],
                                                           "pin": pin, "review_ms": 9000,
                                                           "confirm_amount_minor": bundle["exposure_minor"], **consent})
                approval_trace.append({"attempt": attempt + 1, "operator_id": operator_id, "status": approval["status"],
                                       "risk_acknowledged": bool(consent)})
                if approval["status"] == "mandate_issued":
                    break
            assert approval["status"] == "mandate_issued"
            mandate = approval["mandate"]
            assert len({entry["operator_id"] for entry in mandate["approvals"]}) >= (2 if bundle["dual_approval_required"] else 1)
            owner.post("/api/mandate/execute", {"mandate_id": mandate["mandate_id"], "idempotency_key": "no-exact-consent"}, expected=400)
            negotiation = owner.post("/api/mandate/negotiate", {"mandate_id": mandate["mandate_id"]})
            negotiation_trace.append({"attempt": attempt + 1, "status": negotiation["status"],
                                      "replies": [row["response"]["status"] for row in negotiation.get("replies", [])]})
            if negotiation["status"] == "ready":
                break
            route = "/api/mandate/counter" if negotiation["status"] == "countered" else "/api/mandate/replan"
            assert negotiation["status"] in ("countered", "rejected"), "Unexpected negotiation state"
            plan = owner.post(route, {"mandate_id": mandate["mandate_id"]})
        else:
            raise AssertionError("Counterparties did not agree within bounded attempts")
        receipt = owner.post("/api/mandate/execute", {"mandate_id": mandate["mandate_id"], "idempotency_key": REPLAY_KEY})
        replay = owner.post("/api/mandate/execute", {"mandate_id": mandate["mandate_id"], "idempotency_key": REPLAY_KEY})
        assert receipt["read_back"]["verified"] and replay["receipt_id"] == receipt["receipt_id"] and replay["replayed"]
        signature = owner.request("POST", "/api/mandate/verify", {"document": mandate})
        assert signature["signature_valid"]
        audit = owner.get("/api/audit")
        assert audit["hash_chain_valid"]
        STATE_FILE.write_text(json.dumps({"receipt_id": receipt["receipt_id"], "mandate_id": mandate["mandate_id"]}) + "\n", encoding="utf-8")
        checks.update({"ordinary_pin_approvals": True, "exact_consent_before_execution": True,
                       "execution_read_back": True, "same_receipt_on_replay": True, "mandate_signature_valid": True,
                       "audit_chain_valid": True})
        details = {"receipt_id": receipt["receipt_id"], "approval_trace": approval_trace, "negotiation_trace": negotiation_trace,
                   "audit_entries": len(audit["entries"]), "requests": anonymous.calls + owner.calls + accountant.calls + viewer.calls}
    else:
        expected = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        execution = owner.get("/api/execution", idempotency_key=REPLAY_KEY)
        assert execution["found"], "Persisted receipt was not found"
        receipt = execution["receipt"]
        assert receipt["receipt_id"] == expected["receipt_id"] and receipt["read_back"]["verified"]
        replay = owner.post("/api/mandate/execute", {"mandate_id": expected["mandate_id"], "idempotency_key": REPLAY_KEY})
        assert replay["receipt_id"] == expected["receipt_id"] and replay["replayed"]
        assert owner.get("/api/audit")["hash_chain_valid"]
        checks.update({"receipt_survives_recreated_container": True, "persistent_keys_validate_replay": True,
                       "persistent_audit_chain_valid": True})
        details = {"receipt_id": receipt["receipt_id"], "requests": anonymous.calls + owner.calls}
    keys = list(Path("/app/data").glob("*.key"))
    assert len(keys) >= 2 and all(path.stat().st_mode & 0o777 == 0o600 for path in keys)
    checks["private_signing_key_permissions"] = True
    return {"version": "container-http-smoke-v5", "phase": phase, "passed": all(checks.values()),
            "python": platform.python_version(), "uid": uid, "checks": checks, **details,
            "scope": "Actual HTTP inside an isolated Linux container; scripted synthetic demo approvals and counterparties; no live model, real user or real money."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("workflow", "persisted"), required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    print(json.dumps(run(args.phase, args.host, args.port), indent=2, allow_nan=False))
