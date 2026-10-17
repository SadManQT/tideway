# Owner constraints, screening and final package refresh

Implementation plan and acceptance contract, recorded before screening tuning.

## Scope and journeys

- An owner sets a discount ceiling and ranking preference once. Counter-offers
  and successor plans must retain these instructions, exclusions and target.
- A human reviewing an above-target plan sees its exact remaining risk and gives
  fresh, server-bound consent. H11 is not required to fall below 10%.
- An Inbox operator distinguishes instruction attacks, account verification and
  unavailable classification. Every draft still needs confirmation.
- A reviewer receives a ZIP whose source, tests, browser checks and extracted
  startup attest to the same completed checkout.

No schema change is planned. Legacy plans without recorded owner constraints
remain readable but require an explicit fresh proposal before approval,
replacement or execution; the application must not invent missing consent.

## Screening scoring contract (predeclared)

The v6 historical observation used Windows GGUF Qwen3: semantic attack recall
35/48 (72.9%); broader warning false-positive rate 29/40 (72.5%). These are
different tasks and denominators. Previously observed v6 cases are development
and disclosed regression data, never a new blind set.

Engineering targets: semantic attack recall at least 80%, combined attack recall
at least 90%, broader warning false-positive rate at most 35%, and detection of
all explicitly labelled legitimate account changes. These are acceptance targets,
not promised results. Report any missed target without tuning on fresh failures.

A separately authored, sealed v7 set will be evaluated once after classifier
freeze. Its author must not inspect detector code, old cases or outputs. It is
AI-authored synthetic validation, not external or human-independent validation.
Record exact model identity; native MLX is not the historical Windows GGUF
backend and cannot inherit its scores.

Report rules-only, semantic-only and combined attack confusion matrices;
warning detection uses attacks plus legitimate payment-detail changes as its
positive class. Semantic uncertainty/error counts as no confirmed attack and
remains a warning. Report failure/uncertainty rate and latency separately.
Universal human draft confirmation is not an attack warning or a true positive.
Preserve raw bounded generations and all historical first observations.

## TDD evidence

The first constraint regression run executed 10 tests and produced 14 failing
subtests and one invalid-input error. The reported 1% to 1.5% counter and 1% to
3% replan defects reproduced. Additional failures cover store enforcement,
preference/exclusion propagation, legacy plans and malformed owner arguments.
RED checkpoint: `849052a`. Detailed logs and final results are indexed below
after verification; injected tests never establish model quality.

## Final results

Verification is in progress. Final counts, screening scores and extraction
status are recorded below only after their commands finish.

## Root causes and changes

1. `accept_counter()` checked the policy ceiling without resolving the stored
   owner ceiling, and its recovery branch also used policy defaults.
   `constraints.py` resolves the stricter integer-basis-point ceiling and
   validates preferences. Both direct counter terms and repair planning use it.
   Above-cap terms are rejected without modifying the original authorization.
2. `replan_without()` omitted the original cap and preference and replaced the
   exclusion list. It now preserves instructions and unions exclusions. The
   store saves the resolved policy-effective ceiling, checks successor scope,
  target and constraints before atomically
   cancelling the parent, and records `supersedes` provenance. Approval and
   execution recheck constraints; mandates, receipts and audit retain them.
   Legacy plans without recorded instructions require a fresh reviewed proposal.
3. Rules confused ordinary bank holidays with destination changes and missed
   some explicit multilingual training contexts. Bounded context rules now
   distinguish these while continuing to scan active instructions outside quotes.
   The semantic prompt distinguishes attacks, current account changes, ordinary
   business requests and uncertainty. Only an empty native thinking template
   is tolerated; actual prose, malformed output, timeouts and over-budget output
   still fail to review, with the original raw output retained.
4. Actual native classification with the cached planning LoRA frequently emitted
   malformed JSON. Both failed development runs are retained. Native screening
   now reuses the already cached Qwen3 base weights without that planning LoRA.
   Planning/extraction behavior is unchanged, compatible local backends remain
   supported, and no model weights were downloaded. Base loading uses a local
   cache path and fails closed if it is unavailable. Classification does not
   inherit TideLM planning benchmark scores.
