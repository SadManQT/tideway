"""Record one actual-model regression on disclosed cases; never call it blind."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_blind_readiness import fixture, model_report, utc_now, write_new
from scripts.verify_submission import source_digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("evidence/independent-audit/model-regression"))
    args = parser.parse_args()
    directory = args.out.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        parser.error("Use a new empty output directory; earlier observations must be preserved.")
    digest, files = source_digest()
    history = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
        "evidence/readiness-v3/blind/model-first-observation.json",
        "evidence/readiness-v3/blind/screening-first-observation.json")}
    start = {"schema_version": "tideway-independent-audit-known-case-regression-v1",
             "started_at_utc": utc_now(), "source_tree_sha256": digest, "source_files": files,
             "historical_first_observation_sha256": history,
             "methodology": "All 32 previously disclosed challenge cases; one pass, no selective retry. Not blind or population accuracy."}
    write_new(directory / "started.json", start)
    result = model_report(fixture(), directory / "progress.jsonl")
    result["limitations"] = [
        "Previously observed synthetic cases; this is a regression run, not an unseen quality estimate.",
        "Compatible Qwen inference does not verify the TideLM MLX adapter, receipt model or cloud provider.",
        "Payment containment and request correctness have separate denominators; safe stops do not prove understanding.",
        "Every attempt and miss is retained; no selective retry was performed in this run."]
    unchanged = source_digest()[0] == digest
    history_unchanged = all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha for name, sha in history.items())
    report = {**start, **result, "completed_at_utc": utc_now(), "source_unchanged_at_end": unchanged,
              "historical_first_observations_unchanged": history_unchanged}
    write_new(directory / "report.json", report)
    print(json.dumps({"report": str(directory / "report.json"), "outcome": report["outcome"],
                      "matched": report.get("matched"), "containment": report.get("containment"),
                      "source_unchanged": unchanged, "history_unchanged": history_unchanged}), flush=True)
    return 0 if (unchanged and history_unchanged and report.get("real_model_inference")
                 and report["matched"]["numerator"] == report["requests"]
                 and report["containment"]["numerator"] == report["requests"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
