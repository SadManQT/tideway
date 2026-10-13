# Probaho narrated presentation

English narration: **490 words**. Suggested duration: **3:58**, about 124 words per minute including visual holds. Scene timing is a starting point; the final audio determines the edit. Adapt entrance, hold, and transition motion to the reference once its duration and cadence are measured.

## Evidence basis

- `README.md`, `docs/TECHNICAL_DOCUMENTATION.md`, `docs/EVALUATION_PLAN.md`, `finmate/finance.py`, and `finmate/store.py`.
- `evidence/verification-summary.json`: 30 passing backend tests, 18/18 deterministic cases, browser flow passed, live model not tested.
- `evidence/browser-verification.json`: installed Chrome, 1440×1040 desktop and 390×844 mobile, synthetic Shapla flow.
- The exact default fixture uses target **31 October 2026**, independent of the viewer's current date. The screenshot uses that target.
- Deferring 40,000 BDT does not create cash. It changes the synthetic obligation schedule: 30,000 remains payable at the original due date, and 40,000 is due 7 November. Target-date closing cash becomes 30,000; this is a projection, not a bank balance.
- No claims of real bank connectivity, genuine supplier consent, live AI evaluation, user interviews, regulatory certification, lender approvals, or guaranteed competition outcomes.

## Production labels

Keep “Synthetic sandbox” visible during app footage. Keep “Local demo” visible while showing the assistant. Mock financing must remain labelled MOCK and non-executable. Hash-chain evidence is local tamper-checking, not external immutable certification. Do not display API keys, one-time tokens, or local personal paths.

Existing screenshots are actual app captures; using motion on them produces a presentation, not a live interaction recording. Use new real UI capture for consent, execution, and read-back when available. Never animate a screenshot to imply an action was executed unless the underlying sandbox run actually produced it.

## Scene plan

### 01-problem — 0:00–0:20 — Cash pressure is a timing problem

**Narration:** Payroll is approaching. A customer may pay late. A supplier still needs payment. For a small business, those dates can create a cash gap. Probaho helps the owner see that gap, compare realistic options, and stay in control of the next action.

**Shot cue:** Opening motion graphic: three dated cards for payroll, receivable, and supplier obligation converge into a timeline. Use product colors; do not use a real-business claim.

**On-screen text:** Cash pressure is a timing problem / Payroll • Receivables • Supplier bills

### 02-product — 0:20–0:35 — Meet Probaho

**Narration:** Probaho is an SME finance copilot for Topic E. This presentation uses synthetic Bangladeshi taka records in a local sandbox. The workflow is records, projection, comparison, human approval, execution, and evidence.

**Shot cue:** Logo/title entrance, then real overview-desktop.png framed as a browser. Small permanent synthetic-sandbox label.

**On-screen text:** Probaho / Approval-gated SME cash-flow recovery / Synthetic BDT sandbox

### 03-exact-math — 0:35–0:57 — A concrete cash gap

**Narration:** Shapla Services starts with one hundred twenty thousand taka. Payroll needs eighty thousand, the supplier bill needs seventy thousand, and a confirmed receivable brings twenty thousand. By October thirty-first, closing cash is minus ten thousand. Against a twenty-thousand reserve floor, the shortfall is thirty thousand.

**Shot cue:** Zoom through opening-cash metric and source rows in overview-desktop.png. Animate 120,000 + 20,000 − 80,000 − 70,000 = −10,000; reserve shortfall 30,000.

**On-screen text:** Opening 120,000 BDT / Receivable +20,000 • Payroll −80,000 • Supplier −70,000 / Closing −10,000 BDT / Reserve gap 30,000 BDT

### 04-records — 0:57–1:18 — Records with clear scope

**Narration:** The Records page brings transactions, invoices, and bills together. The owner selects one business and imports a combined CSV. Every row is validated before anything is written. Dates, amounts, currency, and conflicting identifiers are checked, and source records remain linked to the calculations.

**Shot cue:** Use records-import.png or recorded Records navigation. Show business selector, transaction/invoice/bill tabs, Import dialog, and sample combined CSV download. Avoid showing a made-up successful import.

**On-screen text:** One business scope / Transactions • Invoices • Bills / Validate the whole file before writing

### 05-scenarios — 1:18–1:40 — What if the customer pays late?

**Narration:** The overview compares scheduled cash with a seven-day late-collection scenario. Here, the receivable falls beyond the target date, so closing cash drops to minus thirty thousand and the reserve gap grows to fifty thousand. The arithmetic uses integer paisa, rather than a language model's estimate.

**Shot cue:** Crop the Base and Late collection scenario cards from overview-desktop.png. Animate receivable date from Oct 31 to Nov 7 while target remains Oct 31.

