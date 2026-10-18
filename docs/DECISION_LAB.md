# Tideway decision lab

Topic E: SME Finance Copilot, FinTechathon 2026 International Track. These additions strengthen the existing payroll and cash-flow decision, security boundary and judge interaction. They do not add real banking, financing or real counterparty access. Open the running app, sign in, and select **Decision lab**.

## What each tool does

| Tool | Question answered | What it changes |
|---|---|---|
| Find the breaking point | What is the smallest extra integer delay from one customer that breaks this recovery? | Read-only; includes a one-day-less witness |
| Agreement stress | What happens if accepted early-payment agreements arrive late? | Read-only; supplied late-performance assumptions |
| Recovery options | Which available bundles trade cost, consent requests and risk? What extra opening cash would be needed? | Read-only; funding remains unconfirmed |
| Event monitor | How does an authorised synthetic event change the ledger and the next proposal? | Owner PIN applies an event; an armed monitor may save a fresh, unapproved proposal |
| Judge challenge & replay | Can a judge change assumptions and reproduce financial outputs? | Isolated challenge; private capsule export/import; no approvals replayed |
| Privacy inspector | What would the optional cloud model receive first? | Preview only; no network or consent |
| Two-business negotiation | Can a deferral preserve both buyer and supplier cash/payroll? | Supplied synthetic supplier assumptions; compatible quote can become a normal proposal |

Analysis uses the selected business, target, source snapshot and proposal bundle. Without a saved proposal, the engine builds an unsaved recovery preview. Changing business, target or source snapshot clears the UI's old results. Stale explicitly selected proposals are rejected by the server. Each analysis exposes its snapshot and assumptions in the expandable evidence.

## A focused judge demonstration

Use a fresh synthetic database: `python3 run.py --db data/judge-lab.sqlite3`. Demo credentials are shown on the landing page. Nadia is owner (`2468`), Imran accountant (`1357`), and Guest viewer (`0000`). Existing databases are not automatically overwritten.

1. As Nadia, run the existing rescue agent and open **Decision lab**. Find breaking points. Expand the evidence and show that the previous day still holds for a positive breakpoint. A zero means the starting path already breaches; a bounded hold is not proof against arbitrary shocks.
2. Open **Agreement stress**. Compare assumed 0%, 10%, 25%, 50% and 100% late performance. A customer's agreements share a failure draw. The amount is still received after the chosen delay; this does not simulate default loss.
3. Open **Recovery options**. Compare no action and available bundles. Extra cash is a separate conditional opening-cash calculation with a disjoint validation seed. It does not modify opening cash or prove financing is available.
4. Open **Two-business negotiation**, choose an eligible supplier bill, and review all six supplied supplier fields. The defaults are fictional. Negotiate and inspect both minimum cash paths. Make the supplier's opening cash too small or payroll too large to demonstrate rejection. Restore feasible assumptions and create a proposal. Review the assumptions again in the normal rescue card and approval dialog. Fresh PIN approvals and simulated exact counterparty consent are still needed.
5. Return to **Event monitor**. Arm it with Nadia's PIN. Apply a small unexpected expense or a later customer collection date, again with PIN. Compare the before/after likely forecast and inspect the new proposal. Old mandates are invalidated. No approval, negotiation acceptance or financial execution happens automatically. The event trace is deterministic orchestration, not a claim of live-model reasoning.
6. Open **Judge challenge & replay**. Delay a customer or block a supplier in an isolated scenario. The instruction challenge reports advisory rule flags and separately tests a fixed forbidden execution tool against the typed guard; it is not a live-model injection benchmark. Download a private capsule and upload that file to recompute the projection and seeded simulation.
7. Open **Privacy inspector**. Preview a question, expand the exact initial request and inspect names, email/account/possible-phone removal. Unrecognised private text can remain. Returning the question to chat does not send it. Later tool responses are scrubbed separately, and cloud sending still requires per-message consent.

Keep the main presentation within the contest's ten-minute limit. Choose a few live interactions; the complete lab is available for questions. Video remains deferred.

## Financial and security limits

- Reverse stress tests one customer at a time, at most 20 customers, with a 1–60 day bound and other likely receipts fixed. It reports coverage. Simultaneous shocks and forecast/model error are outside this calculation.
- Agreement lateness rates are assumptions, not observed reliability estimates. A separate random stream leaves original invoice draws aligned. Without this optional stress, the original Monte Carlo financial semantics remain unchanged.
- Recovery comparison considers the available bounded planner bundles. It is not a global optimality proof. Conditional cash is available at opening, without fee or repayment; confirm amount, date, availability and financing costs separately.
- Event injection is restricted to an owner membership of a synthetic business, with PIN and a fresh snapshot. Exact retries use a durable request ID and do not add expense or proposals twice. Reusing an ID with altered terms is rejected. The ledger update, approval invalidation, audit entry and event receipt commit atomically. Proposal computation follows that transaction. If proposal creation fails, the response explicitly says the event was applied and needs review.
- An armed monitor can propose only under an allowed autonomy level. Advise mode does not auto-propose; the kill switch blocks synthetic event processing. Prior owner discount limits, preferences, exclusions and retained bilateral constraints survive replanning. Every new proposal still needs fresh approval.
- Supplier figures are supplied assumptions, never another tenant's private ledger. The shared horizon includes supplier payroll and later receipts, even beyond the buyer target. Supplier reserve/payroll checks run when making a quote and again on approval/execution. Counter-offer replacements retain reviewed supplier limits when retaining that bill. This deterministic joint cash-path check is not a guarantee of either business's liquidity.
- Capsules contain private ledger information. The self-hash detects edits but is not an authorship signature. Engine/model file hashes must match. Import recomputes financial outputs only; no SQL, model generations, approvals, mandate issuance or payments are replayed. Export/import support at most 300 records, 150 per kind, 20 customers and 50 adjustments.
- Privacy preview shares the actual initial cloud payload builder and includes the same limited chat history. Known counterparties are pseudonymised, known payee accounts and email/possible phone patterns are removed, and ledger descriptions are omitted. IDs, dates, amounts and unrecognised personal text may remain. This is inspectable minimisation, not complete anonymisation.
- Viewer members may use read-only analysis; they cannot arm/inject events or create bilateral proposals. All HTTP routes retain session, CSRF, tenant membership, strict field validation and existing request-size/rate limits.

## Reproduce

```bash
python3 -m unittest discover -s tests -p 'test_decision_lab*.py' -v
python3 scripts/evaluate_decision_lab.py
node scripts/capture_screens.mjs --test-payment-delay --test-decision-lab
python3 scripts/prepare_release.py
```

The browser driver needs Chrome/Edge, Node 22+ and an unused test port. Evaluation uses three disclosed synthetic businesses; it is not a human study or external review. Actual compatible-model checks are stored separately from injected tool/guard tests. Native MLX/TideLM adapter and receipt-model verification remain deferred until Mac access is available. Real SME participants remain zero.

Set `TIDEWAY_DECISION_LAB=0` in `.env` and restart to hide the workspace and disable its HTTP routes/read tools. Existing financial workflows remain available.

## Contest sources

The official [International Track Appendix 2](https://www.pol.cmu.ac.th/public/blog/attachment/download/7a51866a-4cee-42b5-9187-fa4e1f4df411) describes Topic E and the 40/30/30 task, security/compliance, innovation/interaction rubric. These are optional project enhancements; the rules do not mandate these seven tools or a ten-percent model-risk cutoff. See also [the IEEE CIS Singapore contest page](https://www.ieee-cis-singapore.org/2026-fintechathon). No global uniqueness or winning guarantee is claimed.
