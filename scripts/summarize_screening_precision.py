"""Reconcile paired screening observations without altering raw results."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_screening_v7 import score_records


def main():
    directory = ROOT / 'evidence/upgrade-v14'
    def read(name): return json.loads((directory / name).read_text(encoding='utf-8'))
    def rows(name):
        return [json.loads(line) for line in (directory / name / 'case-results.jsonl').read_text(encoding='utf-8').splitlines()]
    baseline, final, challenge = (read(name + '/report.json') for name in ('screening-baseline','screening-post-fix-known','screening-challenge'))
    old, known = rows('screening-baseline'), rows('screening-post-fix-known')
    by_id = {r['case']['id']:r for r in known}
    paired = [by_id[r['case']['id']] for r in old]
    if any(a['case'] != b['case'] for a,b in zip(old,paired)):
        raise ValueError('Paired texts or labels changed')
    identities = {(r['model_identity']['backend'],r['model_identity']['model']) for r in (baseline,final,challenge)}
    if len(identities) != 1:
        raise ValueError('Backend/model must match; do not compare native and compatible inference')
    for phase,report in [('screening-baseline',baseline),('screening-post-fix-known',final),('screening-challenge',challenge)]:
        raw = directory / phase / 'case-results.jsonl'
        if hashlib.sha256(raw.read_bytes()).hexdigest() != report['case_results_sha256']:
            raise ValueError('Raw observation bytes changed')
        if not report['classifier_unchanged'] or not report['fixture_unchanged']:
            raise ValueError('Classifier or fixture changed during an observation')
    if not final['source_unchanged'] or not challenge['source_unchanged']:
        raise ValueError('Final inference must bind to one complete source tree')
    m = challenge['metrics']
    targets = read('challenge-seal.json')['targets']
    acceptance = dict(
        attack_recall=m['combined_attack']['recall'] >= targets['combined_attack_recall_min'],
        warning_precision=m['combined_warning']['false_positive_rate'] <= targets['warning_false_positive_rate_max'],
        legitimate_changes=m['legitimate_payment_review']['recall'] >= targets['legitimate_payment_change_recall_min'])
    result = dict(model_identity=final['model_identity'],paired_cases=len(paired),
                  baseline_metrics=score_records(old),final_paired_metrics=score_records(paired),
                  disclosed_regression_cases=final['cases'],disclosed_regression_metrics=final['metrics'],
                  initial_known_metrics=read('screening-final-known/report.json')['metrics'],
                  challenge_cases=challenge['cases'],challenge_metrics=m,
                  first_challenge_targets=targets,first_challenge_checks=acceptance,
                  first_challenge_targets_met=all(acceptance.values()),
                  classifier_files=final['classifier_files'],source_tree_sha256=final['source_tree_sha256'],
                  source_aware_ai_authored=True,external_validation=False,human_retest_participants=0,
                  scope='Paired source-aware development and preserved first source-aware challenge on cached Windows compatible Qwen3. Post-fix known includes that now-disclosed challenge. Not native MLX, population accuracy, independent/blind assessment or a human usability result.')
    path = directory / 'screening-summary.json'
    path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(paired_cases=len(paired),baseline_fp=baseline['metrics']['combined_warning']['fp'],
                         final_paired_fp=result['final_paired_metrics']['combined_warning']['fp'],
                         challenge_attack=m['combined_attack'],challenge_warning=m['combined_warning'],
                         first_challenge_targets_met=result['first_challenge_targets_met']),indent=2))


if __name__ == '__main__':
    main()
