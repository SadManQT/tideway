# Tideway model and evidence card

All reported results use synthetic data. They do not estimate real-world lending,
fraud-detection or production accuracy. Application permissions and human approval
remain necessary even when a model produces a valid answer.

## TidePay

Tideway's pure-Python softmax classifier predicts five invoice-lateness bands from
14 features. The recorded experiment compares prior, heuristic, local-only,
simulated federated and pooled models on later invoices from 40 synthetic SMEs.
See `evidence/ml/tidepay_report.json` for sample sizes and measured metrics.

The federated experiment runs in one process. That process holds every client's
synthetic rows, pools training features to fit the scaler and creates predictable
pairwise masks. Masks cancel arithmetically; this is not a cryptographic secure
aggregation deployment. No protection against a curious server, collusion,
client dropout or gradient reconstruction is established. Production federated
learning and privacy guarantees remain future work.

## TideLM v2

This is a Tideway-trained LoRA adapter on Qwen3-4B-Instruct-2507, converted to
4-bit MLX format by mlx-community. The third-party base model is Apache-2.0.
We trained the adapter, not the base model. The public adapter release is
`https://github.com/SadManQT/tideway/releases/tag/tidelm-v2`.

The v2 evaluation uses 300 planning and 200 extraction examples. Names are held
out, while training and test share generated template families. Exact plans:
96.7%; intent: 99%; extraction F1: 0.969; injection-flag accuracy: 98.5%.
These are template-based synthetic benchmark results, not a test of arbitrary
real customer messages. Raw base and tuned outputs are in `evidence/ml/`.
The v3 experiment performed worse on the v2 planning test and is not deployed.

TideLM selects allow-listed tools and drafts records. It has no approval or
execution tool. Validators resolve names and arguments; the application writes
answers from tool output. People confirm extracted records before saving them.

## TideVision

TideVision integrates the third-party Qwen2.5-VL-3B-Instruct model, converted by
mlx-community, without a Tideway fine-tune. The base model has the Qwen Research
license, not the application's MIT license. See `THIRD_PARTY_NOTICES` and
`licenses/Qwen2.5-VL-3B-Research.txt`. Keep research/evaluation use and any future
commercial deployment distinct.

The saved device smoke run found date-format and bill-classification problems.
Regression tests cover the code corrections. A post-fix Apple Silicon model run
is still outstanding, so the saved pre-fix observation is retained unchanged.
No post-fix device accuracy or general receipt-reading accuracy is claimed.

## Supported execution paths

| Path | Requirements | Verified scope |
|---|---|---|
| Deterministic assistant and TidePay | Python 3.11+; Windows, Linux or macOS | Offline automated suite and browser demo |
| TideLM | Apple Silicon, mlx-lm, v2 adapter, cached base model | Historical Apple Silicon evaluation; guarded runtime tests with injected outputs |
| TideVision | Apple Silicon, mlx-vlm and Pillow, cached model | Historical pre-fix device observation and guarded regression tests |
| Optional compatible local server | Windows, macOS or Linux, installed model, literal loopback endpoint | Transport and safety tests; model quality unbenchmarked |
| Optional cloud assistant | User key, network and per-message consent | Simulated transport tests; no measured live-provider run |

First-time downloads require network access. Cached local inference does not send
ledger records to a provider. Local processing still depends on the security of
the user's host. The Windows demo explicitly uses the deterministic assistant.

## Reproduce and extend

Run `python -m unittest discover -s tests -v`, `python -m tideway.selftest` and
`python scripts/evaluate.py`. `scripts/smoke_models.py` requires Apple Silicon.
For stronger generalisation evidence, collect consented, anonymised SME
feedback and author new scenarios and message phrasings before evaluating them.
Do not add invented users or promote planned experiments to measured results.
