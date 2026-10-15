# TidePay evaluation (synthetic held-out invoices)

40 SMEs, 10292 training and 3452 later test invoices. synthetic SME invoice histories (tideway/ml/synth.py); no real customer data.

| Model | Log loss (lower better) | Accuracy | MAE days | AUC (>7 days late) |
|---|---|---|---|---|
| prior | 1.5858 | 0.2367 | 12.09 | 0.5 |
| heuristic_v1 | 1.55 | 0.42 | 7.34 | 0.9096 |
| local_only | 1.1161 | 0.5463 | 7.35 | 0.9126 |
| federated | 1.0361 | 0.5826 | 7.03 | 0.9198 |
| centralised | 1.0357 | 0.5689 | 6.98 | 0.9215 |

Smaller half of SMEs: local-only MAE 6.64 days vs federated 6.12 days.

Simulation only: one process holds all client data and pools features for scaling. Predictable pairwise masks demonstrate cancellation; cryptographic privacy and distributed deployment are not implemented.
Results are on synthetic data and show the method works as designed, not real-world accuracy.
