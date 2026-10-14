# TideLM evaluation (held-out test sets)

Base model: Qwen3-4B-Instruct-2507 (4-bit, MLX). TideLM: the same model plus Tideway's LoRA adapter (rank 16, 16 layers). Test examples use counterparty names never seen in training. Synthetic data from `tideway/ml/tidelm_data.py`; these scores show the method works, not real-world accuracy.

## v2: eight languages, 13 payment-message formats

300 planning and 200 extraction examples (`data/tidelm`).

| Metric | Base model | TideLM |
|---|---|---|
| Valid JSON (plans) | 100.0% | **100.0%** |
| Intent accuracy | 20.0% | **99.0%** |
| Correct tools | 63.0% | **99.0%** |
| Exact plan (tools + every argument) | 26.7% | **96.7%** |
| Record precision | 0.834 | **0.986** |
| Record recall | 0.834 | **0.953** |
| Record F1 | 0.834 | **0.969** |
| Field accuracy | 80.5% | **99.3%** |
| Injection flag accuracy | 91.5% | **98.5%** |

Median seconds per answer during evaluation (Apple M4, 16 GB): base 3.79, TideLM 2.84.

Remaining errors are mostly a missed preference word or an informal phrase read as a different request. In the app they cannot cause harm: names are resolved against the ledger, only read/propose tools exist, every number comes from Tideway's tools, and every action still needs people to approve a signed mandate.
