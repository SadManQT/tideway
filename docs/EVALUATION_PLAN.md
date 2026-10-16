# Tideway: evaluation plan

This plan separates what we have **measured** (deterministic, local, reproducible) from what is **planned** (needs a live provider, real people or the organiser). Nothing in the "planned" column may be reported as a result until it has been run and the raw evidence saved.

## 1. Measured today (reproducible)

`python3 scripts/evaluate.py` runs `tideway.selftest` (every case on a fresh in-memory copy of the synthetic fixtures) and writes `evidence/results.csv`, `evidence/run-log.jsonl` and `evidence/verification-summary.json`. `python3 -m unittest discover -s tests -v` runs the offline suite (latest count in `evidence/test-summary.json`). `node scripts/capture_screens.mjs` drives headless Chrome through the full story and fails on any page error.

| Dimension (roadmap target) | What we run | Result today |
|---|---|---|
| Task completion | 5 end-to-end task cases (payroll rescue, counter-offer, re-plan after refusal, honest failure, delegated reminders) | 5/5 |
| Permission safety | Authorisation, mandate, delegation and kill-switch attacks (13 cases) | 13/13 blocked, zero unauthorised state change |
| Prompt injection | Poisoned record text, hijacked model, hidden Unicode (3 cases) | 3/3 |
| Payee fraud | Changed bank details, look-alike payee, callback rules, separation of duties (4 cases) | 4/4 |
| Isolation, policy, audit, hallucination, resource | Cross-business approval, payroll protection, audit tamper and truncation, ungrounded numbers, burst requests (5 cases) | 5/5 |
| Retry and replay | Same key replays the receipt; new key on consumed mandate refused | included above |
| Money arithmetic | Exact minor-unit parsing, Shapla projection (-1,000,000 minor on 2026-10-31, shortfall 3,000,000), 2%/20-day discount = 3,724 bps APR | unit-tested |
| Determinism | Same records and seed give identical Monte Carlo output | unit-tested |

Total: **30/30 cases, 0 attacks not blocked.** Assumptions: worst-case hijacked model and rubber-stamp human; synthetic fixtures; one run per case. This is evidence for these cases only, not proof of security.

## 2. Product-level scenario comparison

`python scripts/evaluate_scenarios.py` compares a fixed largest-permitted-bill deferral rule against the unchanged Tideway optimiser on 20 authored opening-cash perturbations of the three existing fixtures. The rule finds a feasible cash path in 10/20 and Tideway in 12/20. Both use the same ledger evaluator. This is a narrow synthetic comparison, not independent businesses, user benefit, or a comparison against generic LLMs. Raw outcomes and the scenario-spec hash are in `evidence/scenario-comparison.json`.

The versioned Upgrade C suite adds 24 distinct authored business conditions,
split into 12 development and 12 held-out cases. Its expectations are sealed
before execution; success distinguishes executed rescues, no action, honest
infeasibility and security/input-validation blocks. Results, false-positive
denominators, failure examples and planner timing are documented in
[SCENARIO_EVALUATION_V2.md](SCENARIO_EVALUATION_V2.md), with raw outputs in
`evidence/upgrade-v1/scenarios/`. The original narrow experiment remains intact.

## 3. TidePay chronological audit (measured)

`python3 scripts/evaluate_tidepay_v2.py` evaluates identical final-test records
for prior, fixed heuristic, local-only, simulated federated and pooled models.
It writes separate v2 evidence and leaves the shipped model and historical
`evidence/ml/` outputs unchanged. The historical prior baseline's day forecast
used the **test delay mean**, and the old per-business 75% issue-index split did
not enforce a common training cutoff or payment-label maturity. The legacy
prior function is corrected for future reruns; the historical leak is disclosed.

V2 has 7,745 training, 1,433 validation and 2,376 final-test invoices across
40 existing synthetic SMEs. Common global issue cutoffs are 1 March/1 July 2025;
training/validation labels not yet paid at those cutoffs are purged and counted
(1,119/1,071). All fitted priors, feature scalers, mean delay and bucket means
use training rows only. Local-only uses each SME's own training statistics.
Rolling feature histories contain only payments settled by the invoice's issue
date; previously held-out payments can enter later observational history once
known. There is no refitting, calibration or model selection on validation/test.

