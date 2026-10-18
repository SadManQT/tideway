"""Explicit illustrative conversion never changes settlement authority or source identities."""
import csv
import io
import unittest
from unittest.mock import patch
from tideway.currency_view import convert, display, question
from tideway.domain import ValidationError
from tideway.owner_view import brief_html
from tideway.server import Application


class CurrencyArithmetic(unittest.TestCase):
    def test_hand_calculated_amounts_and_symmetric_rounding(self):
        self.assertEqual(convert(10000,'USD','BDT'),1220000)
        self.assertEqual(convert(2280000,'BDT','USD'),18689)
        self.assertEqual(convert(100,'GBP','EUR'),115)
        self.assertEqual(convert(-100,'GBP','EUR'),-115)
        self.assertEqual(convert(10**14,'USD','IDR'),1630000000000000000)
        self.assertEqual(display(1,'BDT','USD'),'≈ USD < 0.01')

    def test_malformed_or_unknown_currency_cannot_be_used(self):
        for value in ('JPY','usd',None,True,{},'USD<script>'):
            with self.subTest(value=value),self.assertRaises(ValidationError):convert(100,'BDT',value)
        for value in (True,1.5,'100'):
            with self.subTest(value=value),self.assertRaises(ValidationError):convert(value,'USD','BDT')

    def test_questions_convert_only_explicit_money_and_leave_days_and_names(self):
        self.assertEqual(question('Can Nila Traders get USD 100 for 30 days at 5%?', 'USD','BDT'),
                         'Can Nila Traders get BDT 12,200 for 30 days at 5%?')
        self.assertEqual(question('USD 100 Consulting pays 20 days late on 2026-10-31','USD','BDT',['USD 100 Consulting']),
                         'USD 100 Consulting pays 20 days late on 2026-10-31')
        self.assertEqual(question('Nila Traders 20天 later','USD','BDT'),'Nila Traders 20天 later')
        self.assertEqual(question('Compare USD 100 and EUR 86.','USD','BDT'),'Compare BDT 12,200 and BDT 12,200.')
        self.assertEqual(question('Credit usd 100 for 30 days','USD','BDT'),'Credit BDT 12,200 for 30 days')
        details='Review INV-100 and account AC-2201-4471; owner12@example.com +8801712345678'
        self.assertEqual(question(details,'USD','BDT'),details)

    def test_foreign_view_does_not_silently_treat_bare_money_as_ledger_units(self):
        with self.assertRaisesRegex(ValidationError,'currency code'):question('Can I give 100 credit?','USD','BDT')
        self.assertEqual(question('Can I give 100 credit?','BDT','BDT'),'Can I give 100 credit?')
        for message in ('Credit USD 1.001','Credit -USD 1','Credit USD 999999999999999999999999999999'):
            with self.subTest(message=message),self.assertRaises(ValidationError):question(message,'USD','BDT')


class CurrencyReports(unittest.TestCase):
    def setUp(self):
        self.http=Application(':memory:');self.addCleanup(self.http.store.close)
        self.owner=self.http.store.verify_pin('nadia','2468')

    def test_decision_brief_and_bank_pack_use_selected_units_without_writing(self):
        before=self.http.store.snapshot('shapla-services')
        report=self.http.owner_view.analyze('shapla-services',expense_minor=1220000)
        html=brief_html(report,'USD')
        self.assertIn('Extra expense tested: ≈ USD 100',html)
        self.assertNotIn('BDT 12,200',html)
        bank,kind,_=self.http.export(dict(kind=['bank-pack'],business_id=['shapla-services'],display_currency=['USD']),self.owner)
        self.assertEqual(kind,'text/html');self.assertIn('view currency USD',bank)
        self.assertEqual(before,self.http.store.snapshot('shapla-services'))

    def test_selected_record_report_preserves_exact_ledger_provenance(self):
        text,_,_=self.http.export(dict(kind=['records'],business_id=['shapla-services'],display_currency=['USD']),self.owner)
        rows=list(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))))
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row['view_currency'],'USD')
            self.assertEqual(int(row['view_amount_minor']),convert(int(row['ledger_amount_minor']),row['ledger_currency'],'USD'))
        self.assertTrue(all(row['ledger_currency']=='BDT' for row in rows))

    def test_explicit_currency_is_normalized_before_model_and_agent_calls(self):
        body=dict(business_id='shapla-services',message='Credit for Nila Traders: USD 100 for 30 days',input_currency='USD')
        with patch.object(self.http.tidelm,'ask',return_value={'text':'test'}) as called:
            self.http.post('/api/copilot/ask',body,self.owner,None)
        self.assertIn('BDT 12,200',called.call_args.args[3])
        self.assertEqual(body['message'],'Credit for Nila Traders: USD 100 for 30 days')

    def test_selected_unit_privacy_preview_matches_actual_initial_cloud_payload(self):
        captured=[]
        def transport(payload,key):
            captured.append(payload)
            return {'output':[{'type':'message','content':[{'type':'output_text','text':'Review your forecast.'}]}]}
        self.http.agent.key='test-key';self.http.agent.transport=transport
        body=dict(business_id='shapla-services',message='Explain USD 100 credit for Nila Traders',input_currency='USD',history=[])
        preview=self.http.post('/api/lab/privacy',body,self.owner,None)
        self.assertFalse(captured)
        self.assertFalse(preview['consent_granted'])
        self.http.post('/api/chat',{**body,'consent':True},self.owner,None)
        self.assertEqual(preview['initial_payload'],captured[0])
        self.assertIn('BDT 12,200',str(preview['initial_payload']))


if __name__=='__main__':unittest.main()
