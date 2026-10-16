"""Ledger transitions must invalidate authority atomically, without weakening what-if."""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from tideway.domain import ValidationError
from tideway.server import Application
from scripts.demo_payment_delay import rehearse

B = 'shapla-services'


class DemoDelay(unittest.TestCase):
    def setUp(self):
        self.app = Application(':memory:')
        self.owner = self.app.store.verify_pin('nadia', '2468')
        self.addCleanup(self.app.store.close)

    def request(self, **changes):
        return {'business_id': B, 'invoice_id': 'inv-shapla-bay-oct', 'collection_date': '2026-11-15',
                'expected_snapshot': self.app.store.snapshot(B)['snapshot_hash'], 'request_id': 'test-delay-123',
                'pin': '2468', **changes}

    def apply(self, body, operator=None):
        return self.app.post('/api/demo/payment-delay', body, operator or self.owner, None)

    def test_linked_demo_reapproves_and_executes_once(self):
        report = rehearse()
        self.assertTrue(report['stale_execution_blocked'])
        self.assertTrue(report['execution_retry_same_receipt'])
        self.assertTrue(report['read_back_verified'])
        self.assertNotEqual(report['old_actions'], report['fresh_actions'])

    def test_retry_is_exact_and_different_body_is_refused(self):
        body = self.request()
        first = self.apply(body)
        retry = self.apply(body)
        self.assertTrue(retry['replayed'])
        self.assertEqual(first['audit_id'], retry['audit_id'])
        self.assertEqual(first['state_version'], retry['state_version'])
        with self.assertRaises(ValidationError):
            self.apply({**body, 'collection_date': '2026-11-16'})

    def test_stale_snapshot_and_invalid_inputs_do_not_mutate(self):
        original = self.app.store.snapshot(B)['snapshot_hash']
        for changes in ({'expected_snapshot': '0' * 64}, {'collection_date': '2026-11-03'},
                        {'collection_date': '2027-05-01'}, {'invoice_id': 'missing'}, {'pin': '9999'},
                        {'collection_date': '2026-02-30'}, {'expected_snapshot': []}, {'request_id': 'x'}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.apply(self.request(**changes))
            self.assertEqual(original, self.app.store.snapshot(B)['snapshot_hash'])

    def test_failure_during_audit_rolls_back_ledger_and_authority(self):
        original = self.app.store.snapshot(B)['snapshot_hash']
        with patch.object(self.app.store, '_audit', side_effect=RuntimeError('simulated write failure')):
            with self.assertRaises(RuntimeError):
                self.apply(self.request())
        self.assertEqual(original, self.app.store.snapshot(B)['snapshot_hash'])
        self.assertFalse(self.apply(self.request())['replayed'])

    def test_invalid_projection_horizon_cannot_commit_before_response_fails(self):
        original = self.app.store.snapshot(B)['snapshot_hash']
        with self.assertRaises(ValidationError):
            self.apply(self.request(target_date='2030-01-01'))
        self.assertEqual(original, self.app.store.snapshot(B)['snapshot_hash'])

    def test_date_change_preserves_quarantine_and_supersedes_old_promise(self):
        import json
        with self.app.store.connect() as db:
            row = db.execute('SELECT state_json FROM sandbox_state WHERE business_id=?', (B,)).fetchone()
            data = json.loads(row[0]); data['promises'] = {'inv-shapla-bay-oct': '2026-11-04'}
            db.execute('UPDATE sandbox_state SET state_json=? WHERE business_id=?', (json.dumps(data), B))
            db.execute('UPDATE invoices SET risk_flags=? WHERE business_id=? AND id=?',
                       (json.dumps(['hidden_characters']), B, 'inv-shapla-bay-oct'))
        result = self.apply(self.request())
        after = self.app.store.snapshot(B)
        invoice = next(r for r in after['records']['invoices'] if r['id'] == 'inv-shapla-bay-oct')
        self.assertIn('hidden_characters', invoice['risk_flags'])
        self.assertNotIn(invoice['id'], after['state']['promises'])
        self.assertEqual(result['superseded_promise'], '2026-11-04')

    def test_only_owner_member_can_change_demo_invoice(self):
        for who in ('imran', 'guest'):
            pin = '1357' if who == 'imran' else '0000'
            person = self.app.store.verify_pin(who, pin)
            with self.assertRaises(PermissionError):
                self.apply(self.request(pin=pin), person)
        with self.assertRaises(PermissionError):
            self.app.post('/api/demo/payment-delay', self.request(), None, None)

    def test_real_workspace_and_cross_tenant_invoice_are_refused(self):
        business, who = self.app.tideway.signup({'business_name': 'Private Ledger', 'currency': 'USD', 'country': 'US',
              'opening_cash': '1000', 'reserve_floor': '100', 'owner_name': 'Owner', 'username': 'owner-test', 'pin': '739162'})
        body = self.request(business_id=business['business_id'], expected_snapshot=self.app.store.snapshot(business['business_id'])['snapshot_hash'], pin='739162')
        with self.assertRaises(ValidationError):
            self.apply(body, who)
        with self.assertRaises(PermissionError):
            self.apply(self.request(pin='739162'), who)
        with self.assertRaises(ValidationError):
            self.apply(self.request(invoice_id='inv-lotus-harbor-oct'))

    def test_paused_agent_and_executed_invoice_cannot_be_bypassed(self):
        self.app.store.set_policy(B, {'agent_paused': True}, self.owner, 'operator:nadia')
        with self.assertRaises(ValidationError):
            self.apply(self.request())

    def test_stale_approval_is_refused_after_mutation(self):
        plan = self.app.tideway.propose(B, None, 'agent:test')
        self.apply(self.request())
        bundle = plan['bundles'][0]
        with self.assertRaises(ValidationError):
            self.app.store.approve(B, plan['plan_id'], bundle['bundle_id'], self.owner, '2468', 'operator:nadia')
        self.assertEqual(self.app.store.plan(B, plan['plan_id'])['status'], 'invalidated')

    def test_compare_and_swap_concurrent_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Application(Path(directory) / 'race.sqlite3')
            body = self.request(expected_snapshot=app.store.snapshot(B)['snapshot_hash'])
            def change(i):
                try:
                    return app.store.apply_demo_delay(B, body['invoice_id'], body['collection_date'], body['expected_snapshot'],
                                                     f'concurrent-{i}', self.owner, '2468', 'operator:nadia')
                except ValidationError:
                    return None
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(change, (1, 2)))
            self.assertEqual(sum(r is not None for r in results), 1)
            self.assertTrue(app.store.evidence(B)['hash_chain_valid'])
            app.store.close()

    def test_hypothetical_scenario_is_read_only(self):
        before = self.app.store.snapshot(B)['snapshot_hash']
        self.app.tideway.what_if(B, None, {'customer_delays': {'Bay Logistics': 20}})
        self.assertEqual(before, self.app.store.snapshot(B)['snapshot_hash'])
