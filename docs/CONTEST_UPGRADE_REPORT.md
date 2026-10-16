> Historical report for an earlier source version. See [READINESS_CURRENT.md](READINESS_CURRENT.md) for current evidence and remaining gaps.

# Contest upgrade implementation and evidence

Local work for Topic E: cash-flow support, analysis and bounded financing comparisons. Synthetic only; no bank/payment integration, external publication or video recording.

## A. Payment prediction

The chronological audit fits global statistics and weights on matured training labels only. Separate validation is diagnostic; no calibration is fitted on final test data. Same final records for all baselines. Sum Brier is the mean of the sum of five squared class errors (range 0-2).

| Model | Test invoices | MAE days | Log loss | Sum Brier |
|---|---:|---:|---:|---:|
| prior | 2376 | 11.9856 | 1.5882 | 0.7936 |
| heuristic_v1 | 2376 | 7.4107 | 1.5688 | 0.7905 |
| local_only | 2376 | 7.2152 | 1.2329 | 0.6407 |
| federated | 2376 | 6.9568 | 1.0727 | 0.5777 |
| centralised | 2376 | 6.9448 | 1.0927 | 0.5855 |

The historical prior used test-label statistics; raw historical evidence is preserved. The audit benchmark does not replace production weights. Federation remains one-process simulation with pooled scaling and illustrative predictable masks. Seven of forty SMEs have worse federated MAE than the heuristic; pooled MAE is slightly better overall. One synthetic cohort cannot establish real-business accuracy.

Evidence: `evidence/upgrade-v1/tidepay/` (report, raw predictions, splits/hashes, reliability bins/plot, subgroup and uncertainty results). Method: `docs/TIDEPAY_EVALUATION_V2.md`.

## B. Financial tools and conditional selection

Whole-plan preflight validates roles/Advise mode, strict entity identity, money/currency/units, dates, hypothetical isolation and tool budgets before any proposing side effect. Rescue selection consumes deterministic forecast/risk/security outputs and records a bounded model follow-up, observable tool receipts and a code-written rationale. Fallback and injected transports are labelled explicitly.

Archived real-model smoke on macOS: unavailable, zero real requests, exit code 2. That environment had no MLX, released adapter or cached base weights. Historical TideLM v2 scores do not measure the changed protocol. The later Windows compatible-model verification and retained failed runs are separate under `evidence/readiness-v2/model/`; see `docs/READINESS_UPDATE.md`. Reproduction: `python3 scripts/smoke_reasoning.py`; model-enabled commands in `docs/MODEL_REASONING_V2.md`.

Evidence: `evidence/upgrade-v1/model/`; guard tests are separate from model quality.

## C. Distinct conditions, screening and performance

24/24 correct handling, with 9 executed rescues, 9 infeasible, 2 no-action and 4 blocked. 0 unexpected financial-state changes. Development/held-out specifications were sealed before evaluating.

Only 7/9 rescues meet the 10% simulated-risk target; two remain at 18.5%/19%. Outcome handling is not rescue success or calibrated cash-risk accuracy.

- Injection: detected 12/14 labelled attacks, missed 2; flagged 7/14 benign cases.
- Payee: detected 6/8 labelled attacks, missed 2; flagged 3/8 benign cases.

Planner-only 154 timings: median 1.87 ms, p95 149.58 ms, 7 repetitions and 1 discarded warm-up per case. Database, PIN, UI and model time excluded. Input sizes, seeds, search limits and slow per-case timings are saved.

A case-only payee-account bypass was fixed after observation. Pre-fix labels and 5/8 detection remain preserved; the same labels give 6/8 afterward. Other misses and conservative false positives remain. No generic-LLM or general-spreadsheet comparison was run. See `docs/SCENARIO_EVALUATION_V2.md` and `evidence/upgrade-v1/scenarios/`.

## D. Linked payment delay and fresh approval

Bay Logistics collection changes from 2026-11-03 to 2026-11-15. Likely minimum moves from BDT -42,000 to -57,000; reserve shortfall from BDT 62,000 to 77,000. Both states already have 100% breach risk. The chosen actions change from supplier deferral plus Nila early collection to early-payment offers for Bay and Nila.

Owner membership/PIN, current snapshot, demo-only ledger and an atomic request receipt guard the mutation. Superseded promises cannot hide the delay; quarantine flags remain. Old authority is invalidated, fresh approvals and Bay counter-offer approval are required, and execution/read-back/retry is verified. What-if sliders remain read-only.

Run `python3 scripts/demo_payment_delay.py`. For the live UI use a new unused database: `python3 run.py --db data/contest-rehearsal-01.sqlite3 --port 8788`. Then follow `docs/PAYMENT_DELAY_RUNBOOK.md`. Never reset/delete earlier databases or evidence.

## Actual verification and handoff

Latest automated report: 198 tests run, 197 passed, 1 skipped, 0 failures and 0 errors; Python 3.13.7 on Windows. See evidence/test-summary.json for the validated source digest and evidence/test-run.log for skip reasons. The earlier stdlib-only baseline had four optional Pillow skips; each run records its actual skips.

Baseline: `evidence/upgrade-v1/baseline.json`; original self-test and historical observations preserved. Current self-test, unit, compile, browser, model availability and distribution reports describe their own actual environments. Only the environments named in those reports were verified. No Docker build, external penetration test, SME user study or post-change real-model quality result is claimed.

Regenerated deliverables: slides/pitch.pdf; docs/architecture.pdf; docs/security-assessment.pdf; docs/submission-notes.pdf; docs/Tideway_FinTechathon_2026_Roadmap.pdf. Final visual QA evidence and source/package hashes are kept with the release reports. Build the local ZIP with `python3 scripts/build_submission_package.py`, verify extracted bytes/startup with `python3 scripts/verify_package.py`, inspect dist/extraction-verification.json and dist/SHA256SUMS.txt.

## Team-controlled outstanding steps

- Install the exact released text adapter/base and verify real-model behavior on supported hardware; repeat receipt-model smoke separately.
- Supply leader and actual contribution roles; verify eligibility, registration acknowledgement and current reviewer repository access.
- Resolve submission-address conflict and latest organiser instructions; main-site dynamic notices were not fully verified.
- Resolve video requirement or record only when separately instructed; recording remains deferred.
- Review changes and choose final commit/version; no push, publication, organiser contact or submission was performed.

Deadline from checked Appendix/CMU: 20 October 2026, 23:59 Beijing (21:59 Bangladesh, 08:59 PDT). `docs/CONTEST_SOURCES_CHECKED.md` links the sources and records their discrepancies. Technical preparation does not confirm administrative readiness.
