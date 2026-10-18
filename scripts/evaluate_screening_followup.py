"""Record a once-only local-model screening run on a disclosed or sealed sample.

No downloads, external evaluators, human participants or population claims.
Baseline/revised comparisons must use the same runtime and fixture hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_screening_v6 import case_record
from scripts.evaluate_screening_v7 import score_records
from scripts.verify_submission import source_digest


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--kind", choices=("disclosed-development", "source-aware-challenge"), required=True)
    parser.add_argument("--seal", type=Path)
    args = parser.parse_args()
    fixture = args.fixture.resolve()
    value = json.loads(fixture.read_text(encoding="utf-8"))
    seal = json.loads(args.seal.read_text(encoding="utf-8")) if args.seal else None
    if args.kind == "source-aware-challenge" and (not seal or seal.get("fixture_sha256") != sha(fixture)):
        raise ValueError("A matching pre-observation challenge seal is required.")
    cases = value["cases"]
    if not cases or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Cases must have unique IDs.")
    for case in cases:
        if (case["label"] not in ("malicious", "benign")
                or case["review_signal"] not in ("none", "payment_details")
                or not isinstance(case["text"], str) or not 0 < len(case["text"]) <= 2000):
            raise ValueError("Invalid labelled case.")
    from tideway.tidelm import TideLM
    client = TideLM()
    identity = client.status()
    if not identity.get("available"):
        raise RuntimeError("An actual configured local model is required.")
    files = [ROOT / "tideway" / n for n in ("screening.py", "semantic_screening.py", "tidelm.py")]
    frozen = {str(p.relative_to(ROOT)): sha(p) for p in files}
    metadata = {"kind": args.kind, "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "fixture_sha256": sha(fixture), "fixture": str(fixture.relative_to(ROOT)),
                "classifier_files": frozen, "source_tree_sha256": source_digest()[0],
                "model_identity": identity, "external_evaluation": False,
                "human_participants": 0, "challenge_seal": seal,
                "author_scope": value.get("author_scope", "Previously disclosed AI-authored sample."),
                "limitations": ["Synthetic convenience sample; no population accuracy claim.",
                                "Windows compatible GGUF runtime; not native MLX or adapter verification.",
                                "Warnings cannot authorize financial or ledger actions."]}
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "started.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    rows = []
    with (args.out / "case-results.jsonl").open("x", encoding="utf-8") as handle:
        for case in cases:
            row = case_record(case, client, None, runtime_status=identity)
            rows.append(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"{args.out.name}: {len(rows)}/{len(cases)}", flush=True)
    unchanged = frozen == {str(p.relative_to(ROOT)): sha(p) for p in files}
    fixture_unchanged = sha(fixture) == metadata["fixture_sha256"]
    metrics = score_records(rows)
    report = {**metadata, "cases": len(rows), "metrics": metrics,
              "classifier_unchanged": unchanged, "fixture_unchanged": fixture_unchanged,
              "source_unchanged": source_digest()[0] == metadata["source_tree_sha256"],
              "case_results_sha256": sha(args.out / "case-results.jsonl"),
              "finished_at_utc": datetime.now(timezone.utc).isoformat()}
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: metrics[k] for k in ("semantic_attack", "combined_attack", "combined_warning", "latency_ms")}, indent=2))
    return 0 if unchanged and fixture_unchanged and not metrics["pipeline_exception_cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
