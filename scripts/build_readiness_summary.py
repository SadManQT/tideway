"""Publish a current evidence index without rewriting historical observations."""
from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', help='Current versioned release evidence directory')
    args = parser.parse_args(argv)
    tests = read('evidence/test-summary.json')
    model = read('evidence/readiness-v3/blind/model-first-observation.json')
    screening = read('evidence/readiness-v3/blind/screening-first-observation.json')
    pay = read('evidence/readiness-v3/tidepay/report.json')
    current = args.evidence_dir or ('evidence/currency-v13' if (ROOT / 'evidence/currency-v13/scenarios/report.json').is_file()
                                  else 'evidence/owner-view-v12' if (ROOT / 'evidence/owner-view-v12/scenarios/report.json').is_file()
                                  else 'evidence/upgrade-v11' if (ROOT / 'evidence/upgrade-v11/scenarios/report.json').is_file()
                                  else 'evidence/upgrade-v10' if (ROOT / 'evidence/upgrade-v10/scenarios/report.json').is_file()
                                  else 'evidence/release-v9' if (ROOT / 'evidence/release-v9/scenarios/report.json').is_file()
                                  else 'evidence/completion-v8' if (ROOT / 'evidence/completion-v8/scenarios/report.json').is_file()
                                  else 'evidence/remediation-v7' if (ROOT / 'evidence/remediation-v7/scenarios/report.json').is_file()
                                  else 'evidence/readiness-v5' if (ROOT / 'evidence/readiness-v5/scenarios/report.json').is_file()
                                  else 'evidence/readiness-v3')
    scenarios = read(current + '/scenarios/report.json')
    inj = screening['injection']['confusion']
    results = pay['results']
    cases = scenarios['summary']
    regression = read('evidence/readiness-v3/blind/model-post-fix-regression.json')
    python311 = read('evidence/readiness-v3/python311/test-summary.json')
    risk_met = sum(bool(row.get('risk_target_met')) for row in scenarios['rows'] if row['executed'])
    audit_path = ROOT / current / 'model-regression-release/report.json'
    if not audit_path.is_file():
        audit_path = ROOT / current / 'model-regression-final/report.json'
    if not audit_path.is_file():
        audit_path = ROOT / current / 'model-regression/report.json'
    if not audit_path.is_file():
        audit_path = ROOT / 'evidence/readiness-v5/model-regression/report.json'
    if not audit_path.is_file():
        audit_path = ROOT / 'evidence/independent-audit/model-regression/report.json'
    audit = json.loads(audit_path.read_text(encoding='utf-8')) if audit_path.is_file() else {}
    audit_result = (f"{audit['matched']['numerator']}/{audit['requests']} known requests handled; "
                    f"{audit['containment']['numerator']}/{audit['requests']} contained"
                    if audit.get('real_model_inference') else 'Not recorded')
    ci_path = current + '/hosted-ci-status.json'
    if not (ROOT / ci_path).is_file():
        ci_path = 'evidence/infrastructure-v5/hosted-ci-status.json'
    ci = read(ci_path)
    ci_status = f"Stored hosted run {ci.get('run_number', 'unknown')} concluded {ci.get('conclusion', ci.get('remote_baseline_conclusion', 'unknown'))} for commit {ci.get('remote_commit', 'unknown')}."
    doc = f'''# Current technical readiness

This is the current review index. Tideway remains a synthetic SME finance copilot:
cash forecasts, recovery proposals, human approval, simulated negotiation and
verifiable sandbox execution. No bank, real lender or payment rail is connected.
Historical upgrade and Windows reports describe earlier source versions.

## Implemented review fixes

- Above-target reserve risk requires fresh explicit acknowledgement from every
  approver, bound to the stored plan hash, bundle and exact probability/target.
  Consent is checked by the server and retained in audit, mandate and receipt.
  Missing, stale or altered acknowledgements cannot authorize execution.
- Mock financing compares arrival date, fee, APR convention, total repayment,
  unverified eligibility and the cash/payroll path through repayment. Borrowing
  cannot appear feasible merely because repayment falls beyond the first horizon.
- Exact shipped TidePay weights now have a separate frozen-artifact evaluation,
  exposed in the app with integrity and artifact-hash checks. Audited-model scores
  remain separate. The low-history limitation is visible.
- A new independent challenge set was sealed before first observation. Actual
  native macOS Qwen3 inference, full raw generations, misses and source seals are
  preserved. Disclosed credit/entity failures have separate deterministic
  regressions; their fixes do not replace the original blind result.
- Unflagged text is labelled "no flags", not trusted. Every extracted draft
  requires review; message text cannot grant payment authority.
- Cross-platform temporary-path handling is corrected. Release checks enforce LF
  source bytes, detect edits during verification, and bind tests, browser checks
  and the distributed ZIP to the same exact source digest.
- An anonymous, consent-aware study kit supports real SME validation. Its current
  participation count is zero; no feedback or usability score was invented.
- Independent follow-up audit: invalid signing keys are preserved and rejected;
  concurrent first starts publish one complete key. Malformed signatures fail
  validation, and `.env` now loads the documented structured-plan flag.
- Profiles, empirical fallback and illustrative backtests use only paid history
  available at the simulation date. Mock advances exclude already committed and
  not-yet-issued receivables. A Windows SQLite test handle leak is corrected.

## Measured evidence

| Check | Recorded result | Meaning and limit |
|---|---|---|
| Current unit run | {tests['tests_run']} run; {tests['failures']} failures; {tests['errors']} errors; {tests['skipped']} skipped | Python {tests['python']}, {tests['platform']}; injected outputs are not model quality |
| Additional standard-library run | {python311['tests_run']} run; {python311['failures']} failures; {python311['errors']} errors; {python311['skipped']} skipped | Python {python311['python']}; optional photo tests require Pillow; report records its own source hash |
| Financial scenarios | {cases['workflow_successes']}/{cases['cases']} expected workflows; {cases['executed_rescues']} rescues | {risk_met}/{cases['executed_rescues']} executed rescues meet the 10% simulated risk target |
| Shipped TidePay | {results['deployed']['n']:,} unseen synthetic invoices; MAE {results['deployed']['mae_days']:.4f} days | Heuristic {results['customer_history_heuristic']['mae_days']:.4f}; training-only prior {results['historical_training_prior']['mae_days']:.4f}; no weight changes |
| First actual Qwen3 challenge | {model['matched']['numerator']}/{model['requests']} correct; {model['containment']['numerator']}/{model['containment']['denominator']} contained | Four retained misses; no mandate, execution or financial-ledger mutation |
| Post-fix Qwen3 regression | {regression['matched']['numerator']}/{regression['requests']} known cases handled; {regression['safe_stop_handled']['numerator']}/{regression['safe_stop_handled']['denominator']} safe stops | One real-model pass after disclosed guard fixes; not a new blind score |
| Independent-audit Windows Qwen3 rerun | {audit_result} | Actual compatible inference on disclosed cases; retains every output; not blind |
| Historical first unseen instruction screening | {inj['true_positive']}/24 attacks detected; {inj['false_positive']}/24 benign flagged | Historical v3 observation; current v7 evidence is listed below; detection is advisory |
| SME user study | 0 participants; pending | Kit and analysis available; no real-user claim |

The prediction cohort contains 80 new synthetic SMEs, four seeds and 7,427
invoices after the shipped model's historical training period. No fresh labels
were used to fit weights or preprocessing. Runtime feature ordering is matched
and its difference from the training pipeline is disclosed. With no prior paid
history, shipped-model log loss is worse than the training-only prior. These are
synthetic-generator results, not real-world accuracy or a privacy guarantee.

The model first observation predates the disclosed guard fixes. It scored 23/24
tool/argument cases and 5/8 required safe stops, with median {model['median_seconds']:.3f}s.
The four misses were incomplete conditional recovery, amount inferred from a
day term, an unknown customer substituted with a ledger customer, and an
abbreviation silently expanded. The frozen sources and raw outputs remain
available for review. Later regression passes must never be called unseen scores.

## Run and check

From the project root on macOS (`python` on Windows):

```
python3 run.py
```

Open http://127.0.0.1:8787. Personal preparation material is not served or linked by the product.

```
python3 scripts/prepare_release.py --checks-only
python3 scripts/prepare_release.py
```

The complete command requires Node 22+ and Chrome/Edge, refreshes tests and
browser evidence, rebuilds five PDFs, builds the ZIP and tests its fresh extraction.
It does not download model weights or run a cloud provider. Inspect PDF appearance
before sharing. `--reuse-pdfs` keeps already reviewed PDFs while repeating checks.
Use a completed LF checkout: source edits during the run invalidate verification.

## Evidence map and provenance

- [Current test summary](../evidence/test-summary.json) and
  [raw test log](../evidence/test-run.log).
- [Current scenario report](../evidence/readiness-v3/scenarios/report.json),
  [linked delay receipt](../evidence/readiness-v3/payment-delay.json) and
  [browser workflow](../evidence/screens/browser-verification.json).
- [Exact shipped prediction evaluation](DEPLOYED_MODEL_EVALUATION.md), with
  raw invoices, shared test IDs, predictions, intervals and calibration bins.
- [Independent screening/model evaluation](BLIND_EVALUATION.md), source seals,
  native runtime provenance and every first-observation output.
- [Separate post-fix model regression](../evidence/readiness-v3/blind/model-post-fix-regression.json)
  and [Python 3.11 standard-library run](../evidence/readiness-v3/python311/test-summary.json).
- [Release stages and PDF hashes](../evidence/readiness-v3/release-checks.json).
  `dist/extraction-verification.json` and `dist/SHA256SUMS.txt` prove the actual
  distributed bytes, rather than referring to an earlier ZIP.
- [Independent judge/auditor report](INDEPENDENT_AUDIT.md), with reproduced
  defects, the contest requirement map, fixes and remaining validation gaps.
- [Current Windows actual-model regression](../evidence/independent-audit/model-regression/report.json).
- [User study protocol](USER_STUDY_KIT.md) and
  [pending participation status](../evidence/readiness-v3/user-study-status.json).

Current test source digest: `{tests['source_tree_sha256']}`.
Reports contain their own timestamps and hashes; older Windows/upgrade evidence
is historical and does not attest to the current checkout.

## Remaining gaps that code alone cannot close

Instruction screening has finite coverage. The v5 and v6 first observations below
are separate authored sets; they cannot be compared as an uncontrolled percentage
improvement. Optional semantic checks remain advisory and require a local model.
Real consented SME feedback, current MLX/TideLM planning and receipt-model evaluation,
external security testing and real-data calibration remain outstanding.
Partial settlements, reversals and real lender eligibility require separate
financial design before live integration. {ci_status}
That historical receipt does not attest to this local remediation; no push or
hosted run was performed for these changes.
See the explicit infrastructure status below for the separately tested Docker
build; no ordinary bridge or host port exposure is inferred from isolated tests.

The supplied five-person BUET roster is retained. Leader, contribution roles,
eligibility, registration, submission route, reviewer access and the deferred
video still need the team's actual information. This local package has not been
published, deployed, emailed or submitted. A numerical 9+ rating cannot honestly
be guaranteed from synthetic checks while these validation gaps remain.
'''
    for suffix in ('scenarios/report.json', 'payment-delay.json', 'release-checks.json'):
        doc = doc.replace('evidence/readiness-v3/' + suffix, current + '/' + suffix)
    docker_relative = current + '/docker/report.json'
    if not (ROOT / docker_relative).is_file():
        docker_relative = 'evidence/infrastructure-v5/docker/report.json'
    docker_path = ROOT / docker_relative
    docker = json.loads(docker_path.read_text(encoding='utf-8')) if docker_path.is_file() else {}
    infrastructure = ('PASS: frozen-source Linux image, isolated HTTP and persisted-state checks.'
                      if docker.get('passed') and docker.get('source_tree_sha256_after') == tests['source_tree_sha256']
                      else 'Not yet a passing current-source Docker run; inspect raw status.')
    doc += f"""

## Screening, planner and infrastructure follow-up

- Rules v5 first pass: 13/48 attacks detected, 7/48 benign flagged on a new,
  separately authored 96-message set. No misses were hidden. Its source snapshot,
  labels and first observation remain in `evidence/screening-v5/`.
- Optional local semantic screening adds a strict typed classification with one
  bounded generation, preserved errors and raw output, and explicit uncertainty.
  `TIDEWAY_SEMANTIC_SCREENING=1` enables it for Inbox messages and photo transcripts.
  It never authorizes a record or financial action; model-free rules remain available.
- [V6 independently authored first pass](../evidence/screening-v6/first-pass/first-pass-results.json)
  records actual local inference, rules/semantic/combined denominators, uncertainty,
  language/category results and runtime/source seals. It is not external validation.
- Planner candidates now mix cost, stressed cash and headroom, with stable customer
  draws and independent finalist validation. Counteroffer repair locks changed terms
  and requires fresh human approval and exact counterparty consent for every request.
- [Known D06/H11 risk follow-up](../evidence/readiness-v5/planner/report.json)
  separates risk estimates, sampling uncertainty and the allowed-action limit.
  An above-target business is escalated, not made successful by raising the target.
- Docker status: {infrastructure}
  [Raw Docker proof](../{docker_relative}).
  No native MLX, host-network reachability or external penetration test is implied.
- [Stored hosted CI status](../{ci_path}):
  {ci_status} No hosted run for the current remediation is claimed.
- [Implementation and verification report](REMEDIATION_V7.md).
"""
    if (ROOT / current / 'planner/report.json').is_file():
        doc = doc.replace('../evidence/readiness-v5/planner/report.json', f'../{current}/planner/report.json')
    doc += '\n## Owner constraints and v7 screening follow-up\n\n'
    doc += ('Owner discount ceilings, preferences and exclusions survive counter-offers and replans. '
            'The store rejects above-ceiling actions and widened successor constraints. '
            'Legacy plans without recorded instructions need a fresh owner-reviewed proposal. '
            'The UI distinguishes likely-path feasibility from simulated risk and preserves above-target precision.\n\n')
    for phase in ('baseline-development', 'improved-development', 'baseline-base-development',
                  'improved-base-development', 'improved-base-development-r2', 'improved-base-development-r3', 'fresh'):
        path = ROOT / 'evidence/screening-v7' / phase / 'report.json'
        if path.is_file():
            report = json.loads(path.read_text(encoding='utf-8'))
            metrics = report['metrics']
            doc += (f"- [{phase}](../evidence/screening-v7/{phase}/report.json): {report['cases']} cases; "
                    f"semantic attack recall {metrics['semantic_attack']['recall']:.1%}; "
                    f"combined attack recall {metrics['combined_attack']['recall']:.1%}; "
                    f"broader warning false-positive rate {metrics['combined_warning']['false_positive_rate']:.1%}; "
                    f"targets met: {report['targets_met']}. Backend: {report['model_identity']['backend']}; recorded model artifacts apply.\n")
        else:
            doc += f'- {phase}: no completed report; quality verification remains outstanding.\n'
    doc += ('\nDevelopment cases are disclosed v6 regressions. The fresh set is separately AI-authored, '
            'not an external or human-blind assessment. Native MLX classification cannot inherit '
            'Windows GGUF or historical TideLM planning scores. Every miss and raw output is retained. '
            'The native classifier uses the already cached base model without the planning LoRA; '
            'the planning backend is unchanged. Independent remediation review agents were unavailable '
            'because of an account usage limit; no independent review pass is claimed.\n')
    behavior_path = ROOT / current / 'behavior-checks.json'
    if behavior_path.is_file():
        behavior = json.loads(behavior_path.read_text(encoding='utf-8'))
        doc += ('\n## Behavior-driven sandbox checks\n\n'
                'AI-authored assumed behavior scenarios; real participants: 0. '
                'Backend workflow outcomes do not measure human task completion, satisfaction or SUS.\n\n'
                f"[{behavior['checks_passed']}/{behavior['checks_total']} checks passed](../{current}/behavior-checks.json): "
                'decline without changes, incomplete approval, owner discount limits, residual-risk consent, '
                'a known hostile supplier message and repeat execution. '
                'Human validation remains pending.\n')
    if (ROOT / 'docs/RELEASE_V9.md').is_file() and current == 'evidence/release-v9':
        doc = doc.replace('# Current technical readiness\n',
                          '# Current technical readiness\n\nCurrent local release: [fixes and verification scope](RELEASE_V9.md).\n', 1)
    if current == 'evidence/upgrade-v11':
        doc = doc.replace('# Current technical readiness\n', '# Current technical readiness\n\nCurrent local release: [decision support, event replanning and bilateral negotiation](RELEASE_V11.md). Previous screening and HTTP evidence: [v10](RELEASE_V10.md).\n', 1)
        doc += ('\n## Decision lab\n\nReverse stress includes one-day-less witnesses; agreement lateness rates are supplied assumptions; recovery comparisons use disjoint conditional funding draws. Owner-authorised synthetic events invalidate old mandates before optional re-proposal. Two-sided supplied synthetic ledgers are checked again at approval/execution and retained counter-offers. Private replay recomputes financial outputs, while privacy preview shares the initial cloud request builder. See [feature guide](DECISION_LAB.md) and [current evaluation](../evidence/upgrade-v11/decision-lab.json). These engineering checks do not replace real SME participation, native Mac verification or external review.\n')
    if current == 'evidence/owner-view-v12':
        doc = doc.replace('# Current technical readiness\n', '# Current technical readiness\n\nCurrent local release: [simple Owner view and goal-led recovery](RELEASE_V12.md). Prior model and decision-lab observations: [v11](RELEASE_V11.md).\n',1)
        doc += ('\n## Owner view and decision lab\n\nThe default Cash weather screen explains spending room under expected receipts and without unpaid customer receipts, tests an isolated one-off expense, links dated cash flows to records, and compares three recovery priorities. English/Bangla Owner labels, factual data checks and a private script-free decision brief reduce the steps needed to understand a proposal. Saved previews remain unapproved; owner limits, protected relationships and retained bilateral assumptions are enforced atomically. See [feature guide](OWNER_VIEW.md), [Owner evaluation](../evidence/owner-view-v12/owner-view.json) and [decision-lab checks](../evidence/owner-view-v12/decision-lab.json). No human usability improvement or new model-quality score is claimed. The earlier PDF deck is retained; this feature guide describes the new interface.\n')
    if current == 'evidence/currency-v13':
        doc = doc.replace('# Current technical readiness\n','# Current technical readiness\n\nCurrent local release: [consistent selected-currency inputs, text and reports](RELEASE_V13.md). Prior features: [Owner view](OWNER_VIEW.md) and [Decision lab](DECISION_LAB.md).\n',1)
        doc += ('\n## Currency consistency and related UI audit\n\nThe owner-selected currency now applies to editable financial amounts, generated narrative text, trace summaries, approval review, financial cards and human-readable reports. Exact rational conversion preserves the canonical ledger and unchanged rounded inputs. Explicit monetary question tokens are normalized before model/agent calls; ambiguous foreign-unit amounts require a currency code. Signed evidence and settlement documents retain original units. Per-operator preferences and unsaved drafts are preserved; source-aware Inbox review, scoped demo roles and pending lab inputs are corrected. See [conversion checks](../evidence/currency-v13/currency-checks.json), [browser evidence](../evidence/screens/browser-verification.json) and [release notes](RELEASE_V13.md). These are synthetic engineering checks, not live FX or new real-model quality/human usability results. Earlier PDFs and model/container observations retain their original scope.\n')
    if current == 'evidence/upgrade-v10':
        doc = doc.replace('# Current technical readiness\n',
                          '# Current technical readiness\n\nCurrent local release: [screening, cash-gap and HTTP fixes](RELEASE_V10.md).\n', 1)
        doc += '\n## Current Windows follow-up\n\n'
        for phase in ('screening-baseline', 'screening-revised', 'screening-challenge', 'screening-final-known'):
            path = ROOT / current / phase / 'report.json'
            if path.is_file():
                report = json.loads(path.read_text(encoding='utf-8'))
                m = report['metrics']
                doc += (f"- [{phase}](../{current}/{phase}/report.json): {report['cases']} cases; "
                        f"combined attack recall {m['combined_attack']['recall']:.1%}; ordinary-benign warning "
                        f"false-positive rate {m['combined_warning']['false_positive_rate']:.1%}; "
                        f"payment review recall {m['legitimate_payment_review']['recall']:.1%}.\n")
        doc += ('\nSame Windows compatible model for paired disclosed development; source-aware challenge, '
                'not external or independent blind validation. The challenge first observation is preserved; '
                'final-known is a post-fix regression over all disclosed cases. Native MLX planning and '
                'receipt-model verification are deferred until Mac access is available.\n')
        gap_path = ROOT / current / 'liquidity-gap.json'
        if gap_path.is_file():
            gap = json.loads(gap_path.read_text(encoding='utf-8'))
            doc += (f"\n[H11 cash-gap diagnostic](../{current}/liquidity-gap.json): original risk "
                    f"{gap['original']['probability']:.2%}; conditional on MYR "
                    f"{gap['liquidity_gap']['additional_cash_minor']/100:,.2f} extra cash at opening, "
                    f"fresh-draw risk {gap['conditional_cash_added']['probability']:.2%}. Funding is "
                    'unconfirmed and unexecuted. Baseline ledger, target and approval requirements are unchanged.\n')
        doc += ('\nHTTP regressions reject duplicate JSON keys and ambiguous body framing, tolerate malformed '
                'cookies as unauthenticated, share anonymous rate limits across invalid cookie values, and '
                'bound body reads by a total deadline. These are internal tests, not an external security audit.\n')
    (ROOT / 'docs/READINESS_CURRENT.md').write_bytes(doc.encode('utf-8'))
    print('Updated docs/READINESS_CURRENT.md from recorded evidence.')


if __name__ == '__main__':
    main()
