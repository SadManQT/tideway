"""Record bounded decision-support checks on disclosed synthetic demo ledgers."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tideway import replay
from tideway.server import Application
from scripts.verify_submission import source_digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="evidence/upgrade-v11/decision-lab.json")
    args = parser.parse_args()
    before, _ = source_digest()
    app = Application(":memory:")
    results = []
    try:
        for business in app.store.list_businesses():
            bid = business["id"]
            snapshot = app.store.snapshot(bid)["snapshot_hash"]
            start = time.perf_counter()
            reports = {kind: app.lab.analyze(bid, None, kind) for kind in ("reverse", "promises", "frontier")}
            capsule = replay.export_capsule(app.lab.context(bid))
            verified = replay.replay_capsule(capsule)
            witness_ok = all(r.get("one_day_less") is None or not r["one_day_less"]["reserve_shortfall_minor"]
                             and not r["one_day_less"]["payroll_at_risk"] for r in reports["reverse"]["rows"])
            checks = {"replay_matches": verified["passed"], "breakpoint_witnesses_hold": witness_ok,
                      "complete_customer_coverage": reports["reverse"]["complete_customer_coverage"],
                      "ledger_unchanged": app.store.snapshot(bid)["snapshot_hash"] == snapshot,
                      "no_saved_proposals": app.store.latest_plan(bid, business["default_target_date"]) is None,
                      "fresh_funding_draws": all(r["selection_seed"] != r["validation_seed"] and not r["funding_confirmed"] for r in reports["frontier"]["rows"])}
            results.append({"business_id": bid, "currency": business["currency"], "snapshot_hash": snapshot,
                            "checks": checks, "elapsed_ms": round((time.perf_counter()-start)*1000),
                            "analyses": reports, "replay": verified})
        after, _ = source_digest()
        report = {"version": "decision-lab-evaluation-v1", "run_at_utc": datetime.now(timezone.utc).isoformat(),
                  "source_tree_sha256": before, "source_unchanged": before == after,
                  "passed": before == after and all(all(r["checks"].values()) for r in results),
                  "synthetic_businesses": len(results), "checks": sum(len(r["checks"]) for r in results), "results": results,
                  "scope": "Known synthetic engineering checks, not a user study, calibrated prediction accuracy, external review or live-model benchmark."}
        out = ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes((json.dumps(report, indent=2, ensure_ascii=False)+"\n").encode("utf-8"))
        print(json.dumps({"passed": report["passed"], "businesses": len(results), "checks": report["checks"], "report": str(out)}))
        return 0 if report["passed"] else 1
    finally:
        app.store.close()


if __name__ == "__main__":
    raise SystemExit(main())
