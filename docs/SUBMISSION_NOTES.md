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
deterministic default from optional local-compatible and Apple Silicon inference. Receipt
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

## Published instructions rechecked on 17 October 2026

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
Federation uses one process and illustrative masks. Real SME participants remain
zero. Native MLX planning/receipt inference, live-cloud evaluation and external
penetration testing remain outstanding. Behavioral walkthroughs do not measure
human usability, adoption or prediction accuracy.

## Evidence and current remediation

Start with `docs/READINESS_CURRENT.md` and `docs/RELEASE_V9.md`. Current tests,
browser proof and source hashes are under `evidence/release-v9/`. The compatible
Qwen regression handled 32/32 disclosed requests with 32/32 payment containment;
the actual-model browser check passed. Raw outputs are in its `model-regression/`
and `browser-real/` folders. These are known-case/integration results, not unseen
accuracy or native adapter scores. The six checks in `docs/BEHAVIORAL_EVALUATION.md`
exercise AI-authored behavior paths against the backend.

Exact shipped TidePay weights were evaluated on 7,427 new synthetic invoices:
MAE 8.5585 days versus the history heuristic's 10.2296, with low-history limits
disclosed. Historical first observations and misses remain unchanged. The
v7 fresh 48-case screening run detected 23/24 attacks, retained verification
for 8/8 legitimate payment changes and warned on 5/16 ordinary benign messages
(31.25%). One Hindi exfiltration miss and five false warnings remain in
`evidence/screening-v7/`; development results are reported separately.

`python3 scripts/prepare_release.py` checks a frozen LF source tree, including
web fonts/images, refreshes browser/PDF evidence, builds the ZIP and verifies
fresh extraction. The full command needs Node 22+ and Chrome/Edge; `--checks-only`
runs core checks. No weights are downloaded and nothing is pushed or submitted.
Historical defects and verification scope are in `docs/INDEPENDENT_AUDIT.md`
and `docs/COMPLETION_V8.md`; this is the coding assistant's review.

## Owner constraints and residual risk

Counters and replans retain the owner ceiling, preference and exclusions. A 1%
ceiling rejects a 1.5% counter; changing instructions needs a new reviewed plan.
Replacements revalidate signed parent authority and require fresh approval and
consent. Legacy plans without instructions fail closed. H11 retains 11.78% mean
breach risk versus a 10% target; every required approver must acknowledge the
exact residual risk. Likely-path feasibility does not guarantee collections.
Mock financing discloses timing, total repayment, unverified eligibility and
affordability through repayment.
