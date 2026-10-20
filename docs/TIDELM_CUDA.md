# TideLM on a consumer NVIDIA GPU

TideLM was first trained with MLX on Apple Silicon. This path trains the same
LoRA adapter on Windows or Linux with PyTorch + PEFT on a single consumer GPU,
and evaluates it on the same held-out test set with the same scoring code
(`tideway/ml/tidelm_eval.py`, imported rather than rewritten).

## Measured run (evidence: `evidence/ml-cuda/`)

| Setting | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 3060 Ti, 8 GB (peak use 5.2 GB) |
| Base model | `Qwen/Qwen3-1.7B` at revision `70d244cc`, bf16 |
| Adapter | LoRA rank 16, scale 20, last 16 layers, ~10M trainable parameters |
| Training | 450 iterations, batch 4 (1,800 examples seen), **7.3 minutes** |
| Validation loss | 0.465 → 0.0085 |
| Test set | full held-out split: 300 planning + 200 extraction examples, counterparty names unseen in training |

| Held-out metric | Base Qwen3-1.7B | TideLM (CUDA) |
|---|---|---|
| Exact tool plan (every tool and argument) | 21.3% | **92.7%** |
| Intent understood | 13.3% | **94.7%** |
| Correct tools chosen | 37.3% | **95.7%** |
| Record extraction F1 | 0.304 | **0.988** |
| Field accuracy | 67.5% | **99.5%** |
| Hidden-instruction (injection) flag accuracy | 62.0% | **100%** |

Greedy decoding, Qwen3 thinking disabled, batched generation (about 0.25 s per
example). Raw outputs for every example are in `evidence/ml-cuda/*_outputs.jsonl`
and adapter SHA-256 hashes are in `tidelm_cuda_eval.json`.

## Reproduce

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install transformers peft accelerate safetensors
python -m tideway.ml.tidelm_data                    # writes data/tidelm/{train,valid,test}.jsonl
python -m tideway.ml.tidelm_cuda_train              # adapter -> ~/tideway-models/tidelm-cuda-adapter
python -m tideway.ml.tidelm_cuda_eval               # base model
python -m tideway.ml.tidelm_cuda_eval --adapter ~/tideway-models/tidelm-cuda-adapter
```

To use it from the app, serve it on the loopback interface and point Tideway's
local-model setting at it:

```bash
python scripts/serve_tidelm_cuda.py --port 8796
TIDEWAY_LOCAL_MODEL_URL=http://127.0.0.1:8796/v1 TIDEWAY_LOCAL_TEXT_MODEL=tidelm-cuda-qwen3-1.7b python run.py
```

The model still has no authority: every plan passes the same validator, replies
are written from tool output, and extracted records stay drafts until a person
confirms them.

## Scope

Synthetic, generated training and test data; these figures measure the task the
generator defines, not real-world accuracy. The base differs from the released
MLX adapter (Qwen3-4B), so the two sets of scores are separate evaluations. The
weights are not committed to the repository.
