# Screening, liquidity-gap and HTTP follow-up - 18 October 2026

Topic E: SME Finance Copilot. This remains a synthetic sandbox. Native Mac
planning-adapter and receipt-model verification are deferred at the team's
request. No push, deployment, video, registration or submission was performed.

## Changes

- Screening distinguishes an immediately rejected question from an active
  bypass request, recognises additional Bengali prohibitions and Hindi external
  personal-data exports, and handles reported caller/sender quotations. Active
  harmful follow-up instructions are still scanned. The semantic prompt
  distinguishes incident documentation from carrying out the quoted misconduct.
  Flags are advisory; every draft still requires review and signed approvals
  remain outside model authority.
- Recovery bundles now expose a read-only liquidity-gap diagnostic when risk
  remains above target. It computes the smallest constant opening-cash addition
  meeting the target on the sampled paths, with a one-minor-unit boundary
  witness. It cannot create money, alter the ledger or authorize financing.
  Availability, timing, fees and repayment must be confirmed separately.
- Malformed cookies no longer crash a request. Unknown session values share the
  anonymous rate limit; sign-in throttling stays bound to the client address.
  Duplicate JSON fields, duplicate Host headers and ambiguous body framing are
  rejected. Exact body reads have a total two-second deadline that trickled
  bytes cannot restart. Invalid Unicode scalars and overflowed JSON numbers
  are rejected before validation, storage or response encoding. This is limited HTTP hardening, not comprehensive
  denial-of-service protection or an external penetration test.
- Release tools select current v10 evidence and preserve earlier observations.

## Screening evidence

The paired Windows compatible Qwen runs used the same model and the same
48 previously disclosed v7 cases. Baseline: 23/24 attacks detected and 3/16
ordinary benign messages warned. Revised: 24/24 attacks, 0/16 unnecessary
warnings and 8/8 legitimate payment-change reviews. These are development
regressions, not fresh population accuracy. The old native MLX 31.25% result is
retained; a Windows improvement cannot verify the native backend.

The new 24-case source-aware challenge was authored by the implementation-aware
maintainer and sealed before first inference. Its first observation detected
12/12 attacks, reviewed 4/4 legitimate payment changes and warned on 1/8 ordinary
benign messages. That false positive and all raw generations remain preserved.
The reported-caller quote defect then received a fix and a separate final-known
regression over all 72 disclosed cases. No independent blind claim is made.

The challenge's original CRLF fixture bytes are retained beside its report.
The repository copy was subsequently converted to LF without changing decoded
JSON data. A preliminary final-known attempt overlapped that byte conversion;
its raw results and failed integrity status are retained separately and are not
the final frozen-source verification.

A final malformed-Unicode reproduction found one further request-encoding
failure. It was fixed with two additional HTTP regression tests. Frozen-source
checks were repeated; the earlier receipts are retained in `pre-unicode/`.

See [paired baseline](../evidence/upgrade-v10/screening-baseline/report.json),
[revised development](../evidence/upgrade-v10/screening-revised/report.json),
[challenge first observation](../evidence/upgrade-v10/screening-challenge/report.json),
and [final-known regression](../evidence/upgrade-v10/screening-final-known/report.json).

## H11: conditional recovery, with the original risk retained

H11 still has 11.7767% simulated reserve-breach risk under maximal permitted
deferral: 3,533/30,000 fresh draws. Selecting a different permitted timing bundle
cannot eliminate that structural gap. The 10% target, owner constraints and
original fixture are unchanged.

The diagnostic selected MYR 3,000 extra opening cash on 20,000 selection draws.
Three separate validation seeds gave 128/30,000 breaches, or 0.4267%, conditional
on that cash being available at opening without fees or repayment. The approximate
95% sampling interval is 0.3590%-0.5070%; it excludes model/calibration error.
The original ledger was unchanged, funding is unconfirmed, and nothing executed.
This quantifies an owner escalation; it does not turn the unfunded case into a
passed rescue. See the [cash-gap receipt](../evidence/upgrade-v10/liquidity-gap.json).

## Verification and remaining work

The [current readiness index](READINESS_CURRENT.md),
[unit receipt](../evidence/test-summary.json),
[release receipt](../evidence/upgrade-v10/release-checks.json),
[model receipt](../evidence/upgrade-v10/model-regression/report.json),
and `dist/extraction-verification.json` identify their actual source versions.
Only completed reports with matching source and archive hashes attest to the
final package. Earlier reports are historical evidence, not current attestations.

The committed v9 source, `6dbb315`, passed all nine hosted jobs in
[run 14](https://github.com/SadManQT/tideway/actions/runs/39102943815).
This does not attest to the unpushed v10 changes.

Real SME participation remains zero. Native MLX planning/receipt inference,
external security review, real-data calibration, confirmed extra H11 funding,
current hosted CI and team-controlled leader/roles/registration information
remain outstanding. Video stays deferred under the team's earlier instruction.
