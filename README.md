# Probaho

**Approval-gated cash-flow recovery for small businesses**

Probaho is a local-first prototype for the FinTechathon 2026 International Track, **Topic E — SME Finance Copilot**. It helps a small business owner inspect a scheduled cash gap, compare evidence-linked recovery options, approve one bounded action, and execute that action only inside a synthetic sandbox.

> **Important:** this repository contains a synthetic local sandbox. It does not connect to a bank, send money, contact suppliers, approve credit, or provide production financial advice. “Winning” cannot be guaranteed; competition rules, registration, user research, and live evaluation still require the team’s verification.

## What the prototype demonstrates

The default fixture is **Shapla Services**:

- Opening cash: **BDT 120,000**
- Payroll: **BDT 80,000**
- Supplier bill: **BDT 70,000**
- Confirmed receivable: **BDT 20,000**
- Minimum reserve: **BDT 20,000**
- Base closing cash: **BDT -10,000**
- Reserve shortfall: **BDT 30,000**

The main flow is:

1. Import or inspect business-scoped transactions, invoices, and bills.
2. Select a target date and view deterministic base, late-collection, and approved-recovery projections.
3. Compare a collection reminder, supplier reschedule, and clearly labelled mock-financing alternatives.
4. Review the payee, amount, dates, assumptions, constraints, and source records.
5. Approve one bounded action as the local operator.
6. For a supplier reschedule, separately simulate supplier acceptance. This is explicitly not genuine supplier consent.
7. Execute once in the synthetic sandbox using a one-time approval and idempotency key.
8. Read back the post-mutation state and export evidence.

Reminders never count as collected cash. Mock financing is catalogue comparison only and is never executable.

## Start locally

Requires Python 3.11 or newer. Runtime code uses the Python standard library only.

```powershell
python run.py
```

Open **http://127.0.0.1:8787**. `start.ps1` and `start.cmd` run the same command. The default database is `data/probaho.sqlite3` and is ignored by Git.

To start an empty local workspace:

```powershell
python run.py --no-demo --db data/probaho-empty.sqlite3
```

The app binds to loopback only. Do not expose this prototype to the public internet.

## Optional AI provider

The offline assistant is labelled **Local demo** and uses deterministic tools. It is not presented as a live model. To test the optional OpenAI Responses adapter locally, copy `.env.example` to `.env` and set your own key outside the repository:

```dotenv
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5-mini
PROBAHO_PORT=8787
```

Restart the server and enable the per-message consent checkbox. A scoped AI request receives only redacted tool output; raw record descriptions, customer names, and payees are not automatically attached. `store: false` is not a zero-retention guarantee. Provider access, quota, pricing, and competition permission must be verified by the team.

## Combined CSV format

Imports are validated completely before any write and are scoped to the selected business. Required columns include `record_type`, `business_id`, `id`, `currency`, and the fields appropriate to each row. `record_type` is one of `transaction`, `invoice`, or `bill`.

Download the example from the Records screen or use this shape:

```csv
record_type,business_id,id,date,description,amount,type,currency,due_date,status,customer,payee,issue_date,expected_collection_date,priority,reschedule_allowed
transaction,shapla-services,txn-client-001,2026-10-10,Client service receipt,25000,income,BDT,,,,,,,,
invoice,shapla-services,inv-client-001,2026-10-01,Service receivable,35000,,BDT,2026-10-31,confirmed,Nila Traders,,2026-10-01,2026-10-31,,
bill,shapla-services,bill-materials-001,,Supplier materials,12000,,BDT,2026-10-28,open,,,,,normal,true
```

Amounts are positive BDT values with at most two decimal places. The system stores integer paisa. BDT is the only supported currency. Existing records with the same ID must match their financial fields exactly; conflicting records reject the whole file.

## API outline

All POST requests require the CSRF token returned by `GET /api/config` and same-origin/loopback headers.

