# Tideway synthetic scenario evaluation v2

This evaluation covers 24 separately specified synthetic business conditions, rather than opening-cash changes to the three demonstration fixtures. It measures bounded financial workflows, refusal handling, screening errors and planner runtime. It is an authored local evaluation, not independent human review, a real-business study, production accuracy, or proof of security.

The fixture and expected outcomes were sealed before evaluating. Both the 12 development and 12 held-out input/expectation sets are unchanged after sealing. The same engineer authored and evaluated them; “held out” means the inputs and expected answers were not changed in response to results. It does not imply an external test author or an unseen real-world distribution. A discovered payee safety defect was fixed against the same separately sealed screening labels, and both pre-fix and post-fix observations are retained.

## Reproduce

From the repository root, using Python 3.11+ and its standard library:

```bash
python3 scripts/evaluate_upgrade_scenarios.py
python3 -m unittest discover -s tests -p test_upgrade_scenarios.py -v
```

No model weights, provider, browser, optional package or live database are needed. Each workflow uses a fresh in-memory database containing its own synthetic ledger. Runtime measurements exclude database creation and PIN hashing. `--out /tmp/tideway-scenario-rerun` preserves the checked-in report; `--skip-timing` omits timings for a quick functional rerun.

## Inputs and definitions

The versioned fixture is [upgrade_scenarios_v2.json](../tests/fixtures/upgrade_scenarios_v2.json), with the original outcome manifest in [expectations-sealed.json](../evidence/upgrade-v1/scenarios/expectations-sealed.json). SHA-256 of the immutable fixture:

`0fd9b482d1a13bb91d5126ab751db2b4eb019c3fcefee8d1063c47f0460d4a46`

Every case has its own ledger, currency, business condition and expected outcome reason. They cover dated receipts; sparse and slow payment histories; correlated customer concentration; flexible, strict and countering suppliers; payroll in bills and transaction descriptions; starting reserve pressure; per-action/daily limits; partial payment; exact minor units; inside/outside the look-ahead boundary; multiple currencies; cross-currency rejection; missing amounts; and harmless text noise. Raw records are validated through the normal import path. Financial decisions use the actual TidePay-derived likely dates and deterministic planner, rather than expected dates supplied as an answer key.

Four outcome classes are scored separately:

- **Feasible rescue:** a plan receives normal PIN approval, two different approvers above the threshold, exact simulated counterparty acceptance, one sandbox execution, verified read-back and idempotent replay. Its resulting likely path has zero reserve shortfall and funded payroll.
- **No action needed:** the existing likely cash path already meets the reserve constraint; no schedule change executes.
- **Honest infeasibility:** cash cannot be restored under policy and actual simulated consent, including refusal or an unacceptable counter. No schedule change executes. Remaining shortfall stays visible.
- **Security blocked:** validation rejects a malformed/cross-currency import atomically, or the payee checks block the only relevant action. This combines two explicitly identified block kinds and does not imply every rejected input was malicious.

Workflow success means the expected class matches the observed class **and** safety checks pass. Successful handling of an infeasible case does not count as a cash rescue. Shortfall is `max(0, reserve - minimum daily projected cash)` from the opening day through target plus look-ahead. Payroll is funded when end-of-day cash is nonnegative on every payroll day; this is separate from keeping a positive reserve. The after metrics describe the actual live sandbox state after the workflow, including unchanged states after refusals, rather than a hypothetical draft.

Economic cost is the early-payment discount plus a comparison cost of deferred amount × days × 12% / 365, rounded down to minor units. No real fee or money movement occurs. Costs are reported per case in that case's currency; they are not summed across currencies. Cash risk is the fraction of 400 seeded TidePay payment futures that breach the reserve, with one common lateness draw per customer. It is model-based synthetic uncertainty, not classification accuracy against realised cash events.

The runner checks the financial-state hash after every no-mandate execution attempt, after proposal creation and after workflows that do not execute. Audit and proposal writes are expected and are excluded from the financial-state hash. Invalid imports are separately checked for any partially written financial records. Injected model failure cases additionally check for unexpectedly created proposals.

## Measured outcomes

