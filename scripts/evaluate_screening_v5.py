"""One-shot evaluator for the sealed, independently authored synthetic v5 holdout.

Run only after implementation is frozen::

    python scripts/evaluate_screening_v5.py --seal-execution-source
    python scripts/evaluate_screening_v5.py --evaluate

The first command hashes the execution source without importing the scanner. The
second verifies both seals, writes a durable start record before importing the
scanner, and records every case. Existing start/results/partial-output artifacts
block a retry; neither command has an overwrite option. A failed or interrupted
first pass remains evidence and must not be silently rerun as a new first pass.

The result describes this synthetic set only. It is not an external evaluation
or a population performance estimate. This file contains no holdout examples.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_REL = Path("tests/fixtures/screening_holdout_v5.json")
EVIDENCE_REL = Path("evidence/screening-v5")
AUTHOR_SEAL_NAME = "holdout-author-seal.json"
SOURCE_SEAL_NAME = "execution-source-seal.json"
START_NAME = "evaluation-started.json"
RESULT_NAME = "first-pass-results.json"
CASE_NAME = "case-results.jsonl"
RUN_DIR_NAME = "first-pass"

# Names-only interface contract supplied by the implementation owner. These are
# not inferred from case labels, scanner source, or observed scanner outputs.
ATTACK_FLAGS = frozenset({
    "instruction_override", "control_bypass", "forged_authority",
    "payment_redirect", "data_exfiltration", "concealed_action",
    "audit_tampering", "action_command", "hidden_markup", "role_marker",
    "external_link", "encoded_instruction",
})
GENERIC_REVIEW_FLAGS = frozenset({"hidden_characters"})
PAYMENT_REVIEW_FLAGS = frozenset({"payment_detail_change"})
KNOWN_FLAGS = ATTACK_FLAGS | GENERIC_REVIEW_FLAGS | PAYMENT_REVIEW_FLAGS


class EvidenceError(RuntimeError):
    """The immutable evidence protocol cannot safely continue."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_new_json(path: Path, value: Any) -> None:
    """Exclusive creation and fsync: never replace an evidence artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def contract() -> dict[str, Any]:
    return {
        "attack_flags": sorted(ATTACK_FLAGS),
        "generic_review_flags": sorted(GENERIC_REVIEW_FLAGS),
        "payment_review_flags": sorted(PAYMENT_REVIEW_FLAGS),
        "unknown_flag_policy": "preserve_and_report_without_inferring_attack_intent",
        "payment_review_is_attack": False,
        "generic_review_is_attack": False,
        "record_content_is_execution_permission": False,
    }


def evidence_paths(root: Path) -> dict[str, Path]:
    base = root / EVIDENCE_REL
    run = base / RUN_DIR_NAME
    return {
        "base": base,
        "fixture": root / FIXTURE_REL,
        "author": base / AUTHOR_SEAL_NAME,
        "source": base / SOURCE_SEAL_NAME,
        "start": base / START_NAME,
        "run": run,
        "result": run / RESULT_NAME,
        "cases": run / CASE_NAME,
    }


def assert_unstarted(paths: dict[str, Path]) -> None:
    blockers = [paths[name] for name in ("start", "result", "cases", "run")
                if paths[name].exists()]
    # Also recognize legacy/root-level result paths, so moving a result out of
    # the run folder cannot accidentally enable another first-pass invocation.
    for name in (RESULT_NAME, CASE_NAME):
        candidate = paths["base"] / name
        if candidate.exists():
            blockers.append(candidate)
    if blockers:
        rendered = ", ".join(str(path) for path in blockers)
        raise EvidenceError(f"First pass already started or has output; refusing overwrite/retry: {rendered}")


def case_counts(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(cases),
        "by_label": dict(sorted(Counter(case["label"] for case in cases).items())),
        "by_language": dict(sorted(Counter(case["language"] for case in cases).items())),
        "by_category": dict(sorted(Counter(case["category"] for case in cases).items())),
        "by_review_signal": dict(sorted(Counter(case["review_signal"] for case in cases).items())),
        "by_language_label": {
            language: dict(sorted(Counter(case["label"] for case in cases
                                          if case["language"] == language).items()))
            for language in sorted({case["language"] for case in cases})
        },
    }


def verified_fixture(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    paths = evidence_paths(root)
    seal = read_json(paths["author"])
    if seal.get("fixture_path") != FIXTURE_REL.as_posix():
        raise EvidenceError("Author seal names an unexpected fixture path")
    actual_hash = sha256_file(paths["fixture"])
    if actual_hash != seal.get("fixture_sha256"):
        raise EvidenceError("Fixture bytes do not match the immutable author seal")
    fixture = read_json(paths["fixture"])
    if fixture.get("provenance") != "independently_authored_synthetic":
        raise EvidenceError("Fixture provenance must remain independently authored synthetic")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvidenceError("Fixture must contain a nonempty cases list")
    seen: set[str] = set()
    for case in cases:
        required = ("id", "text", "language", "label", "category", "attack_intent", "review_signal")
        if not isinstance(case, dict) or any(key not in case for key in required):
            raise EvidenceError("Malformed case fields")
        if any(not isinstance(case[key], str) or not case[key]
               for key in ("id", "text", "language", "label", "category", "review_signal")):
            raise EvidenceError("Case string fields must be nonempty")
        if case["id"] in seen:
            raise EvidenceError(f"Duplicate case id: {case['id']}")
        seen.add(case["id"])
        if case["label"] not in {"malicious", "benign"}:
            raise EvidenceError("Unexpected case label")
        if not isinstance(case["attack_intent"], bool):
            raise EvidenceError("Attack intent must be a separate boolean annotation")
        if case["attack_intent"] != (case["label"] == "malicious"):
            raise EvidenceError("Label and attack-intent annotation disagree")
        if case["review_signal"] not in {"none", "payment_details"}:
            raise EvidenceError("Unexpected review-signal annotation")
    if case_counts(cases) != seal.get("counts"):
        raise EvidenceError("Fixture counts do not match the author seal")
    return fixture, seal


def implementation_manifest(root: Path) -> dict[str, str]:
    package_roots = [path for path in (root / "tideway", root / "src/tideway") if path.is_dir()]
    if not package_roots:
        raise EvidenceError("No tideway package directory found for implementation hashing")
    # Include code and package resources; generated bytecode is excluded because
    # importing the scanner may legitimately create it during the first pass.
    files = sorted({path for package in package_roots for path in package.rglob("*")
                    if path.is_file() and "__pycache__" not in path.parts
                    and path.suffix not in {".pyc", ".pyo"}})
    if not files:
        raise EvidenceError("No implementation source files found")
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in files}


def reproducibility_manifest(root: Path) -> dict[str, str]:
    names = ("pyproject.toml", "requirements.txt", "requirements-dev.txt", "uv.lock",
             "poetry.lock", "Pipfile.lock", "setup.cfg", "setup.py")
    return {name: sha256_file(root / name) for name in names if (root / name).is_file()}


def runtime_identity() -> dict[str, str]:
    return {"python_version": sys.version, "python_executable": sys.executable,
            "platform": platform.platform()}


def source_snapshot(root: Path) -> dict[str, Any]:
    paths = evidence_paths(root)
    return {
        "implementation_files": implementation_manifest(root),
        "reproducibility_files": reproducibility_manifest(root),
        "evaluator_sha256": sha256_file(root / "scripts/evaluate_screening_v5.py"),
        "fixture_sha256": sha256_file(paths["fixture"]),
        "author_seal_sha256": sha256_file(paths["author"]),
        "runtime": runtime_identity(),
        "scoring_contract": contract(),
    }


def seal_execution_source(root: Path) -> Path:
    paths = evidence_paths(root)
    assert_unstarted(paths)
    if paths["source"].exists():
        raise EvidenceError("Execution source already sealed; refusing overwrite")
    verified_fixture(root)
    snapshot = source_snapshot(root)
    seal = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "scope": "Execution source frozen immediately before a single holdout evaluation; no scanner import or invocation has occurred in this command.",
        **snapshot,
    }
    write_new_json(paths["source"], seal)
    return paths["source"]


def verify_execution_source(root: Path) -> dict[str, Any]:
    paths = evidence_paths(root)
    if not paths["source"].is_file():
        raise EvidenceError("Seal frozen execution source with --seal-execution-source before evaluation")
    seal = read_json(paths["source"])
    current = source_snapshot(root)
    for key, value in current.items():
        if seal.get(key) != value:
            raise EvidenceError(f"Execution source changed after sealing: {key}")
    return seal


def confusion_counts(pairs: list[tuple[bool, bool | None]]) -> dict[str, Any]:
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "errors": 0, "total": len(pairs)}
    for expected, predicted in pairs:
        if predicted is None:
            counts["errors"] += 1
        elif expected and predicted:
            counts["tp"] += 1
        elif not expected and predicted:
            counts["fp"] += 1
        elif expected and not predicted:
            counts["fn"] += 1
        else:
            counts["tn"] += 1
    tp, fp, fn, tn = (counts[key] for key in ("tp", "fp", "fn", "tn"))
    scored = tp + fp + fn + tn

    def ratio(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    return {
        **counts,
        "scored": scored,
        "coverage": ratio(scored, len(pairs)),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "specificity": ratio(tn, tn + fp),
        "false_positive_rate": ratio(fp, fp + tn),
        "accuracy_on_scored_cases": ratio(tp + tn, scored),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
    }


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    def attack_metrics(group: list[dict[str, Any]]) -> dict[str, Any]:
        return confusion_counts([(record["expected_attack"], record["predicted_attack"])
                                 for record in group])

    by_language: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    flag_counts: Counter[str] = Counter()
    unknown_counts: Counter[str] = Counter()
    for record in records:
        by_language[record["case"]["language"]].append(record)
        by_category[record["case"]["category"]].append(record)
        flag_counts.update(record["flags"] or [])
        unknown_counts.update(record["unclassified_flags"] or [])
    payment_pairs = [(record["expected_payment_review"], record["predicted_payment_review"])
                     for record in records]
    return {
        "attack": attack_metrics(records),
        "per_language": {key: attack_metrics(group) for key, group in sorted(by_language.items())},
        "per_category": {key: attack_metrics(group) for key, group in sorted(by_category.items())},
        "payment_review": {
            "meaning": "Payment details requiring review, scored separately from attack intent.",
            **confusion_counts(payment_pairs),
        },
        "generic_review": {
            "meaning": "Review warning observed; no attack intent is inferred and no ground-truth confusion matrix is claimed.",
            "observed_cases": sum(record["predicted_generic_review"] is True for record in records),
            "unscored_error_cases": sum(record["predicted_generic_review"] is None for record in records),
            "flags": sorted(GENERIC_REVIEW_FLAGS),
        },
        "returned_flag_counts": dict(sorted(flag_counts.items())),
        "unclassified_flag_counts": dict(sorted(unknown_counts.items())),
    }


def case_record(case: dict[str, Any], scanner: Any, import_error: str | None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case": case,
        "expected_attack": case["label"] == "malicious",
        "expected_payment_review": case["review_signal"] == "payment_details",
        "started_utc": utc_now(),
        "flags": None,
        "raw_flags": None,
        "unclassified_flags": None,
        "predicted_attack": None,
        "predicted_payment_review": None,
        "predicted_generic_review": None,
        "attack_outcome": "ERROR",
        "payment_review_outcome": "ERROR",
        "error": None,
    }
    try:
        if import_error is not None:
            raise RuntimeError(import_error)
        raw_flags = scanner(case["text"])
        if not isinstance(raw_flags, list) or any(not isinstance(flag, str) for flag in raw_flags):
            raise TypeError("scan_text must return list[str]")
        flags = sorted(set(raw_flags))
        record.update({
            "raw_flags": raw_flags,
            "flags": flags,
            "unclassified_flags": sorted(set(flags) - KNOWN_FLAGS),
            "predicted_attack": bool(set(flags) & ATTACK_FLAGS),
            "predicted_payment_review": bool(set(flags) & PAYMENT_REVIEW_FLAGS),
            "predicted_generic_review": bool(set(flags) & GENERIC_REVIEW_FLAGS),
        })
        for prefix, expected, predicted in (
            ("attack", record["expected_attack"], record["predicted_attack"]),
            ("payment_review", record["expected_payment_review"], record["predicted_payment_review"]),
        ):
            record[f"{prefix}_outcome"] = ("TP" if expected else "FP") if predicted else ("FN" if expected else "TN")
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["finished_utc"] = utc_now()
    return record


def run_evaluation(root: Path) -> Path:
    paths = evidence_paths(root)
    assert_unstarted(paths)
    fixture, _author_seal = verified_fixture(root)
    source_seal = verify_execution_source(root)
    # Reserving both the directory and marker is deliberately conservative:
    # partial artifacts block a second attempt, including after interruption.
    paths["run"].mkdir(parents=True, exist_ok=False)
    started = {
        "schema_version": 1,
        "started_utc": utc_now(),
        "evaluation_kind": "independently_authored_synthetic_first_pass",
        "external_evaluation": False,
        "population_inference": False,
        "fixture_path": FIXTURE_REL.as_posix(),
        "fixture_sha256": sha256_file(paths["fixture"]),
        "author_seal_sha256": sha256_file(paths["author"]),
        "execution_source_seal_sha256": sha256_file(paths["source"]),
        "execution_source": source_seal,
        "case_count": len(fixture["cases"]),
        "scoring_contract": contract(),
        "note": "Written and fsynced before importing or invoking the scanner. No overwrite or retry is permitted by this evaluator.",
    }
    write_new_json(paths["start"], started)

    # The only scanner import is below the durable start marker. This module can
    # be imported for metric arithmetic tests without importing screening code.
    import_error = None
    scanner = None
    try:
        sys.path.insert(0, str(root))
        if (root / "src/tideway").is_dir():
            sys.path.insert(0, str(root / "src"))
        scanner = importlib.import_module("tideway.domain").scan_text
    except Exception as exc:
        import_error = f"scanner import failed: {type(exc).__name__}: {exc}"

    records = []
    with paths["cases"].open("x", encoding="utf-8", newline="\n") as stream:
        for case in fixture["cases"]:
            record = case_record(case, scanner, import_error)
            records.append(record)
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    # A change during execution invalidates the run without erasing its output.
    source_unchanged = True
    source_verification_error = None
    try:
        verify_execution_source(root)
    except Exception as exc:
        source_unchanged = False
        source_verification_error = f"{type(exc).__name__}: {exc}"
    result = {
        "schema_version": 1,
        "evaluation_kind": "independently_authored_synthetic_first_pass",
        "external_evaluation": False,
        "population_inference": False,
        "interpretation": "Descriptive first-pass results on a balanced, independently authored synthetic convenience sample only. No deployment prevalence, external validation, or security guarantee is implied.",
        "started_utc": started["started_utc"],
        "finished_utc": utc_now(),
        "completed_case_count": len(records),
        "fixture_sha256": started["fixture_sha256"],
        "author_seal_sha256": started["author_seal_sha256"],
        "execution_source_seal_sha256": started["execution_source_seal_sha256"],
        "case_results_sha256": sha256_file(paths["cases"]),
        "source_unchanged_after_run": source_unchanged,
        "valid_execution_source": source_unchanged,
        "source_verification_error": source_verification_error,
        "scanner_import_error": import_error,
        "scoring_contract": contract(),
        "metrics": summarize_records(records),
        "cases": records,
    }
    write_new_json(paths["result"], result)
    return paths["result"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--seal-execution-source", action="store_true",
                       help="Seal frozen implementation and evaluator bytes without importing the scanner")
    modes.add_argument("--evaluate", action="store_true",
                       help="Perform the only allowed first pass after verifying both seals")
    args = parser.parse_args(argv)
    try:
        output = seal_execution_source(REPO_ROOT) if args.seal_execution_source else run_evaluation(REPO_ROOT)
    except (EvidenceError, OSError, ValueError, KeyError) as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2
    print(output.relative_to(REPO_ROOT).as_posix())
    if args.evaluate:
        result = read_json(output)
        if not result["valid_execution_source"] or result["metrics"]["attack"]["errors"]:
            print("First pass was recorded with execution/source errors; a retry is not permitted.", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
