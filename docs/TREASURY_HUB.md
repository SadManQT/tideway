# Treasury hub

The **Treasury** view (sidebar, between *Decision lab* and *Records*) turns one SME's
Tideway records into the artefacts that banks, lenders and the finance teams of large
buyers already use: a 13-week cash flow, a working-capital health score, a
payment-integrity scan and a signed, expiring credit passport.

Everything is **read-only analysis of synthetic sandbox data**. No page or endpoint in
the hub can approve, block, pay, defer or edit a financial record. The only write is one
audit-log entry when a passport is issued.

Code: [`tideway/treasury.py`](../tideway/treasury.py), [`web/treasury.js`](../web/treasury.js),
routes in [`tideway/server.py`](../tideway/server.py). Tests:
[`tests/test_treasury.py`](../tests/test_treasury.py),
[`tests/test_treasury_http.py`](../tests/test_treasury_http.py). Evaluation:
[`scripts/evaluate_treasury.py`](../scripts/evaluate_treasury.py) →
[`evidence/treasury/treasury-report.json`](../evidence/treasury/treasury-report.json).

## 1. 13-week cash flow (TWCF)

Weekly buckets of Tideway's existing daily projection (`projection.project`, the same
function the dashboard uses) over exactly 91 days from the ledger opening date (the
sandbox current date), with no look-ahead.

| Line | Source |
|---|---|
| Opening cash | Projection opening balance for the first day of the week |
| Receipts by customer | Open invoices (and accepted early-payment agreements), grouped by customer |
| Other receipts | Income transactions |
| Supplier bills | Open, scheduled or rescheduled bills (and accepted deferrals) that are not payroll |
| Payroll | Bills with payroll priority and expense transactions marked payroll |
| Other disbursements | Other expense transactions |
| Net flow, closing cash | Receipts − disbursements; closing of the last day of the week |
| Lowest cash in week | Minimum daily closing balance inside the week |
| Below reserve | The week's lowest balance is under `policy.reserve_floor_minor` (highlighted) |

Three scenarios use the dashboard's own invoice dates: **scheduled** (each invoice on its
expected collection date), **likely** (TidePay expected delay, `derived["likely_dates"]`)
and **stress** (TidePay 80th-percentile delay, `derived["stress_dates"]`). Accepted
sandbox adjustments and customer promises are applied as on the dashboard.

