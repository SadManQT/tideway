"""Compose the contest-upgrade handoff from current, versioned measured reports."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    read = lambda p: json.loads((ROOT / p).read_text(encoding='utf-8'))
    pay = read('evidence/upgrade-v1/tidepay/report.json')
    cases = read('evidence/upgrade-v1/scenarios/report.json')
    delay = read('evidence/upgrade-v1/payment-delay.json')
    test = read('evidence/test-summary.json')
    rows = ['# Contest upgrade implementation and evidence', '',
            'Local work for Topic E: cash-flow support, analysis and bounded financing comparisons. Synthetic only; no bank/payment integration, external publication or video recording.', '',
            '## A. Payment prediction', '',
            'The chronological audit fits global statistics and weights on matured training labels only. Separate validation is diagnostic; no calibration is fitted on final test data. Same final records for all baselines. Sum Brier is the mean of the sum of five squared class errors (range 0-2).', '',
            '| Model | Test invoices | MAE days | Log loss | Sum Brier |', '|---|---:|---:|---:|---:|']
    for key,value in pay['results'].items():
        rows.append(f"| {key} | {value['n']} | {value['mae_days']:.4f} | {value['log_loss']:.4f} | {value['brier_sum']:.4f} |")
    rows += ['', 'The historical prior used test-label statistics; raw historical evidence is preserved. The audit benchmark does not replace production weights. Federation remains one-process simulation with pooled scaling and illustrative predictable masks. Seven of forty SMEs have worse federated MAE than the heuristic; pooled MAE is slightly better overall. One synthetic cohort cannot establish real-business accuracy.', '',
             'Evidence: `evidence/upgrade-v1/tidepay/` (report, raw predictions, splits/hashes, reliability bins/plot, subgroup and uncertainty results). Method: `docs/TIDEPAY_EVALUATION_V2.md`.', '',
             '## B. Financial tools and conditional selection', '',
             'Whole-plan preflight validates roles/Advise mode, strict entity identity, money/currency/units, dates, hypothetical isolation and tool budgets before any proposing side effect. Rescue selection consumes deterministic forecast/risk/security outputs and records a bounded model follow-up, observable tool receipts and a code-written rationale. Fallback and injected transports are labelled explicitly.', '',
             'Current real-model smoke: unavailable, zero real requests, exit code 2. This Mac has no MLX, released adapter or cached base weights. Historical TideLM v2 scores do not measure the changed protocol. No large model download was attempted. Reproduction: `python3 scripts/smoke_reasoning.py`; model-enabled commands in `docs/MODEL_REASONING_V2.md`.', '',
             'Evidence: `evidence/upgrade-v1/model/`; guard tests are separate from model quality.', '', '## C. Distinct conditions, screening and performance', '']
    summary=cases['summary'];classes=summary['by_expected_outcome']
    rows += [f"{summary['workflow_successes']}/{summary['cases']} correct handling, with {summary['executed_rescues']} executed rescues, {classes['honest_infeasibility']['cases']} infeasible, {classes['no_action_needed']['cases']} no-action and {classes['security_blocked']['cases']} blocked. {summary['unauthorised_state_changes']} unexpected financial-state changes. Development/held-out specifications were sealed before evaluating.", '',
             'Only 7/9 rescues meet the 10% simulated-risk target; two remain at 18.5%/19%. Outcome handling is not rescue success or calibrated cash-risk accuracy.', '']
    for key,label in [('injection_screening','Injection'),('payee_screening','Payee')]:
        c=cases['screening'][key]['confusion']
        rows.append(f"- {label}: detected {c['true_positive']}/{c['malicious_denominator']} labelled attacks, missed {c['false_negative']}; flagged {c['false_positive']}/{c['benign_denominator']} benign cases.")
    timing=cases['planner_timing']
    rows += ['',f"Planner-only {timing['timed_samples']} timings: median {timing['median_ms']:.2f} ms, p95 {timing['p95_ms']:.2f} ms, {timing['repetitions_per_case']} repetitions and {timing['warmup_per_case_discarded']} discarded warm-up per case. Database, PIN, UI and model time excluded. Input sizes, seeds, search limits and slow per-case timings are saved.", '',
             'A case-only payee-account bypass was fixed after observation. Pre-fix labels and 5/8 detection remain preserved; the same labels give 6/8 afterward. Other misses and conservative false positives remain. No generic-LLM or general-spreadsheet comparison was run. See `docs/SCENARIO_EVALUATION_V2.md` and `evidence/upgrade-v1/scenarios/`.', '',
             '## D. Linked payment delay and fresh approval', '']
    c=delay['change']; b=c['before']['likely'];a=c['after']['likely']
    rows += [f"Bay Logistics collection changes from {c['old_date']} to {c['new_date']}. Likely minimum moves from BDT {b['minimum_cash_minor']/100:,.0f} to {a['minimum_cash_minor']/100:,.0f}; reserve shortfall from BDT {b['reserve_shortfall_minor']/100:,.0f} to {a['reserve_shortfall_minor']/100:,.0f}. Both states already have 100% breach risk. The chosen actions change from supplier deferral plus Nila early collection to early-payment offers for Bay and Nila.", '',
             'Owner membership/PIN, current snapshot, demo-only ledger and an atomic request receipt guard the mutation. Superseded promises cannot hide the delay; quarantine flags remain. Old authority is invalidated, fresh approvals and Bay counter-offer approval are required, and execution/read-back/retry is verified. What-if sliders remain read-only.', '',
             'Run `python3 scripts/demo_payment_delay.py`. For the live UI use a new unused database: `python3 run.py --db data/contest-rehearsal-01.sqlite3 --port 8788`. Then follow `docs/PAYMENT_DELAY_RUNBOOK.md`. Never reset/delete earlier databases or evidence.', '',
             '## Actual verification and handoff', '',
             f"Latest automated report: {test['tests_run']} tests run, {test['tests_run']-test['skipped']-test['failures']-test['errors']} passed, {test['skipped']} skipped, {test['failures']} failures and {test['errors']} errors; Python {test['python']} on {test['platform']}. See evidence/test-summary.json for the validated source digest. The stdlib-only baseline had four optional Pillow skips; the isolated QA environment enables those cases.", '',
             'Baseline: `evidence/upgrade-v1/baseline.json`; original self-test and historical observations preserved. Current self-test, unit, compile, browser, model availability and distribution reports describe their own actual environments. No Docker build, Windows run, external penetration test, SME user study or post-change real-model quality result is claimed.', '',
             'Regenerated deliverables: slides/pitch.pdf; docs/architecture.pdf; docs/security-assessment.pdf; docs/submission-notes.pdf; docs/Tideway_FinTechathon_2026_Roadmap.pdf. Final visual QA evidence and source/package hashes are kept with the release reports. Build the local ZIP with `python3 scripts/build_submission_package.py`, verify extracted bytes/startup with `python3 scripts/verify_package.py`, inspect dist/extraction-verification.json and dist/SHA256SUMS.txt.', '',
             '## Team-controlled outstanding steps', '',
             '- Install the exact released text adapter/base and verify real-model behavior on supported hardware; repeat receipt-model smoke separately.',
             '- Supply leader and actual contribution roles; verify eligibility, registration acknowledgement and current reviewer repository access.',
             '- Resolve submission-address conflict and latest organiser instructions; main-site dynamic notices were not fully verified.',
             '- Resolve video requirement or record only when separately instructed; recording remains deferred.',
             '- Review changes and choose final commit/version; no push, publication, organiser contact or submission was performed.', '',
             'Deadline from checked Appendix/CMU: 20 October 2026, 23:59 Beijing (21:59 Bangladesh, 08:59 PDT). `docs/CONTEST_SOURCES_CHECKED.md` links the sources and records their discrepancies. Technical preparation does not confirm administrative readiness.', '']
    (ROOT/'docs/CONTEST_UPGRADE_REPORT.md').write_text('\n'.join(rows),encoding='utf-8')
    print('Wrote docs/CONTEST_UPGRADE_REPORT.md from current evidence')

if __name__=='__main__':
    main()
