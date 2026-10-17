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
TidePay federation is a single-process simulation with illustrative masks.
TideLM has a synthetic template-based benchmark, not real-world accuracy.
Post-fix TideVision inference on Apple Silicon remains unverified. There is no
completed SME user study, live cloud-provider benchmark or external penetration
test. Docker instructions are supplied, but a successful Docker build must only
be claimed on a machine where it was actually run.

## Evidence and current remediation

Start with `docs/READINESS_CURRENT.md`. The exact shipped TidePay model is
evaluated on 7,427 new synthetic invoices; mean absolute timing error is 8.5585
days versus 10.2296 for the history heuristic. The low-history limitation is
reported separately. Historical audit-model scores do not transfer to shipped
weights. Native macOS Qwen3 first handled 28/32 sealed requests; all four misses
and source snapshots are preserved alongside later guard regressions.

Historical v3 message screening detected only 2/24 unfamiliar attacks and flagged
2/24 benign messages. Current v7 screening runs, model identities, confusion
matrices, uncertainty and latency are retained in `evidence/screening-v7/` and
explained in `docs/REMEDIATION_V7.md`; development and fresh results stay separate. Payment authority therefore remains outside the model and
screening. Above-target plans require each approver's server-checked, plan-bound
risk acknowledgement. Mock financing includes timing, total repayment,
unverified eligibility and affordability through repayment.

`python3 scripts/prepare_release.py` rebuilds and checks one frozen LF source
tree, refreshes browser and PDF evidence, builds the local ZIP and verifies its
fresh extraction. `--checks-only` runs core checks; Node 22+ and Chrome/Edge are
required for the full command. No weight download, cloud provider, push or
submission occurs. Real-user study status is pending with zero participants;
the consent-aware kit does not invent feedback.

## Independent audit follow-up

See `docs/INDEPENDENT_AUDIT.md` for the contest requirement map, reproduced signing/configuration/financial defects, fixes and unresolved quality gaps. The current release reports supply exact test, browser and extraction results for one source digest. This review is performed by the coding assistant and is not an external security certification.

## Owner constraints and residual risk

The [completion review](COMPLETION_V8.md) records the current Windows checks,
retained historical model measurements, PDF review and final package commands.

Counter-offers and replans retain the owner discount ceiling, preference and
exclusions. A 1% ceiling rejects a 1.5% counter; changed instructions require a
new reviewed proposal. Replacements require fresh approval and consent. Legacy
plans without recorded owner instructions fail closed. H11 retains approximately
11.78% breach risk against a 10% target; likely-path feasibility and explicit
acknowledgement do not promise successful collections or universal rescue.

The v7 fresh 48-case AI-authored screening run detected 23/24 attacks, retained
verification for 8/8 legitimate payment updates, and warned on 5/16 ordinary
benign messages (31.25%). One Hindi exfiltration attack and five false warnings
remain recorded. These are finite synthetic results; no later tuning used that
fresh set, and no external security review pass is claimed.
