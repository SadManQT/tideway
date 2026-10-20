"""Evaluate the Treasury hub on the synthetic demo businesses.

Writes evidence/treasury/treasury-report.json with, per business: the 13-week cash
flow summary and its reconciliation with the projection engine, the health score
and components, payment-integrity findings (ledger and labelled synthetic sample),
credit-passport verification outcomes (valid, tampered, wrong business, expired)
and timings. Uses an in-memory database: nothing is persisted.

    python scripts/evaluate_treasury.py
"""
from __future__ import annotations

import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tideway.domain import canonical_json  # noqa: E402
from tideway.service import Tideway  # noqa: E402
from tideway.treasury import HEALTH_WEIGHTS, Treasury  # noqa: E402

BUSINESSES = ("shapla-services", "lotus-print", "harbourline-traders")
REPEATS = 5
OWNER = {"id": "nadia", "name": "Nadia Rahman", "role": "owner"}


def timed(function, repeats=REPEATS):
    samples, result = [], None
    for _ in range(repeats):
        start = time.perf_counter()
        result = function()
        samples.append((time.perf_counter() - start) * 1000)
    return result, {"median_ms": round(statistics.median(samples), 2), "max_ms": round(max(samples), 2), "runs": repeats}


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def evaluate():
    tideway = Tideway(":memory:")
    treasury = Treasury(tideway)
    report = {"version": "treasury-evaluation-v1", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "source_commit": commit(), "working_tree_note": "Run on the working tree; uncommitted changes may be present.",
              "python": platform.python_version(), "platform": platform.platform(),
              "data": "Synthetic demo fixtures in an in-memory database. No real business, bank or lender data.",
              "health_weights": HEALTH_WEIGHTS, "businesses": []}
    for business_id in BUSINESSES:
        plan, plan_time = timed(lambda: treasury.twcf(business_id))
        score, health_time = timed(lambda: treasury.health(business_id))
        ledger_scan, scan_time = timed(lambda: treasury.scan(business_id, False))
        sample_scan, sample_time = timed(lambda: treasury.scan(business_id, True))
        deterministic = (digest(plan) == digest(treasury.twcf(business_id)) and digest(score) == digest(treasury.health(business_id))
                         and digest(sample_scan) == digest(treasury.scan(business_id, True)))
        issued, issue_time = timed(lambda: treasury.issue_passport(business_id, OWNER, "operator:nadia"), repeats=1)
        passport = json.loads(json.dumps(issued["passport"]))
        valid, verify_time = timed(lambda: treasury.verify_passport(business_id, passport))
        tampered = json.loads(json.dumps(passport))
        tampered["twcf"]["likely"]["closing_cash_minor"] += 5_000_000
        other = next(item for item in BUSINESSES if item != business_id)
        expired = treasury.verify_passport(business_id, passport, now=datetime.now(timezone.utc) + timedelta(days=31))
        sample = sample_scan["synthetic_sample"]
        report["businesses"].append({
            "business_id": business_id, "currency": plan["currency"], "as_of": plan["as_of"],
            "snapshot_hash": plan["snapshot_hash"],
            "twcf": {"start_date": plan["start_date"], "end_date": plan["end_date"],
                     "reserve_floor_minor": plan["reserve_floor_minor"],
                     "scenarios": {name: {**{key: value for key, value in data["totals"].items() if key != "receipts_by_customer"},
                                          "reconciliation": data["reconciliation"]}
                                   for name, data in plan["scenarios"].items()}},
            "health": {"score": score["score"], "band": score["band"],
                       "components": [{key: item[key] for key in ("id", "value", "score", "weight", "points")}
                                      for item in score["components"]],
                       "suggestions": [{"component": item["component"], "max_gain_points": item["max_gain_points"]}
                                       for item in score["suggestions"]],
                       "simulation_runs": score["simulation"]["runs"], "simulation_seed": score["simulation"]["seed"]},
            "scan": {"bills_scanned": ledger_scan["bills_scanned"], "threshold_minor": ledger_scan["threshold_minor"],
                     "ledger_findings": [{key: item[key] for key in ("finding_id", "rule", "severity", "bill_ids")}
                                         for item in ledger_scan["ledger_findings"]],
                     "synthetic_sample": {key: sample[key] for key in ("bills", "planted_anomalies", "clean_bills", "true_positives",
                                                                       "false_positives", "false_negatives", "precision", "recall",
                                                                       "clean_bills_flagged")},
                     "synthetic_labels": [{key: item[key] for key in ("rule", "bill_ids", "detected")} for item in sample["labels"]]},
            "passport": {"fields": sorted(passport), "health_score": passport["health"]["score"],
                         "expires_at_minus_issued_days": (datetime.fromisoformat(passport["expires_at"])
                                                          - datetime.fromisoformat(passport["issued_at"])).days,
                         "verify_original": {"valid": valid["valid"], "reason": valid["reason"],
                                             "issuance_logged": valid.get("issuance_logged")},
                         "verify_tampered_closing_cash": {key: value for key, value in treasury.verify_passport(business_id, tampered).items()
                                                          if key in ("valid", "reason")},
                         "verify_wrong_business": {key: value for key, value in treasury.verify_passport(other, passport).items()
                                                   if key in ("valid", "reason")},
                         "verify_after_expiry": {key: expired[key] for key in ("valid", "reason")},
                         "verify_as_mandate": tideway.store.verify_mandate_document(passport)["signature_valid"]},
            "deterministic_repeat": deterministic,
            "timings": {"twcf": plan_time, "health_with_1000_run_monte_carlo": health_time, "scan_ledger": scan_time,
                        "scan_with_synthetic_sample": sample_time, "passport_issue": issue_time, "passport_verify": verify_time},
        })
    tideway.store.close()
    rows = report["businesses"]
    report["summary"] = {
        "businesses": len(rows),
        "all_reconcile": all(item["twcf"]["scenarios"][name]["reconciliation"]["matches"] for item in rows for name in item["twcf"]["scenarios"]),
        "all_deterministic": all(item["deterministic_repeat"] for item in rows),
        "health_scores": {item["business_id"]: item["health"]["score"] for item in rows},
        "ledger_findings": {item["business_id"]: len(item["scan"]["ledger_findings"]) for item in rows},
        "synthetic_recall": {item["business_id"]: item["scan"]["synthetic_sample"]["recall"] for item in rows},
        "synthetic_precision": {item["business_id"]: item["scan"]["synthetic_sample"]["precision"] for item in rows},
        "passport_checks_passed": all(item["passport"]["verify_original"]["valid"]
                                      and item["passport"]["verify_tampered_closing_cash"]["reason"] == "signature_mismatch"
                                      and item["passport"]["verify_wrong_business"]["reason"] == "wrong_business"
                                      and item["passport"]["verify_after_expiry"]["reason"] == "expired"
                                      and not item["passport"]["verify_as_mandate"] for item in rows),
        "caveat": "Synthetic fixtures and a synthetic labelled sample written alongside the rules: these results check "
                  "implementation behaviour, not real-world accuracy.",
    }
    return report


def main():
    report = evaluate()
    folder = ROOT / "evidence" / "treasury"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "treasury-report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    print(f"Wrote {path.relative_to(ROOT)}")
    return 0 if report["summary"]["all_reconcile"] and report["summary"]["passport_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
