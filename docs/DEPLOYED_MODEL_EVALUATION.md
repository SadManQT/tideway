# Exact deployed TidePay evaluation

The exact weights used by the application now have a separate evaluation on
**7,427 invoices from 80 new synthetic SMEs**, including cold starts. This closes
the gap between the earlier corrected benchmark and the artifact actually
loaded by `analytics.tidepay_model()`. It does not establish real-world accuracy.

The Overview's **TidePay prediction evidence** now shows these exact-artifact
results and the cold-start limitation. The older audit appears separately as a
different model/test cohort. The dashboard API exposes the summary under
`tidepay.card.deployed_evaluation`. It checks the report integrity manifest and
installed weight hash each time; missing, corrupt, inconsistent or different
weights yield an unavailable summary with no scores. Its `verified` status
means local report integrity and byte agreement, not external certification.
The fixed public URLs are `/benchmarks/tidepay-deployed.json` and
`/benchmarks/tidepay-deployed-reliability.svg`; financial APIs stay protected.

The deployed artifact remains unchanged:

```text
tideway/ml/tidepay_model.json
SHA-256 00639d9b3e408f1a51df20130e804db2f8a031772a772d706f09e6a7428aa466
```

## What was frozen and what was new

The shipped model and the existing v2 audited model were frozen before this
evaluation. Four fresh generator seeds (`410281`, `598217`, `730639`, `951313`),
each with 20 businesses, create distinct SME/customer ID namespaces. Neither
model was trained, calibrated, selected or adjusted using their outcomes.
No newly trained model replaces the shipped one.

The generator family is still `tideway/ml/synth.py`; new seeds and businesses
test generalization within that simulator, not independence from its economic
assumptions. This evaluator was authored after the model and earlier benchmark
were visible, so these are fresh evaluation cohorts, not an independently
administered blind trial. Unfavorable observations remain in the report.

The original training-prior baseline is reconstructed from the original seed-7
historical first 75% of each business's invoice rows, totaling **10,292** rows.
Before accepting that provenance, the evaluator verifies the exact scaler mean,
standard deviation, rounded bucket means and training count against the shipped
artifact. All four match exactly. Those training payment labels had matured by
**18 September 2025**, before the fresh issue window begins. No test labels fit
the prior's class frequencies or day mean.

The v2 diagnostic comparator was previously trained on 7,745 matured labels
before 1 March 2025. Its training population/policy differs from the shipped
model. Their comparison does not isolate a causal effect of training policy.
No new local-only or pooled model is fitted, and their older scores are not
carried across to this different test cohort.

## Dates, features and outcome availability

The fresh invoices were issued **1 November 2025–29 April 2026**. Outcome
ascertainment is fixed at **15 October 2026**. All 7,427 generated outcomes
matured by that date (latest payment: 22 September), so no labels are censored in
this saved run. The evaluator retains and excludes censored manifest rows if
the configuration ever yields them; it never treats unpaid invoices as on time.

Every forecast is an issue-time snapshot. Only earlier invoices already paid
by that issue date enter customer history or the SME portfolio mean. Earlier
test outcomes can enter a later forecast once observed, as in deployment;
weights, scaling and calibration stay frozen. Current/future payment labels and
latent synthetic customer personalities never enter a prediction.

One relevant implementation difference is now explicit: the training dataset
orders customer history by invoice issue date, while the production app orders
it by payment date. This evaluation follows the **production payment-date
order**, and a test proves exact agreement with `analytics.tidepay_predictions`
when invoices settle in a different order from issuance. It does not silently
change production behavior or reinterpret the earlier audit.

The app can also forecast later than issuance, including overdue invoices.
Those conditional later-time forecasts are outside this experiment. The model
training timestamp is in October 2026; these retrospective synthetic dates do
not turn the experiment into a prospective field trial.

## Results on identical test invoices

