# Probaho — Submission checklist

This checklist is aligned to the supplied `FinTechathon_2026_Bangla_Roadmap.pdf`. It is a project-preparation checklist, not an organizer-issued acceptance document. Confirm the latest official notice before submission.

## Product and evidence

| Item | Current state | Owner/action before submission |
|---|---|---|
| Topic E concept | Implemented as Probaho | Team: confirm Topic E and project title |
| SME workflow | Local synthetic import → projection → compare → approve → consent → execute → read-back | Team: verify with real SME stakeholders |
| Deterministic arithmetic | Implemented and tested | Keep raw fixture outcomes with commit SHA |
| Security controls | Implemented self-assessment | Add formal attack matrix and raw results |
| Source-linked evidence | Projection references, hashes, receipts | Export final business evidence from a clean database |
| Baseline comparison | Not yet a measured competition result | Run rule/spreadsheet baseline and generic-LLM comparison |
| Scenario benchmark | Backend/browser checks exist | Run at least 20 independent scenarios and preserve results |
| User feedback | Not yet collected | Interview 3–5 SME owners/domain reviewers with consent |
| Latency/cost | Not yet measured with a live provider | Run 30+ controlled runs if AI mode is used |
| Live AI validation | Not completed until a team key is configured | Run a consented live test; do not commit the key |

## Required package

The roadmap lists technical documentation, deck, demo video, source repository, security self-assessment, and execution evidence. The following project files are present:

- `README.md`
- `docs/TECHNICAL_DOCUMENTATION.md`
- `docs/SECURITY_SELF_ASSESSMENT.md`
- `docs/EVALUATION_PLAN.md`
- `docs/DEMO_SCRIPT.md`
- `docs/PITCH_SCRIPT.md`
- `tests/`
- `evidence/` generated verification outputs
- `.env.example`

The repository now contains draft generated versions of:

- `slides/pitch.pdf`
- `docs/architecture.pdf`
- `docs/security-assessment.pdf`

The team still needs to review and replace/customise them where required, and create:

- Final English pitch deck (the checked-in PDF is a draft; maximum 10-minute presentation)
- Recorded English demo video. `demo/demo.mp4` is currently a visual rehearsal from isolated screenshots, not final live-execution proof; re-record with narration from a running app (≤5 minutes because the roadmap flags an ambiguity).
- Final architecture and security PDFs if the route requires PDFs (drafts are present)
- GitHub repository under the team’s account
- `LICENSE` and `THIRD_PARTY_NOTICES`
- `evidence/run-log.jsonl` and `evidence/results.csv` from actual final evaluation runs
- Team names, institutions, roles, registration confirmation/team ID, and organizer correspondence

## Organizer questions to resolve

1. Authoritative Bangladesh registration and submission route/email.
2. Whether a self-built sandbox is sufficient for Topic E and whether any mandatory dataset/API exists.
3. AI coding-assistant and previously written-code disclosure rules.
4. Secure passport/enrolment submission process, if required.
5. Whether the demo video is optional or required as execution evidence.
6. Private repository, file-size, link-access, naming, and document-template rules.
7. Whether post-deadline fixes are permitted for finalists.
8. Finalist count, presentation/Q&A timing, and funded travel scope.

## Final release gate

Do not submit until the team can reproduce a clean-machine run, open every link in a reviewer account, show the consent gate and approval binding, explain that all records are synthetic, and reconcile every reported number with raw evidence. Preserve the final commit SHA, archive hash, submission timestamp, confirmation email, and the exact evidence files that were submitted.
