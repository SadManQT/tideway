"""Measure disclosed synthetic Owner view checks, without fabricating user feedback."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.verify_submission import source_digest
from tideway.owner_view import brief_html
from tideway.server import Application


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',default='evidence/owner-view-v12/owner-view.json')
    args = parser.parse_args()
    before = source_digest()[0]
    app = Application(':memory:')
    rows = []
    try:
        for business in app.store.list_businesses():
            bid = business['id']
            start = time.perf_counter()
            snapshot = app.store.snapshot(bid)
            base = app.owner_view.analyze(bid)
            report_ms = round((time.perf_counter()-start)*1000,2)
            start = time.perf_counter()
            comparison = app.owner_view.coach(bid,expected_snapshot=snapshot['snapshot_hash'])
            coach_ms = round((time.perf_counter()-start)*1000,2)
            expense = app.owner_view.analyze(bid,expense_minor=123456,expected_snapshot=snapshot['snapshot_hash'])
            html = brief_html(expense)
            checks = dict(same_source=base['snapshot_hash']==comparison['snapshot_hash']==expense['snapshot_hash'],
                          daily_cash_reconciles=all(d['opening_cash_minor']+d['inflow_minor']-d['outflow_minor']==d['closing_cash_minor'] for d in base['calendar']),
                          expense_cannot_increase_low_cash=expense['after_expense']['minimum_cash_minor']<=base['likely']['minimum_cash_minor'],
                          three_priority_previews=len(comparison['options'])==3,
                          brief_bound_to_source=expense['snapshot_hash'] in html and '<script' not in html,
                          ledger_unchanged=app.store.snapshot(bid)==snapshot,
                          no_proposal_or_execution=app.store.latest_plan(bid,base['target_date']) is None and not app.store.live_mandates(bid))
            rows.append(dict(business_id=bid,currency=business['currency'],checks=checks,report_ms=report_ms,coach_ms=coach_ms,
                             report=base,expense=expense,comparison=comparison))
        after = source_digest()[0]
        result = dict(run_at_utc=datetime.now(timezone.utc).isoformat(),source_tree_sha256=before,source_unchanged=before==after,
                      passed=before==after and all(all(r['checks'].values()) for r in rows),
                      businesses=len(rows),checks=sum(len(r['checks']) for r in rows),rows=rows,real_participants=0,
                      scope='Disclosed synthetic engineering checks and single-run timings, not human usability evidence, a load benchmark, real-model verification or a guarantee.')
        path = ROOT/args.out
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
        print(json.dumps({k:result[k] for k in ('passed','businesses','checks')}))
        return 0 if result['passed'] else 1
    finally:app.store.close()


if __name__=='__main__':raise SystemExit(main())
