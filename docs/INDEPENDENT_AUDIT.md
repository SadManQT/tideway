> Historical independent-audit pass before the screening/risk/infrastructure follow-up. See [REMEDIATION_V5.md](REMEDIATION_V5.md) and [READINESS_CURRENT.md](READINESS_CURRENT.md) for later source and evidence.

# Independent judge and auditor review - 17 October 2026

**Verdict:** Tideway is a credible, reproducible Topic E synthetic sandbox, with
working financial decisions and approval-gated execution. It is not yet a
fully cleared contest submission or a validated real-world financial service.
The local defects below were reproduced and repaired. Submission administration,
optional-device verification and the weak unfamiliar-message detector remain
open. Passing the listed checks does not establish the absence of all defects.

This review was conducted by the coding assistant using a fresh check of the
current checkout, rather than adopting previous ratings. It is not an external
penetration test, organiser decision or independent human certification.
Base commit: `bd8c061` (extra features added). Changes remain local; no push,
email, publication, registration or submission was performed.

## Contest requirements and judge assessment

The [competition-branded rules](https://www.its.ac.id/international/wp-content/uploads/sites/66/2026/10/PBCSF-Appendix-2-Problem-Description-and-Competition-Rules-for-International-Track.pdf)
and [IEEE guidance](https://www.ieee-cis-singapore.org/2026-fintechathon) were
reopened on 17 October. Topic E covers financing matching, cash-flow alerts and
financial analysis. The shared rubric is task completion 40%, security/compliance
30%, innovation/interaction 30%. A non-on-chain sandbox is accepted; adding a
real bank or blockchain is not necessary for this topic.

| Requirement / judge concern | Current evidence | Remaining issue |
|---|---|---|
| Topic E problem and complete task | Dated cash forecasts, alerts, exact-money rescue options, consent, approval, signed mandate, negotiation and read-back | No validation with actual SMEs; banking/lending are simulated |
| Financing matching | MOCK catalogue compares timing, fees, annualised-cost convention, total repayment and cash through repayment | Eligibility, collateral assignment and product availability are unverified |
| AI usefulness | Exact deployed weights: 7,427 new synthetic invoices, MAE 8.5585 days versus heuristic 10.2296; Brier/calibration and raw predictions available | Same-generator synthetic evidence; cold-start log loss worse than training prior; no real-data calibration |
| Autonomous reasoning | Recorded model tool selection and computed risk/proposal facts; current Windows run covers 32 disclosed requests, with every generation retained | A known-case regression is not blind accuracy; MLX adapter, receipt model and cloud provider remain separate |
| Security and compliance | Structural roles, PIN, scoped mandates, explicit above-target risk acknowledgement, stale-state rejection, idempotency and audit witness | First unfamiliar screening detects only 2/24 attacks, with 2/24 benign flags; no external security assessment or production compliance claim |
| Interaction and memorable demo | Role-aware quick start, desktop/mobile workflow, linked customer-delay demo that invalidates old authority | Timed presenter rehearsal and real user feedback remain necessary evidence of usability |
| Technical/security reports and English presentation | Source, setup, tests, architecture, self-assessment, deck, scripts and logs included in local package | The 10-minute limit applies to the actual presentation; page count or a script alone cannot prove timing |
| Execution evidence | Sandbox logs, screenshots, execution receipts and fresh-extraction startup | Video explicitly deferred by the team; checklist calls it optional, while execution-evidence wording also names it |
| Source and repository access | Allowlisted ZIP, manifest and hashes; private keys/configuration excluded | Team must confirm the final repository link opens for reviewers |
| Team and registration | Supplied five-person BUET roster included | Leader, roles, eligibility, registration and authoritative delivery route await real team information |

Deadline in the published Appendix: **20 October 2026, 23:59 Beijing / 21:59
Bangladesh**. IEEE warns registration may close early. Contact routes differ
between the Appendix and IEEE, and the main website's complete dynamic notices
were not independently verified. Do not invent organiser confirmation or treat
an enquiry about AI-assistance disclosure as a published requirement for a reply.

## Reproduced defects and repairs

| ID / priority | Reproduced failure | Repair and verification |
|---|---|---|
| A01 / high | A truncated signing-key file was silently replaced. Concurrent initial callers received different keys, invalidating each other's signatures. | Existing invalid files fail closed and remain byte-identical. New keys are fully written and synced before atomic create-if-absent publication; concurrent starts read the winning key. Tests cover corrupt/empty/non-hex keys and 24 concurrent loads. |
| A02 / medium | A 64-character non-ASCII signature raised `TypeError` instead of returning an invalid-signature result. | Strict lowercase SHA-256 hex validation precedes constant-time comparison. Malformed signatures return false; authentic and tampered documents are tested. |
| A03 / medium | `.env.example` documented `TIDEWAY_LOCAL_STRUCTURED_PLANS`, but startup omitted it from the environment allowlist. | Startup now loads the flag, preserves explicit shell settings, and ignores unrelated variables. |
| A04 / high | Profiles and empirical fallback used paid history dated after the simulation date; the model itself already applied the cutoff. Dashboard overdue days also lacked the snapshot date. | Profiles, fallback and the illustrative leave-one-out backtest share the snapshot cutoff; `Store.derived` passes current date. Tests cover future labels, inclusive cutoff, fallback and model/profile consistency. This does not turn the illustrative backtest into a chronological model benchmark. |
| A05 / medium | A receivable already used in an accepted early-payment adjustment could still satisfy mock invoice-advance collateral. Not-yet-issued invoices were also counted. | Mock collateral excludes committed and future-issued invoices. The comparison remains read-only and lender eligibility remains unverified. |
| A06 / medium | Four CRLF files in this Windows checkout contradicted the LF policy. The installed model's raw hash differed from its evaluation, making the deployed-model card unavailable. | Restored actual LF bytes, preserving parsed JSON and model weights. Installed SHA-256 again equals `00639d9b3e408f1a51df20130e804db2f8a031772a772d706f09e6a7428aa466`. Strict byte checks were retained. These byte repairs need not appear as semantic Git diffs. |
| A07 / medium | The old-schema migration test left a raw SQLite connection open; Windows refused temporary-directory cleanup. | Explicit connection closing preserves transaction checks and makes cleanup pass without suppressing errors. |
| A08 / medium | Pitch script and technical/checklist text still described compatible inference as unavailable and led with scores for different model weights. | Current text leads with the shipped artifact's evaluation and distinguishes measured compatible inference from pending MLX/vision/cloud paths. Unresolved video and administrative items remain visible. |

Nine additional behavioural regressions are in `tests/test_independent_audit.py`.
Existing model-card and migration tests cover the two initial suite failures.
No detector score was improved by relabelling cases, hiding misses or replacing
the sealed first-observation reports.

## Verification and reproducibility

The untouched baseline on Windows ran **252 tests with 1 failure, 1 error and
1 skip**. After repairs the suite ran **261 tests with zero failures/errors**;
one symlink test is skipped because this Windows account cannot create symlinks.
Optional Pillow photo tests ran here. The final release run's exact environment,
counts and source digest are authoritative in `evidence/test-summary.json`.

- Baseline raw log and reproduced-finding record:
  `evidence/independent-audit/baseline-test-run.log` and `findings.json`.
- Actual Windows compatible Qwen3 known-case rerun: **32/32 handled, 32/32
  contained**, with 34 completed generations, separate request/generation
  denominators and all outputs in `evidence/independent-audit/model-regression/`.
  The historical first observations remain unchanged. Reproduce in a new empty
  output directory using `python scripts/audit_model_regression.py --out PATH`
  with the local server configured as described in `docs/SETUP_WINDOWS_MAC.md`.
- Final syntax, unit, task/attack scorecard, varied financial scenarios,
  linked-delay approval, desktop/mobile and injected-backend browser checks:
  `evidence/readiness-v3/release-checks.json` and `docs/READINESS_CURRENT.md`.
- Additional actual-backend browser evidence, with runtime identity and UI
  result checks: `evidence/independent-audit/browser-real-model/`.
- The full 7,427-invoice deployed-model evaluation was also reproduced on
  Windows into `evidence/independent-audit/tidepay-reproduction/`. Overall
  results, cohort balance and subgroups match the saved report exactly;
  `comparison.json` records both report hashes. This repeats disclosed cohorts
  to check reproducibility and is not a new unseen evaluation.
- Actual distributed bytes and extracted tests/startup:
  `dist/package-manifest.json`, `dist/SHA256SUMS.txt` and
  `dist/extraction-verification.json`. These reports refer to their exact source
  and archive hashes; old Mac/Windows runs do not attest to later source changes.
- Five refreshed PDF deliverables were rendered and visually reviewed across
  53 pages. Page bounds and all expected pitch text passed automated checks;
  sparse overflow pages were removed from the technical and submission notes.
  Exact final hashes and review scope are in
  `evidence/independent-audit/pdf-review.json`.

The local model cache and native executables are excluded from the ZIP. Core
review requires Python only; full browser/PDF release checks require Node and
Chrome/Edge. A configured workflow is not a passing GitHub-hosted run. Docker's
daemon was unavailable in earlier work; no successful container build is claimed.

## What remains, ordered by practical priority

1. **Before sending:** confirm registration, eligibility, leader, actual roles,
   submission route, reviewer access and any organiser-specific form/signature
   requirements. These facts were explicitly deferred by the team. No passport
   or private contact information belongs in the public source archive.
2. **Video decision:** keep the team's deferral; clarify the conflicting wording
   or provide the required evidence before sending. No video was created here.
3. **Winning-quality evidence:** conduct a timed English pitch and consented SME
   usability study. There are currently zero real participants. Do not present
   the study kit, synthetic outcomes or smoke requests as customer validation.
4. **Detection quality:** unfamiliar instruction screening is weak (8.3% attack
   detection and 8.3% benign flag rate on 24+24 authored cases). Harden and test
   against a newly sealed, independently authored set after future changes.
   Structural payment authority remains essential even with a better detector.
5. **Model validation:** actual compatible Qwen inference is verified for listed
   requests, but native MLX/TideLM, receipt quality, real cloud latency, real-data
   calibration and overdue/default generalization are not established. Shipped
   cold-start probability quality needs attention. Retain the baseline failures.
   Only seven of nine executed scenario rescues meet the 10% simulated reserve
   risk target; the other two require explicit above-target approval. Expected
   workflow handling of 24/24 is not a claim that every case achieves low risk.
6. **Infrastructure / live integration:** run hosted CI and Docker where available;
   obtain external security testing before live use. Partial settlements,
   reversals, genuine lender eligibility and bank execution require separate
   financial design. None is required merely to demonstrate this Topic E sandbox.

Large central modules remain maintainability debt. The regression suite and
configured CI reduce change risk, but they do not replace smaller interfaces,
external review or usability validation. A broad refactor before the deadline
would need its own review and verification.

The fixed local package is reviewable. Administrative completion and the above
unmeasured quality claims cannot honestly be supplied by code changes alone.
