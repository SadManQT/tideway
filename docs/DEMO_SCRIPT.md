# Tideway live demonstration (recording deferred)

Use [PAYMENT_DELAY_RUNBOOK.md](PAYMENT_DELAY_RUNBOOK.md) as the authoritative step-by-step script. Keep the normal demo under five minutes when rehearsing; no video was recorded for this upgrade.

| Time | Live action |
|---|---|
| 0:00-0:30 | State synthetic scope, open a fresh Shapla database, show scheduled and likely cash gap |
| 0:30-1:20 | Run the deterministic rescue; show source actions and risk, obtain Imran and Nadia PIN approvals |
| 1:20-2:10 | Separate from read-only What-if, apply Bay Logistics collection date 15 November as Nadia; show calculated changes |
| 2:10-2:30 | Attempt the old mandate; show explicit invalidation and audit event |
| 2:30-4:20 | Create fresh rescue, approve, receive Bay's 1.5% counter, approve revised terms, negotiate and execute once; show read-back |
| 4:20-4:50 | Explain the guarded optional model trace, honest screening limitations and links to chronological/scenario evidence |

Figures come from the running tools. Do not claim the already 100% breach risk increased, pretend the orchestrated rescue is LLM reasoning, or present injected model results as device inference. If the optional model is missing, demonstrate the explicitly labelled deterministic assistant. Do not force simulated counterparties to accept.

Run `python3 scripts/demo_payment_delay.py` before a rehearsal. A new unused `--db` filename is the reset route; existing databases and audit evidence remain intact. If a step fails, show the failure and restart in another fresh database rather than weakening controls.