| Endpoint | Purpose |
|---|---|
| `GET /api/config` | Businesses, default fixture, capabilities, permission tiers |
| `GET /api/dashboard?business_id=...&target_date=...` | Scoped records, projections, plans, approvals, sandbox state |
| `POST /api/plan/compare` | Persist a deterministic, snapshot-bound comparison |
| `POST /api/plan/approve` | Create a short-lived, one-time scoped approval token |
| `POST /api/sandbox/consent` | Record synthetic supplier acceptance/rejection for one action |
| `POST /api/plan/execute` | Execute an approved reminder or supplier schedule change once |
| `GET /api/execution` | Safely check an idempotent receipt after an uncertain request |
| `POST /api/plan/cancel` | Cancel an unused approval; never reverses execution |
| `POST /api/sandbox/reset` | Reset only synthetic schedules, preserving records and receipts |
| `POST /api/policy` | Update reserve floor/action limit and invalidate stale proposals |
| `POST /api/chat` | Local or consented, scoped read/proposal assistant |
| `GET /api/audit` | Independently verifiable per-business audit chain |
| `GET /api/export` | Evidence JSON, combined records CSV, or execution-results CSV |

## Safety boundaries

- Opening cash, projections, reserve gaps, and plan effects are deterministic integer-paisa calculations.
- Historical records before opening date are retained for evidence but do not alter the opening balance.
- Paid/collected invoices are not projected again.
- Payroll-priority records cannot be deferred.
- Plan, policy, record, target-date, and sandbox snapshot hashes are checked at approval and execution.
- Supplier execution requires both human plan approval and a matching synthetic supplier-consent event.
- Changed payee, amount, dates, currency, policy, records, or sandbox state invalidate the action.
- The same idempotency key returns the original receipt; a different key cannot reuse a consumed approval.
- The model has no approval, execution, shell, SQL, arbitrary HTTP, or payment tool.
- Descriptions and imported text are treated as data, including prompt-injection-looking text.

Known limitations are documented in `docs/SECURITY_SELF_ASSESSMENT.md`. This is not multi-user authentication, encrypted storage, bank connectivity, legal compliance certification, or an immutable external ledger.

## Verification

```powershell
python -m unittest discover -s tests -v
node --check web/app.js
python -m py_compile finmate/*.py run.py
python tests/browser_check.py
```

The browser check uses an isolated temporary database and installed Chrome/Playwright. It verifies the overview, exact Shapla gap, records view, combined import and escaping, comparison, approval, supplier-consent gate, execution receipt/read-back, reset, evidence export, assistant, desktop/mobile layout, and no page errors. It does **not** prove live-model quality or organizer acceptance.

## Motion presentation

[Watch or download the narrated presentation](demo/Probaho-presentation.mp4) — **4:19**, 1080p, English AI voice, reference-inspired motion and genuine synthetic-sandbox UI captures.

[Editable source ZIP](demo/Probaho-presentation-source.zip) and [production instructions](demo/presentation-production/README.md) include the scene script, final narration, motion renderer and QA reports. All twelve scenes were checked for motion and narration timing; the final audio/video decode without errors. The supplied visual reference is [reference.mp4](reference.mp4).

## Repository contents

- `finmate/finance.py` — validation, deterministic projection, gap calculation, and plan comparison.
- `finmate/store.py` — scoped SQLite records, snapshot-bound approvals, supplier consent, sandbox, receipts, and audit chain.
- `finmate/agent.py` — bounded local/optional AI assistant with four scoped tools.
- `finmate/server.py` — loopback HTTP API and security boundaries.
- `web/` — responsive English competition-demo interface.
- `tests/test_probaho_backend.py` — Topic E backend contract and safety tests.
- `tests/browser_check.py` — isolated Chrome end-to-end verification.
- `examples/probaho-sample-records.csv` — combined synthetic transaction/invoice/bill import example.
- `docs/TECHNICAL_DOCUMENTATION.md` — architecture and algorithms.
- `docs/SECURITY_SELF_ASSESSMENT.md` — controls, threat model, and limitations.
- `docs/DEMO_SCRIPT.md` and `docs/PITCH_SCRIPT.md` — honest recording and pitch plans.
- `docs/SUBMISSION_CHECKLIST.md` — competition deliverables still requiring team action.
- `slides/pitch.pdf`, `docs/architecture.pdf`, and `docs/security-assessment.pdf` — generated draft PDFs; team review is required.
- `demo/demo.mp4` — generated visual rehearsal from isolated screenshots; re-record a narrated running-app demo before submission.
- `evidence/` — generated verification artifacts; never present offline evidence as live AI evidence.

## Submission honesty

The supplied roadmap lists organizer questions, deadline conversion, evidence expectations, and a suggested eight-day plan. Confirm the authoritative registration route, AI coding policy, dataset/API requirements, video rule, repository access, and post-deadline change policy with the organizer. Add actual team details, user feedback, measured results, final English deck, and recorded demo only after the team has produced them.
