"""Prepare a private anonymous CSV and export aggregate, consented study counts.

This helper never recruits people, supplies responses or marks an empty study as
validated. Consent is required before any study observations can be entered.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "evidence/private"
DEFAULT_CSV = PRIVATE / "user-study.csv"
DEFAULT_OUT = ROOT / "evidence/readiness-v3/user-study-status.json"
TASKS = ("t1", "t2", "t3", "t4", "t5")
ROLES = {"owner", "bookkeeper", "accountant"}
LANGUAGES = {"en", "bn", "zh", "es", "hi", "ar", "fr", "pt", "other"}
MODEL_STATUSES = {"available", "unavailable", "not_tested"}
TASK_STATUSES = {"completed", "assisted", "failed", "not_attempted", "unavailable_model"}
ATTEMPTED = {"completed", "assisted", "failed"}
HEADERS = ["participant_id", "role", "language", "consent", "model_status",
           *[field for task in TASKS for field in (f"{task}_status", f"{task}_seconds")],
           *[f"sus{number}" for number in range(1, 11)]]


class StudyError(ValueError):
    pass


def blank_row(participant_id="P1"):
    row = {key: "" for key in HEADERS}
    row.update(participant_id=participant_id, consent="no", model_status="not_tested")
    row.update({f"{task}_status": "not_attempted" for task in TASKS})
    return row


def initialise(path):
    """One clearly unconsented placeholder; refuse to overwrite observations."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerow(blank_row())


def sus_score(items):
    if len(items) != 10 or any(type(value) is not int or not 1 <= value <= 5 for value in items):
        raise StudyError("SUS requires ten integer responses from 1 to 5.")
    return 2.5 * sum(value - 1 if index % 2 == 0 else 5 - value for index, value in enumerate(items))


def _seconds(raw, row_number, field):
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as error:
        raise StudyError(f"Row {row_number}: {field} must be a finite number of seconds.") from error
    if not math.isfinite(value) or not 0 <= value <= 3600:
        raise StudyError(f"Row {row_number}: {field} must be finite, from 0 to 3600 seconds.")
    return value


def read_rows(path):
    rows, seen = [], set()
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != HEADERS:
            raise StudyError("CSV columns and order must match the fixed anonymous study template; free-text columns are forbidden.")
        for row_number, raw in enumerate(reader, 2):
            if None in raw or any(value is None for value in raw.values()):
                raise StudyError(f"Row {row_number}: wrong number of CSV fields.")
            row = {key: value.strip() for key, value in raw.items()}
            if not re.fullmatch(r"P[1-9][0-9]{0,2}", row["participant_id"]):
                raise StudyError(f"Row {row_number}: use an anonymous ID from P1 to P999.")
            if row["participant_id"] in seen:
                raise StudyError(f"Row {row_number}: duplicate anonymous participant ID.")
            seen.add(row["participant_id"])
            if row["consent"] not in {"yes", "no"}:
                raise StudyError(f"Row {row_number}: consent must be yes or no.")
            if row["model_status"] not in MODEL_STATUSES:
                raise StudyError(f"Row {row_number}: invalid model_status.")
            if row["consent"] == "no":
                if row != blank_row(row["participant_id"]):
                    raise StudyError(f"Row {row_number}: observations require prior consent; remove data or remove a withdrawn row.")
                rows.append({"consented": False})
                continue
            if row["role"] not in ROLES or row["language"] not in LANGUAGES:
                raise StudyError(f"Row {row_number}: use the documented role and language enums only.")
            parsed = {"consented": True, "role": row["role"], "language": row["language"], "tasks": {}}
            for task in TASKS:
                status = row[f"{task}_status"]
                if status not in TASK_STATUSES:
                    raise StudyError(f"Row {row_number}: invalid {task}_status.")
                seconds = _seconds(row[f"{task}_seconds"], row_number, f"{task}_seconds")
                if status not in ATTEMPTED and seconds is not None:
                    raise StudyError(f"Row {row_number}: timing is only recorded for an attempted task.")
                if status == "unavailable_model" and (task != "t3" or row["model_status"] != "unavailable"):
                    raise StudyError(f"Row {row_number}: only optional AI task t3 can be unavailable_model, with model_status unavailable.")
                if task == "t3" and status in ATTEMPTED and row["model_status"] != "available":
                    raise StudyError(f"Row {row_number}: an attempted optional AI task requires model_status available.")
                parsed["tasks"][task] = {"status": status, "seconds": seconds}
            responses = []
            for number in range(1, 11):
                value = row[f"sus{number}"]
                if value and value not in {"1", "2", "3", "4", "5"}:
                    raise StudyError(f"Row {row_number}: SUS responses must be integer values 1 to 5 or blank.")
                responses.append(int(value) if value else None)
            parsed["sus_complete"] = all(value is not None for value in responses)
            parsed["sus_partial"] = any(value is not None for value in responses) and not parsed["sus_complete"]
            parsed["sus_score"] = sus_score(responses) if parsed["sus_complete"] else None
            rows.append(parsed)
    return rows


