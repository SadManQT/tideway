"""Contextual screening: attack signals and callback review have separate labels.

The development corpus is author-labelled and tuned; a root-authored held-out
corpus is evaluated only after implementation freeze. Neither is real-world
fraud prevalence, financial risk calibration, or proof of the authority boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tideway.analytics import payee_checks  # noqa: E402
from tideway.domain import clean_text, scan_text  # noqa: E402

REVIEW_FLAGS = {"payment_detail_change"}


def confusion(rows, expected="malicious"):
    tp = sum(row[expected] and row["flagged"] for row in rows)
    fn = sum(row[expected] and not row["flagged"] for row in rows)
    fp = sum(not row[expected] and row["flagged"] for row in rows)
    tn = sum(not row[expected] and not row["flagged"] for row in rows)
    return {"true_positive": tp, "false_negative": fn, "false_positive": fp, "true_negative": tn,
            "positive_denominator": tp + fn, "negative_denominator": fp + tn,
            "detection_rate": tp / (tp + fn) if tp + fn else None,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None}


def evaluate(fixture):
    spec = json.loads(fixture.read_text(encoding="utf-8"))
    messages, payees = [], []
    for case in spec["messages"]:
        cleaned, removed = clean_text(case["text"])
        flags = scan_text(cleaned) + (["hidden_characters"] if removed else [])
        attack_flags = [flag for flag in flags if flag not in REVIEW_FLAGS]
        messages.append({**case, "flags": flags, "attack_flags": attack_flags,
                         "flagged": bool(attack_flags), "payment_review": bool(set(flags) & REVIEW_FLAGS)})
    for case in spec["payees"]:
        bills = [{"id": "history", "status": "paid", "payee": case["history_name"], "payee_account": case["history_account"]},
                 {"id": "open", "status": "open", "payee": case["open_name"], "payee_account": case["open_account"]}]
        verified = {case["open_name"]: case["verified_account"]} if case.get("verified_account") else {}
        result = payee_checks(bills, verified)
        payees.append({**case, "flagged": bool(result["flagged"] or result["lookalikes"]),
                       "reasons": [row["reason"] for row in result["flagged"] + result["lookalikes"]]})
    labelled_review = [row for row in payees if "review_expected" in row]
    return {"fixture": str(fixture.relative_to(ROOT)), "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "methodology": spec.get("methodology", spec.get("method", spec.get("label_policy", "Author-labelled synthetic cases."))),
            "definition": "Instruction positives exclude payment_detail_change, which remains a separate conservative review signal. All record text is untrusted regardless of flags. Payee review is not a fraud verdict.",
            "injection": {"confusion": confusion(messages), "rows": messages},
            "payee_intent": {"confusion": confusion(payees), "rows": payees},
            "payee_review_policy": {"confusion": confusion(labelled_review, "review_expected"), "labelled_cases": len(labelled_review)},
            "limitations": ["Small synthetic, author-intent-labelled corpus; not prevalence or production accuracy.",
                            "A legitimate changed/missing historical account or near-match name can correctly require callback.",
                            "Unrelated new-name impostors cannot be distinguished from legitimate new vendors with these fields alone.",
                            "Rules cannot identify all paraphrases; approval and permission controls are independent."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default="tests/fixtures/screening_development_v3.json")
    parser.add_argument("--out", default="evidence/screening-v3/development.json")
    args = parser.parse_args()
    report = evaluate((ROOT / args.fixture).resolve())
    path = ROOT / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value["confusion"] for key, value in report.items() if isinstance(value, dict) and "confusion" in value}, indent=2))


if __name__ == "__main__":
    main()