5. Above-target risk was rounded to whole percentages in the rescue notice.
   Display precision now preserves an excess above target, including floating
   point boundary cases; exact server-bound consent was already enforced and
   remains unchanged. Countered mandates now offer replan as well as counter
   acceptance, so an above-cap counter has a visible recovery path.

No database schema or destructive migration changed. Runtime remains standard
library only; MLX and photo/PDF tools remain optional.

## Verification map

- Owner constraints: `tests/test_owner_constraints.py`, including atomic rejection,
  all preferences, exact-cap approval/consent/execution, faulty producer checks,
  exclusions, provenance and conservative legacy handling.
- Risk: boundary rendering checks plus `tests/test_risk_acknowledgement.py` for
  each approver, stale/altered consent and signed receipt retention.
- Screening: context, strict schema, failure containment, cached-base selection
  and evaluator protocol tests. Injected outputs establish containment only.
- Browser: capped proposal, visible rejection of a 1.5% counter under a 1% cap,
  replan preserving preference/exclusions, no reused approval, full execution
  story, handbook and mobile checks.
- Planner follow-up: documented seeds 20261017, 50737 and 91729, 10,000 draws
  each; no target change or favorable-seed selection.
- Release: `prepare_release.py`, current readiness index, five regenerated PDFs,
  distributed manifest hashes, tests and HTTP startup from a fresh extraction
  without Git or optional site packages.

The reported old ZIP was absent from this checkout at initial inspection; no
261-test archive was available to inspect or replace. Earlier test, browser and
scorecard receipts are preserved under `evidence/history/pre-remediation-v7/`.

Independent remediation reviewers could not start because of an account usage
limit. The separately authored screening fixture was completed and sealed before
that limit. No independent code-review pass or external validation is claimed.

## Remaining limits

H11 remains approximately 11.78% simulated breach risk against a 10% target;
acknowledgement is an explicit decision, not target attainment or a guarantee.
Screening targets are engineering acceptance criteria on synthetic sets, not
population accuracy. Every failed run and missed target must remain visible.
Current changes have not been pushed, deployed, published or submitted. Stored
Windows, Docker and hosted-CI receipts refer to their own historical sources.
Real SME feedback, current native planning/receipt-model verification, external
security testing and team-controlled submission information remain outstanding.

The first unrestricted-browser development pass succeeded. A separate full-suite
preflight without localhost permission produced 11 port-binding errors; the
failed report is preserved as `restricted-preflight-test-summary.json` and
`restricted-preflight-test-run.log` in `evidence/remediation-v7/`. The final release
run uses localhost access and must pass rather than treating those errors as skips.

Scoring audit: early development reports retain the inherited mixed
`payment_review` metric, which includes malicious redirection cases. Acceptance
for legitimate account changes uses a separate benign-case denominator. The
original reports and generations are retained; `scoring-review.json` records
recomputed metrics under that explicit contract without rerunning inference.

Further development observation: the first revised base prompt returned composite
labels such as `attack|control_bypass`; strict parsing correctly treated them
as uncertain. Its completed 96-case run is retained. The next development round
uses complete valid JSON examples and preserves readable UTF-8 in the untrusted
data envelope. The latter has a failing-then-passing regression across Bangla,
Chinese, Hindi and Arabic. It does not weaken parsing or grant authority.

The instrumented pre-final standard-library run passed 346 tests with four
optional-photo skips and approximately 86.43% weighted runtime statement
coverage. It predates the final UTF-8 test/prompt revision and does not replace
the final source-bound suite. Raw coverage and its scope are retained.

The v3 development classifier recovered all 48 attacks and reduced ordinary
warning false positives to 1/40, but recognized only 1/8 legitimate payment
updates. Its target failure remains visible. A further disclosed development
round prioritizes review of proposed, conditional and future-dated payment
updates even when the author preserves callback and approval controls.

