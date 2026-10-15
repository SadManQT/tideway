# Tideway contest upgrade: implementation master prompt

Paste the prompt below into a coding agent with terminal and editing access to a fresh clone of https://github.com/ramim167/Probaho.git. The repository retains the old Probaho name; the current product is Tideway. Work from the latest main and inspect its actual state before changing anything.

---

You are the implementation and verification engineer for Tideway. Improve this existing repository into a stronger, reproducible FinTechathon entry. Make and test the changes directly. Complete the work, rather than returning only a plan or suggestions. Do not claim perfection, a guaranteed win, or successful checks that you did not actually run.

## 1. Contest context and authority

- Competition: 2026 Shenzhen International FinTech Competition (FinTechathon), International Track.
- Theme: AI as a Financial Participant.
- Our selected topic: E, SME Finance Copilot: financing-option matching, cash-flow management/alerts, business financial analysis.
- Published rubric: task completion 40%, security/compliance 30%, innovation/interaction 30%.
- Published deadline: 20 October 2026, 23:59 Beijing time, which is 21:59 Bangladesh time. Verify any newer organiser instruction.
- English is the official submission language. Keep the product's tested multilingual capabilities.
- Non-on-chain sandbox evidence is accepted. This project uses synthetic businesses, simulated counterparties and no real money. Do not introduce real banking/payment execution.
- Required submission context includes technical documentation, a presentation within 10 minutes, source/README/deployment instructions/tests, security assessment and execution evidence. The rules mention video both as optional and under execution evidence. The team has explicitly deferred video recording: prepare and test the live demonstration and update its script, but do not record a video now. Disclose that remaining submission item.

Verify the current primary sources before implementation. Treat repository research notes as secondary summaries:

1. Competition rules PDF: https://www.its.ac.id/international/wp-content/uploads/sites/66/2026/10/PBCSF-Appendix-2-Problem-Description-and-Competition-Rules-for-International-Track.pdf
2. IEEE track instructions: https://www.ieee-cis-singapore.org/2026-fintechathon
3. CMU announcement: https://ird.oou.cmu.ac.th/2026-shenzhen-international-fintech-competition/
4. Main site: https://fintechathon.g-ican.com/#/en

Registration/submission email instructions differ between the published sources. Do not choose on the team's behalf, send emails, submit materials or invent organiser approval. Record unresolved administrative questions separately from technical completion.

## 2. Read the repository context first

Read applicable AGENTS.md instructions, then these files and the actual code they describe:

- README.md
- docs/Tideway_FinTechathon_2026_Roadmap.pdf and its editable source, docs/roadmap/Tideway_FinTechathon_2026_Roadmap.html
- docs/PROJECT_BRIEF.md, as historical intent only. Some referenced paths and rename tasks are obsolete; do not repeat completed work or remove multilingual support because of its earlier wording.
- docs/SUBMISSION_NOTES.md and docs/SUBMISSION_CHECKLIST.md
- docs/TECHNICAL_DOCUMENTATION.md and docs/SECURITY_SELF_ASSESSMENT.md
- docs/MODEL_CARD.md, THIRD_PARTY_NOTICES and licenses/
- docs/EVALUATION_PLAN.md, docs/DEMO_SCRIPT.md, docs/PITCH_SCRIPT.md and docs/SETUP_WINDOWS_MAC.md
- evidence/ml/, evidence/scenario-comparison.json, evidence/test-summary.json and browser evidence
- tideway/ml/, analytics.py, projection.py, planner.py, agent.py, copilot.py, service.py, store.py, security.py, tidelm.py, local_model.py, vision.py and server.py
- web/app.js, web/index.html, web/styles.css, web/guide.html, web/guide.js and tests/

Inspect fresh-clone reproducibility: ignored local files, model caches, .env, submission-team.json and dist/ may not exist. Do not assume that the developer's workstation state is part of Git.

Confirmed public team information:

- Team: The Last BrainCell
- Institution for all five members: Bangladesh University of Engineering and Technology (BUET)
- Nafis Mohtasim Ramim
- Shaharia Rahman Santo
- Md. Atik Khan
- Md. Ashraf Hossain Chowdhury
- Khandaker Shadman Sakib Siddiquee

Leader and contribution roles will be supplied later. Do not invent them, nationality, eligibility, registration or signatures. Make the supplied public roster reproducible from a tracked, non-secret source; keep identity documents, private contact details and credentials out of Git and distributable source archives.

## 3. Establish the baseline

Inspect Git status and current HEAD; preserve unrelated work. Run the existing setup checks and tests before changing behaviour. Record actual versions, counts, failures and optional-model availability. Fix genuine baseline failures without discarding tests.

Historical evidence to verify, not hardcode:

