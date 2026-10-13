# Probaho — Security self-assessment

**Scope:** local, single-operator, synthetic SME prototype. This document is not a security certification, regulatory opinion, penetration-test report, or claim of production readiness.

## Permission matrix

| Tier | Actor | Allowed operation | Enforcement |
|---|---|---|---|
| `agent_read` | Assistant | Read scoped aggregates and projections | Four-tool allowlist, exact schemas, server-selected business/date |
| `agent_propose` | Assistant | Persist a comparison or reminder draft | Deterministic server validation; no approval or execution tool |
| `human_approval` | Local operator | Approve a specific plan/action; simulate supplier response; reset/cancel | CSRF token, business scope, plan/snapshot checks, explicit UI action |
| `sandbox_execute` | Local operator through API | Apply one approved schedule/reminder change | Approval nonce, expiry, consent, state version, policy, payee/amount/date rechecks, idempotency |
| `user_write` | Local operator | Import business records or update policy | Whole-file validation, scoped transaction, exact financial-field conflict checks |
| `denied` | Any caller/model | Unknown tools, cross-business objects, direct execution, stale actions | Rejected and audited without sandbox mutation |

## Assets and trust boundaries

Assets are synthetic business records, planned cash projections, policy constraints, approvals, supplier-consent simulations, execution receipts, optional provider credentials, and audit evidence.

Boundaries:

1. Browser to loopback HTTP API: Host, Origin, CSRF/session token, content-type, body-size, and static-path checks.
2. API to SQLite: parameterized SQL, scoped queries, `BEGIN IMMEDIATE`, snapshot hashes, and transaction-bound receipts.
3. Assistant to domain: strict tool allowlist, server scope, deterministic calculations, redacted tool results, and bounded calls.
4. Optional provider boundary: only explicitly consented conversation plus redacted tool results; credentials remain server-side.
5. Synthetic sandbox boundary: schedule/reminder state only, no bank or supplier integration.

## Implemented controls and evidence

| Threat/control area | Implementation | Evidence |
|---|---|---|
| Money precision | Integer paisa; finite positive amounts; BDT-only | Finance unit tests and projection reconciliation |
| Date safety | ISO calendar validation; opening-to-target window; 366-day cap | Domain tests |
| Record integrity | Whole combined CSV validation; atomic write; exact ID conflict detection | Import tests |
| Cross-business access | Every Probaho query/mutation requires business scope | Isolation tests and scoped exports |
| Projection correctness | Pre-opening history excluded; settled invoices excluded; daily minimum reserve | Projection tests and source references |
| Prompt injection | Imported descriptions are data; no raw descriptions in model requests | Fake-provider injection test |
| Model authority | No approval/execute/payment/shell/SQL/arbitrary HTTP tools | Tool allowlist tests |
| Approval freshness | Plan hash, snapshot hash, policy version, state version, balance, expiry, nonce | Approval/execute tests |
| Supplier consent | Separate accepted/rejected synthetic consent bound to plan/action/bill/payee/date/amount | Consent gate tests |
| Duplicate execution | Business-scoped idempotency key; stored canonical receipt | Retry/restart tests |
| Changed actions | Payee, amount, due date, policy, record, target, and state checks | Mutation rejection tests |
| Failure recovery | Uncertain client checks `GET /api/execution`; no automatic retry | UI flow and endpoint test |
| Browser writes | Loopback, Host, Origin, CSRF, JSON-only, 2 MB cap | HTTP tests |
| UI content | Escaped record text and assistant output; no external script | Browser XSS check |
| Audit | Independent per-business SHA-256 chain including scope and canonical JSON | Hash-chain test/export |
| Reset/cancel | Only synthetic schedule or unused approval is invalidated; ledger/receipts preserved | Reset/cancel tests |

## Abuse cases tested or required before submission

1. Prompt injection in invoice description.
2. Other-business ID in a record, tool call, plan, approval, consent, or export.
3. Approval without matching plan.
4. Direct execution without approval.
5. Supplier execution without consent.
6. Supplier rejection followed by execution.
7. Changed payee after approval.
8. Changed amount or due date after approval.
9. Expired approval.
10. Duplicate idempotency key with another approval.
11. Replay with the same idempotency key.
12. Stale sandbox version or current balance.
13. Payroll-priority bill reschedule.
14. Action above policy limit.
15. Currency mismatch or malformed amount.
16. Combined CSV with one invalid row.
17. Formula-like record descriptions on CSV export.
18. Cross-site or untrusted-host write.

The first 17 are covered by the domain/API/browser suite; the team should add a formal 20-attempt attack matrix and attach raw results before claiming a competition security score.

## Data handling

The SQLite database is local and unencrypted. `.env`, local databases, and private evidence are ignored by Git. The optional API key is read server-side and never returned by `/api/config`. Tool requests use `store: false`, but provider retention and account terms still apply. Raw imported record text remains local unless the operator explicitly types it into a consented conversation or exports it.

Synthetic seed records are fictional. Imported records are labelled `Local / imported` in the UI and are not automatically suitable for an evaluation claim. Do not add passports, private customer data, API keys, or real supplier information to this repository or demo recording.

## Known residual risks

1. **No multi-user authentication:** the loopback token is a browser boundary, not user identity or authorization for another local process.
2. **Local database access:** an OS-level attacker can read or rewrite records, policies, receipts, and audit rows.
3. **Audit rewrite risk:** the per-business chain detects inconsistent edits but is not externally notarized.
4. **Model risk:** a provider can still misunderstand a question or produce a misleading explanation; deterministic results and human review reduce but do not eliminate this.
5. **Synthetic supplier consent:** it demonstrates a safety gate, not real consent or a communication channel.
6. **No bank truth:** scheduled cash is not a verified account balance; missing records distort decisions.
7. **No production compliance:** jurisdiction-specific finance, lending, privacy, retention, and data-processing review is out of scope.
8. **Prototype availability:** no rate limiting, backup system, monitoring, or disaster recovery is provided.

## Release gate

Do not record a “successful execution” claim if any of the following is true: unauthorized mutation succeeds; a cash calculation does not reconcile; a reminder appears as a collection; a mock-financing option can execute; a changed approval still executes; read-back is missing/mismatched; or the evidence chain fails. Disable execution in the demo until the issue is fixed and rerun the relevant tests.
