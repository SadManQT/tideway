# Understand the next decision

After signing in, **Cash weather** opens in **Simple view**. Use **Detailed view**
to return to the existing weather chart, prediction evidence and full analysis.
The new view's labels can switch between English and Bangla; other app screens
and the exported brief remain English. Demo dates are simulation dates.

## A short demonstration

1. Sign in as Nadia. The headline names the problem, followed by lowest likely
   cash, reserve shortfall and next recorded payroll.
2. Enter a one-off expense and its date. **Check this expense** shows its effect
   without saving a transaction. Compare spending room with expected receipts
   against a scenario where no unpaid customer receipt arrives.
3. Inspect **Which receipts matter most?** Each customer is removed separately;
   impacts cannot be added together. At most ten customers are tested in name
   order, with coverage disclosed; the top three tested impacts are shown.
4. Expand **Where do these numbers come from?** Select a source record to open
   the exact invoice, bill or transaction in Records. Day closing equals opening
   plus money in minus money out. Large source lists disclose truncation.
5. Use **Choose what matters to you** to compare lower cost, fewer counterparties
   and lower simulated risk. This uses the saved ledger and explicitly excludes
   the extra-expense preview above; an unrecorded hypothetical cannot enter a
   real proposal silently. Cards name each request as a deferral or early-payment
   discount. You can tighten the discount ceiling or exclude a
   relationship. Existing stricter owner instructions cannot be loosened here.
   Inputs lock while a calculation runs so changed terms cannot silently receive
   an older preview.
   Equal choices are legitimate; the planner searches a bounded candidate set.
6. Save an available priority as a **new unapproved proposal**. Continue in Rescue
   plan through normal PIN review, required approvals and counterparty consent.
   A viewer can compare but cannot save. No button in Simple view executes money.
7. Download the private decision brief. Open the HTML locally; use the browser's
   Print command to print or save as PDF. It contains the **last checked expense**
   and source snapshot, with no JavaScript, remote assets or automatic contact.

## What the spending figure means

All calculations use native integer minor units in the existing projection
engine. The ceiling preserves scheduled **daily closing** cash above the reserve
from the simulation date through target plus look-ahead. A prior shortfall in
that future window yields zero room even if a later expense would miss it.
Historical shortfalls before the simulation date do not block the future bound.
An exact floor is allowed; one additional minor unit creates a shortfall in the
independent witness tests. An ended horizon has no available future spending
estimate. Missing payroll records are explicitly identified.

This is scheduled ledger analysis, not a bank balance, intraday liquidity test,
permission to spend or payment guarantee. Unpaid receipts and unsettled
early-payment agreements remain assumptions. Excluding customer receipts removes
their open invoices and associated unsettled early-payment agreements. Paid
history and actual recorded cash remain. Fees and funding costs are not invented
or automatically added. Display-currency conversion uses the existing labelled
illustrative rates. Inputs, approval review and presentation reports use the
selected currency; the exact ledger and signing units stay in the business
currency. Untouched rounded values are preserved. See [currency behaviour and
verification](RELEASE_V13.md).

## Integrity and privacy

Preview/report/export routes require a signed-in member, CSRF token and an exact
business ID. Unknown fields and malformed amounts are rejected. A supplied source
hash must still match. Saving also rechecks the current parent proposal inside
the database transaction, preserves owner exclusions/ceilings and retained
supplier liquidity assumptions, and uses a durable request ID for exact retries.
The cached result reflects the actual saved proposal's current approval state.

The data checklist reports flagged records, unpaid invoices, thin settled
history and missing payroll. It does not invent a confidence score. Critical
existing warnings remain visible. Private summaries escape untrusted text and
contain business figures; share them only with trusted reviewers. The team's
personal preparation guide remains outside the served app and submission package.

These are engineering features. Actual usability benefit, real SME outcomes,
native Mac model checks and external security review still require separate work.
