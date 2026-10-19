# Current technical readiness

Current local release: [customer/payment review and screening precision](RELEASE_V14.md). Currency foundation: [v13](RELEASE_V13.md). Prior features: [Owner view](OWNER_VIEW.md) and [Decision lab](DECISION_LAB.md).

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
- An anonymous, consent-aware study kit separates task observations, assistance,
  missing model runs and questionnaire scores. The current aggregate records
  20 team-reported participants; its collection scope is stated below.
- Independent follow-up audit: invalid signing keys are preserved and rejected;
  concurrent first starts publish one complete key. Malformed signatures fail
  validation, and `.env` now loads the documented structured-plan flag.
- Profiles, empirical fallback and illustrative backtests use only paid history
  available at the simulation date. Mock advances exclude already committed and
  not-yet-issued receivables. A Windows SQLite test handle leak is corrected.

## Measured evidence

| Check | Recorded result | Meaning and limit |
|---|---|---|
| Latest stored full unit run | 497 run; 0 failures; 0 errors; 1 skipped | Python 3.13.7, Windows; the report records its own source hash; injected outputs are not model quality |
| Additional standard-library run | 252 run; 0 failures; 0 errors; 4 skipped | Python 3.11.16; optional photo tests require Pillow; report records its own source hash |
| Financial scenarios | 24/24 expected workflows; 9 rescues | 8/9 executed rescues meet the 10% simulated risk target |
| Shipped TidePay | 7,427 unseen synthetic invoices; MAE 8.5585 days | Heuristic 10.2296; training-only prior 11.7453; no weight changes |
| First actual Qwen3 challenge | 28/32 correct; 32/32 contained | Four retained misses; no mandate, execution or financial-ledger mutation |
| Post-fix Qwen3 regression | 32/32 known cases handled; 8/8 safe stops | One real-model pass after disclosed guard fixes; not a new blind score |
| Independent-audit Windows Qwen3 rerun | 32/32 known requests handled; 32/32 contained | Actual compatible inference on disclosed cases; retains every output; not blind |
| Historical first unseen instruction screening | 2/24 attacks detected; 2/24 benign flagged | Historical v3 observation; current v7 evidence is listed below; detection is advisory |
| SME user study | 20 team-reported participants; 60/94 unassisted; 85/94 including assistance | Supplied observations and team-confirmed consent; collection and optional-model runtime not independently verified. See [survey report](USER_STUDY_RESULTS.md). |

Two later 20-row files have a separate [team-reported usability study](SURVEY_INTAKE_20.md):
87/97 supplied SME task records completed without help, 94/97 including help,
and mean SUS 75.75/100. The team reports sessions on 19 October, moderated by
Ramim, database resets between participants and a 10-person overlap, giving 30
unique people in this study. The user identified survey commit `9dbe495`, which
Git confirms predates v14 UI improvements. These observations do not measure
the later UI changes. Collection, execution and survey-linked model artifacts
remain independently unverified. The records are kept separate from the earlier
study and do not establish causal improvement. The security file provides assistance and
timings without structured technical outcomes, so no security pass rate is inferred.

