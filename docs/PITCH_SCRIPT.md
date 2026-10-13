# Probaho — English pitch draft

Target: 8–9 minutes of speaking within a 10-minute maximum. Replace team details and measured results before presenting. This is a speaking draft, not a finished slide deck.

## 1. Problem — 0:00–0:55

“A small business owner does not need another dashboard that only reports what already happened. When payroll is approaching and cash is tight, the real question is: which receivable, supplier obligation, or recovery option can be considered without breaking the business’s reserve and payroll constraints?

We built Probaho, an approval-gated cash-flow recovery copilot for small businesses. It turns a business-scoped ledger into an evidence-linked cash gap, compares bounded alternatives, and executes only an approved action in a sandbox.”

Visual: Shapla Services problem statement and `Records → Projection → Plan → Approval → Sandbox → Evidence`.

## 2. Concrete scenario — 0:55–1:45

“Our synthetic Shapla Services fixture starts with BDT 120,000. It has BDT 80,000 payroll, a BDT 70,000 supplier bill, and a confirmed BDT 20,000 receivable. The base closing cash is BDT -10,000. With a BDT 20,000 reserve floor, the reserve shortfall is BDT 30,000.

Those numbers are not an LLM guess. They are deterministic minor-unit calculations linked to source rows.”

Visual: four metrics and the source-linked records.

## 3. End-to-end workflow — 1:45–3:30

“The user first imports or reviews transactions, invoices, and bills. Probaho validates the complete file before writing anything and rejects mixed currencies, conflicting IDs, invalid dates, and malformed amounts.

The projection shows base, late-collection, and approved-recovery scenarios. A collection reminder is useful as a draft, but it never counts the receivable as collected. A supplier reschedule can move only a bounded amount to a later date and must protect payroll and the minimum reserve. Mock financing is displayed as a comparison catalogue, not a lender or executable action.

The user reviews the action’s payee, amount, currency, source record, original due date, deferred date, assumptions, and risks. A human creates the approval. For a supplier scenario, the interface then requires a separate synthetic supplier-consent simulation. Only then can the sandbox action execute.”

Visual: plan cards → approval panel → consent gate.

## 4. What makes it different — 3:30–4:25

“We are not claiming to be the first cash-flow assistant. Existing products already provide guidance and scenario planning. Probaho focuses on a narrow, demonstrable workflow: evidence-linked cash recovery under explicit payroll and reserve constraints, with an approval boundary and replayable safety checks.

The model plans and explains. The backend owns money arithmetic, policy enforcement, state mutation, and receipts. This separation makes the demo auditable instead of asking judges to trust a chat response.”

Visual: architecture diagram and comparison with a generic LLM suggestion.

## 5. Security and failure recovery — 4:25–5:45

“The assistant receives only four scoped tools: read the ledger, project cash, compare plans, and create a reminder draft. It has no approval, execution, payment, shell, SQL, or arbitrary HTTP tool.

Every proposal is bound to a business, policy version, records snapshot, target date, and plan hash. Execution rechecks the payee, amount, dates, policy, expiry, nonce, current state, and supplier-consent binding. The same idempotency key returns the same receipt, and an uncertain client checks the receipt rather than blindly retrying.

Imported descriptions are treated as data, even when they contain prompt-injection text. The audit export has an independent per-business hash chain. It is internal evidence, not third-party certification, and we say that plainly.”

Visual: permission matrix, blocked-action test, read-back receipt, audit page.

## 6. Evaluation plan — 5:45–7:05

“Our evaluation separates development fixtures from holdout scenarios. We measure deterministic calculation correctness, terminal task completion, unauthorized mutation attempts, duplicate and restart behavior, prompt injection, latency, provider cost, and usability with consenting SME owners or domain reviewers.

We compare a rule/spreadsheet baseline, a generic LLM suggestion, and Probaho’s constrained workflow on the same scenarios. We will report exact counts and raw evidence rather than claiming business improvement from a small synthetic dataset.”

Visual: results table with actual measured values only; leave placeholders until measured.

## 7. Limitations and next step — 7:05–8:20

“This is a local synthetic prototype. It does not connect to a bank, contact a supplier, make a credit decision, or provide multi-user authentication. The next deployment step would require contracts, jurisdiction-specific legal review, encrypted storage, stronger authentication, and a professional security assessment.

Our next product step is not adding more features. It is validating the workflow with small-business owners, measuring whether the source-linked plan is understandable, and testing the adapter boundary against real but consented provider behavior.”

## 8. Close — 8:20–8:50

“Probaho’s contribution is a complete and honest financial-agent loop: records become a deterministic gap; the gap becomes bounded alternatives; a human controls approval; the sandbox produces a receipt; and the evidence can be replayed.

The agent participates in the financial workflow without becoming the authority over money. Thank you.”
