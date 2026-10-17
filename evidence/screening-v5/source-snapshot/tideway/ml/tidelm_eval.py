"""Evaluate TideLM (base model vs our fine-tuned adapter) on the held-out test set.

Run: python -m tideway.ml.tidelm_eval --adapter models/tidelm-adapter   (omit --adapter for the base model)
Test examples use counterparty names never seen in training.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_MODEL = "mlx-community/Qwen3-4B-Instruct-2507-4bit"


def parse(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def norm(value):
    if isinstance(value, dict):
        return {str(k).casefold(): norm(v) for k, v in value.items()}
    if isinstance(value, list):
        return [norm(v) for v in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    return str(value).strip().casefold()


def score_plan(predicted, expected):
    result = {"valid_json": predicted is not None, "intent": False, "tools": False, "exact": False}
    if predicted is None:
        return result
    result["intent"] = norm(predicted.get("intent")) == norm(expected["intent"])
    calls = predicted.get("calls") if isinstance(predicted.get("calls"), list) else []
    result["tools"] = [c.get("tool") for c in calls if isinstance(c, dict)] == [c["tool"] for c in expected["calls"]]
    result["exact"] = result["tools"] and all(norm(p.get("args", {})) == norm(e["args"]) for p, e in zip(calls, expected["calls"]))
    return result


def record_key(row):
    return (norm(row.get("record_type")), norm(row.get("counterparty")), norm(row.get("amount")))


def score_extract(predicted, expected):
    result = {"valid_json": predicted is not None, "suspicious": False, "tp": 0, "fp": 0, "fn": 0, "fields_ok": 0, "fields": 0}
    expected_rows = expected["records"]
    if predicted is None:
        result["fn"] = len(expected_rows)
        return result
    result["suspicious"] = bool(predicted.get("suspicious")) == expected["suspicious"]
    rows = predicted.get("records") if isinstance(predicted.get("records"), list) else []
    remaining = list(expected_rows)
    for row in rows:
        if not isinstance(row, dict):
            result["fp"] += 1
            continue
        match = next((e for e in remaining if record_key(e) == record_key(row)), None)
        if match is None:
            result["fp"] += 1
            continue
        remaining.remove(match)
        result["tp"] += 1
        for field in ("currency", "date", "due_date", "direction", "reference"):
            result["fields"] += 1
            result["fields_ok"] += norm(row.get(field)) == norm(match.get(field))
    result["fn"] += len(remaining)
    return result


PAIRS = (  # (label, tuned result, base result on the same test set); the deployed adapter first
    ("v2 (deployed): eight languages, 13 payment-message formats", "tidelm_ft_eval.json", "tidelm_base_eval.json"),
    ("v3 (experiment, not deployed): two extra tools and more safety phrasings. On v2's test it scored 90.0% exact "
     "plans against v2's 96.7% (it over-chose the lowest-risk preference) and was slower, so v2 stays in use",
     "tidelm_v3_eval.json", "tidelm_base_v3test_eval.json"),
)


def write_report():
    """evidence/ml/tidelm_report.md from whichever evaluation pairs exist (numbers are never typed by hand)."""
    folder = ROOT / "evidence" / "ml"
    rows = [("Valid JSON (plans)", "plan", "valid_json", True), ("Intent accuracy", "plan", "intent_accuracy", True),
            ("Correct tools", "plan", "tool_accuracy", True), ("Exact plan (tools + every argument)", "plan", "exact_plan_accuracy", True),
            ("Record precision", "extract", "record_precision", False), ("Record recall", "extract", "record_recall", False),
            ("Record F1", "extract", "record_f1", False), ("Field accuracy", "extract", "field_accuracy", True),
            ("Injection flag accuracy", "extract", "injection_flag_accuracy", True)]
    fmt = lambda v, p: "—" if v is None else (f"{v * 100:.1f}%" if p else f"{v:.3f}")  # noqa: E731
    lines = ["# TideLM evaluation (held-out test sets)", "",
             "Base model: Qwen3-4B-Instruct-2507 (4-bit, MLX). TideLM: the same model plus Tideway's LoRA adapter "
             "(rank 16, 16 layers). Test examples use counterparty names never seen in training. Synthetic data from "
             "`tideway/ml/tidelm_data.py`; these scores show the method works, not real-world accuracy.", ""]
    for label, tuned_name, base_name in PAIRS:
        try:
            tuned = json.loads((folder / tuned_name).read_text())
            base = json.loads((folder / base_name).read_text())
        except (OSError, ValueError):
            continue
        lines += [f"## {label}", "", f"{tuned['n_plan']} planning and {tuned['n_extract']} extraction examples "
                  f"(`{tuned.get('test_set', 'data/tidelm')}`).", "", "| Metric | Base model | TideLM |", "|---|---|---|"]
        lines += [f"| {name} | {fmt(base[s1][k], p)} | **{fmt(tuned[s1][k], p)}** |" for name, s1, k, p in rows]
        lines += ["", f"Median seconds per answer during evaluation (Apple M4, 16 GB): base {base['median_latency_s']}, "
                  f"TideLM {tuned['median_latency_s']}.", ""]
    lines += ["Remaining errors are mostly a missed preference word or an informal phrase read as a different request. "
              "In the app they cannot cause harm: names are resolved against the ledger, only read/propose tools exist, "
              "every number comes from Tideway's tools, and every action still needs people to approve a signed mandate."]
    (folder / "tidelm_report.md").write_text("\n".join(lines) + "\n")
    print("wrote evidence/ml/tidelm_report.md")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default=None)
    parser.add_argument("--data", default=str(ROOT / "data" / "tidelm"))
    parser.add_argument("--report", action="store_true", help="only rebuild evidence/ml/tidelm_report.md")
    args = parser.parse_args()
    if args.report:
        return write_report()
    from mlx_lm import generate, load
    model, tokenizer = load(BASE_MODEL, adapter_path=args.adapter)
    rows = [json.loads(line) for line in open(Path(args.data) / "test.jsonl")]
    if args.limit:
        rows = rows[:args.limit // 2] + rows[-args.limit // 2:]
    plan_scores, extract_scores, latencies, failures = [], [], [], []
    for row in rows:
        system, user, answer = row["messages"]
        prompt = tokenizer.apply_chat_template([system, user], add_generation_prompt=True, tokenize=False)
        started = time.time()
        text = generate(model, tokenizer, prompt=prompt, max_tokens=400, verbose=False)
        latencies.append(time.time() - started)
        predicted, expected = parse(text), json.loads(answer["content"])
        if "planner" in system["content"]:
            score = score_plan(predicted, expected)
            plan_scores.append(score)
            if not score["exact"] and len(failures) < 12:
                failures.append({"input": user["content"], "expected": expected, "got": text[:300]})
        else:
            extract_scores.append(score_extract(predicted, expected))
    tp = sum(s["tp"] for s in extract_scores)
    fp = sum(s["fp"] for s in extract_scores)
    fn = sum(s["fn"] for s in extract_scores)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    mean = lambda items, key: round(sum(1 for s in items if s[key]) / len(items), 4) if items else None  # noqa: E731
    report = {"model": BASE_MODEL, "adapter": args.adapter, "test_set": str(Path(args.data).relative_to(ROOT)) if Path(args.data).is_relative_to(ROOT) else args.data, "n_plan": len(plan_scores), "n_extract": len(extract_scores),
              "plan": {"valid_json": mean(plan_scores, "valid_json"), "intent_accuracy": mean(plan_scores, "intent"),
                       "tool_accuracy": mean(plan_scores, "tools"), "exact_plan_accuracy": mean(plan_scores, "exact")},
              "extract": {"valid_json": mean(extract_scores, "valid_json"), "record_precision": round(precision, 4),
                          "record_recall": round(recall, 4),
                          "record_f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0,
                          "field_accuracy": round(sum(s["fields_ok"] for s in extract_scores) / max(1, sum(s["fields"] for s in extract_scores)), 4),
                          "injection_flag_accuracy": mean(extract_scores, "suspicious")},
              "median_latency_s": round(sorted(latencies)[len(latencies) // 2], 2), "sample_failures": failures}
    print(json.dumps({k: v for k, v in report.items() if k != "sample_failures"}, indent=1))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
