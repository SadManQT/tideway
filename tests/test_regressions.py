"""Regression tests for the QA bug report (one test per fixed defect). Run: python3 -m unittest discover -s tests"""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from tideway import counterparty
from tideway.agent import Agent
from tideway.domain import ValidationError, validate_policy
from tideway.selftest import LOTUS, SHAPLA, TARGET, _mandate, _ops
from tideway.server import Application, make_handler
from tideway.service import Tideway


def audit_count(app, business=SHAPLA):
    with app.store.connect() as db:
        return db.execute("SELECT COUNT(*) FROM audit WHERE business_id=?", (business,)).fetchone()[0]


def mandate_status(app, mandate_id):
    return app.store.mandate(SHAPLA, mandate_id)["status"]


class StoreRegressions(unittest.TestCase):
    def setUp(self):
        self.app = Tideway(":memory:")
        self.owner, self.accountant, self.viewer = _ops(self.app)

    def test_reminder_does_not_invalidate_approved_mandate(self):  # bugs 2 and 3
        plan, mandate = _mandate(self.app)
        reminder = plan["reminders"][0]
        self.app.send_reminder(SHAPLA, TARGET, reminder["action_id"], self.owner, "operator:nadia")
        self.assertEqual(mandate_status(self.app, mandate["mandate_id"]), "active")

    def test_payee_verifier_cannot_be_sole_approver(self):  # bugs 4 and 33
        with self.assertRaises(ValidationError):  # unflagged payee: nothing to verify
            self.app.store.verify_payee(SHAPLA, "Rahman Supplies", "AC-2201-4471", self.owner, "x", "callback_number_on_file")
        with self.app.store.connect() as db:
            db.execute("UPDATE bills SET payee_account='AC-2201-9999' WHERE business_id=? AND id='bill-shapla-rahman-oct'", (SHAPLA,))
        self.app.store.verify_payee(SHAPLA, "Rahman Supplies", "AC-2201-9999", self.owner, "x", "callback_number_on_file")
        plan = self.app.propose(SHAPLA, TARGET, "agent:test")
        alone = self.app.store.approve(SHAPLA, plan["plan_id"], "recommended", self.owner, "2468", "x", 9000)
        self.assertTrue(alone["separation_of_duties"])
        second = self.app.store.approve(SHAPLA, plan["plan_id"], "recommended", self.accountant, "1357", "y", 9000)
        self.assertEqual(second["status"], "mandate_issued")

    def test_verified_lookalike_is_cleared(self):  # bug 4
        meghna = "meghna-traders"
        self.app.store.verify_payee(meghna, "Jamuna Stee1", "AC-6666-4040", self.owner, "x", "callback_number_on_file")
        derived = self.app.store.derived(self.app.store.snapshot(meghna))
        self.assertNotIn("bill-meghna-lookalike-oct", derived["blocked"])

    def test_advise_blocks_proposal_and_failed_replan_keeps_mandate(self):  # bug 7
        _plan, mandate = _mandate(self.app)
        action = self.app.store.plan(SHAPLA, mandate["plan_id"])["bundles"][0]["actions"][0]
        self.app.simulate_decision(SHAPLA, mandate["mandate_id"], action["action_id"], False, self.owner, "x")
        with self.app.store.connect() as db:  # policy flips to advise without bumping (a concurrent change)
            row = db.execute("SELECT policy_json FROM policies WHERE business_id=?", (SHAPLA,)).fetchone()
            policy = {**json.loads(row[0]), "autonomy_level": "advise"}
            db.execute("UPDATE policies SET policy_json=? WHERE business_id=?", (json.dumps(policy), SHAPLA))
        with self.assertRaises(ValidationError):
            self.app.replan_without(SHAPLA, mandate["mandate_id"], "x")
        self.assertEqual(mandate_status(self.app, mandate["mandate_id"]), "rejected")

    def test_counter_needs_a_counter_offer(self):  # bug 8
        _plan, mandate = _mandate(self.app)
        with self.assertRaises(ValidationError):
            self.app.accept_counter(SHAPLA, mandate["mandate_id"], "x")
        self.assertEqual(mandate_status(self.app, mandate["mandate_id"]), "active")

    def test_dead_mandate_allows_reapproval_but_live_one_blocks(self):  # bugs 9 and 10
        plan, mandate = _mandate(self.app)
        with self.assertRaises(ValidationError):
            self.app.store.approve(SHAPLA, plan["plan_id"], "recommended", self.accountant, "1357", "x", 9000)
        with self.app.store.connect() as db:
            db.execute("UPDATE mandates SET status='expired' WHERE id=?", (mandate["mandate_id"],))
        first = self.app.store.approve(SHAPLA, plan["plan_id"], "recommended", self.accountant, "1357", "x", 9000)
        second = self.app.store.approve(SHAPLA, plan["plan_id"], "recommended", self.owner, "2468", "y", 9000)
        self.assertEqual(first["status"], "awaiting_second_approval")
        self.assertEqual(second["status"], "mandate_issued")

    def test_non_text_identifiers_are_rejected(self):  # bug 13
        for bad in ({"a": 1}, ["x"], 7):
            with self.assertRaises(ValidationError):
                self.app.store.mandate(SHAPLA, bad)
            with self.assertRaises(ValidationError):
                self.app.store.verify_payee(SHAPLA, bad, "AC", self.owner, "x", "callback_number_on_file")

    def test_resume_reason_uses_normalised_value(self):  # bug 17
        self.app.store.set_policy(SHAPLA, {"agent_paused": True}, self.owner, "x")
        with self.assertRaises(ValidationError):
            self.app.store.set_policy(SHAPLA, {"agent_paused": "false"}, self.owner, "x")

    def test_breaker_counts_only_denials_since_resume(self):  # bug 18
        for _ in range(5):
            self.app.store.reject(SHAPLA, "t", "x", "invalid_mandate: test", security_relevant=True)
        self.assertTrue(self.app.store.snapshot(SHAPLA)["policy"]["agent_paused"])
        self.app.store.set_policy(SHAPLA, {"agent_paused": False, "resume_reason": "investigated the drill"}, self.owner, "x")
        self.app.store.reject(SHAPLA, "t", "x", "invalid_mandate: test", security_relevant=True)
        self.assertFalse(self.app.store.snapshot(SHAPLA)["policy"]["agent_paused"])

    def test_sign_in_guessing_does_not_lock_step_up(self):  # bug 19
        for _ in range(6):
            with self.assertRaises(ValidationError):
                self.app.store.login("nadia", "0000", client="10.0.0.9")
        self.assertEqual(self.app.store.verify_pin("nadia", "2468")["id"], "nadia")
        with self.assertRaises(ValidationError):
            self.app.store.login("nadia", "2468", client="10.0.0.9")  # that client stays locked
        self.app.store.login("nadia", "2468", client="10.0.0.1")

    def test_discount_percent_keeps_fractions(self):  # bug 21
        action = {"type": "early_payment_offer", "currency": "BDT", "counterparty": "X", "action_id": "a",
                  "days": 1, "discount_bps": 50, "amount_minor": 100, "to_date": TARGET}
        reply = counterparty.respond(action, {"min_discount_bps": 150, "max_acceleration_days": 30})
        self.assertIn("1.5%", reply["message"])

    def test_daily_cap_survives_sandbox_reset(self):  # bug 23
        _plan, mandate = _mandate(self.app)
        self.app.negotiate(SHAPLA, mandate["mandate_id"], "x")
        receipt = self.app.store.execute(SHAPLA, mandate["mandate_id"], "cap-1", self.owner, "x")
        self.app.store.reset_sandbox(SHAPLA, self.owner, "x")
        self.assertEqual(self.app.store._exposure_today(SHAPLA), receipt["exposure_minor"])

    def test_policy_noop_and_cap_order(self):  # bug 34
        version = self.app.store.snapshot(SHAPLA)["state"]["version"]
        current = self.app.store.snapshot(SHAPLA)["policy"]
        result = self.app.store.set_policy(SHAPLA, {"max_discount_bps": current["max_discount_bps"]}, self.owner, "x")
        self.assertFalse(result["changed"])
        self.assertEqual(self.app.store.snapshot(SHAPLA)["state"]["version"], version)
        with self.assertRaises(ValidationError):
            validate_policy({**current, "daily_cap_minor": current["action_limit_minor"] - 1}, SHAPLA, current["currency"])

    def test_what_if_rejects_bad_changes(self):  # bug 34
        for changes in ({"bogus": 1}, {"customer_delays": {"Nobody Ltd": 5}},
                        {"extra_expense": {"amount_minor": 100, "date": "2027-12-01"}}):
            with self.assertRaises(ValidationError):
                self.app.what_if(SHAPLA, TARGET, changes)

    def test_csv_export_reimports_unchanged(self):  # bugs 12 and 27
        web = Application(":memory:")
        for business in (SHAPLA, LOTUS, "meghna-traders"):
            body, _, _ = web.export({"kind": ["records"], "business_id": [business]}, self.owner)
            result = web.tideway.import_csv(business, body, "x", False)
            self.assertEqual(result["total_added"], 0, business)

    def test_identical_rows_with_ids_are_both_kept(self):  # bug 12
        csv_text = ("record_type,id,date,description,amount,type,currency,category\n"
                    "transaction,t-a,2026-09-01,Taxi,10.00,expense,BDT,Travel\n"
                    "transaction,t-b,2026-09-01,Taxi,10.00,expense,BDT,Travel\n")
        self.assertEqual(self.app.import_csv(SHAPLA, csv_text, "x", False)["total_added"], 2)
        with self.assertRaises(ValidationError):
            self.app.import_csv(SHAPLA, csv_text.replace("t-a", "").replace("t-b", ""), "x", False)

    def test_viewer_chat_cannot_create_plans(self):  # bug 6
        agent = Agent(self.app)
        before = self.app.store.latest_plan(SHAPLA, TARGET)
        reply = agent.chat(SHAPLA, TARGET, "please make a rescue plan", actor="agent:local", role="viewer")
        self.assertIn("only an owner or accountant", reply["text"])
        self.assertEqual(self.app.store.latest_plan(SHAPLA, TARGET), before)

    def test_chat_validation_errors_are_conversational(self):  # bug 29
        reply = Agent(self.app).chat(SHAPLA, TARGET, "what if Nila Traders pays 99 days late", actor="agent:local")
        self.assertTrue(reply["text"].startswith("I couldn't do that"))

    def test_profiles_carry_tidepay_delay(self):  # bug 32
        derived = self.app.store.derived(self.app.store.snapshot(SHAPLA))
        owing = [item for item in derived["profiles"]["customers"].values() if item["open_exposure_minor"]]
        self.assertTrue(owing and all(item["tidepay_delay_days"] is not None for item in owing))


class HttpRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application(":memory:")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def raw(self, body, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        base = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json", "X-Tideway-Token": self.app.csrf,
                "Origin": f"http://127.0.0.1:{self.port}", **(headers or {})}
        conn.putrequest("POST", "/api/session/login", skip_host=True, skip_accept_encoding=True)
        for key, value in base.items():
            conn.putheader(key, value)
        conn.endheaders(body)
        response = conn.getresponse()
        status = response.status
        response.read()
        conn.close()
        return status

    def test_anonymous_errors_are_not_audited(self):  # bug 1
        before = audit_count(self.app)
        body = json.dumps({"business_id": SHAPLA, "operator_id": "nadia", "pin": "1"}).encode()
        self.assertEqual(self.raw(body, {"Content-Length": str(len(body))}), 400)
        self.assertEqual(audit_count(self.app), before)

    def test_malformed_requests_get_4xx(self):  # bug 41
        nested = ("[" * 100_000 + "]" * 100_000).encode()
        self.assertEqual(self.raw(nested, {"Content-Length": str(len(nested))}), 400)
        self.assertEqual(self.raw(b"{}", {"Content-Length": "abc"}), 400)
        self.assertEqual(self.raw(b"{}", {"Content-Length": "2", "X-Tideway-Token": "tök€n".encode()}), 403)


if __name__ == "__main__":
    unittest.main()
