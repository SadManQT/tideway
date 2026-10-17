"""Check one frozen source tree, rebuild local deliverables and verify its ZIP.

No model downloads, cloud requests, publishing or submission. Chrome and Node 22+
are needed for the complete run; --checks-only needs Python and Node only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_submission import line_ending_issues, source_digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checks-only', action='store_true', help='Core tests, syntax and sandbox checks; no browser/PDF/package')
    parser.add_argument('--reuse-pdfs', action='store_true', help='Use existing visually reviewed PDFs; still repeat all other checks')
    parser.add_argument('--evidence-dir', default='evidence/remediation-v7', help='Current release evidence; historical observations are retained')
    args = parser.parse_args()
    issues = line_ending_issues()
    if issues:
        parser.exit(1, 'Source bytes violate .gitattributes LF policy: ' + ', '.join(issues) + '\nUse a fresh LF checkout before release; hashes are never normalized.\n')
    digest, _ = source_digest()
    env = os.environ.copy()
    env.update(OPENAI_API_KEY='', TIDEWAY_LOCAL_MODEL_URL='', TIDEWAY_LOCAL_TEXT_MODEL='',
               TIDEWAY_LOCAL_VISION_MODEL='', TIDEWAY_LOCAL_STRUCTURED_PLANS='', TIDEWAY_SEMANTIC_SCREENING='', PYTHON=sys.executable)
    out = ROOT / args.evidence_dir
    out.mkdir(parents=True, exist_ok=True)
    stages = []

    def run(name, command):
        if source_digest()[0] != digest:
            raise RuntimeError('Source changed during release checks; restart from the completed source tree')
        print(f'Running {name}', flush=True)
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        if source_digest()[0] != digest:
            raise RuntimeError(f'Source changed during {name}; results cannot attest to one source tree')
        stages.append(name)

    python = [sys.executable] + (['-S'] if sys.flags.no_site else [])
    run('Python compile', python + ['-m', 'compileall', '-q', 'run.py', 'tideway', 'scripts', 'tests'])
    run('JavaScript syntax', ['node', 'scripts/check_javascript.mjs'])
    run('Unit suite', python + ['scripts/verify_submission.py'])
    run('Sandbox task and attack scorecard', python + ['scripts/evaluate.py'])
    run('Distinct financial scenarios', python + ['scripts/evaluate_upgrade_scenarios.py', '--out', str(out / 'scenarios')])
    run('Payment delay and fresh approvals', python + ['scripts/demo_payment_delay.py', '--out', str(out / 'payment-delay.json')])
    if not args.checks_only:
        run('Browser desktop/mobile and delay', ['node', 'scripts/capture_screens.mjs', '--test-payment-delay'])
        run('Injected local-model integration', ['node', 'scripts/capture_screens.mjs', '--test-local-backend', '--out', str(out / 'browser-integration')])
        run('Current readiness index', python + ['scripts/build_readiness_summary.py', '--evidence-dir', args.evidence_dir])
        if not args.reuse_pdfs:
            run('PDF deliverables', python + ['scripts/build_submission_pdfs.py'])
        pdfs = ['slides/pitch.pdf', 'docs/architecture.pdf', 'docs/security-assessment.pdf',
                'docs/submission-notes.pdf', 'docs/Tideway_FinTechathon_2026_Roadmap.pdf']
        report = {'run_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  'source_tree_sha256': digest, 'stages_passed': stages,
                  'pdfs_rebuilt': not args.reuse_pdfs, 'visual_review_automated': False,
                  'pdf_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in pdfs},
                  'scope': 'Local synthetic checks; no hosted CI, model-quality rerun, SME participation or submission implied.'}
        (out / 'release-checks.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        run('Source ZIP', python + ['scripts/build_submission_package.py'])
        run('Fresh ZIP extraction, tests and server', python + ['scripts/verify_package.py'])
    print(f'Checks passed for source {digest}.', flush=True)
    if not args.checks_only:
        print('ZIP: dist/Tideway-submission.zip; extraction proof: dist/extraction-verification.json')
        print('Review PDF appearance before sharing. Team administration and video remain pending.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
