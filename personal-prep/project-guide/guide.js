"use strict";

/*
 * Tideway personal team preparation guide (not served by the application)
 *
 * This file intentionally has no network calls, framework runtime, or generated
 * server dependency. The viva bank is a deterministic cross-product of the
 * topic notes below and ten question angles. Every value that enters the DOM
 * goes through escapeHTML (or textContent).
 */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
}[character]));
const slugify = (value) => String(value).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const normalize = (value) => String(value ?? "").trim().toLowerCase();

const topic = (focus, fact, use, evidence, limit) => ({focus, fact, use, evidence, limit});

const VIVA_CATALOG = [
  {
    id: "story",
    title: "Product story",
    topics: [
      topic("Tideway's core promise", "Tideway predicts which customers may pay late, plans a cash rescue before a gap, and acts only after human approval.", "Start at Cash weather, then run Rescue for Shapla Services and show the proposed bundle.", "The README names the three-part promise and the demo route exercises it.", "It is an approval-gated prototype, not an autonomous treasury system."),
      topic("Topic E: SME Finance Copilot", "The project is entered in the FinTechathon 2026 International Track under Topic E, SME Finance Copilot, with the theme AI as a Financial Participant.", "State the topic, then connect the demo to the gap-plan-approval loop.", "The project brief and README identify the track and topic.", "Competition fit does not turn the prototype into a production financial service."),
      topic("the synthetic sandbox", "The businesses, balances, counterparties, messages and credentials are fictional local data.", "Say the sandbox disclaimer before showing a number or credential.", "The landing page, footer, README and technical documentation repeat the scope label.", "No bank, lender, supplier, customer or real-money rail is connected."),
      topic("the target user", "The first version targets small service businesses and wholesalers with invoices, supplier bills and payroll approaching.", "Use the Shapla story to show why a dated cash decision matters to an operator.", "The technical documentation defines the first-version records and audience.", "The prototype is not a full ERP or a universal accounting product."),
      topic("the complete product loop", "Tideway moves from records to forecast, proposal, simulated negotiation, human approval, mandate, sandbox execution and read-back.", "Narrate the loop while moving through Overview, Rescue, Security and Evidence.", "The UI and demo script expose each stage as a separate view or action.", "A proposal or assistant response alone never executes anything."),
      topic("local-first operation", "The default runtime uses Python's standard library, SQLite and a deterministic local agent without a paid service.", "Run python3 run.py, open the loopback URL and demonstrate the default agent.", "README setup instructions and the architecture diagram describe the local path.", "The optional cloud-LLM mode is opt-in and has not been measured live."),
      topic("source-linked decisions", "Tideway ties projections and proposals to records, scenarios, tool output and policy rather than presenting an unexplained score.", "Expand an Assistant tool plan and open the source records behind a Rescue proposal.", "Overview, Assistant and Evidence views expose the reasoning inputs and audit trail.", "Source links do not remove uncertainty from synthetic forecasts."),
      topic("the boundary of the product", "Moving real money, binding credit decisions, production bank integration, payroll deferral and a full ERP are out of scope.", "Answer a scope question by naming one included sandbox capability and one excluded production capability.", "The technical documentation lists the out-of-scope items explicitly.", "Do not describe mock financing or a draft payment file as a live integration."),
      topic("the three demo businesses", "Shapla Services has a payroll gap, Lotus Print Studio has a habit-driven risk and counter-offer, and Harbourline Traders demonstrates unsafe records and no safe plan.", "Switch businesses from the picker and use each one for its intended story.", "The README and demo script give the fixture narratives.", "They are fixtures for demonstration, not real customer case studies."),
      topic("proposal before authority", "The model and planner live above the store, while the store is the only layer allowed to approve, sign, execute or change policy.", "Show the proposal first, then switch to the human approval and Evidence steps.", "The architecture and technical documentation describe this authority boundary.", "The separation is implemented for the sandbox; it is not a compliance certification."),
    ]
  },
  {
    id: "cash",
    title: "Cash visibility",
    topics: [
      topic("exact minor-unit money", "Amounts are stored and calculated as integer minor units, with decimal input parsed exactly and excessive precision rejected.", "Open Records or Cash weather and point to a value whose source and currency are visible.", "The technical documentation defines amount_minor and exact parsing rules.", "Exact arithmetic does not make an underlying forecast certain."),
      topic("the daily ledger", "The projection walks each date from opening cash, adds dated inflows and subtracts dated outflows and accepted adjustments.", "Set a target date and inspect the daily minimum behind the weather label.", "Projection documentation describes the event walk and settled-invoice rule.", "Only the records and adjustment types supported by the sandbox enter the ledger."),
      topic("the scheduled scenario", "Scheduled cash uses the dates currently present in records as the base projection.", "Use the Overview scenario cards before opening likely or stress explanations.", "The technical documentation calls scheduled the base scenario.", "A scheduled date is not a promise that a counterparty will pay on that date."),
      topic("the likely scenario", "Likely cash moves open invoices toward the expected date from the customer's payment profile.", "Compare likely with scheduled for an invoice whose customer has settled history.", "Projection and customer-profile documentation define the expected-date input.", "The profile is derived from synthetic history and can have low confidence."),
      topic("the stress scenario", "Stress applies a pessimistic high-percentile delay for each customer to reveal a less comfortable path.", "Open the stress view and identify which customer or date changes the minimum cash.", "The projection documentation defines stress as a high-percentile delay.", "Stress is a defined scenario, not a claim that the worst case will happen."),
      topic("the linked payment-delay demo", "An explicit owner/PIN change to a synthetic invoice advances the snapshot and invalidates previous approval authority; ordinary What-if remains read-only.", "Approve Shapla, delay Bay Logistics to 15 November under What-if, show stale execution refused, and approve a fresh proposal and counter terms before execution.", "PAYMENT_DELAY_RUNBOOK.md and evidence/upgrade-v1/payment-delay.json preserve the calculated transition.", "Never force consent or imply a hypothetical scenario can execute; repeat with a fresh database that preserves earlier evidence."),
      topic("the reserve floor", "The reserve floor is the cash level the workspace policy says should not be crossed.", "Read Shapla's BDT 20,000 reserve on Overview and compare it with the minimum.", "The fixture and policy views show the reserve value and shortfall.", "A reserve floor is a policy target, not a bank guarantee."),
      topic("Shapla's concrete gap", "Shapla opens with BDT 120,000 cash, BDT 80,000 payroll, a BDT 70,000 supplier bill, BDT 20,000 receivable and a BDT 20,000 reserve; scheduled minimum is BDT -10,000 on 31 Oct 2026.", "Use the target date 2026-10-31 and read the BDT 30,000 reserve shortfall aloud.", "The README and technical documentation give these fixture numbers.", "They are synthetic fixture values, not a financial result for a real business."),
      topic("cash-weather labels", "Clear, Unsettled and Storm summarise defined risk thresholds: scheduled breach or at least 50% risk is Storm, and at least 15% breach risk is Unsettled.", "Open the weather explanation and identify whether the label comes from a schedule or simulation.", "The technical documentation states the label thresholds.", "The label is a summary of this model, not a universal risk rating."),
      topic("one currency per workspace", "A business uses exactly one of the supported ISO 4217 currencies, and mixed currencies inside one business are rejected.", "Choose a currency at sign-up and try to keep imported records in that currency.", "The data-model and setup documentation define the whitelist and rejection rule.", "Illustrative display conversion never changes calculation or mandate currency."),
    ]
  },
  {
    id: "planning",
    title: "Planning & rescue",
    topics: [
      topic("five TidePay lateness bands", "TidePay predicts on time, 1–7, 8–15, 16–30 and more than 30 days late for open invoices.", "Open an invoice explanation or ask which customer may be late, then inspect its profile.", "The README, technical documentation and TidePay report describe the bands.", "The output is a probability distribution over synthetic data, not a promise."),
      topic("credibility-weighted customer profiles", "The explainable fallback blends a customer's settled history with the business-wide mean, with confidence based on history size.", "Compare a high-history profile with a no-history customer in the customer explanation.", "The technical documentation describes the Buhlmann-style blend, grade and confidence.", "A thin history should be presented as low confidence, not as certainty."),
      topic("the seeded Monte Carlo", "One thousand runs draw payment timing from TidePay distributions with a seed derived from business, snapshot hash and target date.", "Repeat the same Shapla target date and show that the result is reproducible.", "The technical documentation and evaluation plan state the run count and seed rule.", "The simulation varies payment timing only; it is not a complete economic model."),
      topic("the exact planner search", "The planner evaluates bounded combinations of at most one option per record across the six most relevant records.", "Run Rescue and expand rejected reasons or the alternatives beside the recommended bundle.", "The technical documentation specifies the candidate search and ranking.", "The search space is intentionally bounded for the local prototype."),
      topic("supplier deferral", "A permitted supplier bill may move by 50% or 100% and 7 or 14 days, priced at an assumed 12% annual rate.", "Inspect a proposed deferral and its terms before approval.", "Planner documentation lists the allowed fractions, delays and price assumption.", "Payroll and blocked payees can never be deferred."),
      topic("early-payment offers", "A customer can receive a 1%, 2% or 3% discount for earlier payment, with the cost shown as an annualised rate.", "Open the proposal explanation and ask why a discount is more or less expensive than a delay.", "The planner documents the formula and the example of 2% for 20 days.", "This is a simulated offer, not a contract or collection promise."),
      topic("zero-cash reminders", "A collection reminder is a message draft; a promise to pay is tracked as information and never counted as cash by itself.", "Review a reminder action in Rescue and distinguish it from a cash inflow.", "Planner and autonomy documentation define reminders as zero-cash actions.", "The agent cannot treat an acknowledgement as settled money."),
      topic("feasible bundle ranking", "A feasible bundle holds the reserve on the likely dated path and stays within owner and policy caps. Simulation separately estimates remaining risk; some proposals miss the 10% target.", "Compare proposal terms, risk and the owner's discount ceiling before approving.", "Planner documentation and the disclosed H11 result distinguish feasibility from target attainment.", "H11's historical 11.78% estimate requires explicit residual-risk consent; acknowledgement is not a guarantee."),
      topic("an honest no-safe-plan result", "If no feasible bundle satisfies the rules, Tideway states that no safe plan exists and escalates instead of inventing one.", "Switch to Harbourline Traders and ask which bills are blocked and why.", "The task cases and demo script include the no-safe-plan outcome.", "Escalation does not solve the gap; it makes the constraint visible."),
      topic("the What-if workspace", "What-if changes a payment delay or adds an expense in a temporary simulation without writing to the ledger.", "Open What-if, change one assumption, compare the result and reset it.", "The UI description and app view distinguish What-if from Records.", "A What-if result cannot be approved or executed as if it were a saved record."),
    ]
  },
  {
    id: "approval",
    title: "Approval & execution",
    topics: [
      topic("proposal bundles", "The agent creates up to three bundles with exposure, risk before/after and source records, including recommended and alternative options.", "Run Rescue, open each bundle and read its source records before choosing one.", "The mandate section of the technical documentation defines the proposal shape.", "A bundle is a proposal until the required people approve it."),
      topic("role checks", "Owner, accountant and viewer roles are scoped per business; viewers can read but cannot approve.", "Sign in as Guest and try to approve, then repeat the view as Nadia or Imran.", "Security assessment cases AT-AUTH-02 and the Team view cover this boundary.", "A person's role in one business does not grant authority in another."),
      topic("PIN step-up", "Approval asks the operator to re-enter a PIN, with PBKDF2 hashing and a five-failure, five-minute lockout.", "Open Review and approve and observe the explicit PIN step rather than treating login as approval.", "The technical documentation and security assessment specify the PIN controls.", "The demo PINs are intentionally synthetic and demo-grade."),
      topic("dual approval", "Exposure above the dual-approval threshold needs two different people, one of whom is the owner.", "Approve as Nadia, switch to Imran, and approve the same exact bundle once.", "The demo script and security cases AT-AUTH-03 cover maker-checker approval.", "One person cannot satisfy both approvals by changing roles or repeating a click."),
      topic("typed exposure confirmation", "Each dual approver types the exact total exposure to show they read the amount before the approval is accepted.", "When the dialog asks, type the amount shown in the summary instead of guessing.", "The UI and evaluation plan mention the typed-amount requirement.", "Typing an amount does not replace the PIN or role checks."),
      topic("the HMAC mandate", "The second approval issues an HMAC-SHA256-signed JSON mandate scoped to exact actions, amounts, counterparties, plan and snapshot.", "Open Evidence or the approval summary and inspect the mandate scope before execution.", "Mandate tampering is an explicit security test case.", "The local signing key is demo-grade and the mandate is not a bank instruction."),
      topic("short-lived scope and expiry", "A mandate binds a policy version and snapshot and expires after 15 minutes, so old or changed state cannot be used silently.", "Ask what happens if a record changes or the mandate expires before execution.", "The technical documentation lists expiry and state-hash checks.", "Fresh approval is needed after a counter or material change."),
      topic("simulated counterparty replies", "Simulated suppliers and customers accept, counter or reject using repeatable rules; a counter is a new proposal and a rejection triggers a re-plan.", "Use Lotus Print Studio to show a counter-offer, then inspect the revised approval path.", "Counterparty and task-case documentation define these outcomes.", "There is no live supplier or customer conversation behind a reply."),
      topic("execution checks", "Execution checks signature, expiry, caller authority, pause state, accepted replies and fresh record/state hashes before one transaction.", "After approvals and accepted simulated replies, choose Execute once and read the receipt.", "The store execution sequence and security cases document the checks.", "The transaction changes only the local synthetic sandbox."),
      topic("idempotency and read-back", "The same idempotency key returns the same receipt, while a new key cannot reuse a consumed mandate; before/after hashes are read back.", "Point to the receipt and explain how a retry differs from a second execution.", "The technical documentation and AT-MAN-06 test cover replay and double-spend behaviour.", "Idempotency controls a sandbox operation; it does not create a payment rail."),
    ]
  },
  {
    id: "security",
    title: "Security & trust",
    topics: [
      topic("the model tool allow-list", "The assistant can use six read/propose tools and never receives approve, execute, SQL, shell or URL authority.", "Ask Tideway a question and expand the typed plan under the answer.", "The technical documentation lists the six tools and the validator boundary.", "A hijacked model can still produce bad text, so the enforcement boundary lives outside it."),
      topic("prompt-injection screening", "Instruction-like phrases, links, markup, new account details and known payment identifiers are screened in multiple languages.", "Paste the synthetic injection sample into Inbox and inspect the warning before saving anything.", "The security assessment maps the poisoned-record and injection cases.", "Pattern screening catches defined signals but is not a guarantee against unknown phrasing."),
      topic("hidden Unicode", "Text is NFKC-normalised and invisible format characters are stripped and flagged before suspicious content can hide in a record.", "Use the Inbox or Records warning to show that a hidden character is treated as a signal.", "AT-PI-03 and the domain documentation describe the normalisation rule.", "The structural draft-only and tool boundary controls do not rely on perfect detection."),
      topic("quarantined record text", "Suspicious free text already in ledger records is kept as data and excluded from planning and model context.", "Open a flagged record and explain why its text is visible for review but not an instruction.", "The technical and security documents define quarantine at the reasoning boundary.", "Quarantine preserves the record for review; it does not silently clean a source claim."),
      topic("changed bank details", "A changed bank account blocks every action on the affected bill until the owner verifies it by callback to a number on file.", "Use Harbourline Traders and open the blocked-bill reason in Security or Rescue.", "AT-BEC-01 and the demo script define the changed-account fixture.", "The callback is simulated in the sandbox and is not a bank verification service."),
      topic("look-alike payees", "A payee name with similarity of 0.85 or more to another known payee is treated as a look-alike and blocked.", "Inspect Harbourline's payee warning and ask why the action is excluded.", "The analytics and security assessment specify the threshold and block.", "The threshold is a defined prototype rule, not a complete identity system."),
      topic("owner-only callback verification", "Only the owner can clear a flagged payee, and the verification path is a callback to a number on file.", "Sign in as Nadia and open the verification control; compare with Imran or Guest permissions.", "AT-BEC-03 tests owner-only callback verification.", "The fixture and phone number are synthetic; no real callback occurs."),
      topic("separation of duties", "The operator who verified a payee cannot be the only approver of actions for that payee.", "After a verification in the fixture, try to complete the approval with the same operator alone.", "AT-BEC-04 explicitly tests the separation rule.", "This control supplements, rather than replaces, human review of the payee."),
      topic("the kill switch", "Pausing blocks planning and execution; only the owner can resume after giving a reason.", "Open Security centre, pause with a reason, observe the blocked action, then resume as Nadia.", "AT-KILL-01 and the autonomy section describe the pause path.", "The stop is local to the workspace agent; it does not rewind a completed action."),
      topic("the circuit breaker and rate limits", "Five signed-in security denials within ten minutes pause the agent, and token buckets reject burst requests.", "Run the self-test or inspect the security status after repeated defined denials.", "AT-KILL-02 and AT-DOS-01 are listed in the self-assessment.", "The result is evidence for the defined cases, not a claim of universal denial or availability."),
    ]
  },
  {
    id: "ai",
    title: "AI & languages",
    topics: [
      topic("TideLM typed plans", "TideLM turns an owner's natural-language request into a typed plan that must resolve names and pass the known-tool validator.", "Ask a question in Assistant, then expand the exact plan chosen below the answer.", "The technical documentation and README describe read/propose validation.", "The model cannot approve, execute or bypass the store."),
      topic("the deterministic local agent", "Without the optional adapter, a deterministic local agent answers from tool output and runs a visible step-by-step rescue path.", "Start the app without TideLM and run the same Shapla question or Rescue task.", "README says the app still runs and uses the deterministic local agent.", "Deterministic does not mean forecasts are certain; it means the local path is repeatable."),
      topic("supported reply languages", "The Assistant supports English, Chinese, Spanish, French, Portuguese and Indonesian, with Hinglish and Banglish answered in English; TideLM training also covers the broader input set described in the docs.", "Ask a short question in another supported language and compare the numeric values with English.", "Conversation documentation and the landing page list the language behaviour.", "Language coverage does not create a live translator or change the underlying ledger currency."),
      topic("number grounding", "Assistant numbers are composed from tool output, and optional model text is checked for figures that do not appear in the tool results.", "Ask for a briefing, open its tool plan and look for the source values behind the answer.", "The agent and security documentation define the grounding check.", "A grounding flag is a warning to inspect, not proof that all model prose is correct."),
      topic("TideLM synthetic training", "TideLM is a LoRA fine-tune of Qwen3-4B-Instruct on generated multilingual examples; its held-out names were not used in training.", "If discussing the adapter, point judges to the local evidence report and describe the data as synthetic.", "The README records the training recipe and evidence files.", "Synthetic test scores do not establish production accuracy or a live-provider result."),
      topic("TidePay federated training", "TidePay is a pure-Python softmax model trained with simulated federated averaging across 40 synthetic SMEs and illustrative pairwise masks. One process holds the client data; no deployed privacy guarantee is claimed.", "Use the TidePay explanation or evidence report when a judge asks how customer history becomes a prediction.", "The README, model card and TidePay report describe simulated FedAvg and its limits.", "The training evidence uses synthetic invoices, not a real lender dataset."),
      topic("draft extraction from messages", "The local extractor turns pasted alerts or chats into draft records and flags injection; it cannot write a final record until a person confirms.", "Paste the Inbox sample, press Extract, then inspect and confirm only the clean fields.", "The Inbox view and security assessment document the draft-only boundary.", "A draft is not evidence that the underlying message is genuine."),
      topic("optional cloud-LLM mode", "A user-key, per-message opt-in mode can send pseudonymised names and tool output to an OpenAI-compatible provider while keeping record free text out.", "Read the consent control and optional setup note before discussing this path.", "The README and technical documentation describe the exact privacy boundary.", "No live-LLM run has been measured or claimed in the repository."),
      topic("briefings and follow-up suggestions", "Greetings, status questions and “what can you do?” are answered from live local data, and each answer can suggest up to three useful follow-ups.", "Start Assistant with “hi”, then choose a suggested question about risk or the plan.", "Conversation documentation and the demo script describe the briefing route.", "Suggestions guide the operator; they do not grant new permissions."),
      topic("the missing payment tool", "The Assistant has no payment tool, so a request such as “pay Rahman now” cannot turn into an execution instruction.", "Ask the exact phrase in the demo and point to the refused capability plus the human Rescue route.", "The demo script makes this a deliberate judge moment.", "The absence of a payment tool is a design boundary, not a failure to connect a bank."),
    ]
  },
  {
    id: "records",
    title: "Inbox & records",
    topics: [
      topic("the Inbox workflow", "Inbox input is extracted locally, scanned deterministically, shown as a draft and saved only after explicit confirmation.", "Open Inbox, paste a synthetic message, Extract, inspect warnings and confirm the clean draft.", "The UI, demo script and security assessment all describe the four-stage workflow.", "The extractor does not receive approval or execution capability."),
      topic("the three record types", "The ledger accepts transactions, invoices and bills, each with validation and status fields suited to the cash projection.", "Use Records filters or CSV import to identify a transaction, invoice and bill.", "The data-model section enumerates the types and statuses.", "Not every ERP object or accounting workflow is represented."),
      topic("all-or-nothing CSV import", "CSV input is validated as a whole before anything is written, so a single bad row rejects the file.", "Download the example, import it, and point out that validation happens before commit.", "The technical documentation and Records view specify the transaction boundary.", "A successful import still describes synthetic records and does not reconcile a real account."),
      topic("CSV size and field rules", "Imports reject unknown or duplicate columns, other-tenant rows, mixed currencies and files above 5,000 rows or 1.5 MB.", "Open the Import records dialog and read the validation note before choosing a file.", "The data-model and HTTP documentation list the limits and allow-list rules.", "The limits are prototype safeguards, not a claim of unlimited ingestion."),
      topic("spreadsheet formula escaping", "Exports prefix cells beginning with =, +, - or @ so opening a CSV does not treat untrusted text as a spreadsheet formula.", "Export records or receipts and inspect a suspicious cell in the resulting CSV.", "The security assessment and Evidence documentation state the neutralisation rule.", "Formula escaping protects the export format; it does not validate the meaning of a record."),
      topic("record text as untrusted data", "Text from bills and ledger notes is treated as data, screened and quarantined when suspicious rather than being promoted to an instruction.", "Open a quarantined record and show its warning alongside the source fields.", "The architecture names stored record text as a trust boundary.", "Reviewers still need to decide whether a source record is genuine."),
      topic("mixed-currency rejection", "A workspace has one currency, and CSV rows or records that introduce a different currency are rejected.", "Choose a business currency, then explain why an import in another currency cannot silently join it.", "The money/data model and International feature describe the rule.", "The display selector can show illustrative conversions, but it does not merge currencies."),
      topic("optional receipt photos", "On Apple Silicon, the optional MLX-VLM path can add receipt-photo extraction; the core app runs without it.", "Describe the photo path as optional only after explaining the paste-text Inbox route.", "The README mentions mlx-vlm as an optional addition.", "A receipt photo is still a draft requiring human confirmation and is not real-world verification."),
      topic("the example CSV", "The Records dialog offers a synthetic example file so an operator can see the accepted record shape before importing.", "Open Records, choose Import CSV and press Download example.", "The existing UI includes the sample-csv action.", "The example is a schema aid, not a data feed from a bank."),
      topic("local data privacy", "The deterministic agent and default TideLM path keep questions, records and extracted messages on the owner's machine.", "Run the offline default and explain what is local before discussing the optional provider path.", "The security self-assessment has a dedicated privacy section.", "The local prototype still needs production identity and host hardening for a real deployment."),
    ]
  },
  {
    id: "workspace",
    title: "Workspaces & roles",
    topics: [
      topic("business sign-up", "Sign-up creates a business, owner account, membership and plan in one transaction with safety defaults from the owner's opening cash and reserve.", "Use Start free with a synthetic business name, one currency, cash, reserve, username and PIN.", "The SaaS-workspace documentation and landing form describe the fields.", "Plan pricing is illustrative and no card is charged."),
      topic("one-time team invites", "Owners invite teammates with a hashed, single-use code that expires after seven days and respects seat limits.", "Open Team as Nadia, create an invite and join from a separate synthetic operator.", "The technical documentation lists hashing, expiry and seat rules.", "The code is a demo invitation, not an identity-proofing mechanism."),
      topic("owner, accountant and viewer", "Owners configure and approve, accountants can approve within the maker-checker rules, and viewers read without approval authority.", "Use Nadia, Imran and Guest to demonstrate the different approval outcomes.", "The landing credentials and security assessment define the roles.", "Role names describe this workspace policy; they are not regulated job titles."),
      topic("tenant isolation", "Every API call is scoped to a business membership, and a request for another tenant is refused instead of returning its records.", "Switch between the available demo businesses and explain the per-business scope check.", "The architecture and security docs name the membership/business-id boundary.", "The repository is a local prototype; production would need a hardened deployment."),
      topic("illustrative plans", "Starter and Growth-style plan choices describe seats and businesses for the prototype, but their prices are illustrative and nothing is charged.", "Show the plan cards on the landing page without presenting them as a live subscription checkout.", "README and UI copy label prices illustrative.", "No payment processor or subscription contract is connected."),
      topic("a role per business", "The same operator can be an owner in one business and only a viewer or accountant in another because membership is per business.", "Use the business picker and compare available controls rather than assuming a global role.", "The technical documentation explicitly says roles are per business.", "An operator's other-business role cannot approve this business's mandate."),
      topic("new-account PIN rules", "New account PINs have 6–12 digits and cannot be all repeated or a simple ascending/descending sequence.", "Use the sign-up form and read its inline validation before creating a synthetic account.", "The README and app validation describe the PIN constraints.", "The visible demo PINs are legacy fixture credentials and should not be reused elsewhere."),
      topic("the business picker", "The signed-in shell lists only businesses to which the current operator belongs and scopes the dashboard to the selected one.", "Choose a business from the left-side picker, then compare its cash weather and role controls.", "The app shell and tenant checks implement the picker boundary.", "Changing the picker does not merge ledgers or currencies."),
      topic("the Guest route", "Guest is a viewer fixture with PIN 0000 for showing a read-only perspective in the synthetic demo.", "Sign in as Guest and attempt to open approval controls; then return to Nadia for the action.", "The README credential table and demo account buttons define Guest.", "0000 is public demo data, never a production secret."),
      topic("team accountability", "Membership, approvals, negotiations and executions appear in the per-business audit history so a team can reconstruct who acted.", "Open Team to see roles, then Evidence after an approval or receipt.", "The store and audit documentation link membership actions with evidence.", "Audit evidence is local and does not replace a real organisation's identity system."),
    ]
  },
  {
    id: "evidence",
    title: "Evidence & exports",
    topics: [
      topic("the hash-chained audit log", "Each business audit entry hashes its predecessor so an edit in the chain can be identified.", "After a proposal or approval, open Evidence and run verification.", "The technical documentation and tamper test define the chain.", "A privileged attacker who controls every local key and database remains a residual risk."),
      topic("the independent witness", "A separate witness file periodically co-signs the chain head, helping detect deletion of the tail as well as edits.", "Run the Evidence verification and point to the witness checkpoint result.", "The audit section and security assessment explain the independent witness.", "The witness is local; it is not an external immutable ledger."),
      topic("the tamper drill", "Evidence can edit a copy of the audit data and demonstrate that verification catches the altered chain.", "Open Evidence and choose Tamper drill; read the first invalid entry reported.", "The demo script and security assessment include the drill.", "A passing drill demonstrates the defined detector, not every possible compromise."),
      topic("evidence JSON", "The evidence export packages audit and verification information in JSON for inspection or submission evidence.", "Use Evidence export after running the self-test or a demo action.", "README and technical documentation name evidence JSON as an export.", "The export contains synthetic local activity and is not a legal record."),
      topic("records CSV", "Records can be exported to CSV for spreadsheet review, with formula-like cells neutralised.", "Open Records or Evidence and download the records export, then inspect its headers.", "The security and Evidence sections define records CSV and formula escaping.", "The export is a copy of the sandbox ledger, not a bank statement."),
      topic("receipts CSV", "Execution receipts can be exported separately so an operator can inspect outcomes and before/after state hashes.", "Execute the synthetic plan once, then export receipts from Evidence.", "The Evidence view and README list receipts CSV.", "A receipt proves a sandbox mutation, not settlement on a real rail."),
      topic("the pain.001 draft", "Tideway can create a draft ISO 20022 pain.001.001.09 file for deferred supplier payments.", "Choose the draft export after a permitted deferral and read its sandbox label.", "The technical documentation lists the exact ISO draft format.", "The file is never transmitted and is not a bank instruction."),
      topic("before and after state hashes", "Execution stores state hashes before and after its transaction and reads the state back to verify the result.", "Read the receipt after Execute once and identify both hashes.", "The mandate/execution section documents the read-back check.", "Hash equality or change describes local state integrity, not external settlement."),
      topic("audit events", "Proposals, approvals, negotiations, executions and rejections append structured events to the business chain.", "Perform a small demo action and inspect which event was appended.", "The store and Evidence documentation list the event families.", "A logged event is not permission; the store still enforces the next action."),
      topic("evaluation artifacts", "The repository keeps results.csv, run-log.jsonl and verification-summary.json from the defined evaluation script.", "Run the evaluation command and point to the generated evidence files.", "README, evaluation plan and submission checklist name the artifacts.", "Artifacts report the listed synthetic cases and must not be generalised to production."),
    ]
  },
  {
    id: "setup",
    title: "Setup & demo",
    topics: [
      topic("Python setup", "The default app runs on Python 3.11+ with the standard library and starts from run.py.", "Run python3 run.py and open the loopback URL in a browser.", "README Quick start and the pinned .python-version give the setup path.", "The default server is for local/demo use and binds to loopback."),
      topic("the canonical test command", "make test is the offline test command for the repository; the unittest discovery command is also documented.", "Run make test before a judging session and report the actual output.", "README and the reproducibility notes identify make test.", "Tests cover listed cases and do not prove all possible security properties."),
      topic("the Docker path", "The supplied Dockerfile builds the app with its system/dependency setup and can run it with a loopback host mapping and persistent data volume.", "Build tideway:local and run the documented port mapping for a clean sandbox.", "README gives the docker build and docker run commands.", "The Docker example is still a local prototype deployment, not production hosting."),
      topic("the loopback URL", "The demo opens at http://127.0.0.1:8787 and the server binds to loopback only.", "Open the URL after run.py and use the landing demo account buttons.", "README Quick start and the demo script use this URL.", "Do not expose this development server to a network."),
      topic("the demo credential table", "Nadia/2468 is Owner, Imran/1357 is Accountant and Guest/0000 is Viewer in the fictional fixture.", "Use the one-click demo buttons or the visible credential table in this handbook.", "README and DEMO_SCRIPT.md list the same values.", "These credentials belong to the synthetic demo only."),
      topic("the Shapla route", "The two-minute route starts with Nadia, opens Shapla's Storm cash weather and reads the brief before asking, planning and approving.", "Follow the ordered judge route in the Setup section of this handbook.", "DEMO_SCRIPT.md specifies the timings and screen order.", "The narration must say that no real money moves."),
      topic("the Lotus route", "Lotus Print Studio is the fixture for a schedule that looks fine but customer habits and a counter-offer create a more nuanced plan.", "Switch to Lotus after the core loop and show the counter-offer handling.", "README and DEMO_SCRIPT.md describe Lotus's story.", "The counterparty is a deterministic simulator, not an actual supplier."),
      topic("the Harbourline route", "Harbourline Traders demonstrates a changed account, look-alike payee, poisoned bill and an honest no-safe-plan outcome.", "Ask which bills are blocked and why, then open Security or the risk answer.", "README and DEMO_SCRIPT.md specify Harbourline's evidence story.", "A block in this fixture does not mean every real fraud pattern is stopped."),
      topic("the optional TideLM preparation", "The adapter can be downloaded and installed locally, but the app remains usable with the deterministic agent when it is absent.", "Wait for the local model only if you intentionally set up the optional Apple Silicon path.", "README and DEMO_SCRIPT.md describe the optional command and fallback.", "Do not claim optional-model performance as live-provider performance."),
      topic("the browser and helper scripts", "A normal modern browser runs the app; Node 22+ and Google Chrome are needed only for screenshot and PDF helpers.", "Keep the core demo separate from the optional capture and document-generation commands.", "README identifies the browser, Node and Chrome scope.", "The helpers are not required to understand the product loop."),
    ]
  },
  {
    id: "evaluation",
    title: "Evaluation & judging",
    topics: [
      topic("the 30-of-30 result", "The defined self-test reports 30/30 cases passing: five task cases and 25 attack cases, with zero attacks not blocked in that suite.", "Run python3 -m tideway.selftest or Security centre self-test and name the case scope.", "The security assessment and evaluation plan record the result.", "It is evidence for these synthetic cases, not proof of security or a certification."),
      topic("the five task cases", "The task suite covers payroll rescue, a counter-offer, re-planning after refusal, no safe plan, and delegated zero-cash reminders.", "Use the self-test summary or demo route to map each task to a visible screen.", "The evaluation plan lists the five end-to-end task cases.", "A task case passing does not guarantee an unseen workflow."),
      topic("the 25 attack cases", "The attack cases cover authority, mandate, injection, payee fraud, isolation, policy, kill switch, audit, grounding, denial-of-service and delegation boundaries.", "Open the security self-assessment table when a judge asks what the 30 cases contain.", "SECURITY_SELF_ASSESSMENT.md enumerates each case ID and enforcement.", "The mapping is a self-assessment against the project's own tests, not third-party review."),
      topic("evidence versus claims", "Measured local results can be stated with their case list, while planned live-provider, user-study and baseline comparisons must not be presented as done.", "Answer “what have you measured?” with the evaluation plan's measured/planned split.", "EVALUATION_PLAN.md has a claims policy and raw-evidence paths.", "Never round up, extrapolate or invent participants, accuracy or savings."),
      topic("the automated test suite", "The repository includes offline unit, HTTP and security tests for money parsing, CSV validation, tenant checks, CSRF, cookies and export safety.", "Run the documented unittest discovery command and keep the actual output with the demo evidence.", "README and the security assessment identify the test areas.", "Automated tests are evidence of implemented cases, not a substitute for independent review."),
      topic("reproducible seeds", "Monte Carlo seeds derive from business, snapshot hash and target date so the same records produce the same numbers.", "Repeat Shapla with the same date and compare the risk result.", "The technical documentation and evaluation plan state the determinism rule.", "Changing records, policy or date should legitimately change the result."),
      topic("submission evidence", "The repository documents commands for tests, evaluation, screenshots and submission PDFs so a judge can see how evidence was produced.", "Point to README commands rather than claiming an asset was generated during the viva unless it was.", "README and the submission checklist list the commands and evidence files.", "The old or optional media path must not be presented as a live production run."),
      topic("the honest-claims policy", "The team may claim defined sandbox cases pass, but may not claim production fraud prevention, real-world accuracy, user savings or certification without measured evidence.", "When challenged, state the limitation first and then show the measured artifact.", "EVALUATION_PLAN.md section 3 gives the wording boundary.", "Honesty is part of the product story, not a footnote to hide."),
      topic("the judge route", "A compact route is landing login, Shapla weather, Assistant plan, Rescue approval, Inbox warning, Harbourline block, Team invite, self-test and tamper drill.", "Use the two-minute tour in README or the six-step route in this handbook.", "README and DEMO_SCRIPT.md provide the judge sequence.", "The route is a demonstration of the sandbox, not a claim of deployment readiness."),
      topic("worst-case security assumptions", "The security tests assume a fully hijacked model and a rubber-stamp human, then check that authority enforcement outside the model still blocks unauthorised actions.", "Explain this assumption before citing the attack-suite result.", "The security self-assessment states the threat assumption and controls.", "Human fast-approval is flagged in audit evidence, not magically made safe."),
    ]
  },
  {
    id: "limits",
    title: "Limits & honest scope",
    topics: [
      topic("synthetic training and data", "TidePay, TideLM and the demo workspaces rely on synthetic data and fictional counterparties.", "Label every example and model figure as synthetic while answering.", "README, technical documentation and security assessment repeat this limitation.", "Synthetic evidence shows the method in this sandbox, not real-world performance."),
      topic("simulated counterparties", "Supplier and customer replies are deterministic rules for accept, counter, reject or acknowledgement rather than messages from people.", "Show the reply label in Rescue and explain why a counter needs fresh approval.", "The counterparty documentation defines the simulator.", "The simulator cannot predict how a real supplier will respond."),
      topic("no bank integration", "No bank, payment provider, lender, mobile-money rail or external customer system is connected.", "Use the scope callout and the sandbox footer when asked what is connected.", "The README honest-scope paragraph and technical documentation say this directly.", "The loopback server must not be described as a live finance integration."),
      topic("no real-money movement", "The execute action mutates local synthetic state only and the payment file is never sent.", "Read the receipt as a sandbox state change and point to the no-real-money disclaimer.", "README, Evidence and setup docs make the boundary explicit.", "A successful local receipt is not settlement or a bank confirmation."),
      topic("TidePay's synthetic evaluation", "TidePay's reported log-loss and MAE comparisons are on the repository's synthetic training/evaluation setup.", "If a judge asks for accuracy, name the evidence file and the synthetic dataset scope.", "README links evidence/ml/tidepay_report.md.", "Do not convert those metrics into a live accuracy claim."),
      topic("no live-LLM measurement", "The optional cloud-LLM path has no measured live-provider latency, cost or grounding study in the repository.", "Say “not measured” and point to the planned column in EVALUATION_PLAN.md.", "The evaluation plan and README both prohibit the unmeasured claim.", "The local deterministic path remains the reproducible default."),
      topic("demo-grade identity", "PINs and a local signing key stand in for production identity and hardware-backed keys.", "Answer a deployment-hardening question by naming this residual limitation.", "The security assessment lists demo-grade identity as a known risk.", "Passing the PIN tests does not make this a bank-grade authentication system."),
      topic("the privileged-host risk", "A person who can rewrite the database and both local key files can forge more history; the witness raises the bar but cannot eliminate that risk.", "Use the Evidence explanation to distinguish tamper detection from an external immutable ledger.", "The security assessment lists the residual privileged-attacker risk.", "The handbook should not call the local witness tamper-proof."),
      topic("SQLite and one process", "SQLite and a single local process are adequate for the sandbox, while a production deployment would need hardened service and database operations.", "State the runtime architecture when a judge asks about scale or availability.", "Technical documentation limitations name the one-process/SQLite boundary.", "A working demo is not a production capacity test."),
      topic("no compliance certification", "Tideway is not claiming PCI, SOC 2, local regulator approval, bank approval or any other compliance certification.", "Close a compliance question by naming the self-assessment and its limited scope.", "The security assessment explicitly disclaims certification.", "Security controls in a prototype are not a legal or regulatory status."),
    ]
  }
];

