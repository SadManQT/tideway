# Exact deployed TidePay: fresh synthetic cohorts

Frozen artifacts; no fitting or tuning on the new test cohort.

Scored 7427 invoices from 80 new synthetic SMEs across 4 seeds; 0 unascertained labels excluded and disclosed.

Deployed artifact SHA-256: `00639d9b3e408f1a51df20130e804db2f8a031772a772d706f09e6a7428aa466`.

| Model | MAE days | Log loss | Sum Brier | Likely-day MAE | N |
|---|---:|---:|---:|---:|---:|
| deployed | 8.5585 | 1.2850 | 0.6712 | 8.5504 | 7427 |
| audited_v2 | 8.5754 | 1.2799 | 0.6726 | 8.5741 | 7427 |
| historical_training_prior | 11.7453 | 1.5769 | 0.7871 | 11.8313 | 7427 |
| customer_history_heuristic | 10.2296 | 1.7931 | 0.9156 | 10.1912 | 7427 |

All models use identical examples and production payment-date-ordered issue-time features. Raw probability scores precede display rounding; day forecasts match app precision. The audited v2 artifact is diagnostic and is not deployed.

Cold-start/history and cohort/sector/terms/size results, paired business-cluster bootstrap intervals, full reliability counts (including empty bins), frozen training-prior provenance and all hashes are in report.json. [Reliability plot](reliability.svg).

## Limitations

- Synthetic same-generator-family evaluation; no real SME outcomes, causal evidence, lending validation or real-world calibrated cash-risk estimate.
- Fresh seeded cohorts are a stronger independent regression/evaluation set, not an independently administered blind trial.
- Retrospective synthetic issue dates do not establish a prospective real-time deployment trial; artifacts were trained in October 2026.
- Model was trained on histories ordered by issue date; production sorts by payment date. This evaluation follows production and explicitly covers that mismatch.
- Production can forecast later than issue time. Only issuance snapshots are evaluated here; overdue conditional forecasts are not validated.
- All eventually observed outcomes come from the generator; real unpaid/defaulted and missing-data processes are absent.
- Fresh cohort receives no prior fitting; historical prior was reconstructed from verified original training rows. Audited v2 uses fewer matured labels, so model comparisons do not isolate chronology as a causal factor.
- No local-only/pooled model is newly fitted; those earlier benchmark scores must not be copied onto this different test cohort.
- Business-cluster intervals capture resampling of these synthetic SMEs, not full generator, user, geography or model-selection uncertainty.
- Reliability Wilson bars are descriptive; within-SME/customer correlations violate independent binomial assumptions.
- The simulator's payment tail and festival assumptions remain illustrative; four seeds cannot characterize all plausible shifts.
