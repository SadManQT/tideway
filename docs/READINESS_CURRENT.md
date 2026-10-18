# Current technical readiness

Current local release: [screening, cash-gap and HTTP fixes](RELEASE_V10.md).

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

## Measured evidence

| Check | Recorded result | Meaning and limit |
|---|---|---|
| Current unit run | 375 run; 0 failures; 0 errors; 1 skipped | Python 3.13.7, Windows; injected outputs are not model quality |
| Additional standard-library run | 252 run; 0 failures; 0 errors; 4 skipped | Python 3.11.16; optional photo tests require Pillow; report records its own source hash |
| Financial scenarios | 24/24 expected workflows; 9 rescues | 8/9 executed rescues meet the 10% simulated risk target |
| Shipped TidePay | 7,427 unseen synthetic invoices; MAE 8.5585 days | Heuristic 10.2296; training-only prior 11.7453; no weight changes |
| First actual Qwen3 challenge | 28/32 correct; 32/32 contained | Four retained misses; no mandate, execution or financial-ledger mutation |
| Post-fix Qwen3 regression | 32/32 known cases handled; 8/8 safe stops | One real-model pass after disclosed guard fixes; not a new blind score |
| Independent-audit Windows Qwen3 rerun | 32/32 known requests handled; 32/32 contained | Actual compatible inference on disclosed cases; retains every output; not blind |
| Historical first unseen instruction screening | 2/24 attacks detected; 2/24 benign flagged | Historical v3 observation; current v7 evidence is listed below; detection is advisory |
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
- [Current scenario report](../evidence/upgrade-v10/scenarios/report.json),
  [linked delay receipt](../evidence/upgrade-v10/payment-delay.json) and
  [browser workflow](../evidence/screens/browser-verification.json).
- [Exact shipped prediction evaluation](DEPLOYED_MODEL_EVALUATION.md), with
  raw invoices, shared test IDs, predictions, intervals and calibration bins.
- [Independent screening/model evaluation](BLIND_EVALUATION.md), source seals,
  native runtime provenance and every first-observation output.
- [Separate post-fix model regression](../evidence/readiness-v3/blind/model-post-fix-regression.json)
  and [Python 3.11 standard-library run](../evidence/readiness-v3/python311/test-summary.json).
- [Release stages and PDF hashes](../evidence/upgrade-v10/release-checks.json).
  `dist/extraction-verification.json` and `dist/SHA256SUMS.txt` prove the actual
  distributed bytes, rather than referring to an earlier ZIP.
- [Independent judge/auditor report](INDEPENDENT_AUDIT.md), with reproduced
  defects, the contest requirement map, fixes and remaining validation gaps.
- [Current Windows actual-model regression](../evidence/independent-audit/model-regression/report.json).
- [User study protocol](USER_STUDY_KIT.md) and
  [pending participation status](../evidence/readiness-v3/user-study-status.json).

Current test source digest: `a803d9ffe64bb22bd29ce7899cd9809e47ec05b5e41d2f17bccd9ce919133f09`.
Reports contain their own timestamps and hashes; older Windows/upgrade evidence
is historical and does not attest to the current checkout.

## Remaining gaps that code alone cannot close

Instruction screening has finite coverage. The v5 and v6 first observations below
are separate authored sets; they cannot be compared as an uncontrolled percentage
improvement. Optional semantic checks remain advisory and require a local model.
Real consented SME feedback, current MLX/TideLM planning and receipt-model evaluation,
external security testing and real-data calibration remain outstanding.
Partial settlements, reversals and real lender eligibility require separate
financial design before live integration. Stored hosted run 14 concluded success for commit 6dbb3151562f9c0e8079ad32fbbc71b29f56c87b.
That historical receipt does not attest to this local remediation; no push or
hosted run was performed for these changes.
See the explicit infrastructure status below for the separately tested Docker
build; no ordinary bridge or host port exposure is inferred from isolated tests.

The supplied five-person BUET roster is retained. Leader, contribution roles,
eligibility, registration, submission route, reviewer access and the deferred
video still need the team's actual information. This local package has not been
published, deployed, emailed or submitted. A numerical 9+ rating cannot honestly
be guaranteed from synthetic checks while these validation gaps remain.


## Screening, planner and infrastructure follow-up

- Rules v5 first pass: 13/48 attacks detected, 7/48 benign flagged on a new,
  separately authored 96-message set. No misses were hidden. Its source snapshot,
  labels and first observation remain in `evidence/screening-v5/`.
- Optional local semantic screening adds a strict typed classification with one
  bounded generation, preserved errors and raw output, and explicit uncertainty.
  `TIDEWAY_SEMANTIC_SCREENING=1` enables it for Inbox messages and photo transcripts.
  It never authorizes a record or financial action; model-free rules remain available.
- [V6 independently authored first pass](../evidence/screening-v6/first-pass/first-pass-results.json)
  records actual local inference, rules/semantic/combined denominators, uncertainty,
  language/category results and runtime/source seals. It is not external validation.
- Planner candidates now mix cost, stressed cash and headroom, with stable customer
  draws and independent finalist validation. Counteroffer repair locks changed terms
  and requires fresh human approval and exact counterparty consent for every request.
