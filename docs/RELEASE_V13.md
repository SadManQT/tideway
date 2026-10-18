# Selected-currency consistency and UI audit

The currency selector now controls editable amounts as well as readouts. The
earlier UI converted numeric cards while leaving inputs and generated prose in
ledger units. This caused mismatches such as USD selected with BDT rescue trace
figures or expense fields.

## Fixed

- One exact rational conversion/formatting layer serves cards, Owner expenses,
  what-if, policy, supplier assumptions, synthetic expenses, Inbox review and
  approval confirmation. Inputs use the selected currency and convert once to
  integer ledger minor units. Large converted values use integer arithmetic.
- Untouched rounded fields retain their original exact values. Deliberate edits
  are interpreted as edits, including explicit zero. Invalid or incomplete inputs
  cannot silently relax policy. Clearing an optional what-if expense removes it.
- Generated forecast prose, rescue timelines, plan explanations, negotiation,
  reminder previews and assistant financial text use the selected currency.
  Dates, percentages, known names, record IDs and account identifiers are protected.
  A final text-node presentation pass also covers alternative-plan notes and future
  generated prose; it excludes original source text, user messages and signed or
  technical evidence. Browser checks scan generated text across every view.
- Money in questions must name its currency when the selected units differ from
  the ledger. Explicit supported amounts are converted before model/agent calls;
  days, dates and percentages retain their meaning. No tool gains approval or
  execution authority.
- Approval review and the exposure confirmation field use the selected currency.
  A correct converted confirmation binds the original exact exposure. The native
  terms remain inspectable as immutable signing units; signed documents are never
  rewritten to make the display match.
- Bank-ready HTML, private decision briefs and CSV presentation reports honour
  the selected units. Converted CSVs retain labelled canonical provenance and
  cannot be mistaken for the original ledger import format. Original signed
  evidence, ISO 20022 drafts and original source text remain canonical.
- Currency preference persists per operator. Currency changes preserve unsaved
  expense, policy and chat drafts. Invalid monetary drafts block an ambiguous unit
  switch. Preferences reset in memory across operator changes without exposing
  another operator's private drafts.
- The privacy inspector applies the same selected-unit normalization as chat,
  so its initial cloud payload matches what consent would send. Returning an
  edited inspector question retains that draft across currency changes.
- Inbox amounts use selected units while original extraction remains available.
  Foreign source records require explicit human conversion/correction before
  entering a single-currency ledger. Missing/invalid source amounts remain editable.
- Decision lab clears private state on operator changes, rejects stale in-flight
  responses and locks inputs during calculations. Demo controls use the selected
  business role. Financial warnings open recovery; identity warnings open security.
  Invalid table markup in an empty what-if form and a stale tool-count label are
  corrected.

## Verification and limits

[Current readiness](READINESS_CURRENT.md), [unit results](../evidence/test-summary.json),
[exact currency checks](../evidence/currency-v13/currency-checks.json) and
[browser verification](../evidence/screens/browser-verification.json) record the
actual current source, results and timestamps. Browser checks exercise all 29
supported currencies across 10 views, selected-unit input payloads, exposure
confirmation, source-aware Inbox review, exports, draft preservation and mobile
layouts. Known development failures remain in versioned evidence directories.
The extended currency workflow uses a separate fresh sandbox: a combined
development run correctly hit the daily exposure cap after earlier executions.
The cap and preserved execution history were retained; test isolation was fixed.
A compatibility regression for correctly prefixed approval amounts was also
fixed; a prefix from a different selected currency remains rejected.

Rates remain illustrative fixed rates, not market quotes or an FX service. The
financial engine, ledger, signed authority and settlement currency are unchanged.
Finite tests cannot establish that every possible bug has been eliminated.
Real SME feedback, native Mac adapter/receipt checks and external review remain
outstanding; previous PDFs/model/container evidence is not relabelled as a new run.