const QUESTION_FORMS = [
  (focus) => `Explain ${focus} in one clear sentence, and why it matters in Tideway.`,
  (focus) => `If a judge asks about ${focus}, what is your shortest accurate answer?`,
  (focus) => `How would you demonstrate ${focus} in the running synthetic sandbox?`,
  (focus) => `Which input does ${focus} use, and what output should a reviewer inspect?`,
  (focus) => `What boundary or control is visible around ${focus}?`,
  (focus) => `How does ${focus} help the Shapla payroll-gap story?`,
  (focus) => `What can ${focus} not claim or do?`,
  (focus) => `Which screen, test or evidence file supports ${focus}?`,
  (focus) => `What would change in the response if ${focus} were unavailable?`,
  (focus) => `Give a 30-second explanation of ${focus} for a non-technical judge.`
];

const generateVivaQuestions = () => VIVA_CATALOG.flatMap((category) => category.topics.flatMap((item, topicIndex) => QUESTION_FORMS.map((makeQuestion, angleIndex) => ({
  id: `V-${String((VIVA_CATALOG.slice(0, VIVA_CATALOG.indexOf(category)).reduce((total, entry) => total + entry.topics.length, 0) + topicIndex) * QUESTION_FORMS.length + angleIndex + 1).padStart(4, "0")}`,
  category: category.title,
  categoryId: category.id,
  focus: item.focus,
  question: makeQuestion(item.focus),
  fact: item.fact,
  use: item.use,
  evidence: item.evidence,
  limit: item.limit
}))));

