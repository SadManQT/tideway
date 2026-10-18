"""Independent cash witnesses and normal authority boundaries for the simple view."""
import unittest
from unittest.mock import patch

from tideway.domain import ValidationError
from tideway.owner_view import build_report, brief_html
from tideway.projection import project
from tideway.server import Application

BID = "shapla-services"


def example():
    business = dict(business_id="example", name="Example", currency="BDT", opening_date="2026-10-01", opening_cash_minor=10000)
    policy = dict(reserve_floor_minor=2000, lookahead_days=0)
    records = {
        "transactions": [dict(id="income", date="2026-10-02", type="income", category="Sales", amount_minor=1000, risk_flags=[])],
        "invoices": [dict(id="receipt", customer="Customer A", status="confirmed", expected_collection_date="2026-10-02", amount_minor=5000, risk_flags=[])],
        "bills": [dict(id="payroll", payee="Team", priority="payroll", status="open", due_date="2026-10-03", amount_minor=3000, risk_flags=[])]}
    return dict(business=business, policy=policy, records=records, snapshot_hash="a"*64,
                state=dict(current_date="2026-10-02", adjustments=[], promises={}))


def facts(s):
    return dict(target_date="2026-10-05", derived=dict(likely_dates={}, profiles=dict(customers={})),
                projections=dict(likely=project(s["business"], s["policy"], s["records"], "2026-10-05", s["state"]["adjustments"],
                                               promises=s["state"]["promises"], lookahead_days=s["policy"]["lookahead_days"])))