**On-screen text:** Target: 31 Oct 2026 / Late collection: +7 days / Closing −30,000 BDT • Reserve gap 50,000 BDT

### 06-options — 1:40–2:01 — Compare recovery options

**Narration:** Probaho compares a collection reminder, supplier rescheduling, and mock financing. A reminder creates a draft; it never counts as collected cash. Financing shows illustrative fees and repayment terms, but cannot execute. The supplier option proposes deferring forty thousand taka to November seventh, while protecting payroll.

**Shot cue:** Use real Recovery plans page from new recording; if unavailable, crop plan-approval.png for actual supplier plan and animate separate faithful option cards. Explicit DRAFT and MOCK labels.

**On-screen text:** Reminder: draft only, cash effect 0 / Supplier: defer 40,000 BDT to 7 Nov / MOCK financing: comparison only

### 07-review — 2:01–2:21 — Human review is a separate step

**Narration:** Before approval, the owner reviews the payee, source bill, amount, dates, assumptions, and policy limits. Approval is a separate human action. Supplier rescheduling also needs a separate acceptance simulation. That button represents a sandbox scenario, not a genuine supplier response.

**Shot cue:** Use plan-approval.png. Highlight payee Rahman Supplies, bill-supplier-001, amount 40,000, original date Oct31, deferred date Nov7. Then new live-recording consent panel if available.

**On-screen text:** Review the exact action / Human approval required / Supplier acceptance simulation required

### 08-execute — 2:21–2:45 — Execute once and read it back

**Narration:** After both gates, execution changes only the synthetic payment schedule. Target-date closing cash becomes thirty thousand taka, with no reserve shortfall. The deferred supplier obligation still exists. A receipt shows the approved action and before-and-after state. Retrying with the same idempotency key returns the original receipt, instead of executing twice.

**Shot cue:** Use execution-receipt.png only for fields it truly contains; new recording should show actual approved-recovery card after execution (30,000 closing, 0 shortfall). Show deferred 40,000 obligation at Nov7. Receipt read-back flow.

**On-screen text:** Sandbox schedule changed / Target closing 30,000 BDT • Reserve gap 0 / 40,000 BDT remains due on 7 Nov / Same key → Same receipt

### 09-security — 2:45–3:05 — Evidence and bounded authority

**Narration:** Plans are bound to the selected business, policy, source records, and sandbox snapshot. Changed details invalidate a pending action. Activity exports include permission events and a per-business hash chain. The assistant has no approval, execution, payment, shell, or SQL tool.

**Shot cue:** Motion permission matrix (read/propose allowed; approve/execute human-only) connected to real Activity & evidence recording/export. Hash chain is local evidence, not immutable certification.

**On-screen text:** Snapshot-bound proposals / Model: read + propose / Human: approve / Local evidence export

### 10-assistant — 3:05–3:25 — An honest assistant mode

**Narration:** The Assistant can explain the cash gap, project scenarios, compare plans, and draft reminders. The demonstrated mode is labelled Local demo and uses deterministic tools. An optional AI adapter requires the owner's key and per-message consent; live-model quality has not yet been tested.

**Shot cue:** Use assistant-demo.png showing Local demo label. Ask “What is the cash gap?” only with real generated answer present. Small provider-status callout.

**On-screen text:** Local demo / Four scoped tools / Optional live AI requires key + consent / Live-model evaluation pending

### 11-validation — 3:25–3:42 — What has been verified

**Narration:** Checked-in verification records thirty passing backend tests, eighteen passing deterministic evaluation cases, and desktop and mobile browser checks. These are synthetic correctness and safety results. They do not establish real-world business improvement or production readiness.

**Shot cue:** Animated results cards tied to evidence/verification-summary.json; use overview-mobile.png inset. Never label them competition scores or live-AI results.

**On-screen text:** 30 backend tests passed / 18 / 18 deterministic cases / Desktop + mobile browser checks / Synthetic verification

### 12-close — 3:42–3:58 — Keep the owner in control

**Narration:** Probaho connects a cash gap to a reviewed action and a verifiable receipt. The next step is consented SME usability testing and live-model evaluation. Financial participation, with the owner in control.

**Shot cue:** Return to product logo, then single linear workflow and closing phrase. Hold readable end frame.

**On-screen text:** Records → Gap → Plans → Approval → Sandbox → Evidence / Financial participation. Owner in control.

## Shorter edit option

For a shorter reference-led presentation, use scenes 01, 02, 03, 06, 07, 08, 10, and 12 while retaining the complete version as a separate deliverable. Do not remove the synthetic, supplier-simulation, mock-financing, or Local demo disclosures. A very short reference may guide visual rhythm without restricting the complete presentation to the same runtime.