- [Known D06/H11 risk follow-up](../evidence/upgrade-v10/planner/report.json)
  separates risk estimates, sampling uncertainty and the allowed-action limit.
  An above-target business is escalated, not made successful by raising the target.
- Docker status: PASS: frozen-source Linux image, isolated HTTP and persisted-state checks.
  [Raw Docker proof](../evidence/upgrade-v10/docker/report.json).
  No native MLX, host-network reachability or external penetration test is implied.
- [Stored hosted CI status](../evidence/upgrade-v10/hosted-ci-status.json):
  Stored hosted run 14 concluded success for commit 6dbb3151562f9c0e8079ad32fbbc71b29f56c87b. No hosted run for the current remediation is claimed.
- [Implementation and verification report](REMEDIATION_V7.md).

## Owner constraints and v7 screening follow-up

Owner discount ceilings, preferences and exclusions survive counter-offers and replans. The store rejects above-ceiling actions and widened successor constraints. Legacy plans without recorded instructions need a fresh owner-reviewed proposal. The UI distinguishes likely-path feasibility from simulated risk and preserves above-target precision.

- [baseline-development](../evidence/screening-v7/baseline-development/report.json): 96 cases; semantic attack recall 0.0%; combined attack recall 14.6%; broader warning false-positive rate 100.0%; targets met: False. Backend: mlx; recorded model artifacts apply.
- [improved-development](../evidence/screening-v7/improved-development/report.json): 96 cases; semantic attack recall 14.6%; combined attack recall 27.1%; broader warning false-positive rate 100.0%; targets met: False. Backend: mlx; recorded model artifacts apply.
- [baseline-base-development](../evidence/screening-v7/baseline-base-development/report.json): 96 cases; semantic attack recall 83.3%; combined attack recall 87.5%; broader warning false-positive rate 52.5%; targets met: False. Backend: mlx-base; recorded model artifacts apply.
- [improved-base-development](../evidence/screening-v7/improved-base-development/report.json): 96 cases; semantic attack recall 0.0%; combined attack recall 14.6%; broader warning false-positive rate 45.0%; targets met: False. Backend: mlx-base; recorded model artifacts apply.
- [improved-base-development-r2](../evidence/screening-v7/improved-base-development-r2/report.json): 96 cases; semantic attack recall 100.0%; combined attack recall 100.0%; broader warning false-positive rate 2.5%; targets met: False. Backend: mlx-base; recorded model artifacts apply.
- [improved-base-development-r3](../evidence/screening-v7/improved-base-development-r3/report.json): 96 cases; semantic attack recall 100.0%; combined attack recall 100.0%; broader warning false-positive rate 2.5%; targets met: True. Backend: mlx-base; recorded model artifacts apply.
- [fresh](../evidence/screening-v7/fresh/report.json): 48 cases; semantic attack recall 95.8%; combined attack recall 95.8%; broader warning false-positive rate 31.2%; targets met: True. Backend: mlx-base; recorded model artifacts apply.

Development cases are disclosed v6 regressions. The fresh set is separately AI-authored, not an external or human-blind assessment. Native MLX classification cannot inherit Windows GGUF or historical TideLM planning scores. Every miss and raw output is retained. The native classifier uses the already cached base model without the planning LoRA; the planning backend is unchanged. Independent remediation review agents were unavailable because of an account usage limit; no independent review pass is claimed.

## Behavior-driven sandbox checks

AI-authored assumed behavior scenarios; real participants: 0. Backend workflow outcomes do not measure human task completion, satisfaction or SUS.

[6/6 checks passed](../evidence/upgrade-v10/behavior-checks.json): decline without changes, incomplete approval, owner discount limits, residual-risk consent, a known hostile supplier message and repeat execution. Human validation remains pending.

## Current Windows follow-up

- [screening-baseline](../evidence/upgrade-v10/screening-baseline/report.json): 48 cases; combined attack recall 95.8%; ordinary-benign warning false-positive rate 18.8%; payment review recall 100.0%.
- [screening-revised](../evidence/upgrade-v10/screening-revised/report.json): 48 cases; combined attack recall 100.0%; ordinary-benign warning false-positive rate 0.0%; payment review recall 100.0%.
- [screening-challenge](../evidence/upgrade-v10/screening-challenge/report.json): 24 cases; combined attack recall 100.0%; ordinary-benign warning false-positive rate 12.5%; payment review recall 100.0%.
- [screening-final-known](../evidence/upgrade-v10/screening-final-known/report.json): 72 cases; combined attack recall 100.0%; ordinary-benign warning false-positive rate 0.0%; payment review recall 100.0%.

Same Windows compatible model for paired disclosed development; source-aware challenge, not external or independent blind validation. The challenge first observation is preserved; final-known is a post-fix regression over all disclosed cases. Native MLX planning and receipt-model verification are deferred until Mac access is available.

[H11 cash-gap diagnostic](../evidence/upgrade-v10/liquidity-gap.json): original risk 11.78%; conditional on MYR 3,000.00 extra cash at opening, fresh-draw risk 0.43%. Funding is unconfirmed and unexecuted. Baseline ledger, target and approval requirements are unchanged.

HTTP regressions reject duplicate JSON keys and ambiguous body framing, tolerate malformed cookies as unauthenticated, share anonymous rate limits across invalid cookie values, and bound body reads by a total deadline. These are internal tests, not an external security audit.