class CashExplanationTests(unittest.TestCase):
    def test_exact_spending_boundary_has_independent_one_minor_unit_failure(self):
        s = example()
        r = build_report(s, facts(s))
        # Hand calculation: 10,000 + 1,000 + 5,000 - 3,000 - 2,000 reserve.
        self.assertEqual(r["spending_room"]["likely"]["ceiling_minor"], 11000)
        self.assertEqual(r["spending_room"]["without_unpaid_customers"]["ceiling_minor"], 6000)
        self.assertEqual(build_report(s, facts(s), 11000)["after_expense"]["reserve_shortfall_minor"], 0)
        self.assertEqual(build_report(s, facts(s), 11001)["after_expense"]["reserve_shortfall_minor"], 1)
        self.assertEqual(build_report(s, facts(s), 11000)["after_expense"]["minimum_cash_minor"], 2000)

    def test_spending_ceiling_matches_exhaustive_small_ledger_search(self):
        for receipt in (0, 5, 20):
            s = example()
            s["business"]["opening_cash_minor"] = 10
            s["policy"]["reserve_floor_minor"] = 2
            s["records"]["transactions"][0]["amount_minor"] = 1
            s["records"]["invoices"][0]["amount_minor"] = receipt
            s["records"]["bills"][0]["amount_minor"] = 3
            safe = [n for n in range(40) if min(10+1+receipt-n, 10+1+receipt-3-n) >= 2]
            self.assertEqual(build_report(s, facts(s))["spending_room"]["likely"]["ceiling_minor"], max(safe))

    def test_expense_only_affects_its_date_and_later(self):
        s = example()
        r = build_report(s, facts(s), 11000, "2026-10-04")
        self.assertEqual(r["after_expense"]["minimum_cash_date"], "2026-10-04")
        self.assertEqual(r["after_expense"]["minimum_cash_minor"], 2000)
        self.assertEqual(r["payroll"]["next_amount_minor"], 3000)

    def test_earlier_future_shortfall_cannot_be_hidden_by_later_spending_date(self):
        s = example()
        s["records"]["transactions"][0]["type"] = "expense"
        s["records"]["transactions"][0]["amount_minor"] = 14000
        r = build_report(s, facts(s), expense_date="2026-10-04")
        self.assertEqual(r["spending_room"]["likely"]["reason"], "earlier_shortfall")
        self.assertEqual(r["spending_room"]["likely"]["ceiling_minor"], 0)

    def test_historical_shortfall_does_not_prevent_future_spending(self):
        s = example()
        s["records"]["transactions"] += [dict(id="old", date="2026-10-01", type="expense", category="Other", amount_minor=9500, risk_flags=[])]
        s["records"]["transactions"][0]["amount_minor"] = 30000
        self.assertGreater(build_report(s, facts(s))["spending_room"]["likely"]["ceiling_minor"], 0)
        self.assertEqual(facts(s)["projections"]["likely"]["first_breach_date"], "2026-10-01")

    def test_unpaid_early_agreement_is_removed_in_customer_absence_scenario(self):
        s = example()
        s["state"]["adjustments"] = [dict(kind="invoice_early_payment",invoice_id="receipt",face_minor=5000,amount_minor=4900,to_date="2026-10-02")]
        r = build_report(s, facts(s))
        self.assertEqual(r["spending_room"]["likely"]["ceiling_minor"], 10900)
        self.assertEqual(r["spending_room"]["without_unpaid_customers"]["ceiling_minor"], 6000)
        self.assertEqual(r["dependencies"][0]["impact_on_lowest_cash_minor"], 4900)
        self.assertTrue(any(x["basis"] == "unsettled_agreement" for d in r["calendar"] for x in d["sources"]))

    def test_cash_story_reconciles_and_links_the_actual_record(self):
        s = example()
        r = build_report(s, facts(s))
        for d in r["calendar"]:
            self.assertEqual(d["closing_cash_minor"], d["opening_cash_minor"]+d["inflow_minor"]-d["outflow_minor"])
            self.assertEqual(sum(x["effect_minor"] for x in d["sources"]), d["inflow_minor"]-d["outflow_minor"])
        p = next(x for d in r["calendar"] for x in d["sources"] if x["payroll"])
        self.assertEqual((p["id"],p["kind"],p["party"]), ("payroll","bill","Team"))

    def test_dependency_coverage_is_explicitly_limited_and_not_a_confidence_score(self):
        s = example()
        original = s["records"]["invoices"][0]
        s["records"]["invoices"] = [dict(original,id=f"i-{i}",customer=f"Customer {i:02d}") for i in range(12)]
        r = build_report(s, facts(s))
        self.assertEqual(r["dependency_coverage"], dict(customers_total=12,tested=10,complete=False))
        self.assertEqual(len(r["data_checks"]["customers_under_three_settlements"]),12)
        self.assertNotIn("confidence",r)

    def test_payroll_is_not_claimed_for_missing_records(self):
        s = example()
        s["records"]["bills"] = []
        r = build_report(s, facts(s))
        self.assertFalse(r["payroll"]["identified"])
        self.assertEqual(r["status"],"no_payroll_identified")
        s["records"] = dict(transactions=[],invoices=[],bills=[])
        self.assertEqual(build_report(s,facts(s))["status"],"no_records")

    def test_historical_horizon_and_bad_inputs_are_handled_without_fabricated_cash(self):
        s = example()
        s["state"]["current_date"] = "2026-10-10"
        r = build_report(s, facts(s))
        self.assertEqual(r["status"],"historical_horizon")
        self.assertIsNone(r["likely"]["minimum_cash_minor"])
        self.assertFalse(r["spending_room"]["likely"]["available"])
        with self.assertRaises(ValidationError):build_report(s,facts(s),1)
        s = example()
        for amount in (-1, True, .1, "100", None, 10**15):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):build_report(s,facts(s),amount)
        for date in (False,"2026-10-01","2026-10-06","not-a-date"):
            with self.subTest(date=date), self.assertRaises(ValidationError):build_report(s,facts(s),1,date)

    def test_brief_escapes_untrusted_text_and_has_no_active_or_remote_content(self):
        s = example()
        s["business"]["name"] = '<script>alert(1)</script>'
        s["records"]["invoices"][0]["customer"] = '<img src=x onerror="alert(1)">'
        r = build_report(s, facts(s), 100)
        html = brief_html(r)
        self.assertNotIn('<script',html)
        self.assertNotIn('<img',html)
        self.assertNotIn('https://',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('BDT 129',html)
        self.assertIn(r["snapshot_hash"],html)
        self.assertIn('Private business figures',html)


class RecoveryCoachTests(unittest.TestCase):
    def setUp(self):
        self.http = Application(":memory:")
        self.app,self.store,self.owner = self.http.tideway,self.http.store,self.http.owner_view
        self.addCleanup(self.store.close)

    def counts(self):
        with self.store.connect() as db:
            return tuple(db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in ("plans","approvals","mandates","executions","transactions","audit"))

    def preview(self, **kwargs):return self.owner.coach(BID,**kwargs)

    def save(self, r, request_id="coach-test-0001", **kwargs):
        o = next(x for x in r["options"] if x["status"] == "proposal_available")
        return self.owner.propose(BID,r["target_date"],r["criteria"]["max_discount_bps"],r["criteria"]["protected_counterparties"],o["priority"],o["option_id"],r["snapshot_hash"],request_id,"operator:nadia",**kwargs)

    def test_dashboard_expense_and_three_priority_previews_never_write(self):
        before, snapshot = self.counts(),self.store.snapshot(BID)
        d = self.app.dashboard(BID)
        r = self.owner.analyze(BID,expense_minor=10000)
        c = self.preview()
        self.assertEqual(len(c["options"]),3)
        self.assertEqual({x["priority"] for x in c["options"]},{"lowest_cost","fewest_asks","lowest_risk"})
        self.assertEqual(d["owner_view"]["snapshot_hash"],r["snapshot_hash"])
        self.assertFalse(r["proposal_counted_as_cash"])
        self.assertEqual(self.store.snapshot(BID),snapshot)
        self.assertEqual(self.counts(),before)

    def test_save_is_idempotent_and_always_a_fresh_unapproved_proposal(self):
        r = self.preview()
        p = self.save(r)
        before = self.counts()
        again = self.save(r)
        self.assertEqual(again["plan_id"],p["plan_id"])
        self.assertTrue(again["replayed"])
        self.assertEqual(self.counts(),before)
        self.assertEqual(p["status"],"pending")
        self.assertEqual(p["approvals"],[])
        self.assertEqual(self.store.live_mandates(BID),[])
        self.assertEqual(self.store.snapshot(BID)["snapshot_hash"],r["snapshot_hash"])

    def test_id_reuse_cannot_change_terms(self):
        self.save(self.preview())
        r = self.preview(cap=100)
        before = self.counts()
        with self.assertRaisesRegex(ValidationError,"different proposal terms"):self.save(r)
        self.assertEqual(self.counts(),before)

    def test_current_owner_cap_and_exclusions_survive_a_different_priority(self):
        parent = self.app.propose(BID,None,"agent:test",max_discount_bps=100,excluded=["Rahman Supplies"])
        r = self.preview()
        self.assertEqual(r["criteria"]["max_discount_bps"],100)
        self.assertIn("Rahman Supplies",r["criteria"]["protected_counterparties"])
        with self.assertRaises(ValidationError):self.preview(cap=101)
        p = self.save(r)
        self.assertEqual(p["owner_coach"]["source_plan_id"],parent["plan_id"])
        self.assertEqual(p["owner_constraints"]["max_discount_bps"],100)
        self.assertIn("Rahman Supplies",p["excluded_counterparties"])

    def test_malformed_or_foreign_counterparties_are_refused(self):
        for protected in (False,{},[[]],["Another business"],["Nila Traders"]*21):
            with self.subTest(protected=protected), self.assertRaises(ValidationError):self.preview(protected=protected)
        for cap in (True,-1,1.5,"100"):
            with self.subTest(cap=cap), self.assertRaises(ValidationError):self.preview(cap=cap)

    def test_stale_records_invalidate_analysis_and_preview_before_saving(self):
        r = self.preview()
        owner = self.store.verify_pin("nadia","2468")
        self.store.apply_lab_event(BID,dict(type="unexpected_expense",amount_minor=10000,date="2026-10-02"),r["target_date"],r["snapshot_hash"],"coach-ledger-event",owner,"2468","operator:nadia")
        before = self.counts()
        with self.assertRaises(ValidationError):self.save(r)
        with self.assertRaises(ValidationError):self.owner.analyze(BID,expected_snapshot=r["snapshot_hash"])
        self.assertEqual(self.counts(),before)

    def test_owner_instruction_race_is_checked_inside_the_plan_transaction(self):
        r = self.preview()
        actual = self.store.create_plan
        def intervene(*args,**kwargs):
            with patch.object(self.store,"create_plan",actual):
                self.app.propose(BID,None,"agent:other-owner")
            return actual(*args,**kwargs)
        with patch.object(self.store,"create_plan",intervene):
            with self.assertRaisesRegex(ValidationError,"instructions changed"):self.save(r)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM plans").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM metadata WHERE key LIKE 'owner-coach-request:%'").fetchone()[0],0)

    def test_read_only_can_run_during_pause_but_saving_obeys_kill_switch(self):
        owner = self.store.verify_pin("nadia","2468")
        self.store.set_policy(BID,{"agent_paused":True},owner,"operator:nadia")
        r = self.preview()
        with self.assertRaisesRegex(ValidationError,"paused"):self.save(r)

    def test_advise_mode_does_not_allow_coach_to_escalate_autonomy(self):
        owner = self.store.verify_pin("nadia","2468")
        self.store.set_policy(BID,{"autonomy_level":"advise"},owner,"operator:nadia")
        r = self.preview()
        with self.assertRaisesRegex(ValidationError,"advise"):self.save(r)

    def test_infeasible_preview_does_not_fabricate_a_savable_option(self):
        snapshot = self.store.snapshot(BID)
        snapshot["business"]["opening_cash_minor"] = 0
        snapshot["records"]["invoices"] = []
        snapshot["records"]["bills"] = [r for r in snapshot["records"]["bills"] if r["priority"]=="payroll"]
        with patch.object(self.store,"snapshot",return_value=snapshot):
            r = self.preview()
        self.assertTrue(all(x["status"]=="infeasible" for x in r["options"]))

    def test_no_action_ledger_yields_explanation_instead_of_fake_recovery(self):
        # A sufficiently funded clone checks the actual planner's no-action result.
        snapshot = self.store.snapshot(BID)
        snapshot["business"]["opening_cash_minor"] = 10**10
        with patch.object(self.store,"snapshot",return_value=snapshot):
            r = self.preview()
        self.assertTrue(all(x["status"] == "no_action_needed" for x in r["options"]))

    def test_saved_coach_proposal_uses_normal_dual_approval_and_consent(self):
        p = self.save(self.preview())
        b = next(x for x in p["bundles"] if x["feasible"])
        terms = self.store.risk_acknowledgement_terms(p,b)
        for identifier,pin in (("imran","1357"),("nadia","2468")):
            op = self.store.verify_pin(identifier,pin)
            result = self.store.approve(BID,p["plan_id"],b["bundle_id"],op,pin,"operator:"+identifier,
                                        risk_acknowledgement={"acknowledged":True,**terms} if terms else None)
            if result["status"] == "mandate_issued":break
            self.assertEqual(self.store.live_mandates(BID),[])
        mandate = result["mandate"]
        owner = self.store.verify_pin("nadia","2468")
        with self.assertRaisesRegex(ValidationError,"has not accepted"):
            self.store.execute(BID,mandate["mandate_id"],"coach-no-consent",owner,"operator:nadia")
        self.app.negotiate(BID,mandate["mandate_id"],"agent:test")
        receipt = self.store.execute(BID,mandate["mandate_id"],"coach-with-consent",owner,"operator:nadia")
        self.assertFalse(receipt.get("replayed",False))
        self.assertTrue(self.store.execute(BID,mandate["mandate_id"],"coach-with-consent",owner,"operator:nadia")["replayed"])

    def test_bilateral_assumptions_are_bound_to_preview_and_retained_in_saved_terms(self):
        ledger = dict(opening_cash_minor=6000000,reserve_floor_minor=1000000,payroll_minor=3000000,
                      payroll_date="2026-10-31",other_income_minor=0,other_income_date="2026-10-31")
        report = self.http.lab.bilateral_quotes(BID,None,"bill-shapla-karim-nov",ledger)
        quote = next(x for x in report["quotes"] if x["jointly_feasible"])
        self.http.lab.bilateral_propose(BID,None,report["bill_id"],ledger,quote["quote_id"],report["snapshot_hash"],"agent:test")
        r = self.preview()
        self.assertTrue(r["criteria"]["bilateral_assumptions"])
        p = self.save(r)
        for b in p["bundles"]:
            if any(a["record_id"]==report["bill_id"] for a in b["actions"]):
                self.assertEqual(b["bilateral"]["supplier_ledger"],ledger)


if __name__ == "__main__":unittest.main()
