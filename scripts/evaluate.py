"""Run the Tideway self-test suite and write reproducible evidence files.

Writes evidence/results.csv, evidence/run-log.jsonl and evidence/verification-summary.json.
Synthetic sandbox only: this evidences the listed cases, not live-model or user-study results.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tideway import selftest  # noqa: E402

OUT = ROOT / "evidence"


def main():
    report = selftest.run()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUT.mkdir(exist_ok=True)
    columns = ["case_id", "category", "owasp", "title", "passed", "elapsed_ms", "observed"]
    with (OUT / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["results"])
    with (OUT / "run-log.jsonl").open("w", encoding="utf-8") as handle:
        for item in report["results"]:
            handle.write(json.dumps({"run_at": stamp, "fixture": "tideway-synthetic", "live_ai": False, **item}, sort_keys=True) + "\n")
    summary = {"project": "Tideway", "track": "FinTechathon 2026 International, Topic E", "run_at": stamp,
               **report["summary"], "live_model_tested": False,
               "live_model_reason": "The suite uses simulated model transports; no provider key is used.",
               "fixture": "Synthetic sandbox (Shapla Services, Lotus Print, Harbourline Traders)"}
    (OUT / "verification-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"{summary['passed']}/{summary['cases']} cases passed -> evidence/")
    sys.exit(0 if summary["passed"] == summary["cases"] else 1)


if __name__ == "__main__":
    main()
