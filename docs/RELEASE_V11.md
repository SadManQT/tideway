# Decision lab upgrade - 18 October 2026

This local upgrade adds seven connected decision-support features to Tideway's Topic E SME Finance Copilot. It remains a synthetic sandbox with no bank, real lender or real counterparty connected. No submission, deployment or push is implied by this local work.

## Implemented

1. Bounded reverse stress finds the smallest single-customer extra delay and provides a one-day-less witness, with explicit customer coverage and search bounds.
2. Assumed agreement-performance stress tests five lateness rates using customer-correlated failure draws, independently of the original invoice random stream.
3. Recovery comparison exposes available bundle cost, risk, actions and consents, plus unconfirmed additional opening cash and fresh conditional validation draws.
4. Owner-authorised synthetic event monitoring supports delayed/received invoices, unexpected expenses and supplier refusal. Atomic event receipts invalidate stale authority, preserve owner instructions, and coordinate idempotent optional re-proposal. No automatic financial execution occurs.
5. Isolated judge challenges and portable private capsules recompute projection and seeded risk under matching engine hashes. A browser numeric round-trip bug was fixed; self-hashing is explicitly not an authorship signature.
6. The privacy inspector shares the actual initial cloud request builder, previews the relevant limited chat history, removes known names/accounts and email/possible-phone patterns, and makes no provider call or consent change. Unrecognised personal text can remain.
7. Two-business synthetic negotiation checks buyer and supplied supplier reserve/payroll paths. Compatible quotes create ordinary proposals; assumptions are displayed, hash-bound and rechecked at approval/execution, including retained counter-offer requests.

The UI, three new read-only model tools, strict schemas, authenticated HTTP routes, release automation, CI browser command and reviewer documentation are integrated. Set `TIDEWAY_DECISION_LAB=0` to disable the lab. See [the feature guide](DECISION_LAB.md).

## Verification

- Final Windows suite: 429 tests, zero failures/errors, one platform-specific skip.
- Final Python 3.11 Linux Docker suite: 429 tests, zero failures/errors, five optional-dependency skips; non-root HTTP workflow and persistence across container recreation passed.
- Actual compatible Qwen inference: 32/32 disclosed workflow requests handled and contained; 7/7 new lab smoke requests matched. These are known synthetic cases, not population accuracy.
- Three synthetic businesses pass all 18 lab engineering checks. The normal scorecards retain 30/30 sandbox cases, 24/24 scenario outcomes and 6/6 scripted behavior paths.
- Regression coverage includes browser JSON number round-trips, later existing payment promises, rejection of fractional money beyond two decimals, stale mandates, idempotent events, owner instructions and retained supplier constraints.

Current frozen-source outcomes are recorded in [the readiness index](READINESS_CURRENT.md), [unit summary](../evidence/test-summary.json), [lab evaluation](../evidence/upgrade-v11/decision-lab.json), [browser verification](../evidence/screens/browser-verification.json) and [release checks](../evidence/upgrade-v11/release-checks.json). The final ZIP is rebuilt and extraction-tested after PDF review; its manifest and extraction report identify the exact distributed bytes.

Actual compatible Qwen model runs preserve every attempt: the first two known-case regressions each handled 31/32, with all 32 contained. One selected an unnecessary read comparison; the other stopped safely after an unrequested hypothetical in a follow-up. Tool-selection instructions were clarified without weakening guards. The [final frozen-source regression](../evidence/upgrade-v11/model-regression-release/report.json) and [new lab smoke requests](../evidence/upgrade-v11/model-lab-release.json) are separate from these retained observations. All are disclosed synthetic regression/smoke cases, not blind accuracy or native adapter verification.

## Still outside this implementation

- Real SME participants remain zero. Scripted simulations do not become human evidence.
- Native Apple Silicon MLX/TideLM adapter and receipt-model device checks remain deferred until Mac access is available. Windows compatible Qwen inference is separate evidence.
- External security review and new genuinely unseen screening validation remain open. Known-case improvements do not erase first observations.
- H11's original unfunded reserve risk remains 11.78%; the additional-cash calculation remains conditional and unexecuted. Explicit acknowledgement does not reduce that risk.
- Team leader, contribution roles, registration/eligibility confirmation and related submission administration await the team. Video remains deferred by the team.
- Hosted CI for these local edits requires a later authorized push. Prior green CI applies to its recorded commit only.

No finite test suite establishes an error-free system or guarantees a contest result.

## Personal preparation separation

The team's guide and viva bank now live under `personal-prep/project-guide/` and open directly as a local HTML file. Product landing, sidebar, footer and Quick start links were removed. The old guide URLs and direct preparation paths return 404 for both anonymous and signed-in users. Guide assets and screenshots are excluded from submission ZIPs and Docker images. Current privacy checks and product browser evidence are recorded in `evidence/guide-isolation/`; older guide-related observations describe previous source versions.
