# Current technical readiness — evidence v6 / Docker v5

This is the current review index. Tideway remains a synthetic SME finance copilot:
cash forecasts, recovery proposals, human approval, simulated negotiation and
verifiable sandbox execution. No bank, real lender or payment rail is connected.
Historical upgrade and Windows reports describe earlier source versions.

## Implemented review fixes

- Above-target reserve risk requires fresh explicit acknowledgement from every
  approver, bound to the stored plan hash, bundle and exact probability/target.
  Consent is checked by the server and retained in audit, mandate and receipt.
  Missing, stale or altered acknowledgements cannot authorize execution.
- Mock financing compares arrival date, fee, APR convention, total repayment,
  unverified eligibility and the cash/payroll path through repayment. Borrowing
  cannot appear feasible merely because repayment falls beyond the first horizon.
- Exact shipped TidePay weights now have a separate frozen-artifact evaluation,
  exposed in the app with integrity and artifact-hash checks. Audited-model scores
  remain separate. The low-history limitation is visible.
- A new independent challenge set was sealed before first observation. Actual
  native macOS Qwen3 inference, full raw generations, misses and source seals are
  preserved. Disclosed credit/entity failures have separate deterministic
  regressions; their fixes do not replace the original blind result.
- Unflagged text is labelled "no flags", not trusted. Every extracted draft
  requires review; message text cannot grant payment authority.
- Cross-platform temporary-path handling is corrected. Release checks enforce LF
  source bytes, detect edits during verification, and bind tests, browser checks
  and the distributed ZIP to the same exact source digest.
- An anonymous, consent-aware study kit supports real SME validation. Its current
  participation count is zero; no feedback or usability score was invented.
- Independent follow-up audit: invalid signing keys are preserved and rejected;
  concurrent first starts publish one complete key. Malformed signatures fail
  validation, and `.env` now loads the documented structured-plan flag.
- Profiles, empirical fallback and illustrative backtests use only paid history
  available at the simulation date. Mock advances exclude already committed and
  not-yet-issued receivables. A Windows SQLite test handle leak is corrected.
- The persisted Docker smoke client now consumes the API's `{found, receipt}`
  envelope, and the container verifier uses Docker's current `--timeout` stop
  flag. Above-target plans now show an explicit owner-decision escalation in the
  rescue UI.

## Measured evidence

| Check | Recorded result | Meaning and limit |
|---|---|---|
| Current unit run | 319 run; 0 failures; 0 errors; 5 skipped | Python 3.13.7, Windows; injected outputs are not model quality |
| Additional standard-library run | 252 run; 0 failures; 0 errors; 4 skipped | Python 3.11.16; optional photo tests require Pillow; report records its own source hash |
| Financial scenarios | 24/24 expected workflows; 9 rescues | 7/9 executed rescues meet the 10% simulated risk target |
| Planner rescue follow-up | D06 0.00% mean risk; H11 11.78% mean risk over 30,000 fresh draws | D06 keeps the accepted 7-day counter-offer and adds recovery; H11 shortlists risk-diverse candidates but remains above target and requires owner decision/acknowledgement |
| Docker v5 verification | Build and HTTP workflow passed; persisted receipt/replay/audit passed; 319 tests, 0 failures, 0 errors | Linux amd64 WSL2, Python 3.11.17, non-root uid 10001; synthetic sandbox only |
| Hosted GitHub Actions run 6 | 9/9 jobs passed | Ubuntu, Windows and macOS stdlib lanes; Pillow; browser/package; and Docker; receipt at `evidence/infrastructure-v5/hosted-ci-status.json` |
| Shipped TidePay | 7,427 unseen synthetic invoices; MAE 8.5585 days | Heuristic 10.2296; training-only prior 11.7453; no weight changes |
| First actual Qwen3 challenge | 28/32 correct; 32/32 contained | Four retained misses; no mandate, execution or financial-ledger mutation |
| Post-fix Qwen3 regression | 32/32 known cases handled; 8/8 safe stops | One real-model pass after disclosed guard fixes; not a new blind score |
| Independent-audit Windows Qwen3 rerun | 32/32 known requests handled; 32/32 contained | Actual compatible inference on disclosed cases; retains every output; not blind |
| Historical unseen instruction screening | 2/24 attacks detected; 2/24 benign flagged | Retained v3/v5 observation; detection cannot be the authorization boundary |
| Current v6 instruction screening first pass | 96 independently authored synthetic cases; combined warning 55 TP, 11 TN, 29 FP, 1 FN | Recall 98.2% but false-positive rate 72.5%; local-compatible Qwen3 is unbenchmarked and this is not external or population accuracy |
| SME user study | 0 participants; pending | Kit and analysis available; no real-user claim |