| Frozen predictor | MAE days | Natural-log loss | Brier, sum of 5 classes | Likely-day MAE |
|---|---:|---:|---:|---:|
| Deployed artifact | 8.5585 | 1.2850 | 0.6712 | 8.5504 |
| Earlier v2 audited artifact | 8.5754 | 1.2799 | 0.6726 | 8.5741 |
| Historical training prior | 11.7453 | 1.5769 | 0.7871 | 11.8313 |
| Fixed customer-history heuristic | 10.2296 | 1.7931 | 0.9156 | 10.1912 |

Each denominator is **7,427**. MAE uses the app's expected-delay precision of one
decimal day for model outputs. Likely-day MAE uses the actual likely-scenario
forecast `max(0, round(expected_delay_days))`. Probability scores use the exact
softmax probabilities before the API rounds them to four decimal places for
display; they are not renormalized or calibrated. Log loss is mean `-ln(p_true)`.
Brier is the mean **sum** of five squared probability errors, not divided by
five (range 0–2).

The heuristic preserves the existing issue-time credibility mean as its day
forecast and arbitrary fixed 0.6/0.1 bucket probabilities. Its probability scores
therefore describe that coarse baseline, not an optimized probabilistic rule.

Using 1,000 paired business-cluster bootstrap draws over the 80 SMEs, the
deployed artifact's 95% MAE interval is **[8.0999, 9.0233] days**. Its MAE minus
the heuristic interval is **[-1.9221, -1.3977] days**. Against the v2 artifact,
the MAE difference interval crosses zero (**[-0.0492, 0.0155]**), while the
deployed model has slightly worse log loss (**difference interval
[0.0011, 0.0089]**). There is no basis here to declare one artifact universally
better or automatically promote the v2 model.

## Cold starts remain a limitation

| Issue-time customer history | Invoices | Deployed MAE | Deployed log loss |
|---|---:|---:|---:|
| No settled customer invoice | 2,640 | 11.6254 | 1.6161 |
| Settled history available | 4,787 | 6.8671 | 1.1024 |

For cold starts, the historical prior's log loss is **1.5932**, slightly better
than the deployed model's 1.6161. Cold-start probability superiority is therefore
not established, even though the model's cold-start day MAE is better than that
prior's 12.2878 days. The overall result should not conceal this weakness.
Sector, seed, payment-term and relative-invoice-size subgroups are also saved.
Per-seed deployed MAE ranges from **7.9083 to 9.6150 days**.

## Evidence and reproduction

From the project root, using only Python's standard library:

```bash
python3 scripts/evaluate_deployed_tidepay.py
python3 -m unittest tests.test_deployed_tidepay -v
```

Use `--out /tmp/tidepay-fresh-check` to preserve the checked-in run. Configuration,
dataset/feature/split hashes, exact artifact/source hashes, full metric
definitions, class balances, all ten calibration bins (including empty ones),
subgroups and confidence intervals are in
[`report.json`](../evidence/readiness-v3/tidepay/report.json).

The directory also includes:

- [`report.md`](../evidence/readiness-v3/tidepay/report.md): concise results.
- [`raw_dataset.jsonl`](../evidence/readiness-v3/tidepay/raw_dataset.jsonl): generated businesses and invoice outcomes, with explicit latent simulation fields retained for audit rather than supplied to models.
- [`split_manifest.csv`](../evidence/readiness-v3/tidepay/split_manifest.csv): every outcome/date, history count and exact feature vector, including any censored rows.
- [`predictions.csv`](../evidence/readiness-v3/tidepay/predictions.csv): each model's predictions on identical scored invoice IDs.
- [`reliability.svg`](../evidence/readiness-v3/tidepay/reliability.svg) and [`reliability.csv`](../evidence/readiness-v3/tidepay/reliability.csv): >7-day lateness calibration, Ns and descriptive Wilson intervals.
- [`per_business.csv`](../evidence/readiness-v3/tidepay/per_business.csv): metrics per SME/model.
- [`artifact_sha256.json`](../evidence/readiness-v3/tidepay/artifact_sha256.json): file-integrity manifest.

Wilson bars do not account for correlated invoices. The bootstrap captures
resampling of these generated SMEs, not uncertainty across real customers,
countries, generator assumptions or deployment conditions. Synthetic defaults,
unpaid/missing data and actual credit losses remain unvalidated.