const VIVA_BANK = generateVivaQuestions();

// Fail loudly during development if an edit accidentally weakens the bank.
const VIVA_TARGET_COUNT = 1200;
if (VIVA_BANK.length < VIVA_TARGET_COUNT || new Set(VIVA_BANK.map((item) => item.question)).size !== VIVA_BANK.length) {
  throw new Error(`Viva bank must contain ${VIVA_TARGET_COUNT} distinct questions; found ${VIVA_BANK.length}.`);
}
if (typeof window !== "undefined") window.TIDEWAY_VIVA_BANK = VIVA_BANK;

const state = {
  query: "",
  category: "all",
  limit: 48,
  currentId: VIVA_BANK[0]?.id || "",
  printMode: "page",
  printLimit: 48
};

const filteredQuestions = () => {
  const query = normalize(state.query);
  return VIVA_BANK.filter((item) => {
    if (state.category !== "all" && item.categoryId !== state.category) return false;
    if (!query) return true;
    return [item.category, item.focus, item.question, item.fact, item.use, item.evidence, item.limit]
      .some((value) => normalize(value).includes(query));
  });
};

const answerHTML = (item) => `
  <p><strong>Short answer:</strong> ${escapeHTML(item.fact)}</p>
  <p><strong>Show it:</strong> ${escapeHTML(item.use)}</p>
  <p><strong>Proof and guardrail:</strong> ${escapeHTML(item.evidence)} ${escapeHTML(item.limit)}</p>`;

