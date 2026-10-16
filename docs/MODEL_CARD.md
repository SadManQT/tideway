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

The **exact deployed artifact** now has a separate fresh-cohort evaluation:
**7,427 invoices from 80 new synthetic SMEs across four seeds**, issued
1 November 2025–29 April 2026, with all labels matured by the fixed
15 October 2026 ascertainment date. The frozen shipped weights have SHA-256
`00639d9b3e408f1a51df20130e804db2f8a031772a772d706f09e6a7428aa466`.
No training, calibration or model selection uses the fresh cohorts. Historical
training statistics are reconstructed and matched exactly before fitting the
frozen prior baseline; none of its statistics come from the test outcomes.

| Fresh-cohort frozen predictor | MAE days | Natural-log loss | Sum Brier |
|---|---:|---:|---:|
| Exact deployed artifact | 8.5585 | 1.2850 | 0.6712 |
| Existing v2 audit artifact | 8.5754 | 1.2799 | 0.6726 |
| Historical training prior | 11.7453 | 1.5769 | 0.7871 |
| Fixed customer-history heuristic | 10.2296 | 1.7931 | 0.9156 |

These scores use identical invoices and **production payment-date-ordered
issue-time history**. Training histories were ordered by issuance instead; the
evaluation follows production and tests agreement with the real prediction
function. MAE uses app precision (0.1 day); probability scores use the raw model
probabilities before display rounding. Earlier outcomes may enter later
features once observed, with weights/statistics frozen. Forecasts made after
issuance, including conditional overdue forecasts, remain outside this test.

Cold starts remain a weakness: 2,640 invoices without settled customer history
have deployed MAE **11.6254 days** and log loss **1.6161**, versus the frozen
prior's **1.5932** log loss. With history, deployed MAE is **6.8671** over 4,787
invoices. The overall deployed MAE 95% business-cluster interval is
**[8.0999, 9.0233]**; the MAE difference from the audit artifact crosses zero,
and the audit artifact has slightly better overall log loss. No automatic
artifact replacement is justified by these observations.

See [`DEPLOYED_MODEL_EVALUATION.md`](DEPLOYED_MODEL_EVALUATION.md) and
[`evidence/readiness-v3/tidepay/report.json`](../evidence/readiness-v3/tidepay/report.json)
for raw data, per-example predictions, class balances, hashes, all reliability
bins and subgroups. The Overview card exposes this report separately from the
earlier benchmark, and suppresses its scores if the report is missing, invalid
or its artifact hash differs from the installed weights. “Verified” here means
local report integrity and artifact-byte agreement, not independent model
certification. These remain retrospective synthetic cohorts from the same
generator family, not real users or an independently administered blind trial.

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

The released MLX adapter has **no post-change device measurement of this loop**. The historical macOS arm64/Python 3.14.7 availability run lacked mlx-lm, the adapter and cached base weights and attempted zero real generations. Historical released v2 scores do not validate this loop or an arbitrary compatible local model. The later real Windows compatible-model results below are a separate identity and evidence class. `python3 scripts/smoke_reasoning.py` records availability and exits 2 when unavailable; `--injected` separately runs containment examples. Historical evidence is retained under `evidence/upgrade-v1/model/`, with current procedure and limits in [MODEL_REASONING_V2.md](MODEL_REASONING_V2.md).

## Optional compatible GGUF text models

The separately provisioned helper `scripts/local_demo_model.py` offers two profiles; neither contains a Tideway fine-tune or the released MLX adapter:

| Profile | Alias/artifact | Download bytes |
|---|---|---:|
| `compact` (default) | `Qwen2.5-1.5B-Instruct-Q4_K_M`, official Qwen GGUF | 1,117,320,736 |
| `qwen3-4b` | `Qwen3-4B-Instruct-2507-Q4_K_M`, Unsloth GGUF conversion | 2,497,281,120 |

Both upstream model cards identify Apache-2.0; [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES) links their provenance. Immutable revisions, exact filenames, sizes and SHA-256 pins are in the helper, with a separate pinned llama.cpp runtime. No weights/native runtimes are bundled. `--cache-dir` explicitly selects storage outside the default ignored `models/local-demo/`. Windows x64 and macOS arm64/x64 provisioning paths are defined, but native Mac helper execution was not run here. Hardened Mac TAR extraction requires Python 3.11.11+.

Real Windows 11 x64 / Python 3.13.7 inference with the 4B profile and `TIDEWAY_LOCAL_STRUCTURED_PLANS=1` matched [6/6 authored requests](../evidence/readiness-v2/model/qwen3-final-smoke.json) and [12/12 expanded authored requests](../evidence/readiness-v2/model/qwen3-final-expanded.json), completing seven and fourteen generations respectively. Both final reports recorded zero executions and zero mandates issued. These overlapping synthetic smoke sets measure expected tool coverage; they are not a sealed accuracy benchmark, MLX adapter evaluation or proof of safety. The final evidence preserves raw outputs and timings. The runtime label remains **unbenchmarked**.

Earlier compact configurations matched **3/6, 2/6 and 4/6**, and the initial 4B run matched **5/6**. Failures were retained rather than replaced; see the full [run history](MODEL_REASONING_V2.md#evidence-actually-recorded). Prompt/schema revisions used observations from these cases, which limits generalisation claims. No arbitrary-language, receipt-extraction or cross-device quality result follows from these request sets.

Structured planning is opt-in and off by default. Supporting local servers receive a scoped JSON Schema for tool/argument shape; unsupported servers fail without an unconstrained retry. The same role, name, amount, date and approval checks remain authoritative even when the model produces schema-valid output. See [SETUP_WINDOWS_MAC.md](SETUP_WINDOWS_MAC.md) for explicit provisioning and reproduction commands.

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
| Optional compatible local server | Windows, macOS or Linux, installed model, literal loopback endpoint | Transport/guard tests; authored Windows Qwen3 4B text smoke 6/6 and expanded 12/12, not a general benchmark |
| Optional cloud assistant | User key, network and per-message consent | Simulated transport tests; no measured live-provider run |

First-time downloads require network access. The helper's cached inference is local; independently installed compatible servers must be trusted not to forward input elsewhere, which Tideway's loopback check cannot audit. Local processing depends on host security. The default Windows path remains deterministic unless a local model is explicitly configured. Post-change Apple Silicon TideLM and post-fix vision verification remain outstanding.

## Reproduce and extend

Run `python -m unittest discover -s tests -v`, `python -m tideway.selftest` and
`python scripts/evaluate.py`. Run the audited prediction benchmark with
`python scripts/evaluate_tidepay_v2.py`; it has no optional dependencies and
writes its model only into versioned evidence. `scripts/smoke_models.py` requires Apple Silicon.
For stronger generalisation evidence, collect consented, anonymised SME
feedback and author new scenarios and message phrasings before evaluating them.
Do not add invented users or promote planned experiments to measured results.
