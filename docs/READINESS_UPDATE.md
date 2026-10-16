# Competition readiness follow-up - 16 October 2026

Tideway remains a synthetic Topic E prototype. No bank, real counterparty or payment
rail is connected. The team has deferred leader/roles/registration details and video.

## Improvements

| Review area | Implemented follow-up |
|---|---|
| Problem and financial workflow | Preserve the tested SME cash-flow loop; replace the guaranteed-payroll slogan with "Plan ahead for payroll" |
| Security | Contextual instruction screening, distinct account-review signals, missing-account blocking and clearer corrective warnings |
| AI | Actual Windows Qwen3 compatible-model inference, optional schema-constrained selections and accurate per-generation evidence |
| Interaction | Four-step, collapsible, role-aware first-use guidance with keyboard/mobile support; residual-risk warnings in proposals and approval dialogs |
| Evidence | Preserve initial failures, raw model outputs, measured outcomes, source hashes and isolated package verification |
| Maintainability | Separate guidance/schema modules, dynamic JS syntax checks and pinned CI covering Windows/macOS/Linux |

## Actual model verification

The optional compatible model is Unsloth's GGUF conversion of
Qwen3-4B-Instruct-2507 at Q4_K_M, served locally with pinned llama.cpp b11678.
It is not the released TideLM LoRA adapter. Provisioning verifies immutable URLs,
byte counts and SHA-256; model/runtime binaries are excluded from the package.

- `evidence/readiness-v2/model/qwen3-final-smoke.json`: 6/6 authored requests matched,
  including a result-aware rescue with two model selections.
- `evidence/readiness-v2/model/qwen3-final-expanded.json`: 12/12 additional authored
  requests matched, including credit, multilingual what-if, security, refusal and
  constrained rescue requests.
- Both runs issued zero mandates and performed zero financial executions. Model
  generations choose tools; deterministic tools calculate results and write replies.
- Initial compact-model failures (3/6, then 2/6, then 4/6 with schema) and the first
  4B run (5/6) remain preserved. Schema alone cannot establish semantic correctness.

These are authored synthetic smoke checks, not an independent model-quality
benchmark. Native Mac MLX/TideLM and receipt-model device verification remain
outstanding. Historical adapter scores do not transfer to this backend.

## Screening evidence

New development fixtures were sealed before tuning. Two separately authored sets
were evaluated after successive implementation freezes. First results were 4/10
attacks with 1/12 benign flagged, then 5/10 with 0/12. These first outcomes remain
unchanged under `evidence/readiness-v2/screening/`.

After disclosure, fixes and explicit compositional regression tests, the revised
sets detect 10/10 with 1/12 and 0/12 benign flagged. These later results are
regressions, not unseen scores. Development scores and definitions are recorded
under `evidence/screening-v3/`. The historical v2 fixture and raw reports remain
unchanged. Payment-detail review is separate from classifying an instruction attack.
Legitimate changed accounts can still require callback, and unrelated new-name
impostors cannot be identified reliably from the supplied fields.

## Financial limits and human approval

The existing 24-scenario report still has nine executed rescues; seven meet the
10% simulated reserve-risk target. Two retain 18.5% and 19% risk. The UI now shows
an explicit warning before approval when its measured plan risk exceeds the target.
No result was forced to improve these figures. An infeasible case remains explicit.

## Reproduce and inspect

Use `docs/SETUP_WINDOWS_MAC.md` for core and optional model startup. The selected
local model server requires a separate process; the deterministic core continues
to run without it. `TIDEWAY_LOCAL_STRUCTURED_PLANS=1` explicitly enables schema
support on a compatible local server. Unsupported schema requests fail closed.

The latest actual test counts and skip reasons are in `evidence/test-summary.json`
and `evidence/test-run.log`. Browser reports include first-use controls, no financial
mutation, role restrictions, residual-risk warnings and linked payment delay.
`dist/extraction-verification.json` records the fresh extracted-package run;
`dist/SHA256SUMS.txt` records the ZIP hash.

CI configuration is tracked and locally linted. GitHub-hosted jobs have not run,
because nothing was pushed. Native macOS helper/model execution, Docker, independent
SME feedback and an external penetration test were not performed here. Broad file
refactoring was avoided while changing financial workflows; targeted modules and
automated checks improve maintenance without rewriting the approval store.

## Team-controlled final steps

The confirmed five-person BUET roster is included. Leader, contribution roles,
eligibility, registration, submission route and reviewer access remain pending at
the team's request. Video recording remains deferred. This work does not establish
administrative readiness and has not pushed, deployed or submitted anything.
