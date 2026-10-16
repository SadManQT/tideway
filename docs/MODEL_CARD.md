# Tideway model and evidence card

All reported results use synthetic data. They do not estimate real-world lending,
fraud-detection or production accuracy. Application permissions and human approval
remain necessary even when a model produces a valid answer.

## TidePay

Tideway's pure-Python softmax classifier predicts five invoice-lateness bands from
14 features. The shipped artifact remains `tideway/ml/tidepay_model.json`, with
its historical observation retained at `evidence/ml/tidepay_report.json`. The
historical prior baseline's MAE used the test delay mean; its split also lacked
global date cutoffs and a payment-label maturity purge. Those observations are
preserved rather than presented as a clean chronological benchmark. Legacy
training reruns now require training delays for the prior day forecast.

The versioned **v2 audit benchmark**, separate from the shipped artifact, uses
7,745 matured training invoices before 1 March 2025, 1,433 validation invoices
before 1 July and 2,376 identical final-test invoices from 40 existing synthetic
SMEs. Training/validation invoices unpaid at the next period's start are purged
(1,119/1,071); all split rows, including exclusions, are saved. Priors, scaling
and representative bucket means are fitted only from training rows. Local-only
models use their own SME's training statistics. Issue-time features use only
already settled history, including earlier held-out invoices once observed;
weights/statistics stay frozen. No calibration or test-set tuning is fitted.

| V2 model | MAE days | Natural-log loss | Brier, sum over 5 classes |
|---|---:|---:|---:|
| Training prior | 11.9856 | 1.5882 | 0.7936 |
| Fixed customer-history heuristic | 7.4107 | 1.5688 | 0.7905 |
| Local-only | 7.2152 | 1.2329 | 0.6407 |
| Simulated federated | 6.9568 | 1.0727 | 0.5777 |
| Pooled centralised | 6.9448 | 1.0927 | 0.5855 |

Each denominator is 2,376 test invoices. MAE measures the expected day forecast;
log loss averages `-ln(p_true)` and Brier averages the **sum**, not mean, of five
squared class errors (range 0–2). The heuristic's day mean and fixed smoothed
bucket probabilities are separate forecasts; its coarse probabilities partly
explain its worse log loss. Federated minus heuristic MAE is -0.4539 days, with
95% paired business-cluster bootstrap interval [-0.6880, -0.2568]. Seven of 40
SMEs have worse MAE; pooled centralised MAE is slightly better overall.

The reliability plot defines the event as >7 days late, with ten equal-width
probability bins, counts and descriptive Wilson intervals. Per-business, sector,
training-size, payment-term and relative-invoice-size results, SME-cluster metric
intervals, per-example predictions, class balance, split/dataset hashes and
machine/configuration information are saved in
[`evidence/upgrade-v1/tidepay/`](../evidence/upgrade-v1/tidepay/report.md).
See [the full audit](TIDEPAY_EVALUATION_V2.md) for definitions and caveats.
The test covers one synthetic generator seed and existing businesses/customers;
there are no cold-start test customers. Maturity purging induces selection near
boundaries. These scores are neither production generalisation nor calibrated
cash-risk probabilities, and do not automatically describe the shipped model.

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

The Upgrade B runtime adds a two-selection rescue loop: the installed model
first selects read-only tools, then consumes deterministic observed results
before selecting a bounded proposal. The visible trace distinguishes
model-selected calls from deterministic preflight checks; public explanations
are composed from tool facts and do not expose or invent hidden thoughts.
Whole-plan validation checks roles, exact ledger names, currencies, units and
dates before any selected tool runs; unknown names require clarification.

This new loop has **no new real-model quality measurement**. On the current
macOS arm64/Python 3.14.7 environment, mlx-lm, the released adapter and cached base
weights are unavailable, so device verification remains outstanding. Historical
released v2 scores do not validate this loop or an arbitrary compatible local
model. `python3 scripts/smoke_reasoning.py` records actual availability and exits
2 when unavailable; `--injected` separately runs containment examples using
injected selections. Evidence is under `evidence/upgrade-v1/model/`, with
procedure and limits in [MODEL_REASONING_V2.md](MODEL_REASONING_V2.md).

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
`python scripts/evaluate.py`. Run the audited prediction benchmark with
`python scripts/evaluate_tidepay_v2.py`; it has no optional dependencies and
writes its model only into versioned evidence. `scripts/smoke_models.py` requires Apple Silicon.
For stronger generalisation evidence, collect consented, anonymised SME
feedback and author new scenarios and message phrasings before evaluating them.
Do not add invented users or promote planned experiments to measured results.
