"""Rehearse the linked payment-delay demo on a fresh synthetic database.

Uses Application.post (the validated API workflow), ordinary PIN approvals and
simulated counterparty responses. Never force acceptance or change policy.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tideway.server import Application
from tideway.domain import ValidationError

BUSINESS = "shapla-services"
TARGET = "2026-10-31"


def rehearse(db=":memory:"):
    app = Application(db)
    calls = []
    def post(path, body, who="nadia"):
        pin = {"nadia": "2468", "imran": "1357"}[who]
        operator = app.store.verify_pin(who, pin)
        result = app.post(path, {"business_id": BUSINESS, **body}, operator, None)
        calls.append({"path": path, "operator": who})
        return result
    def approve(plan):
        bundle = next(b for b in plan["bundles"] if b["feasible"])
        assert bundle["feasible"], "No safe recommendation: the demo cannot execute."
        result = None
        for who, pin in (("imran", "1357"), ("nadia", "2468")):
            result = post("/api/plan/approve", {"plan_id": plan["plan_id"], "bundle_id": bundle["bundle_id"],
                          "pin": pin, "confirm_amount_minor": bundle["exposure_minor"], "review_ms": 9000}, who)
            if result["status"] == "mandate_issued":
                return result["mandate"]
        raise AssertionError("Ordinary approvals did not issue a mandate")
    try:
        old_plan = post("/api/plan/propose", {"target_date": TARGET})
        old_mandate = approve(old_plan)
        snapshot = app.store.snapshot(BUSINESS)
        request = {"invoice_id": "inv-shapla-bay-oct", "collection_date": "2026-11-15",
                   "expected_snapshot": snapshot["snapshot_hash"], "request_id": "linked-delay-v1", "pin": "2468", "target_date": TARGET}
        changed = post("/api/demo/payment-delay", request)
        retried = post("/api/demo/payment-delay", request)
        assert retried["replayed"] and retried["after_snapshot"] == changed["after_snapshot"]
        stale_blocked = False
        try:
            post("/api/mandate/execute", {"mandate_id": old_mandate["mandate_id"], "idempotency_key": "stale-delay-v1"})
        except ValidationError as exc:
            stale_blocked = True
            stale_error = str(exc)
        assert stale_blocked, "Stale mandate executed"
        fresh = post("/api/plan/propose", {"target_date": TARGET})
        final_plan = fresh
        for attempt in range(4):
            mandate = approve(final_plan)
            negotiated = post("/api/mandate/negotiate", {"mandate_id": mandate["mandate_id"]})
            view = app.store.mandate(BUSINESS, mandate["mandate_id"])
            if view["status"] == "ready":
                break
            endpoint = "/api/mandate/counter" if view["status"] == "countered" else "/api/mandate/replan"
            final_plan = post(endpoint, {"mandate_id": mandate["mandate_id"]})
        else:
            raise AssertionError("Counterparties did not agree after bounded re-planning")
        receipt = post("/api/mandate/execute", {"mandate_id": mandate["mandate_id"], "idempotency_key": "fresh-delay-v1"})
        replay = post("/api/mandate/execute", {"mandate_id": mandate["mandate_id"], "idempotency_key": "fresh-delay-v1"})
        assert replay["receipt_id"] == receipt["receipt_id"]
        assert receipt["read_back"]["verified"]
        evidence = app.store.evidence(BUSINESS)
        assert evidence["hash_chain_valid"]
        actions = lambda p: [{k: a.get(k) for k in ("type", "record_id", "counterparty", "amount_minor", "discount_bps", "to_date")}
                             for a in p["bundles"][0]["actions"]]
        result = {"version": "linked-delay-v1", "passed": True, "python": platform.python_version(),
                  "machine": platform.platform(), "source": "Application.post with normal PIN/dual approval; no model inference",
                  "change": changed, "old_actions": actions(old_plan), "fresh_actions": actions(fresh),
                  "final_actions": actions(final_plan), "stale_execution_blocked": stale_blocked, "stale_error": stale_error,
                  "delay_retry_replayed": retried["replayed"], "execution_retry_same_receipt": True,
                  "read_back_verified": receipt["read_back"]["verified"], "receipt": receipt,
                  "audit_valid": evidence["hash_chain_valid"], "audit_entries": len(evidence["entries"]), "workflow": calls}
        return result
    finally:
        app.store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=":memory:", help="New database only; existing paths are refused")
    parser.add_argument("--out", default="evidence/upgrade-v1/payment-delay.json")
    args = parser.parse_args()
    if args.db != ":memory:" and Path(args.db).exists():
        parser.error("Choose a new database path; existing data/evidence is never reset or deleted.")
    report = rehearse(args.db)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Linked delay passed: stale execution blocked, fresh execution/read-back verified -> {out}")
    print("Changed actions:", report["old_actions"] != report["fresh_actions"])


if __name__ == "__main__":
    main()