const categoryLabel = (categoryId) => VIVA_CATALOG.find((category) => category.id === categoryId)?.title || "All categories";

function renderCategoryControls() {
  const select = $("#viva-category");
  const chips = $("#viva-chips");
  if (!select || !chips) return;
  select.innerHTML = `<option value="all">All categories</option>${VIVA_CATALOG.map((category) => `<option value="${escapeHTML(category.id)}">${escapeHTML(category.title)}</option>`).join("")}`;
  select.value = state.category;
  chips.innerHTML = [`<button class="category-chip active" type="button" data-category="all" aria-pressed="true">All</button>`]
    .concat(VIVA_CATALOG.map((category) => `<button class="category-chip" type="button" data-category="${escapeHTML(category.id)}" aria-pressed="false">${escapeHTML(category.title)}</button>`))
    .join("");
  updateCategoryVisuals();
}

function updateCategoryVisuals() {
  const select = $("#viva-category");
  if (select) select.value = state.category;
  $$(".category-chip").forEach((chip) => {
    const active = chip.dataset.category === state.category;
    chip.classList.toggle("active", active);
    chip.setAttribute("aria-pressed", String(active));
  });
}

function renderVivaResults() {
  const results = $("#viva-results");
  const count = $("#viva-count");
  const status = $("#viva-status");
  const more = $("#viva-more");
  if (!results || !count || !status || !more) return;
  const filtered = filteredQuestions();
  const visible = filtered.slice(0, state.limit);
  count.textContent = `${filtered.length.toLocaleString("en-US")} ${filtered.length === 1 ? "question" : "questions"} match`;
  status.textContent = filtered.length
    ? `Showing ${visible.length.toLocaleString("en-US")} of ${filtered.length.toLocaleString("en-US")} matching questions in ${categoryLabel(state.category)}.`
    : "No questions match that search. Try another term or choose All categories.";
  results.innerHTML = visible.map((item) => `
    <article class="viva-card" role="listitem" data-viva-card="${escapeHTML(item.id)}">
      <div class="viva-card-meta"><span>${escapeHTML(item.category)}</span><span>${escapeHTML(item.id)}</span></div>
      <h4>${escapeHTML(item.question)}</h4>
      <details>
        <summary>Reveal answer</summary>
        <div class="answer-body">${answerHTML(item)}</div>
      </details>
      <button class="card-promote" type="button" data-viva-id="${escapeHTML(item.id)}">Practise this question</button>
    </article>`).join("");
  more.hidden = visible.length >= filtered.length || filtered.length === 0;
}