The prediction cohort contains 80 new synthetic SMEs, four seeds and 7,427
invoices after the shipped model's historical training period. No fresh labels
were used to fit weights or preprocessing. Runtime feature ordering is matched
and its difference from the training pipeline is disclosed. With no prior paid
history, shipped-model log loss is worse than the training-only prior. These are
synthetic-generator results, not real-world accuracy or a privacy guarantee.

The model first observation predates the disclosed guard fixes. It scored 23/24
tool/argument cases and 5/8 required safe stops, with median 1.225s.
The four misses were incomplete conditional recovery, amount inferred from a
day term, an unknown customer substituted with a ledger customer, and an
abbreviation silently expanded. The frozen sources and raw outputs remain
available for review. Later regression passes must never be called unseen scores.

## Run and check

From the project root on macOS (`python` on Windows):

```
python3 run.py
```

Open http://127.0.0.1:8787 and http://127.0.0.1:8787/guide.html.
Opening guide.html directly from Finder does not start the application server.

```
python3 scripts/prepare_release.py --checks-only
python3 scripts/prepare_release.py
```

The complete command requires Node 22+ and Chrome/Edge, refreshes tests and
browser evidence, rebuilds five PDFs, builds the ZIP and tests its fresh extraction.
It does not download model weights or run a cloud provider. Inspect PDF appearance
before sharing. `--reuse-pdfs` keeps already reviewed PDFs while repeating checks.
Use a completed LF checkout: source edits during the run invalidate verification.

## Evidence map and provenance

- [Current test summary](../evidence/test-summary.json) and
  [raw test log](../evidence/test-run.log).
- [Current scenario report](../evidence/readiness-v3/scenarios/report.json),
  [linked delay receipt](../evidence/readiness-v3/payment-delay.json) and
  [browser workflow](../evidence/screens/browser-verification.json).
- [Exact shipped prediction evaluation](DEPLOYED_MODEL_EVALUATION.md), with
  raw invoices, shared test IDs, predictions, intervals and calibration bins.
- [Independent screening/model evaluation](BLIND_EVALUATION.md), source seals,
  native runtime provenance and every first-observation output.
- [Current v6 screening first pass](../evidence/screening-v6/first-pass/first-pass-results.json)
  with the sealed fixture, model attempts and raw outputs.
- [Planner risk remediation](../evidence/readiness-v5/planner/report.json), including
  D06 counter-offer repair and H11 fresh-seed validation.
- [Docker v5 report](../evidence/infrastructure-v5/docker/report.json), including
  build tests, non-root HTTP flow and persisted receipt replay.
- [Hosted CI receipt](../evidence/infrastructure-v5/hosted-ci-status.json), linking
  the current remote commit and all nine successful jobs.
- [Separate post-fix model regression](../evidence/readiness-v3/blind/model-post-fix-regression.json)
  and [Python 3.11 standard-library run](../evidence/readiness-v3/python311/test-summary.json).
- [Release stages and PDF hashes](../evidence/readiness-v3/release-checks.json).
  `dist/extraction-verification.json` and `dist/SHA256SUMS.txt` prove the actual
  distributed bytes, rather than referring to an earlier ZIP.
- [Independent judge/auditor report](INDEPENDENT_AUDIT.md), with reproduced
  defects, the contest requirement map, fixes and remaining validation gaps.
- [Current Windows actual-model regression](../evidence/independent-audit/model-regression/report.json).
- [User study protocol](USER_STUDY_KIT.md) and
  [pending participation status](../evidence/readiness-v3/user-study-status.json).

Current test source digest: `4d640007a6be2ecd247d14f31609aa229940216a5e54c4b382ca2d32d7659905`.
Reports contain their own timestamps and hashes; older Windows/upgrade evidence
is historical and does not attest to the current checkout.

## Remaining gaps that code alone cannot close

Unfamiliar instruction screening now has a fresh v6 first pass, but the high false
positive rate and unbenchmarked compatible-model status require further detector
work and another separately sealed evaluation; repeating known examples is
regression only. Real consented SME feedback, native MLX/TideLM and receipt-model
evaluation, external security testing and real-data calibration remain outstanding.
Partial settlements, reversals and real lender eligibility require separate
financial design before live integration. GitHub-hosted Offline validation run 6
passed all nine jobs for the pushed implementation; its receipt is recorded
separately from local evidence. Docker v5 has passed locally on Linux/WSL2, but
neither check is production deployment.

The supplied five-person BUET roster is retained. Leader, contribution roles,
eligibility, registration, submission route, reviewer access and the deferred
video still need the team's actual information. This local package has not been
published, deployed, emailed or submitted. A numerical 9+ rating cannot honestly
be guaranteed from synthetic checks while these validation gaps remain.
