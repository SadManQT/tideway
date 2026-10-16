"""MOCK funding must disclose timing, unsupported eligibility and repayment gaps."""
import copy
import unittest
from tideway.financing import compare

class FinancingComparison(unittest.TestCase):
    def setUp(self):
        self.business = {'business_id':'test','currency':'USD','opening_date':'2026-10-01','opening_cash_minor':100_000}
        self.policy = {'reserve_floor_minor':20_000,'lookahead_days':14}
        self.records = {'invoices':[], 'bills':[], 'transactions':[
            {'id':'expense','date':'2026-10-05','description':'Operating expense','amount_minor':100_000,
             'type':'expense','currency':'USD','category':'Other'}]}

    def run_comparison(self, gap=20_000, as_of='2026-10-01'):
        return compare(self.business,self.policy,self.records,'2026-10-31',gap,'2026-10-05',as_of=as_of)

    def test_repayment_cannot_be_hidden_past_original_horizon(self):
        before = copy.deepcopy(self.records)
        rows = self.run_comparison()
        self.assertEqual(before,self.records)
        for row in rows:
            self.assertFalse(row['executable'])
            self.assertEqual(row['eligibility_status'],'unverified')
            self.assertEqual(row['repayment_minor'],row['principal_minor']+row['fee_minor'])
            self.assertGreater(row['repayment_projection']['reserve_shortfall_minor'],0)
            self.assertFalse(row['feasible'])

    def test_qualified_receivable_is_only_a_ledger_condition(self):
        self.records['invoices']=[{'id':'i','customer':'Client','status':'confirmed','amount_minor':300_000,
                'due_date':'2026-11-01','expected_collection_date':'2026-11-01','currency':'USD','risk_flags':[]}]
        row=self.run_comparison()[0]
        self.assertTrue(row['ledger_requirement_met'])
        self.assertEqual(row['eligibility_status'],'unverified')
        self.assertTrue(row['feasible'])
        self.assertTrue(row['eligibility_unknowns'])
        self.records['invoices'][0]['risk_flags']=['instruction_override']
        self.assertFalse(self.run_comparison()[0]['ledger_requirement_met'])

    def test_availability_uses_simulation_date_not_old_opening(self):
        row=self.run_comparison(as_of='2026-10-05')[0]
        self.assertEqual(row['available_date'],'2026-10-07')
        self.assertFalse(row['arrives_in_time'])

    def test_no_gap_never_recommends_borrowing(self):
        for row in self.run_comparison(gap=0):
            self.assertEqual(row['principal_minor'],0)
            self.assertEqual(row['comparison_status'],'not_needed')
            self.assertFalse(row['feasible'])

    def test_unsupported_repayment_horizon_is_explicit(self):
        rows=self.run_comparison(as_of='2027-09-29')
        for row in rows:
            self.assertFalse(row['feasible'])
            self.assertNotIn('repayment_projection',row)
            self.assertTrue(any('one-year' in reason for reason in row['reasons']))