The first fresh preflight stopped before loading cases or starting inference:
the unchanged author seal used `sha256` rather than `fixture_sha256`. Both exact
hash field schemas are now verified, with a regression test. The fixture bytes
match the original author hash. No fresh outputs existed at the time of this
correction. The aborted release correctly rejected changed-source browser
results; its log and the preceding 347-test pass are preserved separately.

## Completed screening measurements

Historical Windows GGUF v6: semantic attack recall 35/48 (72.9%); broader warning false positives 29/40 (72.5%). The native rows below use the same disclosed v6 development set, but a different backend. Only base-to-base rows form a paired native comparison. Fresh evaluation is a separate AI-authored set, not external validation.

| Run | Semantic attack recall | Combined attack recall | Warning FP / ordinary benign | Legitimate payment updates | Uncertain / errors | Median / p95 ms |
|---|---|---|---|---|---|---|
| baseline-development | 0/48 (0.0%) | 7/48 (14.6%) | 40/40 (100.0%) | 0/8 | 96 / 96 | 3350 / 9247 |
| improved-development | 7/48 (14.6%) | 13/48 (27.1%) | 40/40 (100.0%) | 0/8 | 85 / 85 | 3047 / 6521 |
| baseline-base-development | 40/48 (83.3%) | 42/48 (87.5%) | 21/40 (52.5%) | 5/8 | 2 / 0 | 2297 / 7495 |
| improved-base-development | 0/48 (0.0%) | 7/48 (14.6%) | 18/40 (45.0%) | 3/8 | 67 / 67 | 2072 / 6738 |
| improved-base-development-r2 | 48/48 (100.0%) | 48/48 (100.0%) | 1/40 (2.5%) | 1/8 | 0 / 0 | 1481 / 2398 |
| improved-base-development-r3 | 48/48 (100.0%) | 48/48 (100.0%) | 1/40 (2.5%) | 8/8 | 0 / 0 | 1419 / 2051 |
| fresh | 23/24 (95.8%) | 23/24 (95.8%) | 5/16 (31.2%) | 8/8 | 0 / 0 | 1556 / 2374 |

Fresh confusion matrices (TP / FP / FN / TN):

| Task | TP | FP | FN | TN | Recall | Precision | FPR |
|---|---|---|---|---|---|---|---|
| pure_rules_attack | 3 | 2 | 21 | 22 | 12.5% | 60.0% | 8.3% |
| semantic_attack | 23 | 3 | 1 | 21 | 95.8% | 88.5% | 12.5% |
| combined_attack | 23 | 5 | 1 | 19 | 95.8% | 82.1% | 20.8% |
| combined_warning | 31 | 5 | 1 | 11 | 96.9% | 86.1% | 31.2% |
| legitimate_payment_review | 8 | 0 | 0 | 16 | 100.0% | 100.0% | 0.0% |

Fresh acceptance targets met: **True**. No prompt/rule tuning followed fresh observation. The raw report records exact source, fixture, model-weight hashes and outputs. Attack detection and broader verification warnings use different positive classes; universal human draft confirmation is excluded. Small synthetic denominators are not population accuracy. Latency is descriptive on this local machine with other release checks running.


Full metrics, language/category breakdowns, raw bounded outputs, strict-schema failures, original source stamps and model identities remain in each run directory. `scoring-review.json` records denominator corrections without overwriting earlier reports. `native-runtime.json` records installed MLX/software versions, greedy generation configuration and cached snapshot hashes.


Fresh remaining weaknesses: one Hindi exfiltration attack was labelled benign.
Three reported/rejected attack quotations (English, Spanish, French) were
semantic false positives. Two negated bypass messages (English, Bangla) retained
independent rule warnings despite benign semantic labels. Those warnings were
not suppressed to improve scores. The broader-warning negative denominator is
16 ordinary benign messages, excluding eight legitimate payment updates that
require verification; semantic attack false positives use all 24 benign cases.
The observed median/p95 were approximately 1.556/2.374 seconds, with concurrent
local release checks; this is not a controlled performance comparison.
