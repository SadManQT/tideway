"""Independent witnesses for the customer-history and payroll-date explanation."""
from copy import deepcopy
import unittest

from tideway.owner_view import customer_receipts


class CustomerReceiptEvidence(unittest.TestCase):
    def setUp(self):
        self.invoices = [dict(id='a', customer='A', status='confirmed', amount_minor=5000)]
        self.snapshot = dict(records=dict(invoices=self.invoices), state=dict(current_date='2026-10-20'))
        self.projection = dict(source_references=[dict(kind='invoice',id='a',date='2026-11-02',effect_minor=5000,certainty='expected')],excluded=[])

    def result(self, payroll='2026-10-31'):
        return customer_receipts(self.snapshot,self.projection,payroll)[0]

    def test_history_excludes_future_settlements_and_keeps_exact_late_count(self):
        for ident, paid, due in [('p1','2026-10-05','2026-10-01'),('p2','2026-10-10','2026-10-10'),('p3','2026-10-18','2026-10-15'),('future','2026-10-25','2026-10-01')]:
            self.invoices.append(dict(id=ident,customer='A',status='paid',amount_minor=100,paid_date=paid,due_date=due))
        r=self.result()
        self.assertEqual((r['settled_invoices'],r['late_settlements']),(3,2))
        self.assertFalse(r['limited_history'])

    def test_after_payroll_receipt_is_not_presented_as_payroll_funding(self):
        r=self.result()
        self.assertTrue(r['next_receipt']['after_payroll'])
        self.assertEqual(r['expected_by_payroll_minor'],0)
        self.assertEqual(r['expected_after_payroll_minor'],5000)

    def test_different_invoices_and_same_day_cash_are_counted_separately(self):
        self.invoices.append(dict(id='b',customer='A',status='overdue',amount_minor=2000))
        self.projection['source_references'].append(dict(kind='invoice',id='b',date='2026-10-31',effect_minor=2000,certainty='promised'))
        r=self.result()
        self.assertEqual(r['next_receipt']['id'],'b')
        self.assertFalse(r['next_receipt']['after_payroll'])
        self.assertEqual((r['expected_by_payroll_minor'],r['expected_after_payroll_minor']),(2000,5000))

    def test_agreement_uses_discounted_projection_amount_and_actual_event_date(self):
        self.projection['source_references'][0].update(kind='invoice_early_payment',date='2026-10-23',effect_minor=4900,certainty='agreed')
        r=self.result()
        self.assertEqual(r['next_receipt'],dict(id='a',date='2026-10-23',amount_minor=4900,basis='agreed',after_payroll=False))
        self.assertEqual(r['open_amount_minor'],5000)
        self.assertEqual(r['expected_by_payroll_minor'],4900)

    def test_after_horizon_receipt_is_still_explained_and_missing_payroll_is_unknown(self):
        self.projection['excluded']=self.projection.pop('source_references')
        self.projection['source_references']=[]
        r=self.result(None)
        self.assertEqual(r['next_receipt']['date'],'2026-11-02')
        self.assertIsNone(r['next_receipt']['after_payroll'])
        self.assertIsNone(r['expected_by_payroll_minor'])

    def test_past_expectation_and_cancelled_invoices_do_not_create_future_cash(self):
        self.projection['source_references'][0]['date']='2026-10-19'
        self.invoices.append(dict(id='cancelled',customer='B',status='cancelled',amount_minor=9000))
        r=self.result()
        self.assertIsNone(r['next_receipt'])
        self.assertEqual(len(customer_receipts(self.snapshot,self.projection,None)),1)

    def test_explanation_is_read_only(self):
        original=deepcopy((self.snapshot,self.projection))
        self.result()
        self.assertEqual((self.snapshot,self.projection),original)


if __name__ == '__main__':
    unittest.main()
