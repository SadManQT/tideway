"""Evaluate TideLM on CUDA (base model vs the CUDA-trained LoRA adapter) on the held-out test set.

Same test file, same parser and the same scoring functions as tideway/ml/tidelm_eval.py (imported, not
rewritten); only the generation backend differs (PyTorch/transformers instead of MLX). Greedy decoding,
max 400 new tokens, Qwen3 thinking disabled. Generation is batched (left padding) for speed, so the reported
per-example time is the batch time divided by the batch size, not a single-request latency.

Run (repo root, ML venv):
  python -m tideway.ml.tidelm_cuda_eval --out evidence/ml-cuda/base_eval.json
  python -m tideway.ml.tidelm_cuda_eval --adapter %USERPROFILE%/tideway-models/tidelm-cuda-adapter --out evidence/ml-cuda/tidelm_cuda_eval.json
--limit N keeps tidelm_eval.py's convention: the first N/2 (planning) and last N/2 (extraction) test rows.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from .tidelm_cuda_common import (DEFAULT_BASE, DEFAULT_REVISION, ROOT, adapter_hashes, chat_prompt, data_hashes,
                                 environment, load_model, read_jsonl, stop_ids)
from .tidelm_eval import parse, score_extract, score_plan


def generate_batch(model, tokenizer, prompts, max_new_tokens):
    import torch
    encoded = tokenizer(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
    with torch.no_grad():
        output = model.generate(**encoded, max_new_tokens=max_new_tokens, do_sample=False, eos_token_id=stop_ids(tokenizer),
                                pad_token_id=tokenizer.pad_token_id)
    new = output[:, encoded["input_ids"].shape[1]:]
    return [tokenizer.decode(row, skip_special_tokens=True) for row in new], [int((row != tokenizer.pad_token_id).sum()) for row in new]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=DEFAULT_BASE)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--data", default=str(ROOT / "data" / "tidelm"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-new-tokens", type=int, default=400)
    parser.add_argument("--no-merge", action="store_true", help="keep LoRA unmerged (slower)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--outputs", default=None, help="raw outputs JSONL (default: <out>_outputs.jsonl)")
    args = parser.parse_args()

    from tideway.tidelm import parse_json as app_parse_json
    started = time.time()
    model, tokenizer = load_model(args.model, args.revision, args.adapter, merge=not args.no_merge)
    tokenizer.padding_side = "left"
    load_seconds = time.time() - started
    rows = read_jsonl(Path(args.data) / "test.jsonl")
    indices = list(range(len(rows)))
    if args.limit:
        indices = indices[:args.limit // 2] + indices[-args.limit // 2:]
    prompts = {i: chat_prompt(tokenizer, rows[i]["messages"][0]["content"], rows[i]["messages"][1]["content"]) for i in indices}
    # Batch similar-length prompts of the same skill together; results are restored to test-file order.
    order = sorted(indices, key=lambda i: ("planner" not in rows[i]["messages"][0]["content"], len(prompts[i])))
    texts, tokens, per_example = {}, {}, {}
    gen_started = time.time()
    for b in range(0, len(order), args.batch_size):
        chunk = order[b:b + args.batch_size]
        t0 = time.time()
        outs, counts = generate_batch(model, tokenizer, [prompts[i] for i in chunk], args.max_new_tokens)
        elapsed = time.time() - t0
        for i, text, count in zip(chunk, outs, counts):
            texts[i], tokens[i], per_example[i] = text, count, elapsed / len(chunk)
        print(f"{b + len(chunk)}/{len(order)} batch {elapsed:.1f}s", flush=True)
    gen_seconds = time.time() - gen_started

    plan_scores, extract_scores, failures, raw = [], [], [], []
    for i in indices:
        system, user, answer = rows[i]["messages"]
        text = texts[i]
        predicted, expected = parse(text), json.loads(answer["content"])
        if "planner" in system["content"]:
            kind = "plan"
            score = score_plan(predicted, expected)
            score["app_parser_accepts"] = app_parse_json(text) is not None
            plan_scores.append(score)
            if not score["exact"] and len(failures) < 12:
                failures.append({"input": user["content"], "expected": expected, "got": text[:300]})
        else:
            kind = "extract"
            score = score_extract(predicted, expected)
            extract_scores.append(score)
        raw.append({"index": i, "skill": kind, "input": user["content"], "output": text, "new_tokens": tokens[i], "score": score})
    # Aggregation identical to tidelm_eval.main().
    tp = sum(s["tp"] for s in extract_scores)
    fp = sum(s["fp"] for s in extract_scores)
    fn = sum(s["fn"] for s in extract_scores)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    mean = lambda items, key: round(sum(1 for s in items if s[key]) / len(items), 4) if items else None  # noqa: E731
    data_path = Path(args.data).resolve()
    report = {"backend": "cuda-transformers", "model": args.model, "revision": args.revision, "adapter": args.adapter,
              "adapter_sha256": adapter_hashes(args.adapter) if args.adapter else None, "merged_lora": bool(args.adapter) and not args.no_merge,
              "test_set": str(data_path.relative_to(ROOT)) if data_path.is_relative_to(ROOT) else str(data_path),
              "data_sha256": data_hashes(args.data), "subset": {"limit": args.limit or None, "indices": "all" if not args.limit else
                                                                  f"first {args.limit // 2} + last {args.limit // 2} rows of test.jsonl"},
              "decoding": {"greedy": True, "max_new_tokens": args.max_new_tokens, "batch_size": args.batch_size, "padding": "left",
                           "enable_thinking": False},
              "n_plan": len(plan_scores), "n_extract": len(extract_scores),
              "plan": {"valid_json": mean(plan_scores, "valid_json"), "intent_accuracy": mean(plan_scores, "intent"),
                       "tool_accuracy": mean(plan_scores, "tools"), "exact_plan_accuracy": mean(plan_scores, "exact"),
                       "app_parser_accepts": mean(plan_scores, "app_parser_accepts")},
              "extract": {"valid_json": mean(extract_scores, "valid_json"), "record_precision": round(precision, 4),
                          "record_recall": round(recall, 4),
                          "record_f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0,
                          "field_accuracy": round(sum(s["fields_ok"] for s in extract_scores) / max(1, sum(s["fields"] for s in extract_scores)), 4),
                          "injection_flag_accuracy": mean(extract_scores, "suspicious")},
              "median_batched_seconds_per_example": round(statistics.median(per_example.values()), 3),
              "generation_seconds": round(gen_seconds, 1), "load_seconds": round(load_seconds, 1),
              "mean_new_tokens": round(statistics.mean(tokens.values()), 1), "environment": environment(),
              "sample_failures": failures}
    print(json.dumps({k: v for k, v in report.items() if k not in ("sample_failures", "environment")}, indent=1))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    outputs = Path(args.outputs) if args.outputs else out.with_name(out.stem + "_outputs.jsonl")
    with open(outputs, "w", encoding="utf-8") as handle:
        for row in raw:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {out} and {outputs}")


if __name__ == "__main__":
    main()
