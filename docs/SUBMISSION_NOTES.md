# Tideway submission notes

FinTechathon 2026 International Track, Topic E: SME Finance Copilot.
This package is a synthetic research prototype. It connects to no real bank,
lender, customer or supplier and moves no real money.

## Team

**The Last BrainCell**

Bangladesh University of Engineering and Technology (BUET).

- Nafis Mohtasim Ramim
- Shaharia Rahman Santo
- Md. Atik Khan
- Md. Ashraf Hossain Chowdhury
- Khandaker Shadman Sakib Siddiquee

Roles and team leader: awaiting the team's confirmation.

## Reviewer quick start

Requires Python 3.11 or newer. No package installation, API key or paid service
is required for the core sandbox. From the source directory:

```
python run.py
```

Open `http://127.0.0.1:8787`. Choose Imran for the accountant demo or Nadia for
the owner demo. Demo PINs: Imran `1357`, Nadia `2468`, Guest `0000`.
Use a fresh database for a repeatable run:

```
python run.py --db data/reviewer-fresh.sqlite3 --port 8788
python -m unittest discover -s tests -v
python -m tideway.selftest
```

The public handbook is at `/guide`. The model-status card distinguishes the
deterministic Windows demo from optional Apple Silicon inference. Receipt
extraction and TideLM are optional, with limitations in `docs/MODEL_CARD.md`.

## Deliverable map

| Requirement | Package location |
|---|---|
| Architecture, algorithm and security design | `docs/architecture.pdf`, `docs/TECHNICAL_DOCUMENTATION.md` |
| Presentation (10-minute maximum) | `slides/pitch.pdf`, `docs/PITCH_SCRIPT.md` |
| Demo video, within 5 minutes | Deferred by the team; recording is not included in this package |
| Source, setup and tests | `source/` in the ZIP; root README, run.py and tests in the working copy |
| Permission tiers and known risks | `docs/security-assessment.pdf`, `docs/SECURITY_SELF_ASSESSMENT.md` |
| Sandbox execution evidence | `evidence/results.csv`, `run-log.jsonl`, `verification-summary.json`, `screens/` |
| Validation and package integrity | `evidence/test-summary.json`, `package-manifest.json` and ZIP SHA-256 |
| Model origin, licenses and limits | `docs/MODEL_CARD.md`, `THIRD_PARTY_NOTICES`, `licenses/` |

## Team-controlled final steps

The supplied roster is included. Confirm the team leader and actual roles, eligibility,
registration acknowledgement, submission route and reviewer access. Keep the supplied public names/institution in tracked `submission-team.public.json`; roles and leader stay blank until confirmed. Private administrative facts belong in ignored `submission-team.json` and are never copied into the source archive. Follow any organiser requirement for truthful AI-assistance disclosure.
No roles, nationality, registration or consent have been invented.

## Published instructions checked on 15 October 2026

Registration and submission deadline: 20 October 2026, 23:59 Beijing time,
which is 21:59 Bangladesh time. English is the submission language. The published
rubric assigns 40% task completion, 30% security/compliance and 30% innovation/
interaction. Sandbox evidence is accepted for non-on-chain topics. Video is
listed as optional but also named under execution evidence; the team has explicitly deferred the recording. Add it before final submission or obtain written organiser clarification.

- [Competition rules](https://www.its.ac.id/international/wp-content/uploads/sites/66/2026/10/PBCSF-Appendix-2-Problem-Description-and-Competition-Rules-for-International-Track.pdf)
- [IEEE track instructions](https://www.ieee-cis-singapore.org/2026-fintechathon)
- [CMU announcement](https://ird.oou.cmu.ac.th/2026-shenzhen-international-fintech-competition/)

IEEE lists `fintechathon@ican-x.com`; CMU and the rules list
`wangyr@pbcsf.tsinghua.edu.cn`. Use the team's acknowledgement to confirm the
route before sending personal documents. This package contains no passports.

## Honest limits

All data and counterparties are synthetic. Identity and keys are demo-grade.
TidePay federation is a single-process simulation with illustrative masks.
TideLM has a synthetic template-based benchmark, not real-world accuracy.
Post-fix TideVision inference on Apple Silicon remains unverified. There is no
completed SME user study, live cloud-provider benchmark or external penetration
test. Docker instructions are supplied, but a successful Docker build must only
be claimed on a machine where it was actually run.

## Contest upgrade evidence

Use `docs/PAYMENT_DELAY_RUNBOOK.md` for the live linked approval/invalidation/reapproval sequence. `evidence/upgrade-v1/` contains the corrected chronological prediction benchmark, distinct scenario workflows and screening/performance measurements, real-model availability report and delay receipt. Historical observations are retained under `evidence/history/pre-upgrade-v1/` and `evidence/ml/`. See `docs/CONTEST_UPGRADE_REPORT.md` for measured results and remaining verification limits.

The package source is tested and browser-checked at the same source digest; `python3 scripts/verify_package.py` checks archive hashes, extracted tests and a new loopback server with Python `-S`, no Git or developer configuration. This local preparation does not establish registration or submission readiness. The main site is dynamic and its full latest notices remain unverified.