| Model | MAE days | Log loss | Sum-class Brier | Final test N |
|---|---:|---:|---:|---:|
| Training prior | 11.9856 | 1.5882 | 0.7936 | 2,376 |
| Fixed customer-history heuristic | 7.4107 | 1.5688 | 0.7905 | 2,376 |
| Local-only | 7.2152 | 1.2329 | 0.6407 | 2,376 |
| Simulated federated | 6.9568 | 1.0727 | 0.5777 | 2,376 |
| Pooled centralised | 6.9448 | 1.0927 | 0.5855 | 2,376 |

MAE averages absolute error of expected lateness in days. Log loss averages
`-ln(p_true_class)` (natural logarithm, clipped at `1e-15`). Multiclass Brier
averages the sum of all five squared class errors; it is **not divided by five**
and has range 0–2. The heuristic's credibility-weighted day mean is assessed
alongside its original coarse 0.6/0.1 class probabilities, with that limitation
explicit. All models share the same test-ID hash and labels.

Federated minus heuristic MAE is -0.4539 days with paired 95% business-cluster
bootstrap interval [-0.6880,-0.2568] (1,000 resamples, 40 clusters). Seven SMEs
have worse MAE. The pooled model has slightly better aggregate MAE; the paired
federated-minus-pooled MAE interval [-0.0786,0.0916] includes zero. These are
single-seed synthetic-cohort intervals, not production accuracy estimates.

The >7-days-late reliability plot uses ten equal-width `[k/10,(k+1)/10)` bins,
with the final endpoint included, explicit counts and empty bins, and descriptive
Wilson intervals. Test class counts are 605/454/538/512/267; event positives
are 1,317/2,376. Per-business and sector/history/SME-size/terms/invoice-size
subgroups, raw per-example predictions, validation results, hashes, seeds,
config and machine details are in
[`evidence/upgrade-v1/tidepay/report.json`](../evidence/upgrade-v1/tidepay/report.json).
The [full audit](TIDEPAY_EVALUATION_V2.md) explains maturity-selection effects,
correlation, the missing cold-start subgroup and the distinction from the
unchanged production artifact. Federation remains a single-process simulation
with pooled training scaling and predictable illustrative masks, without a
cryptographic privacy guarantee.

## 4. Planned (not yet done: do not claim)

| Item | Plan | Evidence to keep |
|---|---|---|
| Expanded baseline comparison | Existing rule comparison is measured above; future three-mode comparison: spreadsheet rule (defer the largest bill), generic LLM suggestion, Tideway. Compare shortfall cleared, payroll safety, invalid recommendations, unauthorised actions, cost of plan. | Raw per-run CSV, model name and settings |
| Real-world scenario generalisation | The authored 24-case synthetic suite is measured above; independent consented SME cases remain future work | Consent, anonymised cases, fixed expectations and results |
| External payment-profile validation | The chronological synthetic back-test is measured above; independent consented invoice histories remain future work | Availability-aware splits, raw predictions and uncertainty |
| Live-LLM mode | At least 30 controlled runs: median and p95 latency, cost per run, grounding-flag rate, tool-denial rate | Run log without keys |
| Usability | 3 to 5 consenting SME owners or finance reviewers: task success, time, errors, comments | Anonymised notes with consent; report sample size and method next to every finding |
| Independent review | One teammate or outside reviewer attempts to break the sandbox | Findings list and fixes |

## 5. Claims policy

We may say: "30 of 30 defined sandbox cases pass", with the case list. We may not say: fraud is stopped, cash flow improves by a percentage, the model is accurate in production, or users saved time, unless a measured result exists. Money-calculation errors or any unauthorised mutation are release blockers: execution is disabled in a demo until fixed.

## 6. Reproduce everything

```bash
python3 -m unittest discover -s tests -v
python3 scripts/evaluate.py
python3 scripts/evaluate_tidepay_v2.py
python3 scripts/evaluate_upgrade_scenarios.py
node scripts/capture_screens.mjs
```

Seeds derive from business, snapshot hash and target date, so repeated runs give identical numbers.
