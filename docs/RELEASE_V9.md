# Local release fixes - 18 October 2026

This release addresses the current Windows test failure and stale local review
package. All execution is synthetic. No push, publication, registration, video
recording or submission is part of this work.

- The risk-display regression reads the UTF-8 browser source explicitly. The
  failure was reproduced with Windows CP1252 before the fix; verification keeps
  UTF-8 mode disabled so the locale issue remains covered.
- Source stamps now include the shipped web fonts and raster images. Changing
  their bytes invalidates test/browser/package provenance. Binary carriage-return
  bytes are excluded from text line-ending validation. Two regression tests
  cover the integrity boundary.
- Six [behavior-driven workflow checks](BEHAVIORAL_EVALUATION.md) have a repeatable
  runner and actual backend results. Real SME participation remains zero.
- Release preparation uses a new `evidence/release-v9/` directory and refreshes
  the current readiness links. Historical v6/v7 screening observations, v8
  failures, raw model generations and earlier infrastructure receipts remain.
- The linked demo and optional model trace retain their existing approval,
  counterparty consent, stale-mandate refusal and read-back checks. Model-backed
  tool selections are distinguished from deterministic financial calculations.

See the [current readiness index](READINESS_CURRENT.md),
[unit report](../evidence/test-summary.json),
[release stages](../evidence/release-v9/release-checks.json),
[browser report](../evidence/screens/browser-verification.json), and
[behavior paths](../evidence/release-v9/behavior-checks.json) for actual outcomes.
The local ZIP, manifest, checksum and extraction proof are under `dist/`.
Only a completed release with matching hashes attests to the distributed bytes.

## Verified local results

- Windows CP1252: 355 tests, zero failures/errors, one symlink skip.
- Actual compatible Qwen: 32/32 disclosed requests handled and 32/32 contained;
  [raw outputs and report](../evidence/release-v9/model-regression/report.json).
  This is a known-case regression, with unchanged historical first observations.
- [Actual-model desktop/mobile browser check](../evidence/release-v9/browser-real/browser-verification.json):
  risk answer, payment refusal and unchanged financial state passed; no page errors.
- [Docker](../evidence/release-v9/docker/report.json): frozen-source build,
  355 tests with zero failures/errors and five platform/dependency skips,
  non-root HTTP, persisted receipt, audit and idempotent replay passed.
- [Planner reproduction](../evidence/release-v9/planner/report.json): D06 mean
  follow-up risk 0%; H11 11.78% over three fresh seeds and 30,000 draws.

The release log and extraction receipt contain the final archive checks. Test,
browser, model and Docker reports identify the same frozen runtime source.

## Remaining validation

The v7 native base-classifier first observation retains 23/24 detected attacks
and a 5/16 ordinary-benign warning false-positive rate. It is a finite,
AI-authored set. No tuning or new blind-quality claim is made by this release.
Known-case compatible-model inference, if available, is separate from the
released native MLX planning adapter and receipt-model device verification.
H11 retains above-target simulated risk and requires exact acknowledgement;
no target, seed or financial constraint is relaxed to manufacture a success.

Real consented SME feedback, external security review, real-data calibration,
native planning/receipt inference and team-controlled eligibility, registration,
leader, roles and reviewer access still need actual evidence. Hosted CI for
uncommitted local changes remains pending. Stored remote receipts identify the
commit they actually tested.
