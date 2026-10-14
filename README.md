# Tideway

**Approval-gated cash-flow rescue for small businesses.**

Tideway is a working prototype for the FinTechathon 2026 International Track, **Topic E: SME Finance Copilot** (theme: *AI as a Financial Participant*). It finds a coming cash gap, plans a recovery with an exact, risk-aware optimiser, negotiates with simulated counterparties, and moves forward only through human approval and a signed, scoped mandate. The agent can read, analyse and propose. It cannot approve or execute.

> **Honest scope.** Everything runs in a **synthetic sandbox**: fictional businesses, no real money, no bank, lender, supplier or customer connected. Financing offers are labelled **MOCK** catalogue comparisons and are never executable. The payment file (ISO 20022 pain.001) is a draft that is never sent. A passing test suite is evidence for the listed cases only, not proof of security. The optional LLM mode has not been measured against a live provider.

## Quick start (Python 3.11+, standard library only)

```bash
python3 run.py
```

Open <http://127.0.0.1:8787>. The server binds to loopback only; do not expose it to a network.

| Role | Operator | PIN |
|---|---|---|
| Owner | Nadia | `2468` |
| Accountant | Imran | `1357` |
| Viewer | Guest | `0000` |

These PINs belong to the synthetic demo only.

```bash
python3 -m unittest discover -s tests -v   # unit, HTTP and security tests
python3 -m tideway.selftest                # 30-case scorecard (5 tasks, 25 attacks)
python3 scripts/evaluate.py                # writes evidence/results.csv, run-log.jsonl, verification-summary.json
node scripts/capture_screens.mjs           # drives headless Chrome through the demo, writes evidence/screens/
python3 scripts/build_submission_pdfs.py   # pitch, architecture and security PDFs (headless Chrome)
```

`python3 run.py --no-demo --db data/empty.sqlite3` starts an empty workspace. Node 22+ and Google Chrome are needed only for screenshots and PDFs.

## What it does

1. **Sees the gap.** Exact integer minor-unit cash projection with three scenarios (scheduled, likely, stress) and a 14-day look-ahead so a deferral cannot hide a problem just beyond the target date.
2. **Models customers, not just invoices.** Per-customer payment profiles use credibility weighting (own history counts n/(n+5), the rest from the business-wide average), so one lucky payment never makes a customer look reliable.
3. **Quantifies risk.** A seeded Monte Carlo (1,000 runs; the same records and seed give the same answer) estimates the chance of breaching the reserve floor and is shown as a "cash weather" read-out.
4. **Optimises.** An exact search over supplier deferrals, early-payment discounts and zero-cash reminders finds the cheapest bundle that holds the reserve floor on every day and keeps payroll funded, then re-checks candidates with Monte Carlo. Early-payment discounts are priced as an annual rate (2% for 20 days is about 37% APR).
5. **Negotiates.** Simulated suppliers and customers answer each request with accept, counter-offer or reject. A counter becomes a new proposal that needs fresh approval; a refusal triggers a re-plan without that counterparty.
6. **Authorises like a bank.** Maker-checker approval with PIN step-up; high-value bundles need two people (including the owner) and a typed exposure amount. Approval issues an **HMAC-signed mandate** (modelled on the AP2 mandate idea: verifiable, scoped, expiring), bound to the exact actions, snapshot, policy and expiry.
7. **Executes once, verifiably.** Idempotent execution against the sandbox, state hashes before and after, and a read-back check.
8. **Stays stoppable.** A kill switch pauses the agent (only the owner resumes, with a reason). A circuit breaker pauses it automatically after repeated security denials.
9. **Resists fraud.** Changed bank details and look-alike payee names block every action on the bill. Payees are verified only by the owner, only by callback to a number on file, and the verifier cannot then approve that payee (separation of duties).
10. **Quarantines injection.** Hidden Unicode is stripped and flagged; instruction-like text in records is quarantined and never reaches a model.
11. **Optional LLM mode.** Off by default. With a key and per-message consent, counterparty names are pseudonymised, record free text is never sent, and every number in the answer is checked against tool output (ungrounded numbers are flagged).
12. **Proves what happened.** A hash-chained audit log with an independent witness checkpoint (truncation is detected), and a one-click tamper drill.
13. **Dials autonomy.** Advise, Propose or Delegate. Under Delegate, a standing mandate lets the agent send zero-cash reminders only, capped per day. Moving money is never delegated.
14. **Multi-currency fixtures.** Shapla Services and Meghna Traders in BDT, Lotus Print Studio in CNY; mixed currencies inside one business are rejected.
15. **Exports.** Evidence JSON, records and receipts CSV (spreadsheet-formula-safe), and a draft ISO 20022 `pain.001` for the deferred payments.

## The demo businesses

| Business | Story |
|---|---|
| Shapla Services (BDT) | Payroll day. Scheduled minimum cash is BDT -10,000 on 31 Oct 2026; shortfall against the BDT 20,000 reserve is BDT 30,000. |
| Lotus Print Studio (CNY) | The schedule looks fine; the customers' payment habits say it is not. Includes a counter-offer. |
| Meghna Traders (BDT) | No safe plan exists. A changed bank account, a look-alike payee and a poisoned bill are blocked; Tideway says so and escalates. |

## Layout

```
tideway/    domain, projection, analytics (profiles, Monte Carlo), planner, counterparty,
            security (PIN, HMAC, rate limit), store (SQLite workflow + audit), service, agent, server, selftest
web/        vanilla JS single-page UI (no build step)
tests/      stdlib unittest suite
scripts/    evaluate.py, capture_screens.mjs, build_submission_pdfs.py
evidence/   results.csv, run-log.jsonl, verification-summary.json, screens/
docs/       brief, technical documentation, security self-assessment, evaluation plan, demo and pitch scripts, checklist, roadmap
slides/     pitch.pdf
```

## Optional LLM mode

Copy `.env.example` to `.env`, set your own `OPENAI_API_KEY` (never commit it) and restart. The model sees only pseudonyms and tool output, can call six read/propose tools, and has no approval, execution, SQL, shell or URL tool.

## Documents

[Technical documentation](docs/TECHNICAL_DOCUMENTATION.md) · [Security self-assessment](docs/SECURITY_SELF_ASSESSMENT.md) · [Evaluation plan](docs/EVALUATION_PLAN.md) · [Demo script](docs/DEMO_SCRIPT.md) · [Pitch script](docs/PITCH_SCRIPT.md) · [Submission checklist](docs/SUBMISSION_CHECKLIST.md) · [Project brief](docs/PROJECT_BRIEF.md) · [English roadmap](docs/Tideway_FinTechathon_2026_Roadmap.pdf)

## Licence

MIT. See `LICENSE` and `THIRD_PARTY_NOTICES`.