- An earlier offline suite had 97 passing tests and a 30-case sandbox scorecard.
- TidePay's simulated federated model reported MAE 7.03 days versus heuristic 7.34, and log loss 1.0361 versus 1.55 on 3,452 synthetic test invoices. The overall MAE improvement is modest.
- The existing product comparison contains 20 opening-cash perturbations of three fixtures; feasibility was 10/20 for one fixed deferral rule and 12/20 for Tideway. These are not 20 independent held-out businesses.
- The core rescue run is largely an orchestrated sequence. Optional TideLM can choose typed tools. Do not describe every deterministic step as LLM reasoning.
- Existing what-if scenarios are read-only and do not automatically change the live ledger, proposal or approval state.

## 4. Upgrade A: measurable, honest TidePay prediction evidence

Reproduce the evaluation with leakage-free chronological splits and fair baselines. Audit feature availability, scaling, class priors and baseline statistics. Fit all such statistics on training data only; audit whether any baseline MAE uses test-label statistics. Keep a separate validation set if fitting calibration or tuning thresholds. Never fit calibration on the final test set.

Report appropriate metrics with definitions and denominators:

- MAE in days for predicted expected lateness.
- Multiclass log loss and multiclass Brier score for the lateness buckets; state the Brier normalisation convention.
- A calibration/reliability plot for a defined event such as payment more than seven days late, with sample counts and documented binning.
- Bucket/class balance, sample sizes and per-business/subgroup results. Explain uncertainty and small subgroup sizes; use suitable intervals where supported.
- The same held-out records for prior/heuristic/local-only/simulated-federated comparisons. Preserve unfavourable results and tradeoffs.

Save reproducible scripts/configuration, seeds, raw outputs or sufficient per-example predictions, dataset/split hashes, machine information, JSON/CSV reports and readable plots. Show a concise, evidence-linked summary in the app/deck where useful. Do not promise that calibration or a more complex model will improve every metric.

TidePay's current federation is a single-process FedAvg simulation with illustrative, predictable masks and pooled scaling. Preserve that disclosure. A deployed cryptographic privacy guarantee is outside this task.

## 5. Upgrade B: demonstrable financial reasoning and tool selection

Build on the existing tool/agent architecture. Demonstrate an actual installed model understanding different financial requests, selecting relevant allow-listed tools, consuming their results, explaining risk using those results and producing a bounded rescue proposal when warranted.

- Make decisions conditional on observed state; do not relabel a fixed animation as model-selected reasoning.
- Present an observable tool/action trace, evidence and a brief decision rationale. Do not fabricate hidden reasoning or a model transcript.
- Keep all money calculations, projections, feasibility checks and risk calculations in deterministic tools.
- Validate tool names, argument shapes, units, currency, dates, names and role permissions before tools run. Bound call counts, iterations, timeouts and output sizes.
- Handle no-gap, no-safe-plan, ambiguity, invalid JSON, hallucinated entities, unavailable model, timeout and forbidden-tool requests clearly.
- The model must never approve, sign a mandate, execute money actions, run SQL/shell, fetch arbitrary URLs or bypass human confirmation. Preserve maker-checker, dual approval, mandates, idempotency, kill switch and the circuit breaker.
- Retain an explicitly labelled deterministic fallback. It must not masquerade as TideLM inference.
- Support Apple Silicon MLX and the existing opt-in local-compatible backend on Windows/macOS. Preserve loopback restrictions and redirect blocking. An arbitrary local model is unbenchmarked and must not inherit the released TideLM v2 scores.

Run real-model smoke tests on hardware actually available. Record model/adapter identity and results separately from injected-output tests. If hardware or weights are unavailable, complete independent work, provide exact reproduction commands, and mark device verification outstanding. Never fabricate a successful model run or silently switch a tested adapter for a different model.

## 6. Upgrade C: broader evaluation, false positives, performance and failures

Create a versioned, independently specified synthetic scenario suite beyond opening-cash variations. Cover at least 20 genuinely distinct business conditions, with development and held-out scenarios. Author expectations before evaluating, and do not tune the held-out cases to manufacture a perfect score.

Vary receivable timing, payment habits/concentration, supplier terms/refusals/counters, payroll/reserve pressure, policy limits, partial payments, timing near the look-ahead boundary, currencies and missing/noisy inputs. Include feasible rescues, no action needed, honest infeasibility and security-blocked situations. Separate those outcome classes when scoring.

Also measure:

- False positives on labelled benign messages/payee cases, with denominators, alongside detection/false-negative results on labelled attacks. Distinguish injection screening, payee fraud screening and cash-risk predictions.
- Planner wall-clock median and p95 with documented input sizes, seeds, repetitions/warm-up, search limits and machine details.
- Concrete AI failure cases and whether validation, clarification, fallback or refusal contained them.
- Workflow success, remaining shortfall, payroll protection, plan cost, risk and unauthorised state changes using precise definitions.

