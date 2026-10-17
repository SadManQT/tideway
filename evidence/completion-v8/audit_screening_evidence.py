"""Recompute retained screening evidence; performs no inference or model downloads."""
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_screening_v7 import score_records
from scripts.verify_submission import source_digest


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def audit(folder, report_name, fixture, historical_v6=False):
    folder = ROOT / folder
    report = read(folder / report_name)
    rows = [json.loads(line) for line in (folder / "case-results.jsonl").read_text(encoding="utf-8").splitlines()]
    metrics = score_records(rows)
    checks = {
        "case_results_hash_matches": sha(folder / "case-results.jsonl") == report["case_results_sha256"],
        "fixture_hash_matches": sha(ROOT / fixture) == report["fixture_sha256"],
        "case_count_matches": len(rows) == report.get("completed_case_count", report.get("cases")),
    }
    for task in ("pure_rules_attack", "semantic_attack", "combined_warning"):
        checks[task + "_counts_match"] = all(metrics[task][key] == report["metrics"][task][key]
                                                for key in ("tp", "fp", "fn", "tn"))
    raw_checks = []
    for row in rows:
        attempt = row.get("model_attempt") or {}
        raw = attempt.get("raw_output")
        if raw is not None and not attempt.get("raw_output_truncated"):
            raw_checks.append(hashlib.sha256(raw.encode("utf-8")).hexdigest() == attempt.get("raw_output_sha256"))
    checks["all_retained_complete_raw_output_hashes_match"] = all(raw_checks)
    current_classifier = None
    if historical_v6:
        seal = ROOT / "evidence/screening-v6/execution-source-seal.json"
        source = read(seal)
        checks["execution_source_seal_hash_matches"] = sha(seal) == report["execution_source_seal_sha256"]
        checks["model_artifact_records_match_seal"] = source["model_runtime_artifacts"] == report["model_runtime_artifacts"]
        checks["author_seal_hash_matches"] = sha(ROOT / "evidence/screening-v6/holdout-author-seal.json") == report["author_seal_sha256"]
        identity = {"served_model": report["evaluation_configuration"]["served_model_id"],
                    "artifacts": report["model_runtime_artifacts"]}
        source_record = source["implementation_files"]
    else:
        source_record = report["classifier_files"]
        current_classifier = all(sha(ROOT / name) == value for name, value in source_record.items())
        identity = report["model_identity"]
        if report.get("phase") == "fresh":
            seal = read(ROOT / "evidence/screening-v7/holdout-author-seal.json")
            checks["author_fixture_seal_matches"] = seal.get("fixture_sha256", seal.get("sha256")) == report["fixture_sha256"]
    return {
        "path": str(folder.relative_to(ROOT)), "checks": checks, "passed": all(checks.values()),
        "cases": len(rows), "complete_raw_outputs_rehashed": len(raw_checks),
        "model_identity_recorded": identity, "source_hashes_recorded": source_record,
        "classifier_matches_current_bytes": current_classifier, "recomputed_metrics": metrics,
        "inference_rerun": False,
        "limits": "Recomputed retained outputs only. Absent model/runtime files cannot be independently rehashed or attest loaded weights. Development and previously observed fresh sets are disclosed regression data."
    }


def main():
    runs = [audit("evidence/screening-v6/first-pass", "first-pass-results.json",
                  "tests/fixtures/screening_holdout_v6.json", True)]
    for phase in ("baseline-base-development", "improved-base-development-r3", "fresh"):
        fixture = "screening_holdout_v7.json" if phase == "fresh" else "screening_holdout_v6.json"
        runs.append(audit("evidence/screening-v7/" + phase, "report.json", "tests/fixtures/" + fixture))
    status = {"mlx_installed": importlib.util.find_spec("mlx") is not None,
              "historical_windows_model_file_available": Path("E:/Tideway-model-cache/Qwen3-4B-Instruct-2507-Q4_K_M.gguf").is_file(),
              "model_downloaded": False, "actual_inference_performed": False}
    result = {"audited_at_utc": datetime.now(timezone.utc).isoformat(),
              "current_source_tree_sha256": source_digest()[0], "passed": all(row["passed"] for row in runs),
              "current_inference_status": status, "runs": runs}
    (Path(__file__).parent / "screening-evidence-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "runs": [{"path": row["path"], "checks": row["checks"]} for row in runs]}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