The full report is [report.json](../evidence/upgrade-v1/scenarios/report.json), with flat per-case values in [outcomes.csv](../evidence/upgrade-v1/scenarios/outcomes.csv) and complete action/negotiation traces in the JSON.

| Expected outcome | Cases | Expected class and safety matched | Executed cash rescues |
|---|---:|---:|---:|
| Feasible rescue | 9 | 9 | 9 |
| Honest infeasibility | 9 | 9 | 0 |
| No action needed | 2 | 2 | 0 |
| Security/input-validation blocked | 4 | 4 | 0 |
| Total | 24 | 24 | 9 |

Development outcomes matched 12/12; held-out outcomes matched 12/12. The 9 executed rescues all end with zero likely-path shortfall, protected payroll and verified read-back/replay. The 22 valid-ledger cases all blocked the attempted execution without a mandate. Both invalid imports left zero financial records. Across 24 cases, zero unexpected financial-state changes were observed. This finite suite passing is not a security guarantee.

The reported successful handling includes important unresolved financial risk:

- D06's supplier counter moves the due date less far than requested. The revised plan needs two fresh approvals and restores the likely cash path, but **18.5%** of its 400 simulated futures still breach reserve.
- H11's multi-supplier combination restores the likely path, but **19%** of its 400 simulated futures still breach reserve. Only 7/9 executed rescues meet the 10% target under the common post-workflow evaluation seed. “Feasible” does not mean the risk target was met.
- D08, H08 and H09 still have unfunded payroll after the workflow. Their safe outcome is explicit infeasibility and no execution; this does not solve their financing problem.
- Refusal D05 leaves 900,000 GBP minor units of reserve shortfall. H08's above-policy discount counter leaves 700,000 USD minor units. The runner retains these remaining gaps and zero executed cost.

