# Tideway presentation script (target 9 minutes, maximum 10)

Distinguish likely-path feasibility from simulated risk. H11's disclosed follow-up
remained at 11.78% against the 10% target; human acknowledgement does not make it
a target-met rescue. Owner discount ceilings remain binding during negotiation.

Match the regenerated `slides/pitch.pdf`. Keep the full linked live runbook ready; use a shorter live excerpt inside the pitch and offer the full workflow during questions. No recording is included.

For a behavior example, use `docs/BEHAVIORAL_EVALUATION.md`: the 1% owner cap
rejects a 1.5% counter-offer, and a repeated execution returns the same receipt.
Keep the scope visible: six AI-authored backend paths, zero human participants.
Show the model-selected tool and source result when a real model is available;
the financial calculations and permission checks run in deterministic tools.

| Time | Slides / message |
|---|---|
| 0:00-0:40 | Title/problem: SME owners need a dated payroll decision, with authority kept outside the model. Synthetic sandbox only. |
| 0:40-1:15 | Cash forecast: exact amounts, three scenarios and a look-ahead that exposes delayed shortfalls. |
| 1:15-2:05 | Shipped TidePay: 7,427 new synthetic invoices from 80 SMEs; MAE 8.56 vs history heuristic 10.23 days and training-only prior 11.75. Show the cold-start limitation. Distinguish the separate 2,376-invoice chronological benchmark; its weights are not shipped. |
| 2:05-2:35 | TideLM: historical synthetic v2 scores do not measure the new protocol. Trace distinguishes deterministic preflight from model selection after tool results. Actual compatible Qwen3 first handled 28/32 requests, with four retained misses and 32/32 containment; later known-case regressions are separate. Native MLX adapter and receipt-model verification remain pending. |
| 2:35-5:35 | Live excerpt: approved original plan, apply Bay payment delay, blocked stale mandate, changed fresh proposal, normal approvals and counterparty consent. Use PAYMENT_DELAY_RUNBOOK.md; show read-back if time permits. |
| 5:35-6:35 | Security: approval/PIN/dual approval/mandate/hash/version/idempotency remain deterministic controls. Pattern screening has measured misses and false positives; do not claim complete fraud protection. |
| 6:35-7:35 | Evidence: 24 genuinely distinct synthetic conditions, split dev/held out, separated no-action/rescue/infeasible/blocked outcomes; latency, screening and current test counts come from reports. |
| 7:35-8:15 | Decision lab: breaking-point witness, assumed agreement stress and fresh conditional funding draws; synthetic supplier/buyer payroll-safe quote, private replay and privacy preview. Show one interaction and leave the rest for questions. Core needs only Python stdlib. |
| 8:15-9:00 | Limits/team: simulated federation/counterparties, no real money, a team-reported usability study whose collection is not independently verified, and no external audit. Confirmed five-member BUET roster; leader/roles and administrative eligibility/registration remain unconfirmed. |

If a model times out, say so and use the labelled fallback. If execution is refused, explain the boundary; do not call it a successful payment. Submission route and video ambiguity are team-controlled administrative items, not technical claims.
