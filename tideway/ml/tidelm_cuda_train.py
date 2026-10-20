"""Train the TideLM LoRA adapter on an NVIDIA GPU with PyTorch + PEFT (Windows or Linux).

The CUDA counterpart of `python -m mlx_lm lora --config tideway/ml/tidelm_lora.yaml` (Apple Silicon).
Hyperparameters mirror tidelm_lora.yaml: LoRA rank 16, scale 20 (PEFT lora_alpha = 20 * 16), dropout 0.05,
on every linear projection (q/k/v/o/gate/up/down) of the last 16 transformer layers; batch 4, 450 iterations,
Adam at a constant 1e-4, max sequence 1024, loss on the assistant answer only, seed 11, gradient checkpointing.
Differences (recorded in the train log): bf16 weights instead of 4-bit, gradient-norm clipping at 1.0, and
batches drawn like mlx_lm (length-sorted, batch order shuffled) with a fixed seeded 100-example validation set.

The adapter is written OUTSIDE the repository (default ~/tideway-models/tidelm-cuda-adapter); weights are never
committed. Only data/tidelm/train.jsonl (validation loss: valid.jsonl) is read; the test split is never touched.

Run (from the repo root, in the ML venv):
  python -m tideway.ml.tidelm_cuda_train --model Qwen/Qwen3-1.7B --out %USERPROFILE%/tideway-models/tidelm-cuda-adapter
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

from .tidelm_cuda_common import (DEFAULT_ADAPTER, DEFAULT_BASE, DEFAULT_REVISION, EVIDENCE, ROOT, adapter_hashes,
                                 chat_prompt, data_hashes, environment, read_jsonl)

TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def encode(tokenizer, row, max_seq):
    system, user, answer = row["messages"]
    prompt = tokenizer(chat_prompt(tokenizer, system["content"], user["content"]), add_special_tokens=False)["input_ids"]
    completion = tokenizer(answer["content"] + "<|im_end|>", add_special_tokens=False)["input_ids"]
    ids = (prompt + completion)[:max_seq]
    labels = ([-100] * len(prompt) + completion)[:max_seq]
    return ids, labels


def collate(batch, pad_id, device):
    import torch
    width = max(len(ids) for ids, _ in batch)
    ids = torch.full((len(batch), width), pad_id, dtype=torch.long)
    labels = torch.full((len(batch), width), -100, dtype=torch.long)
    mask = torch.zeros((len(batch), width), dtype=torch.long)
    for i, (row_ids, row_labels) in enumerate(batch):
        ids[i, :len(row_ids)] = torch.tensor(row_ids)
        labels[i, :len(row_labels)] = torch.tensor(row_labels)
        mask[i, :len(row_ids)] = 1
    return ids.to(device), labels.to(device), mask.to(device)


def masked_loss(model, ids, labels, mask):
    """Mean cross-entropy over answer tokens only. The LM head runs only on answer positions, which keeps
    the 152k-vocabulary logits small enough for an 8 GB card."""
    import torch.nn.functional as F
    inner = model.get_base_model()
    hidden = inner.model(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state
    hidden, targets = hidden[:, :-1], labels[:, 1:]
    selected = targets != -100
    logits = inner.lm_head(hidden[selected]).float()
    return F.cross_entropy(logits, targets[selected], reduction="sum"), int(selected.sum())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=DEFAULT_BASE, help="Hugging Face id or local directory of the base model")
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--data", default=str(ROOT / "data" / "tidelm"))
    parser.add_argument("--out", default=str(DEFAULT_ADAPTER))
    parser.add_argument("--log", default=str(EVIDENCE / "train_log.json"))
    parser.add_argument("--iters", type=int, default=450)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--scale", type=float, default=20.0)
    parser.add_argument("--dropout", type=float, default=0.05)
    parser.add_argument("--num-layers", type=int, default=16)
    parser.add_argument("--max-seq", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--clip", type=float, default=1.0)
    parser.add_argument("--steps-per-report", type=int, default=25)
    parser.add_argument("--steps-per-eval", type=int, default=150)
    parser.add_argument("--val-examples", type=int, default=100)
    parser.add_argument("--max-minutes", type=float, default=40.0, help="stop early (and say so) after this much training time")
    args = parser.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    started = time.time()
    local = Path(args.model).exists()
    kwargs = {} if local else {"revision": args.revision}
    tokenizer = AutoTokenizer.from_pretrained(args.model, **kwargs)
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16, **kwargs).to("cuda")
    model.config.use_cache = False
    layers = model.config.num_hidden_layers
    lora = LoraConfig(r=args.rank, lora_alpha=args.scale * args.rank, lora_dropout=args.dropout, target_modules=TARGETS,
                      layers_to_transform=list(range(layers - args.num_layers, layers)), bias="none", task_type="CAUSAL_LM")
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model = get_peft_model(model, lora)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    load_seconds = time.time() - started

    train_rows = read_jsonl(Path(args.data) / "train.jsonl")
    valid_rows = read_jsonl(Path(args.data) / "valid.jsonl")
    train = [encode(tokenizer, row, args.max_seq) for row in train_rows]
    val_pick = sorted(random.Random(args.seed).sample(range(len(valid_rows)), min(args.val_examples, len(valid_rows))))
    valid = [encode(tokenizer, valid_rows[i], args.max_seq) for i in val_pick]
    truncated = sum(1 for row in train_rows if len(encode(tokenizer, row, 10 ** 6)[0]) > args.max_seq)

    # mlx_lm-style batching: sort by length, cut into batches, shuffle batch order each epoch.
    order = sorted(range(len(train)), key=lambda i: len(train[i][0]))
    batches = [order[i:i + args.batch_size] for i in range(0, len(order) - args.batch_size + 1, args.batch_size)]
    rng = random.Random(args.seed)
    schedule = []
    while len(schedule) < args.iters:
        epoch = list(range(len(batches)))
        rng.shuffle(epoch)
        schedule += epoch
    schedule = schedule[:args.iters]

    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.Adam(params, lr=args.lr)
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id

    def validate():
        model.eval()
        loss_sum, count = 0.0, 0
        with torch.no_grad():
            for i in range(0, len(valid), args.batch_size):
                loss, n = masked_loss(model, *collate(valid[i:i + args.batch_size], pad_id, "cuda"))
                loss_sum, count = loss_sum + float(loss), count + n
        model.train()
        return round(loss_sum / max(1, count), 4)

    log = {"what": "TideLM LoRA trained with PyTorch/PEFT on CUDA", "base_model": args.model if local else args.model,
           "base_model_hf_id": DEFAULT_BASE if local else args.model, "base_revision": args.revision,
           "config": {k: v for k, v in vars(args).items() if k not in ("log",)},
           "lora": {"rank": args.rank, "lora_alpha": args.scale * args.rank, "scaling": args.scale, "dropout": args.dropout,
                    "target_modules": TARGETS, "layers": [layers - args.num_layers, layers - 1], "num_hidden_layers": layers},
           "differences_from_mlx_yaml": ["bf16 base weights (the MLX run used a 4-bit 4B model)",
                                         "different base: Qwen3-1.7B (MLX: Qwen3-4B-Instruct-2507)",
                                         f"gradient-norm clipping at {args.clip} (mlx_lm default: none)",
                                         f"validation loss on a fixed seeded sample of {len(valid)} valid examples"],
           "trainable_params": trainable, "total_params": total, "data_sha256": data_hashes(args.data),
           "n_train_examples": len(train), "n_train_truncated": truncated, "n_valid_used": len(valid),
           "valid_indices_sample_head": val_pick[:10], "examples_seen": args.iters * args.batch_size,
           "epochs_equivalent": round(args.iters * args.batch_size / len(train), 3), "load_seconds": round(load_seconds, 1),
           "reports": [], "validation": [], "environment": environment()}
    Path(args.log).parent.mkdir(parents=True, exist_ok=True)

    def write_log():
        Path(args.log).write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")

    torch.cuda.reset_peak_memory_stats()
    model.train()
    log["validation"].append({"iter": 0, "val_loss": validate()})
    print(f"trainable {trainable / 1e6:.2f}M / {total / 1e6:.0f}M; iter 0 val {log['validation'][-1]['val_loss']}", flush=True)
    write_log()
    train_started = time.time()
    window_loss, window_tokens, window_time, completed = 0.0, 0, time.time(), 0
    stopped_early = None
    for step, batch_index in enumerate(schedule, 1):
        ids, labels, mask = collate([train[i] for i in batches[batch_index]], pad_id, "cuda")
        loss_sum, n = masked_loss(model, ids, labels, mask)
        (loss_sum / max(1, n)).backward()
        grad_norm = float(torch.nn.utils.clip_grad_norm_(params, args.clip)) if args.clip else None
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        window_loss, window_tokens, completed = window_loss + float(loss_sum), window_tokens + n, step
        if not math.isfinite(float(loss_sum)):
            stopped_early = f"non-finite loss at iter {step}"
            break
        if step % args.steps_per_report == 0 or step == len(schedule):
            elapsed = time.time() - window_time
            entry = {"iter": step, "train_loss": round(window_loss / max(1, window_tokens), 4), "grad_norm": round(grad_norm, 4) if grad_norm else None,
                     "answer_tokens": window_tokens, "seconds": round(elapsed, 1),
                     "elapsed_min": round((time.time() - train_started) / 60, 2),
                     "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 2 ** 30, 2)}
            log["reports"].append(entry)
            print(json.dumps(entry), flush=True)
            window_loss, window_tokens, window_time = 0.0, 0, time.time()
        if step % args.steps_per_eval == 0 or step == len(schedule):
            log["validation"].append({"iter": step, "val_loss": validate()})
            print(f"iter {step} val {log['validation'][-1]['val_loss']}", flush=True)
            if step != len(schedule):
                model.save_pretrained(str(Path(args.out) / f"checkpoint-{step}"))
            write_log()
        if (time.time() - train_started) / 60 > args.max_minutes:
            stopped_early = f"time cap {args.max_minutes} min reached after iter {step}"
            break
    if stopped_early and (not log["validation"] or log["validation"][-1]["iter"] != completed):
        log["validation"].append({"iter": completed, "val_loss": validate()})
    train_seconds = time.time() - train_started
    model.peft_config["default"].base_model_name_or_path = log["base_model_hf_id"]
    model.peft_config["default"].revision = args.revision
    model.save_pretrained(args.out)
    log.update(iters_completed=completed, stopped_early=stopped_early, train_seconds=round(train_seconds, 1),
               train_minutes=round(train_seconds / 60, 2), total_wall_seconds=round(time.time() - started, 1),
               peak_vram_gb=round(torch.cuda.max_memory_allocated() / 2 ** 30, 2), adapter_dir=str(args.out),
               adapter_sha256=adapter_hashes(args.out))
    write_log()
    print(f"saved {args.out} after {completed} iters in {train_seconds / 60:.1f} min; {log['adapter_sha256']}", flush=True)


if __name__ == "__main__":
    main()
