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

## 3. Planned (not yet done: do not claim)

| Item | Plan | Evidence to keep |
|---|---|---|
| Expanded baseline comparison | Existing rule comparison is measured above; future three-mode comparison: spreadsheet rule (defer the largest bill), generic LLM suggestion, Tideway. Compare shortfall cleared, payroll safety, invalid recommendations, unauthorised actions, cost of plan. | Raw per-run CSV, model name and settings |
| Scenario breadth | At least 20 independent scenarios beyond the three demo businesses, written before tuning, with a held-out set | Scenario files, expected outcomes, results |
| Back-test of payment profiles | Compare predicted against actual lateness on held-out settled invoices | Error table; report as synthetic |
| Live-LLM mode | At least 30 controlled runs: median and p95 latency, cost per run, grounding-flag rate, tool-denial rate | Run log without keys |
| Usability | 3 to 5 consenting SME owners or finance reviewers: task success, time, errors, comments | Anonymised notes with consent; report sample size and method next to every finding |
| Independent review | One teammate or outside reviewer attempts to break the sandbox | Findings list and fixes |

## 4. Claims policy

We may say: "30 of 30 defined sandbox cases pass", with the case list. We may not say: fraud is stopped, cash flow improves by a percentage, the model is accurate in production, or users saved time, unless a measured result exists. Money-calculation errors or any unauthorised mutation are release blockers: execution is disabled in a demo until fixed.

## 5. Reproduce everything

```bash
python3 -m unittest discover -s tests -v
python3 scripts/evaluate.py
node scripts/capture_screens.mjs
```

Seeds derive from business, snapshot hash and target date, so repeated runs give identical numbers.