**Reconciliation.** For each scenario the server checks, and the UI shows, that the
week-13 closing equals the engine's closing balance and `opening + receipts −
disbursements`, and that the minimum of the opening balance and the weekly lows equals
the engine's daily minimum. A mismatch raises an error instead of returning numbers.
`tests/test_treasury.py` re-runs the engine independently and also checks that every
shared day matches the dashboard's base/likely/stress projections. Events after week 13
are reported as "beyond horizon" totals.

Export: `GET /api/export?kind=twcf&business_id=…[&scenario=all|scheduled|likely|stress]`
returns a UTF-8 CSV with a byte-order mark, integer minor units, one row per scenario-week
and one `receipts_from:<customer>` column per customer. Customer names pass through the
existing `csv_cell` formula guard.

## 2. Working-capital health score

A 0–100 weighted mean of component scores. Weights and scoring anchors are **Tideway
design parameters, not industry benchmarks**. If a component has no data (for example no
settled invoices), it is dropped and the remaining weights are renormalised; the UI shows
the weight actually used.

| Component | Weight | Formula (score clamped to 0–100) |
|---|---:|---|
| Collection speed | 15 | `100 − 100 × max(0, DSO − average terms) / 30`. DSO = mean issue-to-payment days of settled invoices (existing `financial_kpis`) |
| Overdue share | 15 | `100 × (1 − overdue open receivables / open receivables)`; overdue = status overdue or due before the current date |
| Customer concentration | 15 | `100 × (10,000 − HHI) / 8,000`, capped at 100. HHI = 10,000 × Σ(customer share of open receivables)²; full marks at HHI ≤ 2,000 (five equal customers) |
| Cash runway | 15 | runway = opening cash ÷ daily burn, where daily burn = max(historical monthly expenses ÷ 30, scheduled 13-week disbursements ÷ 91); score = `100 × runway / 90` |
| Reserve coverage | 20 | `100 × lowest likely 13-week cash / (2 × reserve floor)` |
| Breach risk | 20 | `100 × (1 − P(breach))`, from the existing seeded Monte Carlo (`analytics.monte_carlo`, 1,000 runs, seed derived from business, snapshot hash and horizon) over the 13-week horizon |

Bands: Strong ≥ 75, Watch ≥ 50, Weak below 50.

DPO (balance method: open payables ÷ average daily paid-bill spend over the paid-bill
history window) is **shown but not scored**: a longer DPO helps cash but can strain
suppliers, and no benchmark is assumed.

**What would move the score most.** For each component the maximum gain is
`weight × (100 − score) / weights used`. The three largest are shown with a sentence built
from the business's own data (for example the lowest likely cash and its date, the
largest overdue invoice, the top customer's share, or the simulated liquidity gap, which
is labelled a diagnostic and not a funding offer).

## 3. Payment-integrity scan

Deterministic rules over supplier bills (cancelled bills excluded). Payee names are
compared case-insensitively with punctuation and common legal suffixes removed. Every
finding carries evidence, an explanation, a stable `finding_id` (hash of rule and bill ids)
and `blocks_nothing: true`.

| Rule | Fires when |
|---|---|
| `duplicate_bill` | Same payee and amount with due dates ≤ 7 days apart, or same payee and the same invoice-like reference in the description (e.g. `INV-2291` and `INV 2291`; four-digit years are ignored). High severity if either bill is still open |
| `split_below_threshold` | ≥ 2 bills to one payee within 7 days, each below the dual-approval threshold, together at or above it. The threshold is `policy.dual_approval_threshold_minor`, Tideway's two-person approval threshold for recovery bundles, used here as the AP control threshold |
| `amount_outlier` | Modified z-score `0.6745 × (amount − median) / MAD` above 3.5 against the payee's other bills (at least 3) **and** at least 25% from that median. If MAD is 0, the mean absolute deviation (× 1.253314) is used |
| `bank_details_changed` | Existing `analytics.payee_checks`: bank details differ from paid history or the callback-verified account. Accounts are masked |
| `lookalike_payee` | Existing `analytics.payee_checks`: a new payee name ≥ 85% similar to an established supplier |
| `round_amount` | Open bill that is a multiple of 1,000 currency units with at least 2 more trailing zeros than any of the payee's other bills (at least 2), or a first-time payee's round bill at or above the threshold |

The scan is advisory. Tideway's existing payee blocks, approval rules and execution guard
remain authoritative and are unchanged.

**Synthetic test sample.** The demo ledgers contain few anomalies, so the UI offers "Also
run on a synthetic test sample". The server then scans the real snapshot **plus** 26
in-memory bills (ids `syn-001`…`syn-026`, descriptions starting "SYNTHETIC TEST") with 6
planted anomalies (one per rule) and 17 clean controls, including a monthly retainer that
must not be called a duplicate. The sample is never written to the database. Precision and
recall are computed against those labels. The sample was written alongside the rules, so
this checks that each rule fires as specified; **it is not evidence of real-world
precision or recall.**

## 4. Verifiable credit passport

A JSON document a business can hand a lender, with exactly these top-level fields:
`type`, `version` (`tideway-credit-passport-v1`), `passport_id`, `issuer` (instance name,
key id, issuing role and operator), `business` (id, name, currency, synthetic flag),
`as_of`, `issued_at`, `expires_at` (30 days), `snapshot_hash`, `audit` (audit-chain head
hash and entry count *before* the issuance entry, chain validity), `twcf` (scheduled,
likely and stress summaries), `health` (score, band, weights, components with formulas),
`breach_risk` (probability, runs, seed, horizon), `limitations`, `signature_alg` and
`signature`.

* **Signing.** HMAC-SHA256 with `security.sign`, the same canonical-JSON helper used for
  mandates, under a purpose-bound sub-key `HMAC(store key, "tideway-credit-passport-v1")`.
  A passport therefore never verifies as a mandate (tested). Non-integer values are
  encoded as decimal strings so the signature survives JSON round-trips in any language.
* **Issue** (`POST /api/treasury/passport/issue`, fields `business_id`, `pin`): owner or
  accountant only, with PIN step-up (wrong PINs count toward the existing lockout). Writes
  one `treasury.passport.issue` audit entry with the passport id, expiry, snapshot hash,
  score and the document's SHA-256.
* **Verify** (`POST /api/treasury/passport/verify`, fields `business_id`, `passport`): any
  member. Returns `valid: true`, or `valid: false` with reason `malformed`,
  `signature_mismatch` (altered or not issued by this instance; HMAC cannot say which
  field changed), `wrong_business`, `expired` or `not_yet_valid`. Passport contents are not
  echoed for wrong-business results. Valid results also report whether the issuance is in
  the audit log and whether records changed since issue.
* **UI.** Issue → summary card, **Download JSON**, **Verify**, and a **Tamper drill** that
  adds 50,000 to `twcf.likely.closing_cash_minor` in a browser copy and shows the server
  rejecting it while the original still verifies. Any member can verify an uploaded file.

**Public-key verification.** Every passport also carries an Ed25519 signature (pure-Python
RFC 8032, checked against the RFC test vector) over all fields except the two signatures.
A lender verifies it offline with the issuer's public key alone:
`python scripts/verify_passport.py passport.json --public-key <hex>`. Edits and attacker
re-signing with another key are rejected. The signing key is derived from the instance key
(no hardware security module or revocation list). A passport is not a credit rating, offer
or guarantee.

## Endpoints and permissions

All routes are `POST`, JSON, and go through the existing handler: loopback host check,
origin check, CSRF token, per-session rate limit, strict body parsing, `self.fields`
allow-lists (unexpected fields are rejected) and `self.scoped` membership checks.

| Route | Body fields | Owner | Accountant | Viewer |
|---|---|:-:|:-:|:-:|
| `/api/treasury/twcf` | `business_id` | ✓ | ✓ | ✓ |
| `/api/treasury/health` | `business_id` | ✓ | ✓ | ✓ |
| `/api/treasury/scan` | `business_id`, optional boolean `synthetic_sample` | ✓ | ✓ | ✓ |
| `/api/treasury/passport/issue` | `business_id`, `pin` | ✓ | ✓ | ✗ (403) |
| `/api/treasury/passport/verify` | `business_id`, `passport` | ✓ | ✓ | ✓ |
| `GET /api/export?kind=twcf` | `business_id`, optional `scenario` | ✓ | ✓ | ✓ |

Non-members receive 403 for every route; requests without a session receive 401. All
server strings are escaped in the UI with the existing `esc` helper. TWCF, health and
scan responses contain no timestamps and are deterministic: the same records produce
byte-identical JSON (tested).

## Measured results (synthetic demo data)

From `python scripts/evaluate_treasury.py` (Python 3.11.9, in-memory database, demo
fixtures; see the JSON for every value). Amounts are in each business's ledger currency.

| Business | Likely week-13 closing | Lowest likely cash | Weeks below reserve (likely) | Health score | Ledger findings | Synthetic recall / precision |
|---|---:|---:|---|---:|---:|---|
| Shapla Services | BDT 23,000 | −BDT 42,000 (3 Nov) | 5, 6 | 41 (Weak) | 0 | 6/6 · 1.0 |
| Lotus Print Studio | CNY 34,000 | CNY 8,000 (31 Oct) | 5 | 58 (Watch) | 0 | 6/6 · 1.0 |
| Harbourline Traders | −SGD 27,000 | −SGD 42,000 (31 Oct) | 4–13 | 26 (Weak) | 2 (changed bank details, look-alike payee) | 6/6 · 1.0 |

For all three businesses and all three scenarios the 13-week cash flow reconciled exactly
with the projection engine, repeated runs were identical, and the passport checks behaved
as specified: original valid; edited closing cash → `signature_mismatch`; other business →
`wrong_business`; 31 days later → `expired`; not accepted as a mandate. Median timings on
the development machine: TWCF 1.6–2.0 ms, health score with the 1,000-run Monte Carlo
34–48 ms, scan with the synthetic sample 2.7–2.9 ms, passport verify under 1 ms.

## Limits

* Synthetic businesses only; a scheduled ledger, not a bank balance. No bank, lender or
  accounting system is connected.
* The health score is a transparent heuristic for conversation with a lender, not a
  credit model; its weights and anchors have not been validated against outcomes.
* The scan's synthetic precision/recall is a specification check on a designed sample.
  Real AP data would contain patterns these rules miss and legitimate bills they flag.
* Bills carry a due date but no issue or payment date, so DPO uses the balance method.
* The passport signing key is demo-grade (derived from the instance key), and passports are
  not revocable before expiry.
