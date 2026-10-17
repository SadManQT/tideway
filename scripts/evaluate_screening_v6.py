"""One-shot evaluator for the sealed, independently authored synthetic v6 holdout.

Run only after implementation is frozen::

    python scripts/evaluate_screening_v6.py --seal-execution-source \
        --model-file MODEL.gguf --runtime-archive RUNTIME.zip \
        --provenance-file PROVENANCE.json
    python scripts/evaluate_screening_v6.py --evaluate

Set TIDEWAY_LOCAL_MODEL_URL and TIDEWAY_LOCAL_TEXT_MODEL to the selected local
server before sealing. The first command hashes execution source, model and
runtime without inference. The second verifies both seals, writes a durable
start record before importing the actual TideLM pipeline, and records every case.
Existing start/results/partial-output artifacts
block a retry; neither command has an overwrite option. A failed or interrupted
first pass remains evidence and must not be silently rerun as a new first pass.

The result describes this synthetic set only. It is not an external evaluation
or a population performance estimate. This file contains no holdout examples.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import math
import time
from typing import Any
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_REL = Path("tests/fixtures/screening_holdout_v6.json")
EVIDENCE_REL = Path("evidence/screening-v6")
AUTHOR_SEAL_NAME = "holdout-author-seal.json"
SOURCE_SEAL_NAME = "execution-source-seal.json"
START_NAME = "evaluation-started.json"
RESULT_NAME = "first-pass-results.json"
CASE_NAME = "case-results.jsonl"
ATTEMPT_NAME = "model-attempts.jsonl"
RUN_DIR_NAME = "first-pass"
PIPELINE_CONTRACT_READY = True

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
SEMANTIC_LABELS = frozenset({"attack", "review", "benign", "uncertain"})
SEMANTIC_CATEGORIES = frozenset({
    "instruction_override", "control_bypass", "forged_authority", "payment_redirect",
    "data_exfiltration", "concealed_action", "audit_tampering", "encoded_instruction",
    "payment_detail_change",
})

CLASSIFIER_SCOPE = {
    "purpose": "classification_only",
    "financial_authority": "none",
    "can_approve_payments": False,
    "can_execute_payments": False,
    "model_text_is_execution_permission": False,
    "record_text_is_execution_permission": False,
}


def json_compatible(value: Any) -> Any:
    """Preserve typed pipeline data without executing or interpreting its text."""
    if is_dataclass(value) and not isinstance(value, type):
        return json_compatible(asdict(value))
    if isinstance(value, Enum):
        return json_compatible(value.value)
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite numeric value in pipeline evidence")
        return value
    if isinstance(value, (list, tuple)):
        return [json_compatible(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: json_compatible(item) for key, item in value.items()}
    raise TypeError(f"Unsupported pipeline evidence type: {type(value).__name__}")


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
        "pipeline_api": "tideway.tidelm.TideLM().screen(text, enabled=True)",
        "semantic_labels": sorted(SEMANTIC_LABELS),
        "semantic_categories": sorted(SEMANTIC_CATEGORIES),
        "generation_contract": {"maximum_attempts_per_case": 1, "max_tokens": 220,
                                "acceptance_budget_seconds": 30, "transport_hardcap_seconds": 45,
                                "strict_schema": "classification_schema()"},
        "primary_semantic_metric": "All labelled cases; uncertain/error is no confirmed attack detection. Attack cases then count as FN; benign cases do not become false attacks. Coverage and selective metrics are separate.",
        "semantic_scope": CLASSIFIER_SCOPE,
        "privacy_evidence_limit": "Recorded local configuration/runtime evidence is not independent proof of privacy, telemetry behavior, or external certification.",
        "accuracy_evidence_limit": "Independently authored synthetic first pass with disclosed authoring context; not external, population, or blind-human validation.",
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
        "attempts": run / ATTEMPT_NAME,
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
    if seal.get("fixture_path", seal.get("artifact")) != FIXTURE_REL.as_posix():
        raise EvidenceError("Author seal names an unexpected fixture path")
    actual_hash = sha256_file(paths["fixture"])
    if actual_hash != seal.get("fixture_sha256"):
        raise EvidenceError("Fixture bytes do not match the immutable author seal")
    fixture = read_json(paths["fixture"])
    # The isolated v6 author sealed its provenance/context in the author seal,
    # rather than adding a fixture-level provenance key. Do not alter its bytes.
    if fixture.get("provenance", "independently_authored_synthetic") != "independently_authored_synthetic":
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


def local_configuration(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.base_url or os.environ.get("TIDEWAY_LOCAL_MODEL_URL", "")
    model_id = args.model_id or os.environ.get("TIDEWAY_LOCAL_TEXT_MODEL", "")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise EvidenceError("An explicit loopback local-model URL is required")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise EvidenceError("Local-model URL must not contain credentials, query, or fragment")
    if not model_id:
        raise EvidenceError("An explicit served model identity is required")
    files = {}
    for key in ("model_file", "runtime_archive", "provenance_file"):
        value = getattr(args, key)
        if not value:
            raise EvidenceError(f"--{key.replace('_', '-')} is required when sealing")
        path = Path(value).expanduser().resolve(strict=True)
        if not path.is_file():
            raise EvidenceError(f"Not an artifact file: {path}")
        files[key] = str(path)
    executable = args.runtime_executable
    if executable:
        executable = str(Path(executable).expanduser().resolve(strict=True))
    else:
        executable = discover_runtime_executable(parsed.port, Path(files["runtime_archive"]).parent)
    files["runtime_executable"] = executable
    return {
        "base_url": base_url.rstrip("/"),
        "served_model_id": model_id,
        "artifact_paths": files,
        "scope": CLASSIFIER_SCOPE,
        "artifact_binding_limit": "Measured local artifact hashes and configured/server-reported identity are evidence, not an independent attestation of the server's loaded weights or privacy.",
    }


def discover_runtime_executable(port: int | None, cache_root: Path) -> str:
    """Return only the matching local server executable path, never its CLI."""
    if os.name != "nt" or port is None:
        raise EvidenceError("Pass --runtime-executable explicitly on this platform/configuration")
    # Only inspect llama-server processes with the selected port. Do not emit
    # command lines or any process environment; output is restricted to a path.
    pattern = rf"(?:^|\s)--port(?:=|\s+){int(port)}(?:\s|$)"
    command = (
        "$taskRuntimeMatches = @(Get-CimInstance Win32_Process -Filter \"Name = 'llama-server.exe'\" "
        f"| Where-Object {{ $_.CommandLine -match '{pattern}' }} "
        "| ForEach-Object { $_.ExecutablePath }); "
        "ConvertTo-Json -InputObject $taskRuntimeMatches -Compress"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        check=True, capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    candidates = json.loads(completed.stdout.strip() or "[]")
    if isinstance(candidates, str):
        candidates = [candidates]
    base = cache_root.resolve(strict=True)
    accepted = sorted({str(Path(value).resolve(strict=True)) for value in candidates
                       if value and Path(value).resolve(strict=True).is_relative_to(base)
                       and Path(value).is_file()})
    if len(accepted) != 1:
        raise EvidenceError("Cannot uniquely identify the selected server inside runtime cache; pass --runtime-executable")
    return accepted[0]


def artifact_manifest(configuration: dict[str, Any]) -> dict[str, Any]:
    return {name: {"path": value, "sha256": sha256_file(Path(value)),
                   "bytes": Path(value).stat().st_size}
            for name, value in sorted(configuration["artifact_paths"].items())}


def source_snapshot(root: Path, configuration: dict[str, Any]) -> dict[str, Any]:
    paths = evidence_paths(root)
    return {
        "implementation_files": implementation_manifest(root),
        "reproducibility_files": reproducibility_manifest(root),
        "evaluator_sha256": sha256_file(root / "scripts/evaluate_screening_v6.py"),
        "fixture_sha256": sha256_file(paths["fixture"]),
        "author_seal_sha256": sha256_file(paths["author"]),
        "runtime": runtime_identity(),
        "scoring_contract": contract(),
        "evaluation_configuration": configuration,
        "model_runtime_artifacts": artifact_manifest(configuration),
    }


def seal_execution_source(root: Path, configuration: dict[str, Any]) -> Path:
    paths = evidence_paths(root)
    assert_unstarted(paths)
    if paths["source"].exists():
        raise EvidenceError("Execution source already sealed; refusing overwrite")
    verified_fixture(root)
    snapshot = source_snapshot(root, configuration)
    seal = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "scope": "Execution source, selected model/runtime artifacts and configuration frozen immediately before one holdout pass; no pipeline import or inference in this command.",
        **snapshot,
    }
    write_new_json(paths["source"], seal)
    return paths["source"]


def verify_execution_source(root: Path) -> dict[str, Any]:
    paths = evidence_paths(root)
    if not paths["source"].is_file():
        raise EvidenceError("Seal frozen execution source with --seal-execution-source before evaluation")
    seal = read_json(paths["source"])
    current = source_snapshot(root, seal["evaluation_configuration"])
    for key, value in current.items():
        if seal.get(key) != value:
            raise EvidenceError(f"Execution source changed after sealing: {key}")
    return seal


def confusion_counts(pairs: list[tuple[bool, bool | None]]) -> dict[str, Any]:
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "unscored": 0, "total": len(pairs)}
    for expected, predicted in pairs:
        if predicted is None:
            counts["unscored"] += 1
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
        "accuracy": ratio(tp + tn, scored),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
    }


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    def mode_metrics(group: list[dict[str, Any]]) -> dict[str, Any]:
        semantic = confusion_counts([(record["expected_attack"], record["semantic_attack_detected"])
                                     for record in group])
        labels = Counter(record["semantic_label"] or "pipeline_error" for record in group)
        covered = sum(record["semantic_covered"] for record in group)
        semantic.update({
            "scoring": "Full labelled denominator; uncertainty/error is no confirmed attack detection.",
            "decision_coverage": covered / len(group) if group else None,
            "primary_denominator": len(group),
            "primary_scoring_coverage": semantic["coverage"],
            "coverage": covered / len(group) if group else None,
            "covered_cases": covered,
            "uncertain_cases": labels.get("uncertain", 0),
            "error_cases": sum(bool(record["pipeline_error"] or record["pipeline_errors"]) for record in group),
            "label_counts": dict(sorted(labels.items())),
            "selective_metrics": confusion_counts([
                (record["expected_attack"], record["semantic_attack_detected"] if record["semantic_covered"] else None)
                for record in group
            ]),
        })
        return {
            "pure_rules_attack": {
                **confusion_counts([(record["expected_attack"], record["rule_attack_detected"])
                                    for record in group]),
                "rule_output_cases": sum(record["rule_output_available"] for record in group),
                "rule_output_coverage": sum(record["rule_output_available"] for record in group) / len(group) if group else None,
            },
            "semantic_attack": semantic,
            "combined_warning": {
                **confusion_counts([(record["expected_warning"], record["combined_warning"])
                                    for record in group]),
                "meaning": "Warning/review detection, not a claim of confirmed attack intent.",
                "uncertainty_review_cases": sum(record["semantic_label"] == "uncertain"
                                                and record["combined_warning"] for record in group),
                "benign_uncertainty_review_cases": sum(record["semantic_label"] == "uncertain"
                                                       and record["combined_warning"] and not record["expected_attack"]
                                                       for record in group),
            },
        }

    by_language: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    flag_counts: Counter[str] = Counter()
    unknown_counts: Counter[str] = Counter()
    for record in records:
        by_language[record["case"]["language"]].append(record)
        by_category[record["case"]["category"]].append(record)
        flag_counts.update(record["combined_flags"])
        unknown_counts.update(record["unclassified_flags"] or [])
    payment_pairs = [(record["expected_payment_review"], record["predicted_payment_review"])
                     for record in records]
    return {
        **mode_metrics(records),
        "per_language": {key: mode_metrics(group) for key, group in sorted(by_language.items())},
        "per_category": {key: mode_metrics(group) for key, group in sorted(by_category.items())},
        "payment_review": {
            "meaning": "Payment details requiring review, scored separately from attack intent.",
            **confusion_counts(payment_pairs),
        },
        "generic_review": {
            "meaning": "Review warning observed; no attack intent is inferred and no ground-truth confusion matrix is claimed.",
            "observed_cases": sum(record["predicted_generic_review"] is True for record in records),
            "semantic_review_cases": sum(record["semantic_label"] == "review" for record in records),
            "semantic_uncertain_cases": sum(record["semantic_label"] == "uncertain" for record in records),
            "flags": sorted(GENERIC_REVIEW_FLAGS),
        },
        "returned_flag_counts": dict(sorted(flag_counts.items())),
        "unclassified_flag_counts": dict(sorted(unknown_counts.items())),
        "pipeline_error_counts": dict(sorted(Counter(
            code for record in records for code in record["pipeline_errors"]
        ).items())),
        "pipeline_exception_cases": sum(record["pipeline_error"] is not None for record in records),
        "model_attempt_count": sum(record["model_attempt"]["attempt_count"]
                                   for record in records
                                   if type(record["model_attempt"]["attempt_count"]) is int),
        "unknown_attempt_count_cases": sum(record["model_attempt"]["attempt_count_unknown"] for record in records),
    }


def validate_pipeline_result(result: dict[str, Any]) -> None:
    required = {
        "label", "categories", "reason", "rule_flags", "combined_flags", "warning_required",
        "human_review_required", "trusted", "attempt_count", "raw_output", "raw_output_sha256",
        "raw_output_bytes", "raw_output_truncated", "errors", "elapsed_ms", "model_identity",
    }
    if not isinstance(result, dict) or not required.issubset(result):
        raise EvidenceError("Typed pipeline result is missing required evidence fields")
    if result["label"] not in SEMANTIC_LABELS:
        raise EvidenceError("Unknown semantic label")
    for key in ("categories", "rule_flags", "combined_flags", "errors"):
        if not isinstance(result[key], list) or any(not isinstance(item, str) for item in result[key]):
            raise EvidenceError(f"Expected list[str] for {key}")
    if set(result["categories"]) - SEMANTIC_CATEGORIES:
        raise EvidenceError("Unknown semantic category")
    if not isinstance(result["reason"], str):
        raise EvidenceError("Semantic reason must remain text data")
    if result["human_review_required"] is not True or result["trusted"] is not False:
        raise EvidenceError("Pipeline violated classification-only financial authority contract")
    if not isinstance(result["warning_required"], bool):
        raise EvidenceError("Warning decision must be boolean")
    if type(result["attempt_count"]) is not int or result["attempt_count"] not in {0, 1}:
        raise EvidenceError("Pipeline reported an invalid attempt count; retries are prohibited")
    if result["attempt_count"] == 0 and result["label"] != "uncertain":
        raise EvidenceError("Semantic decision reported without a model attempt")
    if not isinstance(result["elapsed_ms"], (float, int)) or isinstance(result["elapsed_ms"], bool) or result["elapsed_ms"] < 0:
        raise EvidenceError("Invalid generation latency")
    if result["raw_output"] is not None and not isinstance(result["raw_output"], str):
        raise EvidenceError("Raw model output must remain a string or null")
    if type(result["raw_output_bytes"]) is not int or result["raw_output_bytes"] < 0:
        raise EvidenceError("Invalid raw generation byte count")
    if not isinstance(result["raw_output_truncated"], bool):
        raise EvidenceError("Raw truncation indicator must be boolean")
    raw = result["raw_output"]
    digest = result["raw_output_sha256"]
    if raw is not None:
        encoded = raw.encode("utf-8")
        if result["raw_output_bytes"] < len(encoded):
            raise EvidenceError("Retained raw output exceeds reported full byte count")
        # Zero-attempt/transport-error paths may retain the empty string with
        # no hash because no model generation was received. Preserve that fact.
        empty_without_generation = (not encoded and result["raw_output_bytes"] == 0
                                    and not result["raw_output_truncated"] and not digest)
        if empty_without_generation:
            return
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise EvidenceError("Full raw generation SHA-256 is required")
        if not result["raw_output_truncated"] and (
            len(encoded) != result["raw_output_bytes"] or hashlib.sha256(encoded).hexdigest() != digest
        ):
            raise EvidenceError("Raw generation byte count/hash does not match retained output")


def binary_outcome(expected: bool, detected: bool) -> str:
    return ("TP" if expected else "FP") if detected else ("FN" if expected else "TN")


def case_record(case: dict[str, Any], client: Any, initialization_error: str | None,
                *, runtime_status: Any = None, source_seal_sha256: str | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case": case,
        "expected_attack": case["label"] == "malicious",
        "expected_payment_review": case["review_signal"] == "payment_details",
        "expected_warning": case["label"] == "malicious" or case["review_signal"] != "none",
        "started_utc": utc_now(),
        "scope": CLASSIFIER_SCOPE,
        "rule_flags": [], "combined_flags": [], "unclassified_flags": [],
        "rule_output_available": False, "rule_attack_detected": False,
        "semantic_label": None, "semantic_attack_detected": False, "semantic_covered": False,
        "combined_warning": False,
        "predicted_payment_review": False, "predicted_generic_review": False,
        "pipeline_result": None, "pipeline_error": None, "pipeline_errors": [],
        "screen_elapsed_ms": None,
        "model_attempt": {
            "case_id": case["id"], "attempt_count": None, "attempt_count_unknown": True,
            "raw_output": None, "raw_output_sha256": None, "raw_output_bytes": None,
            "raw_output_truncated": None, "errors": [], "elapsed_ms": None,
            "model_identity": None, "runtime_status": runtime_status,
            "execution_source_seal_sha256": source_seal_sha256, "scope": CLASSIFIER_SCOPE,
        },
    }
    start = time.perf_counter()
    try:
        if initialization_error is not None:
            raise RuntimeError(initialization_error)
        result = json_compatible(client.screen(case["text"], enabled=True))
        record["pipeline_result"] = result
        # Copy trace fields before validation, so malformed results remain raw
        # evidence rather than disappearing behind a protocol exception.
        if isinstance(result, dict):
            # Preserve independent rule/warning outputs even when later model
            # evidence validation fails; a semantic protocol error must not
            # silently erase the pure-rule baseline.
            for key in ("rule_flags", "combined_flags"):
                value = result.get(key)
                if isinstance(value, list) and all(isinstance(item, str) for item in value):
                    record[key] = sorted(set(value))
            if isinstance(result.get("rule_flags"), list) and all(isinstance(item, str) for item in result["rule_flags"]):
                record["rule_output_available"] = True
                record["rule_attack_detected"] = bool(set(record["rule_flags"]) & ATTACK_FLAGS)
            record["unclassified_flags"] = sorted(set(record["combined_flags"]) - KNOWN_FLAGS)
            record["predicted_payment_review"] = bool(set(record["combined_flags"]) & PAYMENT_REVIEW_FLAGS)
            record["predicted_generic_review"] = bool(set(record["combined_flags"]) & GENERIC_REVIEW_FLAGS)
            if isinstance(result.get("warning_required"), bool):
                record["combined_warning"] = result["warning_required"]
            for key in ("attempt_count", "raw_output", "raw_output_sha256", "raw_output_bytes",
                        "raw_output_truncated", "errors", "elapsed_ms", "model_identity"):
                if key in result:
                    record["model_attempt"][key] = result[key]
            record["model_attempt"]["attempt_count_unknown"] = (type(result.get("attempt_count")) is not int
                                                                 or result.get("attempt_count") not in {0, 1})
            if isinstance(result.get("errors"), list):
                record["pipeline_errors"] = [str(item) for item in result["errors"]]
        validate_pipeline_result(result)
        rules = sorted(set(result["rule_flags"]))
        combined = sorted(set(result["combined_flags"]))
        record.update({
            "rule_flags": rules, "combined_flags": combined,
            "unclassified_flags": sorted(set(combined) - KNOWN_FLAGS),
            "rule_output_available": True,
            "rule_attack_detected": bool(set(rules) & ATTACK_FLAGS),
            "semantic_label": result["label"],
            "semantic_attack_detected": result["label"] == "attack",
            "semantic_covered": result["label"] != "uncertain",
            "combined_warning": result["warning_required"],
            "predicted_payment_review": bool(set(combined) & PAYMENT_REVIEW_FLAGS)
                                        or "payment_detail_change" in result["categories"],
            "predicted_generic_review": bool(set(combined) & GENERIC_REVIEW_FLAGS),
        })
    except Exception as exc:
        record["pipeline_error"] = f"{type(exc).__name__}: {exc}"
        record["model_attempt"]["harness_error"] = record["pipeline_error"]
    record["screen_elapsed_ms"] = (time.perf_counter() - start) * 1000
    record["model_attempt"]["screen_elapsed_ms"] = record["screen_elapsed_ms"]
    record["finished_utc"] = utc_now()
    record["model_attempt"]["started_utc"] = record["started_utc"]
    record["model_attempt"]["finished_utc"] = record["finished_utc"]
    for name, expected, detected in (
        ("pure_rules_attack", record["expected_attack"], record["rule_attack_detected"]),
        ("semantic_attack", record["expected_attack"], record["semantic_attack_detected"]),
        ("combined_warning", record["expected_warning"], record["combined_warning"]),
    ):
        record[f"{name}_outcome"] = binary_outcome(expected, detected)
    return record


def run_evaluation(root: Path) -> Path:
    paths = evidence_paths(root)
    assert_unstarted(paths)
    fixture, _author_seal = verified_fixture(root)
    source_seal = verify_execution_source(root)
    configuration = source_seal["evaluation_configuration"]
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
        "scope": CLASSIFIER_SCOPE,
        "evaluation_configuration": configuration,
        "note": "Written and fsynced before importing TideLM or invoking any inference. No overwrite or retry is permitted by this evaluator.",
    }
    write_new_json(paths["start"], started)

    # Only the two selected nonsecret variables are written/read here. Import
    # and construction are after the durable marker; status is metadata only.
    os.environ["TIDEWAY_LOCAL_MODEL_URL"] = configuration["base_url"]
    os.environ["TIDEWAY_LOCAL_TEXT_MODEL"] = configuration["served_model_id"]
    initialization_error = None
    client = None
    runtime_status = None
    try:
        sys.path.insert(0, str(root))
        if (root / "src/tideway").is_dir():
            sys.path.insert(0, str(root / "src"))
        client = importlib.import_module("tideway.tidelm").TideLM()
        runtime_status = json_compatible(client.status())
    except Exception as exc:
        initialization_error = f"actual TideLM initialization/status failed: {type(exc).__name__}: {exc}"

    records = []
    with paths["cases"].open("x", encoding="utf-8", newline="\n") as stream, \
         paths["attempts"].open("x", encoding="utf-8", newline="\n") as attempts:
        for case in fixture["cases"]:
            attempts.write(json.dumps({"event": "case_started", "case_id": case["id"],
                                       "started_utc": utc_now(), "scope": CLASSIFIER_SCOPE,
                                       "execution_source_seal_sha256": started["execution_source_seal_sha256"]},
                                      ensure_ascii=False, sort_keys=True) + "\n")
            attempts.flush()
            os.fsync(attempts.fileno())
            record = case_record(case, client, initialization_error, runtime_status=runtime_status,
                                 source_seal_sha256=started["execution_source_seal_sha256"])
            records.append(record)
            attempts.write(json.dumps({"event": "case_finished", **record["model_attempt"]},
                                      ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            attempts.flush()
            os.fsync(attempts.fileno())
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
        "interpretation": "Descriptive first-pass results on a balanced, independently authored synthetic convenience sample with disclosed authoring context. No external or blind-human validation, population inference, privacy certification, or security guarantee is implied.",
        "scope": CLASSIFIER_SCOPE,
        "started_utc": started["started_utc"],
        "finished_utc": utc_now(),
        "completed_case_count": len(records),
        "fixture_sha256": started["fixture_sha256"],
        "author_seal_sha256": started["author_seal_sha256"],
        "execution_source_seal_sha256": started["execution_source_seal_sha256"],
        "case_results_sha256": sha256_file(paths["cases"]),
        "model_attempts_sha256": sha256_file(paths["attempts"]),
        "runtime_status": runtime_status,
        "evaluation_configuration": configuration,
        "model_runtime_artifacts": source_seal["model_runtime_artifacts"],
        "source_unchanged_after_run": source_unchanged,
        "valid_execution_source": source_unchanged,
        "source_verification_error": source_verification_error,
        "pipeline_initialization_error": initialization_error,
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
    parser.add_argument("--base-url", help="Loopback model URL; defaults to TIDEWAY_LOCAL_MODEL_URL (seal only)")
    parser.add_argument("--model-id", help="Served model ID; defaults to TIDEWAY_LOCAL_TEXT_MODEL (seal only)")
    parser.add_argument("--model-file", help="Exact local model artifact to hash (seal only)")
    parser.add_argument("--runtime-archive", help="Downloaded runtime archive to hash (seal only)")
    parser.add_argument("--provenance-file", help="Local model/runtime provenance record to hash (seal only)")
    parser.add_argument("--runtime-executable", help="Actual serving executable; otherwise discover selected port inside runtime cache (seal only)")
    args = parser.parse_args(argv)
    if not PIPELINE_CONTRACT_READY:
        print("Refused: v6 typed semantic pipeline contract integration is not complete.", file=sys.stderr)
        return 2
    try:
        if args.evaluate and any(getattr(args, key) for key in (
            "base_url", "model_id", "model_file", "runtime_archive", "provenance_file", "runtime_executable"
        )):
            raise EvidenceError("Evaluation uses sealed configuration; configuration arguments are seal-only")
        output = (seal_execution_source(REPO_ROOT, local_configuration(args))
                  if args.seal_execution_source else run_evaluation(REPO_ROOT))
    except (EvidenceError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2
    print(output.relative_to(REPO_ROOT).as_posix())
    if args.evaluate:
        result = read_json(output)
        if not result["valid_execution_source"] or result["metrics"]["pipeline_exception_cases"]:
            print("First pass was recorded with execution/source errors; a retry is not permitted.", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