def _ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def summarise(path):
    rows = read_rows(path)
    consented = [row for row in rows if row["consented"]]
    tasks = {}
    for task in TASKS:
        observations = [row["tasks"][task] for row in consented]
        counts = Counter(row["status"] for row in observations)
        attempted = sum(counts[status] for status in ATTEMPTED)
        times = [row["seconds"] for row in observations if row["seconds"] is not None]
        tasks[task] = {"counts": {status: counts[status] for status in sorted(TASK_STATUSES)},
                       "attempted_denominator": attempted,
                       "unassisted_completion": _ratio(counts["completed"], attempted),
                       "completion_including_assistance": _ratio(counts["completed"] + counts["assisted"], attempted),
                       "timing_observations": len(times), "median_seconds": statistics.median(times) if times else None,
                       "timing_note": "Median across observed attempted-task timings, including failures; missing timings are excluded, not replaced by zero."}
    scores = [row["sus_score"] for row in consented if row["sus_score"] is not None]
    has_observations = any(row["sus_complete"] or row["sus_partial"] or
                           any(item["status"] != "not_attempted" for item in row["tasks"].values()) for row in consented)
    status = ("pending_no_consented_participants" if not consented else
              "collected_exploratory_observations" if has_observations else "consented_sessions_no_observations")
    return {"schema_version": "tideway-user-study-v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "consented_participants": len(consented), "excluded_rows_without_consent": len(rows) - len(consented),
            "roles": {role: sum(row["role"] == role for row in consented) for role in sorted(ROLES)},
            "tasks": tasks,
            "sus": {"complete_responses": len(scores), "partial_responses_not_scored": sum(row["sus_partial"] for row in consented),
                    "missing_responses": sum(not row["sus_complete"] and not row["sus_partial"] for row in consented),
                    "mean_score": statistics.mean(scores) if scores else None,
                    "median_score": statistics.median(scores) if scores else None,
                    "scale": "0 to 100, not a percentage of tasks completed",
                    "formula": "2.5 * sum(odd response - 1, 5 - even response), one-based item numbering"},
            "limitations": ["No participants or responses are synthesized by this helper. Zero participants means user validation remains outstanding.",
                            "Small convenience samples support exploratory feedback only, not representative usability or market-fit claims.",
                            "Unattempted and unavailable-model tasks are excluded from attempted-task denominators and reported separately.",
                            "Only complete ten-item SUS responses are scored; partial or missing responses produce no fabricated score.",
                            "Public output contains aggregates only: no participant IDs, raw rows, response items, free text, contact details or input paths."]}


def _private_csv(path):
    result = Path(path).expanduser().resolve()
    if result.suffix != ".csv" or not result.is_relative_to(PRIVATE.resolve()):
        raise StudyError("Store raw study CSVs under the ignored evidence/private/ directory with a .csv extension.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "summarize"))
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Aggregate JSON only; never exports participant rows")
    args = parser.parse_args()
    try:
        path = _private_csv(args.csv)
        if args.action == "init":
            initialise(path)
            print("Private anonymous CSV template created; consent is no and no study observations are recorded.")
        else:
            report = summarise(path)
            out = args.out.expanduser().resolve()
            if out.suffix != ".json" or out == path:
                raise StudyError("Aggregate output must be a .json file and must not overwrite a study CSV.")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"status": report["status"], "consented_participants": report["consented_participants"],
                              "sus_complete_responses": report["sus"]["complete_responses"]}))
        return 0
    except (StudyError, OSError, UnicodeError, csv.Error) as error:
        message = str(error) if isinstance(error, StudyError) else "Study file could not be read or written; check its path and format."
        print(message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
