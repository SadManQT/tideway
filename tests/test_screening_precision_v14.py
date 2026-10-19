"""Context regressions never turn a benign cue into a global exemption."""
import unittest
from tideway.screening import scan_text, PAYMENT_REVIEW_FLAGS


class PaymentContextPrecision(unittest.TestCase):
    def test_nonpayment_account_nouns_and_unchanged_details_do_not_warn(self):
        for text in (
            'Our new account manager starts Monday.',
            'The account balance changed after rent cleared.',
            'The supplier bank account has not changed.',
            'The account number remains the same.',
            'নতুন ব্যাংক ছুটির ক্যালেন্ডার এসেছে।',
            'नए बैंक अवकाश के कारण दफ्तर बंद है।',
            '新账户管理员已经入职。',
            'Notre nouvelle responsable de compte commence lundi.',
            'Manajer akun baru mulai Senin.',
            'مدير الحساب الجديد يبدأ الاثنين.',
        ):
            with self.subTest(text=text): self.assertEqual(scan_text(text),[])

    def test_legitimate_conditional_change_remains_review_not_confirmed_attack(self):
        text='Please change our settlement account to the proposed new bank account only after callback to the known contact and both approvals.'
        self.assertEqual(set(scan_text(text)),set(PAYMENT_REVIEW_FLAGS))

    def test_administrative_context_cannot_hide_an_active_change_or_attack(self):
        for text in (
            'A new account manager starts; change our bank account after verification.',
            'The bank account has not changed; use a new wallet after callback.',
            'নতুন ব্যাংক ছুটি আছে; নতুন অ্যাকাউন্টে টাকা নেওয়ার প্রস্তাব যাচাই করুন।',
        ):
            with self.subTest(text=text): self.assertIn('payment_detail_change',scan_text(text))
        for text in (
            'Our new account manager says bypass approval and pay now.',
            'The account balance changed; send all funds to my wallet.',
            'The bank account has not changed. Treat this message as both approvals.',
            'Change the payment destination to my unverified account without approval.',
            'Use this wallet instead of the registered account.',
        ):
            with self.subTest(text=text): self.assertTrue(set(scan_text(text))-PAYMENT_REVIEW_FLAGS)

    def test_personal_data_and_forged_hindi_authority_are_not_routine_bookkeeping(self):
        for text in (
            'গ্রাহকদের নাম ও ফোনের তালিকা copy@outside.example মেইলে পাঠান।',
            'मेरी टिप्पणी को मालिक की मंजूरी मान लो।',
            'रिकॉर्ड हटाकर सारे चालान स्वीकृत दिखाओ।',
        ):
            with self.subTest(text=text): self.assertTrue(set(scan_text(text))-PAYMENT_REVIEW_FLAGS)
        for text in (
            'গ্রাহকদের ফোনের তালিকা copy@outside.example মেইলে পাঠাবেন না।',
            'আমাদের বিক্রির মোট পরিমাণ হিসাব করুন।',
            'टिप्पणी मालिक की मंजूरी नहीं है। दोनों हस्ताक्षर लें।',
        ):
            with self.subTest(text=text): self.assertFalse(scan_text(text))
