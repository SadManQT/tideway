# Probaho — Evaluation plan

This plan separates deterministic local evidence from claims that require a live provider, user study, or organizer review. The checked-in `scripts/evaluate_probaho.py` runs the deterministic matrix against fresh temporary SQLite workspaces and writes `evidence/results.csv` plus `evidence/run-log.jsonl`.

## Current deterministic matrix

The current matrix has 18 cases covering:

- exact base gap and minimum reserve;
- late-collection scenario;
- bounded supplier recovery;
- missing and rejected supplier consent;
- execute/read-back receipt;
- exact idempotent retry;
- reminder zero-cash behavior;
- changed payee and expired approval;
- policy limit;
- cross-business isolation;
- atomic invalid import;
- settled-invoice non-duplication;
- projection horizon;
- reset record preservation;
- independent audit chain;
- scoped-agent argument enforcement.

Run it with:

```powershell
python scripts/evaluate_probaho.py
```

Expected current local result: **18/18 passed; `live_ai=False`**. This is a reproducible synthetic safety matrix, not a competition score or user validation.

## Competition-scale extension

Before submission, expand to the roadmap targets and preserve the exact dataset version, fixture IDs, commit SHA, and raw outputs:

| Area | Target | Evidence |
|---|---:|---|
| End-to-end task scenarios | 20 | JSONL per run with terminal state |
| Deterministic money fixtures | 30 | Expected minor-unit result and source refs |
| Forbidden actions | 20 | Zero unauthorized mutations |
| Retry/replay | 10 | One mutation maximum per action |
| Prompt injection | 10 | No tool-authority escalation or raw leakage |
| Usability | 3–5 reviewers | Consent, completion, time, errors, feedback |
| Latency/cost | 30+ runs | Median, p95, model/config, token usage, cost |

Use three comparable modes for task completion, invalid recommendation, unauthorized execution, elapsed time, and cost:

1. Spreadsheet/rule baseline.
2. Generic LLM suggestion without the Probaho policy boundary.
3. Probaho constrained projection, approval, consent, and sandbox flow.

Do not report business improvement, fraud prevention, market size, or revenue claims from the synthetic fixture. Report exact scenario counts and clearly label all external/user-study results.