Keep the existing narrow baseline experiment as historical evidence. If adding comparators, use the same data, information and policy constraints and state what each comparator represents. Do not call a simple rule all spreadsheets, or claim a generic-LLM comparison without running it. Tests with fake transports are not real-model quality measurements.

Add meaningful regression/security tests for discovered failure modes. Preserve the existing safety suite and report every actual failure. A passing finite suite is not proof of security.

## 7. Upgrade D: a memorable linked payment-delay demonstration

Implement a repeatable live sequence:

1. Show the original synthetic customer's payment timing, cash forecast, risk and rescue proposal.
2. Obtain an approval through the normal role/PIN/dual-approval workflow.
3. Explicitly apply a controlled payment-delay change to the synthetic demo ledger through the application's validated mutation path.
4. Recompute forecasts and risk, invalidate the stale proposal/approval/mandate and block attempted execution using the previous authority.
5. Create and explain a fresh rescue proposal from the changed state, obtain fresh human approval and simulated counterparty consent, then execute once and verify read-back.

Preserve read-only what-if behaviour. A hypothetical forecast or proposal must be visibly non-executable. Applying a demo change must be a separate, explicit, authorised operation, restricted to synthetic demo data, audited and snapshot/version aware. Never silently mutate records or bypass approval in order to make the demo smoother.

Make before/after changes easy to understand: payment date, projected cash minimum, reserve shortfall, risk, selected actions and why fresh approval is necessary. Values must come from actual calculations. Use a real fixture where the delay changes the financial decision; do not fake a result or force the planner to return a preferred answer.

Provide a repeatable fresh-database/reset route that preserves security controls, handles retries and does not delete unrelated databases or erase evidence. Test stale approvals, concurrent/repeated actions, cross-tenant access and failure during the transition. Update the live demo and pitch scripts, without recording a video.

## 8. Engineering and verification requirements

- Make focused extensions to the existing architecture and UI. Preserve unrelated features, English default copy, multilingual support, imports/exports and tenant isolation.
- Keep the core sandbox runnable using Python 3.11+ standard library. Isolate and document optional evaluation/model/browser dependencies. Avoid unnecessary large downloads or paid services.
- Keep /guide, /guide.html, /guide.css and /guide.js public while protected financial APIs still require authentication. A stale running server may need a restart; do not remove authentication to fix a public-page problem or kill unrelated processes.
- Verify desktop/mobile UI, new model-enabled and fallback paths, ordinary invalid input and graceful optional-model failure.
- Keep public roster metadata reproducible on a clean clone and make metrics/test counts derive from current evidence. Do not hardcode an old test count or inflate completion claims.
- Preserve historical raw evaluations. Write clearly versioned new evidence instead of overwriting old observations as if they had always passed.
- Update README, model card, technical/security/evaluation docs, checklist, guide/viva content where affected, demo/pitch scripts and roadmap source. Regenerate affected PDFs and visually inspect every changed page/slide for clipping, overlap, legibility and consistent numbers.

Run appropriate existing commands, adapting interpreter/browser paths to the OS:

    python scripts/check_setup.py
    python -m unittest discover -s tests -v
    python scripts/verify_submission.py
    python -m tideway.selftest
    python scripts/evaluate.py
    python scripts/evaluate_scenarios.py
    python -m compileall -q run.py tideway scripts tests
    node --check web/app.js
    node --check web/guide.js
    node scripts/capture_screens.mjs
    node scripts/capture_screens.mjs --test-local-backend --out tmp/local-backend-browser
    python scripts/build_submission_pdfs.py
    python scripts/build_submission_package.py

Add and run commands for the new evaluations and scenario demonstration. Check git diff --check, source/evidence consistency, ZIP contents and hashes, and fresh extraction startup without Git or private workstation files. Exclude .env/secrets, real customer data, identity documents, caches and unrelated files. Verify the final distributed source, not merely the original working directory. Do not claim a Docker build or another OS/device check unless you ran it.

## 9. Permissions, scope and final handoff

Proceed with authorised, reversible local edits and verification. Preserve unrelated changes. Do not stop after proposing a plan or repeatedly ask permission for normal implementation choices.

Do not push, force-push, rename the repository, deploy, publish, contact anyone, register, submit, spend money or record a video without a separate explicit instruction. Do not invent team roles, leader, registration, eligibility, user studies, production accuracy, partnerships or certifications.

Finish with:

1. What was implemented under each of the four upgrades and why it matters to Topic E/the rubric.
2. Exact measured results, denominators, fair baseline comparisons, limitations and evidence paths.
3. Tests/browser/device checks actually run, including unresolved failures or unverified hardware.
4. A short, reliable live-demo runbook showing the linked state transition and approval boundary.
5. Updated source/docs/PDFs and a verified local submission package.
6. A precise list of team-controlled outstanding steps, with technical readiness distinguished from registration/submission readiness.

Start by reading the repository context and establishing the baseline, then implement and verify the upgrades to completion.