function selectQuestion(item, announce = true) {
  if (!item) return;
  state.currentId = item.id;
  const category = $("#viva-current-category");
  const id = $("#viva-current-id");
  const question = $("#viva-current-question");
  const answer = $("#viva-current-answer");
  const details = $("#viva-current-details");
  const reveal = $("#viva-reveal");
  if (category) category.textContent = item.category;
  if (id) id.textContent = item.id;
  if (question) question.textContent = item.question;
  if (answer) answer.innerHTML = answerHTML(item);
  if (details) details.open = false;
  if (reveal) reveal.textContent = "Reveal answer";
  if (announce) {
    const status = $("#viva-status");
    if (status) status.textContent = `Featured ${item.id}: ${item.category}. Answer aloud, then reveal the details.`;
  }
}

function randomIndex(maximum) {
  if (maximum <= 1) return 0;
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const values = new Uint32Array(1);
    crypto.getRandomValues(values);
    return values[0] % maximum;
  }
  return Math.floor(Math.random() * maximum);
}

function randomQuestion() {
  const filtered = filteredQuestions();
  if (!filtered.length) return;
  selectQuestion(filtered[randomIndex(filtered.length)]);
}

function exportQuestions() {
  const selected = filteredQuestions();
  const payload = {
    title: "Tideway viva bank",
    generated: "deterministic local handbook data",
    synthetic_scope: "Questions and answers cover the current Tideway prototype; they are not external claims.",
    count: selected.length,
    category: state.category === "all" ? "all" : categoryLabel(state.category),
    query: state.query,
    questions: selected.map((item) => ({
      id: item.id,
      category: item.category,
      focus: item.focus,
      question: item.question,
      answer: {short_answer: item.fact, show_it: item.use, proof_and_guardrail: `${item.evidence} ${item.limit}`}
    }))
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `tideway-viva-${state.category === "all" ? "bank" : state.category}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  const status = $("#viva-status");
  if (status) status.textContent = `Exported ${selected.length.toLocaleString("en-US")} local viva questions as JSON.`;
}

function prepareForPrint(mode) {
  state.printMode = mode;
  state.printLimit = state.limit;
  window.print();
}

function wireViva() {
  if (!$("#viva-results")) return;
  renderCategoryControls();
  selectQuestion(VIVA_BANK[0], false);
  renderVivaResults();

  $("#viva-search")?.addEventListener("input", (event) => {
    state.query = event.target.value;
    state.limit = 48;
    renderVivaResults();
  });
  $("#viva-category")?.addEventListener("change", (event) => {
    state.category = event.target.value;
    state.limit = 48;
    updateCategoryVisuals();
    renderVivaResults();
  });
  $("#viva-chips")?.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-category]");
    if (!chip) return;
    state.category = chip.dataset.category;
    state.limit = 48;
    updateCategoryVisuals();
    renderVivaResults();
  });
  $("#viva-random")?.addEventListener("click", randomQuestion);
  $("#viva-export")?.addEventListener("click", exportQuestions);
  $("#viva-print")?.addEventListener("click", () => prepareForPrint("bank"));
  $("#viva-more")?.addEventListener("click", () => {
    state.limit += 48;
    renderVivaResults();
  });
  $("#viva-results")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-viva-id]");
    if (!button) return;
    const item = VIVA_BANK.find((question) => question.id === button.dataset.vivaId);
    selectQuestion(item);
    $("#viva-current-question")?.scrollIntoView({behavior: "smooth", block: "center"});
  });
  $("#viva-reveal")?.addEventListener("click", () => {
    const details = $("#viva-current-details");
    if (!details) return;
    details.open = !details.open;
    $("#viva-reveal").textContent = details.open ? "Hide answer" : "Reveal answer";
  });
  $("#viva-current-details")?.addEventListener("toggle", (event) => {
    const button = $("#viva-reveal");
    if (button) button.textContent = event.target.open ? "Hide answer" : "Reveal answer";
  });
}

function wireNavigation() {
  $("#print-guide")?.addEventListener("click", () => prepareForPrint("page"));
}

let beforePrintLimit = null;
window.addEventListener("beforeprint", () => {
  beforePrintLimit = state.limit;
  $$("details").forEach((details) => { details.open = true; });
  if (state.printMode === "bank") {
    state.limit = filteredQuestions().length;
    renderVivaResults();
    $$("#viva-results details").forEach((details) => { details.open = true; });
  }
});
window.addEventListener("afterprint", () => {
  if (state.printMode === "bank" && beforePrintLimit !== null) {
    state.limit = beforePrintLimit;
    renderVivaResults();
  }
  beforePrintLimit = null;
  state.printMode = "page";
});

// Static sections rise in as they scroll into view; the question bank animates on render instead.
function revealOnScroll() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) return;
  const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
    if (!entry.isIntersecting) return;
    entry.target.classList.add("in");
    observer.unobserve(entry.target);
  }), {rootMargin: "0px 0px -8% 0px"});
  const groups = [".chapter-heading", ".editorial-card", ".quote-band", ".problem-row", ".lifecycle-step", ".example-panel",
    ".feature-card", ".setup-card", ".demo-card", ".scope-callout", ".viva-featured-grid > *"];
  $$(groups.join(",")).forEach((element) => {
    const siblings = [...element.parentElement.children].filter((item) => item.matches(groups.join(",")));
    element.style.setProperty("--i", String(Math.min(6, Math.max(0, siblings.indexOf(element)))));
    element.classList.add("reveal-up");
    observer.observe(element);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  wireNavigation();
  wireViva();
  revealOnScroll();
});
