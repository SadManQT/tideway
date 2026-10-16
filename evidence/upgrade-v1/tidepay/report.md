# TidePay v2 chronological synthetic evaluation

This audit benchmark leaves historical raw observations and the shipped model unchanged.

Training: 7745; validation: 1433; final test: 2376 invoices from 40 existing synthetic SMEs.
Global cutoffs: 2025-03-01 / 2025-07-01; purged immature train/validation labels: 1119 / 1071.

| Model | MAE days | Log loss | Brier (sum of 5 classes) | Accuracy | N |
|---|---:|---:|---:|---:|---:|
| prior | 11.9856 | 1.5882 | 0.7936 | 0.2264 | 2376 |
| heuristic_v1 | 7.4107 | 1.5688 | 0.7905 | 0.4095 | 2376 |
| local_only | 7.2152 | 1.2329 | 0.6407 | 0.5097 | 2376 |
| federated | 6.9568 | 1.0727 | 0.5777 | 0.5366 | 2376 |
| centralised | 6.9448 | 1.0927 | 0.5855 | 0.5396 | 2376 |

The heuristic preserves its original raw credibility-mean day forecast and fixed smoothed class probabilities. A better day forecast can coexist with worse probability scores.

## Paired business-cluster bootstrap

95% percentile intervals for federated minus comparator (negative favours federated):

| Comparator | MAE difference interval | Log loss difference interval | Brier difference interval |
|---|---:|---:|---:|
| prior | [-5.4898, -4.5419] | [-0.5686, -0.4634] | [-0.2421, -0.1925] |
| heuristic_v1 | [-0.6880, -0.2568] | [-0.5718, -0.4156] | [-0.2556, -0.1658] |
| local_only | [-0.4423, -0.0994] | [-0.2154, -0.1109] | [-0.0895, -0.0404] |
| centralised | [-0.0786, 0.0916] | [-0.0344, -0.0065] | [-0.0136, -0.0022] |

See report.json for class balance, all per-business/sector/history/size subgroups, validation diagnostics, definitions, fitted statistics, seeds and hashes.

[Reliability plot](reliability.svg) uses event delay >7 days, 10 equal-width bins, counts and descriptive Wilson bars. Correlation limits their interpretation. [CSV](reliability.csv).

## Historical audit

- Historical train.prior_eval computes mean_delay from test delays for prior MAE: test-label leakage; v2 uses training delay mean.
- Historical split uses each business's invoice index at 75%, without a common global cutoff or payment-label maturity purge.
- Historical scaler and bucket means were training-row-only, but training rows could carry labels unavailable when early held-out invoices were issued.
- Historical local-only model shared pooled training scaling and bucket means; v2 local models fit those from their own matured training rows.
- Issue-time feature history filters paid_date <= issue_date. Latent personality and current invoice delay/paid_date are not features.
- Bucket means represent training observations (including any >90-day synthetic tail in final class); frozen empty-class means are used only when a local class is absent.

## Limitations

- Synthetic histories from the same generator family and same 40 businesses, not real-world or unseen-business validation.
- One seed/cohort; cluster intervals capture business resampling, not generator, hyperparameter or deployment uncertainty.
- Test invoices all have eventually observed synthetic labels; there is no real-world censoring model.
- Purging unmatured labels selects faster-settling invoices near each cutoff; gaps and class balances are reported rather than silently treating unpaid invoices as on-time.
- No cold-start customer exists in this final test; history:none has N=0 and establishes no performance for new customers.
- The fixed heuristic's probability mass is arbitrary and coarse; its raw expected delay can differ from its smoothed class distribution's mean.
- Local, FedAvg and centralised optimisers have different update paths. Same rows/information/policy does not imply identical compute or convergence.
- FedAvg is a single-process simulation holding raw client data, pooled train scaling, reproducible predictable masks; no cryptographic privacy guarantee.
- Small subgroups and within-customer correlations limit precision; per-business rows have no claimed inferential interval.
- Wilson reliability bars are descriptive binomial intervals; correlated invoices violate the independence assumption.
- Historic evidence and the shipped production model remain unchanged; v2 is an audit benchmark, not a deployed calibration update.