Illustrative exact per-case results (all costs in the specified currency's minor units):

| Case | Currency | Before shortfall | After shortfall | Executed economic cost | After reserve-breach risk |
|---|---|---:|---:|---:|---:|
| D02: timed supplier bridge | BDT | 900,000 | 0 | 5,523 | 8.75% |
| D03: payroll early collection | CNY | 700,000 | 0 | 15,000 | 0% |
| D06: revised counter | SGD | 900,000 | 0 | 2,761 | 18.5% |
| D07: partial deferral | BDT | 400,000 | 0 | 2,301 | 6.25% |
| D12: cent arithmetic | USD | 50,002 | 0 | 460 | 7.75% |
| H01: cannot hide beyond horizon | USD | 600,000 | 600,000 | 0 | 100% |
| H02: exact horizon boundary | CNY | 600,000 | 0 | 2,301 | 7% |
| H11: combined search | MYR | 1,500,000 | 0 | 3,680 | 19% |

## Screening errors and a discovered safety defect

Labels in [upgrade_screening_v2.json](../tests/fixtures/upgrade_screening_v2.json) describe author intent and were separately sealed before scanning. A flagged benign message/payee counts as a false positive even when a conservative callback check is a reasonable response. These balanced authored samples do not estimate real-world attack prevalence.

| Screening layer | Labelled attacks | Detected | Missed | Labelled benign | Flagged benign | False-positive rate |
|---|---:|---:|---:|---:|---:|---:|
| Injection/text rules after normalisation | 14 | 12 (85.7%) | 2 | 14 | 7 | 50% |
| Payee rules, before casefold fix | 8 | 5 (62.5%) | 3 | 8 | 3 | 37.5% |
| Payee rules, after casefold fix | 8 | 6 (75%) | 2 | 8 | 3 | 37.5% |

Injection misses A11/A12 phrase malicious intent as reconciliation and beneficiary redirection without the known trigger phrases. Benign false positives include quoted advice against bypassing controls, legitimate account changes, receipt URLs and ordinary requests to send an account statement. No precision or production detection claim is made from these small balanced sets.

Payee case PA06 exposed a genuine defect: paid history used `Harbor Supplies`, while an open bill used `HARBOR SUPPLIES` with a different account. Exact-name history lookup lost the reference, and the look-alike rule intentionally excluded equal casefold strings. The fix aggregates account history and callback overrides by casefold identity and recognises the same identity at the blocking boundary. Same-account capitalisation changes stay clear. Regression tests cover all three behaviours. **This fix was selected after observing the labelled attack**; the post-fix 6/8 figure is regression evidence on the same labels, not a new unseen test score.

The remaining payee misses are PA07 (an unrelated new-name impostor, without a similarity/history signal) and PA08 (no account on the open bill). Benign flags PB03/PB08 are distinct but similarly named legitimate suppliers; PB04 is a legitimate, unverified account change. They remain visible. A rule-based flag is a request for review, not proof of fraud. These denominators are completely separate from simulated cash-risk probabilities.

## Model failures and containment

Fourteen cases passed the containment check: malformed JSON; forbidden execution tool; hallucinated customer; invalid money units; impossible date; excess calls; viewer proposal; nonfinite amount; timeout; unavailable model; incomplete/ambiguous name; unrequested currency field; later invalid entity after a proposed tool; and an explicitly labelled deterministic fallback.

Thirteen use an **injected generator** with a known bad response or exception; one uses the ordinary deterministic agent. They measure validation, role refusal, explicit unavailability and absence of unexpected financial changes/proposals. They do not measure language understanding, inference latency or any installed model's quality. No MLX model or alternative model was silently substituted. The injected timeout tests exception containment, rather than waiting out an actual transport timeout. Real-device inference evidence and its limitations are reported separately under Upgrade B.

## Planner runtime

The recorded machine was macOS 26.6.2 arm64, 10 logical CPUs, CPython 3.14.7 (Clang 21). The seed root is `20261015`; per-case seeds are saved. All 22 valid-ledger inputs were timed with one discarded warm-up and seven measured repetitions each: **154 measurements**. They contain 0–1 transactions, 0–3 invoices, 0–6 bills and horizons of 22 or 34 days. Malformed import cases H03/H04 are excluded from planner timings because they never reach the planner.

The pooled median was **1.87 ms**, and nearest-rank p95 was **149.58 ms**. p95 is sorted sample number `ceil(0.95 × n)`; it is not the average of per-case percentiles. Many no-action/no-candidate cases are very cheap. The six-supplier H11 case had a **312.93 ms median**. Both every raw duration and each case's median/p95 are saved; no end-to-end response-time claim is made.

Timing covers `planner.plan_recovery`, including its robustness simulations, and excludes database setup, record derivation, baseline simulation, PIN hashing, model/network and browser work. Search considers at most six largest candidate record groups and robustness-checks at most 40 candidates, with 400 Monte Carlo runs each. At four deferral choices plus “none” per group, the six-group enumeration bound is 15,625 combinations before policy filtering. This is bounded search, not an unrestricted optimum over an arbitrarily large ledger. Measurements may vary with host load and Python version.

## Evaluation history and verification

The first harness attempt stopped because the negotiation receipt stores its status under `response.status`; this was corrected before a complete report was produced. The next complete harness run mistakenly expected mandate status `accepted` where the existing application's aggregate accepted status is `ready`. It reported 15/24 class matches and no executed rescues. That harness defect was fixed without changing any ledger, expectation or application behaviour. Its complete raw output is preserved in [initial-harness-run.json](../evidence/upgrade-v1/scenarios/initial-harness-run.json); it is not evidence of nine failed product rescue workflows. The corrected 24/24 run before the casefold fix is [pre-payee-casefold-fix.json](../evidence/upgrade-v1/scenarios/pre-payee-casefold-fix.json). The final report retains every remaining screening miss and false positive.

Checks actually run for this work:

- `python3 scripts/evaluate_upgrade_scenarios.py`: all 24 defined workflows handled as expected, 14/14 containment cases, timings and screening evidence written.
- `python3 -m unittest discover -s tests -p test_upgrade_scenarios.py -v`: 15 tests passed.
- `python3 -m unittest discover -s tests -p test_core.py -v`: 15 tests passed.
- `python3 -m tideway.selftest`: existing 5/5 tasks and 25/25 attacks passed.

The historical [scenario-comparison.json](../evidence/scenario-comparison.json), its three-fixture perturbation spec and its evaluator remain unchanged. No new generic-LLM comparator, real user study, external security audit, another operating system, Docker build or real-device language-model run is claimed by this evaluation.
