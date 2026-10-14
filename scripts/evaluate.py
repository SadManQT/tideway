"""Run a reproducible deterministic Topic E evaluation matrix.

This produces local sandbox evidence only. It does not test a live model or
claim user-study results. Every case uses a fresh temporary SQLite database.
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from finmate.agent import Agent
from finmate.finance import ValidationError, project_cash
from finmate.server import Application


TARGET = "2026-10-31"
BUSINESS = "shapla-services"


def new_app(folder):
    return Application(Path(folder) / "evaluation.sqlite3", seed=True)


def compare(app, business=BUSINESS):
    return app.post("/api/plan/compare", {"business_id": business, "target_date": TARGET})


def approve(app, plan, action_id):
    return app.post("/api/plan/approve", {"business_id": BUSINESS, "plan_id": plan["plan_id"], "action_id": action_id})


def consent(app, plan, action_id, accepted=True):
    return app.post("/api/sandbox/consent", {"business_id": BUSINESS, "plan_id": plan["plan_id"], "action_id": action_id, "accepted": accepted})


def expect_rejection(callback):
    try:
        callback()
    except ValidationError:
        return True
    return False


def cases():
    def base_gap(app):
        projection = app.dashboard(BUSINESS, TARGET)["projection"]["base"]
        assert projection["closing_cash_minor"] == -1_000_000
        assert projection["reserve_shortfall_minor"] == 3_000_000
        assert projection["minimum_reserve_shortfall_minor"] == 3_000_000

    def late_collection(app):
        dashboard = app.dashboard(BUSINESS, TARGET)
        assert dashboard["projection"]["late_collection"]["closing_cash_minor"] < dashboard["projection"]["base"]["closing_cash_minor"]

    def recovery_option(app):
        plan = compare(app)
        action = next(item for item in plan["plans"] if item["action_id"] == "supplier-reschedule")
        assert action["amount_minor"] == 4_000_000 and action["feasible"]
        assert action["projected_closing_cash_minor"] == 3_000_000

    def supplier_consent_gate(app):
        plan = compare(app)
        approval = approve(app, plan, "supplier-reschedule")
        assert expect_rejection(lambda: app.post("/api/plan/execute", {"business_id": BUSINESS, "approval_id": approval["approval_id"], "idempotency_key": "no-consent"}))

    def supplier_rejection_gate(app):
        plan = compare(app)
        approval = approve(app, plan, "supplier-reschedule")
        consent(app, plan, "supplier-reschedule", False)
        assert expect_rejection(lambda: app.post("/api/plan/execute", {"business_id": BUSINESS, "approval_id": approval["approval_id"], "idempotency_key": "rejected-consent"}))

    def execute_and_read_back(app):
        plan = compare(app)
        approval = approve(app, plan, "supplier-reschedule")
        consent(app, plan, "supplier-reschedule", True)
        receipt = app.post("/api/plan/execute", {"business_id": BUSINESS, "approval_id": approval["approval_id"], "idempotency_key": "execute-read-back"})
        assert receipt["status"] == "executed" and receipt["read_back"]["verified"]
        assert receipt["state_before"]["version"] + 1 == receipt["state_after"]["version"]

    def idempotent_retry(app):
        plan = compare(app)
        approval = approve(app, plan, "supplier-reschedule")
        consent(app, plan, "supplier-reschedule", True)
        first = app.post("/api/plan/execute", {"business_id": BUSINESS, "approval_id": approval["approval_id"], "idempotency_key": "exact-retry"})
        second = app.post("/api/plan/execute", {"business_id": BUSINESS, "approval_id": approval["approval_id"], "idempotency_key": "exact-retry"})
        assert first == second and len(app.store.executions(BUSINESS)) == 1

    def reminder_zero_cash(app):
        plan = compare(app)
        approval = approve(app, plan, "collection-reminder")
        receipt = app.post("/api/plan/execute", {"business_id": BUSINESS, "approval_id": approval["approval_id"], "idempotency_key": "reminder-zero-cash"})
        assert receipt["cash_effect_minor"] == 0
        assert receipt["state_before"]["cash_minor"] == receipt["state_after"]["cash_minor"]

    def changed_payee(app):
        plan = compare(app)
        approval = approve(app, plan, "supplier-reschedule")
        consent(app, plan, "supplier-reschedule", True)
        with app.store.connect() as db:
            db.execute("UPDATE bills SET payee='Attacker Payee' WHERE business_id=? AND id=?", (BUSINESS, "bill-supplier-001"))
        assert expect_rejection(lambda: app.post("/api/plan/execute", {"business_id": BUSINESS, "approval_id": approval["approval_id"], "idempotency_key": "changed-payee"}))

    def expired_approval(app):
        plan = compare(app)
        approval = approve(app, plan, "supplier-reschedule")
        consent(app, plan, "supplier-reschedule", True)
        with app.store.connect() as db:
            db.execute("UPDATE approvals SET expiry='2000-01-01T00:00:00+00:00' WHERE id=?", (approval["approval_id"],))
        assert expect_rejection(lambda: app.post("/api/plan/execute", {"business_id": BUSINESS, "approval_id": approval["approval_id"], "idempotency_key": "expired"}))

    def policy_limit(app):
        app.store.set_policy(BUSINESS, {"reserve_floor_minor": 2_000_000, "action_limit_minor": 1_000, "currency": "BDT", "payroll_priority": True})
        plan = compare(app)
        action = next(item for item in plan["plans"] if item["action_id"] == "supplier-reschedule")
        assert not action["feasible"] and not action["executable"]

    def other_business_scope(app):
        csv_text = "record_type,business_id,id,date,description,amount,type,currency\ntransaction,meghna-traders,cross-tenant,2026-10-05,Wrong tenant,100,income,BDT\n"
        assert expect_rejection(lambda: app.post("/api/import", {"business_id": BUSINESS, "csv": csv_text, "replace_demo": False}))

    def atomic_bad_import(app):
        before = app.store.records(BUSINESS)
        csv_text = ("record_type,business_id,id,date,description,amount,type,currency,due_date,status\n"
                     "transaction,shapla-services,atomic-good,2026-10-05,Good,100,income,BDT,,,\n"
                     "bill,shapla-services,atomic-bad,,Bad,100,expense,USD,2026-10-31,open\n")
        assert expect_rejection(lambda: app.post("/api/import", {"business_id": BUSINESS, "csv": csv_text, "replace_demo": False}))
        assert app.store.records(BUSINESS) == before

    def settled_invoice_not_double_counted(app):
        projection = project_cash(opening_cash_minor=100_000, opening_date="2026-10-01", target_date=TARGET,
                                  transactions=[], invoices=[{"id": "settled", "business_id": BUSINESS, "issue_date": "2026-10-01", "due_date": "2026-10-10", "expected_collection_date": "2026-10-10", "status": "collected", "amount_minor": 90_000, "currency": "BDT"}], bills=[],
                                  policy={"business_id": BUSINESS, "currency": "BDT", "reserve_floor_minor": 0, "action_limit_minor": 100_000, "payroll_priority": True}, business_id=BUSINESS)
        assert projection["closing_cash_minor"] == 100_000 and projection["total_inflow_minor"] == 0

    def projection_horizon(app):
        assert expect_rejection(lambda: project_cash(opening_cash_minor=100, opening_date="2026-01-01", target_date="2027-01-03", transactions=[], invoices=[], bills=[], policy={"currency": "BDT", "reserve_floor_minor": 0, "action_limit_minor": 100, "payroll_priority": True}))

    def reset_preserves_records(app):
        count = sum(len(values) for values in app.store.records(BUSINESS).values())
        app.store.reset_sandbox(BUSINESS)
        assert sum(len(values) for values in app.store.records(BUSINESS).values()) == count

    def evidence_chain(app):
        compare(app)
        evidence = app.store.evidence(BUSINESS)
        assert evidence["hash_chain_valid"] and evidence["self_verifiable"] and evidence["hash_chain_scope"] == BUSINESS

    def scoped_agent(app):
        calls = []

        def fake(payload, key):
            calls.append(payload)
            if len(calls) == 1:
                return {"output": [{"type": "function_call", "name": "read_ledger", "arguments": json.dumps({"business_id": "meghna-traders", "target_date": TARGET}), "call_id": "cross"}]}
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "The scoped request was rejected."}]}]}

        result = Agent(app.store, "synthetic-key", transport=fake).chat("Read", business_id=BUSINESS, target_date=TARGET, external_consent=True)
        assert result["mode"] == "openai" and any(event["action"] == "agent.tool_rejected" for event in app.store.evidence(BUSINESS)["entries"])

    return [
        ("base-gap", "calculation", base_gap),
        ("late-collection", "scenario", late_collection),
        ("recovery-option", "planning", recovery_option),
        ("supplier-consent-gate", "security", supplier_consent_gate),
        ("supplier-rejection-gate", "security", supplier_rejection_gate),
        ("execute-read-back", "execution", execute_and_read_back),
        ("idempotent-retry", "replay", idempotent_retry),
        ("reminder-zero-cash", "safety", reminder_zero_cash),
        ("changed-payee", "security", changed_payee),
        ("expired-approval", "security", expired_approval),
        ("policy-limit", "policy", policy_limit),
        ("other-business-scope", "isolation", other_business_scope),
        ("atomic-bad-import", "import", atomic_bad_import),
        ("settled-invoice", "calculation", settled_invoice_not_double_counted),
        ("projection-horizon", "validation", projection_horizon),
        ("reset-preserves-records", "recovery", reset_preserves_records),
        ("audit-chain", "evidence", evidence_chain),
        ("scoped-agent", "agent", scoped_agent),
    ]


def main():
    results = []
    logs = []
    for case_id, category, callback in cases():
        started = time.perf_counter()
        passed = False
        error = ""
        with tempfile.TemporaryDirectory() as folder:
            try:
                callback(new_app(folder))
                passed = True
            except Exception as exc:  # evidence records failures instead of hiding them
                error = f"{type(exc).__name__}: {exc}"
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        result = {"case_id": case_id, "category": category, "passed": passed, "elapsed_ms": elapsed, "live_ai": False, "error": error}
        results.append(result)
        logs.append({"run_id": f"det-{case_id}", "fixture_id": "probaho-synthetic-v3", "business_id": BUSINESS, "target_date": TARGET, **result})
    evidence_dir = ROOT / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    with (evidence_dir / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "category", "passed", "elapsed_ms", "live_ai", "error"])
        writer.writeheader()
        writer.writerows(results)
    with (evidence_dir / "run-log.jsonl").open("w", encoding="utf-8") as handle:
        for entry in logs:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    passed = sum(1 for item in results if item["passed"])
    print(f"Probaho deterministic evaluation: {passed}/{len(results)} passed; live_ai=False")
    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
