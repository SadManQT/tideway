"""Write deterministic, sanitized evidence for the five contest security cases.

The evaluator uses only fresh in-memory synthetic fixtures and the repository's
actual membership, Inbox, screening, mandate, execution and delay boundaries.
It never contacts a model provider, bank, payment rail or external service.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from scripts.verify_submission import base_commit, source_digest  # noqa: E402
from test_contest_security import CASE_IDS, run_all_cases  # noqa: E402


NOTE = ("Automated synthetic boundary evidence only: these records use fresh in-memory fictional "
        "fixtures and do not constitute human, external, penetration, real-model or production security validation.")


def main():
    digest, _files = source_digest()
    cases = run_all_cases()
    passed = len(cases) == len(CASE_IDS) and all(item["status"] == "PASS" for item in cases)
    report = {
        "schema_version": "contest-security-v1",
        "source_digest": digest,
        "source_commit": base_commit(),
        "status": "PASS" if passed else "FAIL",
        "case_count": len(cases),
        "cases": cases,
        "automated_synthetic_boundary_evidence": True,
        "human_or_external_security_validation": False,
        "note": NOTE,
    }
    output = ROOT / "evidence" / "contest-security.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": output.relative_to(ROOT).as_posix(), "status": report["status"],
                      "cases": [{"id": item["id"], "status": item["status"]} for item in cases]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