The [survey artifact audit](SURVEY_INTAKE_20.md#artifact-verification) verifies both
source exports, 40 row fingerprints, the reported overlap references, cached
model/runtime hashes and related application trees. Current Edge 155.0.4283.62
was measured on the desktop PC. The team confirmed that the survey used a
separate laptop, explaining the hardware difference. The reported historical
commit is resolved and its committed source is hashed; laptop browser/runtime
invocations and local working-tree changes remain unverified.

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

Open http://127.0.0.1:8787. Personal preparation material is not served or linked by the product.

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
- [Current scenario report](../evidence/upgrade-v14/scenarios/report.json),
  [linked delay receipt](../evidence/upgrade-v14/payment-delay.json) and
  [browser workflow](../evidence/screens/browser-verification.json).
- [Exact shipped prediction evaluation](DEPLOYED_MODEL_EVALUATION.md), with
  raw invoices, shared test IDs, predictions, intervals and calibration bins.
- [Independent screening/model evaluation](BLIND_EVALUATION.md), source seals,
  native runtime provenance and every first-observation output.
- [Separate post-fix model regression](../evidence/readiness-v3/blind/model-post-fix-regression.json)
  and [Python 3.11 standard-library run](../evidence/readiness-v3/python311/test-summary.json).
- [Release stages and PDF hashes](../evidence/upgrade-v14/release-checks.json).
  `dist/extraction-verification.json` and `dist/SHA256SUMS.txt` prove the actual
  distributed bytes, rather than referring to an earlier ZIP.
- [Independent judge/auditor report](INDEPENDENT_AUDIT.md), with reproduced
  defects, the contest requirement map, fixes and remaining validation gaps.
- [Current Windows actual-model regression](../evidence/independent-audit/model-regression/report.json).
- [User study protocol](USER_STUDY_KIT.md) and
  [current participation aggregate](../evidence/readiness-v3/user-study-status.json).

Current test source digest: `f2ee85f656329ef4d0db2f01ec625373dc8e6284dfb5da3f340bf08b93cd741c`.
Reports contain their own timestamps and hashes; older Windows/upgrade evidence
is historical and does not attest to the current checkout.

## Remaining gaps that code alone cannot close

Instruction screening has finite coverage. The v5 and v6 first observations below
are separate authored sets; they cannot be compared as an uncontrolled percentage
improvement. Optional semantic checks remain advisory and require a local model.
Independent verification of the supplied SME observations, usability re-testing,
current MLX/TideLM planning and receipt-model evaluation,
external security testing and real-data calibration remain outstanding.
Partial settlements, reversals and real lender eligibility require separate
financial design before live integration. Stored hosted run 8 concluded success for commit f60a6752e26723ae6b696a40e52335d15f1e3339.
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
- [Known D06/H11 risk follow-up](../evidence/readiness-v5/planner/report.json)
  separates risk estimates, sampling uncertainty and the allowed-action limit.
  An above-target business is escalated, not made successful by raising the target.
- Docker status: Not yet a passing current-source Docker run; inspect raw status.
  [Raw Docker proof](../evidence/infrastructure-v5/docker/report.json).
  No native MLX, host-network reachability or external penetration test is implied.
- [Stored hosted CI status](../evidence/infrastructure-v5/hosted-ci-status.json):
  Stored hosted run 8 concluded success for commit f60a6752e26723ae6b696a40e52335d15f1e3339. No hosted run for the current remediation is claimed.
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

[6/6 checks passed](../evidence/upgrade-v14/behavior-checks.json): decline without changes, incomplete approval, owner discount limits, residual-risk consent, a known hostile supplier message and repeat execution. These scripted checks do not count as human participants. Separate supplied survey observations are described in [the survey report](USER_STUDY_RESULTS.md).

## Currency consistency and related UI audit

The owner-selected currency now applies to editable financial amounts, generated narrative text, trace summaries, approval review, financial cards and human-readable reports. Exact rational conversion preserves the canonical ledger and unchanged rounded inputs. Explicit monetary question tokens are normalized before model/agent calls; ambiguous foreign-unit amounts require a currency code. Signed evidence and settlement documents retain original units. Per-operator preferences and unsaved drafts are preserved; source-aware Inbox review, scoped demo roles and pending lab inputs are corrected. See [conversion checks](../evidence/currency-v13/currency-checks.json), [browser evidence](../evidence/screens/browser-verification.json) and [release notes](RELEASE_V13.md). These are synthetic engineering checks, not live FX or new real-model quality/human usability results. Earlier PDFs and model/container observations retain their original scope.

## Customer decisions and screening precision

Customer cards separate observed late settlements from projected receipt dates and compare those dates with payroll. The same exact proposal cost, cash, reserve and remaining-risk explanation appears on the rescue card and approval dialog. Selected display currency, same-day timing uncertainty, missing history and above-target acknowledgement remain visible. These are engineering improvements; no new human usability score is claimed.

- [screening-baseline](../evidence/upgrade-v14/screening-baseline/report.json): 48 cases; combined attack recall 100.0%; ordinary-benign warning false-positive rate 70.8%; legitimate payment-change recall 100.0%.
- [screening-revised](../evidence/upgrade-v14/screening-revised/report.json): 48 cases; combined attack recall 100.0%; ordinary-benign warning false-positive rate 0.0%; legitimate payment-change recall 100.0%.
- [screening-final-known](../evidence/upgrade-v14/screening-final-known/report.json): 120 cases; combined attack recall 96.2%; ordinary-benign warning false-positive rate 0.0%; legitimate payment-change recall 100.0%.
- [screening-challenge](../evidence/upgrade-v14/screening-challenge/report.json): 48 cases; combined attack recall 93.8%; ordinary-benign warning false-positive rate 0.0%; legitimate payment-change recall 100.0%.
- [screening-post-fix-known](../evidence/upgrade-v14/screening-post-fix-known/report.json): 168 cases; combined attack recall 100.0%; ordinary-benign warning false-positive rate 0.0%; legitimate payment-change recall 100.0%.

Actual cached Windows Qwen3 compatible inference; same-model paired development and a source-aware AI-authored challenge. Historical misses and all raw outputs are retained. These runs do not verify the native MLX backend or establish population accuracy. See [scope and reproduction](RELEASE_V14.md).
