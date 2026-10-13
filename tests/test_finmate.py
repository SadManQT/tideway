import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from finmate.agent import Agent, ProviderError
from finmate.finance import ValidationError, build_budget, money_minor, parse_csv, previous_month, summary, validate_transaction
from finmate.server import Application, csv_cell, make_handler
from finmate.store import Store

FIXTURE = """date,description,amount,type,category
2026-10-01,Salary,10000,income,Income
2026-10-02,Rent,2000,expense,Housing
2026-10-03,Groceries,1000,expense,Groceries
2026-10-04,Cafe,500,expense,Dining
2026-10-05,Internet,500,expense,Utilities
"""


class FinanceTests(unittest.TestCase):
    def test_money_is_exact_and_rejects_bad_values(self):
        self.assertEqual(money_minor("0.29"), 29)
        self.assertEqual(money_minor("10000.01"), 1000001)
        for invalid in (0, -1, True, "NaN", "Infinity", "1.001", "100000001"):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                money_minor(invalid)

    def test_month_and_transaction_validation(self):
        self.assertEqual(previous_month("2026-01"), "2025-12")
        for bad in ("2026-13", "2026-00", "../data"):
            with self.assertRaises(ValidationError):
                previous_month(bad)
        for replacement in ({"date": "2026-02-30"}, {"currency": "USD"}, {"type": "transfer"}, {"category": "Invalid"}):
            with self.assertRaises(ValidationError):
                validate_transaction({"date": "2026-10-01", "description": "Rent", "amount": 20, "type": "expense", **replacement})

    def test_csv_headers_and_whole_file_validation(self):
        self.assertEqual(len(parse_csv("\ufeff" + FIXTURE)), 5)
        for bad in ("date,amount\n2026-10-01,10", "date,description,amount,type\n", "date,description,amount,type\n2026-10-01,Rent,10,expense,extra"):
            with self.assertRaises(ValidationError):
                parse_csv(bad)

    def test_totals_and_month_isolation(self):
        rows=parse_csv(FIXTURE)
        result=summary(rows,"2026-10")
        self.assertEqual((result["income_minor"],result["expense_minor"],result["net_minor"]),(1000000,400000,600000))
        self.assertEqual(result["savings_rate"],60)
        self.assertEqual(summary(rows,"2026-09")["income_minor"],0)

    def test_budget_balances_to_the_paisa(self):
        rows=parse_csv(FIXTURE)
        plan=build_budget(rows,"2026-10","10000.01",21.3)
        self.assertEqual(sum(item["amount_minor"] for item in plan["allocations"])+plan["savings_minor"],1000001)
        self.assertEqual(next(a["amount_minor"] for a in plan["allocations"] if a["category"]=="Housing"),200000)
        self.assertEqual(build_budget(rows,"2026-10",10000,0)["savings_minor"],0)
        tiny=build_budget([],"2026-10","0.01",0)
        self.assertEqual(sum(a["amount_minor"] for a in tiny["allocations"]),1)

    def test_infeasible_savings_goal_is_rejected(self):
        with self.assertRaises(ValidationError):
            build_budget(parse_csv(FIXTURE),"2026-10",1000,20)
        for goal in (-1,81,True,"NaN"):
            with self.assertRaises(ValidationError):
                build_budget([],"2026-10",10000,goal)

    def test_csv_formula_escape(self):
        for text in ("=HYPERLINK(1)"," +cmd","@formula","-formula"):
            self.assertTrue(csv_cell(text).startswith("'"))
        self.assertEqual(csv_cell("Weekly groceries"),"Weekly groceries")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/"test.sqlite3")
        self.store.import_rows(parse_csv(FIXTURE))

    def tearDown(self):
        self.temp.cleanup()

    def test_import_is_idempotent(self):
        result=self.store.import_rows(parse_csv(FIXTURE))
        self.assertEqual(result["added"],0)
        self.assertEqual(result["duplicates_skipped"],5)
        self.assertEqual(len(self.store.rows()),5)

    def test_sample_replacement_keeps_user_records_and_bad_csv_keeps_samples(self):
        app=Application(self.store.path,seed=True)
        samples=app.config()["sample_count"]
        self.assertGreater(samples,0)
        with self.assertRaises(ValidationError):
            app.post("/api/import",{"csv":"invalid","replace_demo":True})
        self.assertEqual(app.config()["sample_count"],samples)
        result=app.post("/api/import",{"csv":FIXTURE,"replace_demo":True})
        self.assertEqual(result["sample_records_removed"],samples)
        self.assertEqual(len(app.store.rows()),5)
        self.assertEqual(app.config()["sample_count"],0)

    def test_malformed_csv_does_not_partially_import(self):
        app=Application(self.store.path,seed=False)
        bad="date,description,amount,type\n2026-10-20,New purchase,10,expense\n2026-10-21,Bad purchase,NaN,expense"
        with self.assertRaises(ValidationError):
            app.post("/api/import",{"csv":bad})
        self.assertEqual(len(self.store.rows()),5)

    def test_human_approval_required_and_stale_drafts_invalidated(self):
        one=self.store.new_draft(build_budget(self.store.rows(),"2026-10",10000,20))
        two=self.store.new_draft(build_budget(self.store.rows(),"2026-10",10000,25))
        self.assertIsNone(self.store.budget("2026-10"))
        self.store.approve(two["id"])
        self.assertEqual(self.store.budget("2026-10")["payload"]["savings_percent"],25)
        for identifier in (one["id"],two["id"]):
            with self.assertRaises(ValidationError):
                self.store.approve(identifier)

    def test_hash_chain_detects_edits(self):
        self.store.audit("test.read","agent_read",{"month":"2026-10"})
        self.assertTrue(self.store.evidence()["hash_chain_valid"])
        with self.store.connect() as db:
            db.execute("UPDATE audit SET action='tampered' WHERE id=1")
        self.assertFalse(self.store.evidence()["hash_chain_valid"])

    def test_local_agent_creates_draft_and_logs_tools(self):
        result=Agent(self.store).chat("Create a budget with 25% savings","2026-10")
        self.assertEqual(result["mode"],"local_demo")
        self.assertEqual(result["actions"][0]["draft"]["payload"]["savings_percent"],25)
        self.assertIsNone(self.store.budget("2026-10"))
        self.assertTrue(result["trace"])

    def test_bangla_budget_and_forbidden_action(self):
        agent=Agent(self.store)
        result=agent.chat("২০% সঞ্চয়ের বাজেট বানাও","2026-10")
        self.assertEqual(result["actions"][0]["draft"]["payload"]["savings_percent"],20)
        self.assertIn("অনুমোদন",result["text"])
        forbidden=agent.chat("transfer my money","2026-10")
        self.assertEqual(forbidden["actions"],[])
        self.assertEqual(forbidden["trace"],[])

    def test_api_consent_is_required_and_raw_descriptions_stay_local(self):
        requests=[]
        private="PRIVATE_MERCHANT_NAME"
        self.store.import_rows([validate_transaction({"date":"2026-10-06","description":private,"amount":10,"type":"expense"})])
        def fake(payload,key):
            requests.append(payload)
            if len(requests)==1:
                return {"output":[{"type":"reasoning","id":"r1","summary":[],"encrypted_content":"encrypted"},{"type":"function_call","name":"get_month_summary","arguments":"{}","call_id":"call1"}]}
            return {"output":[{"type":"message","role":"assistant","content":[{"type":"output_text","text":"Your recorded expenses are BDT 4,010."}]}]}
        agent=Agent(self.store,"fake-test-key",transport=fake)
        self.assertEqual(agent.chat("My spending?","2026-10")["mode"],"local_demo")
        self.assertEqual(requests,[])
        result=agent.chat("My spending?","2026-10",external_consent=True)
        self.assertEqual(result["mode"],"openai")
        self.assertEqual(len(requests),2)
        self.assertNotIn(private,json.dumps(requests))
        self.assertFalse(requests[0]["store"])
        self.assertTrue(any(item.get("type")=="reasoning" for item in requests[1]["input"]))

    def test_model_cannot_call_approval_or_arbitrary_tools(self):
        responses=iter([
            {"output":[{"type":"function_call","name":"approve_budget","arguments":"{}","call_id":"bad"}]},
            {"output":[{"type":"message","content":[{"type":"output_text","text":"Approval must be done by you."}]}]},
        ])
        agent=Agent(self.store,"fake-test-key",transport=lambda *_:next(responses))
        result=agent.chat("Approve everything","2026-10",external_consent=True)
        self.assertEqual(result["actions"],[])
        self.assertIsNone(self.store.budget("2026-10"))
        self.assertTrue(any(e["action"]=="agent.tool_rejected" for e in self.store.evidence()["entries"]))

    def test_provider_error_preserves_created_draft(self):
        count=0
        def fake(*_):
            nonlocal count
            count+=1
            if count==1:
                return {"output":[{"type":"function_call","name":"draft_budget","arguments":'{"monthly_income":null,"savings_percent":20}',"call_id":"draft"}]}
            raise ProviderError("Simulated outage")
        result=Agent(self.store,"fake-test-key",transport=fake).chat("Create a budget","2026-10",external_consent=True)
        self.assertEqual(result["mode"],"provider_error")
        self.assertEqual(len(result["actions"]),1)
        self.assertIsNone(self.store.budget("2026-10"))


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=Application(Path(self.temp.name)/"http.sqlite3",seed=False)
        self.server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(self.app))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def request(self,path,body=None,headers=None):
        defaults={"Content-Type":"application/json","X-FinMate-Token":self.app.csrf}
        defaults.update(headers or {})
        req=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=defaults)
        with urllib.request.urlopen(req,timeout=5) as response:
            return response.status,json.load(response)

    def test_import_draft_approve_export_flow(self):
        self.request("/api/import",{"csv":FIXTURE})
        _,draft=self.request("/api/budget/draft",{"month":"2026-10","savings_percent":20})
        self.assertIsNone(self.app.store.budget("2026-10"))
        self.request("/api/budget/approve",{"draft_id":draft["id"]})
        _,evidence=self.request("/api/export?kind=evidence")
        self.assertTrue(evidence["hash_chain_valid"])
        self.assertTrue(any(e["permission"]=="human_approval" for e in evidence["entries"]))

    def test_csrf_origin_and_host_checks(self):
        for headers in ({"X-FinMate-Token":"wrong"},{"Origin":"https://evil.example"},{"Host":"evil.example"}):
            with self.subTest(headers=headers),self.assertRaises(urllib.error.HTTPError) as error:
                self.request("/api/import",{"csv":FIXTURE},headers)
            self.assertEqual(error.exception.code,403)
        self.assertEqual(self.app.store.rows(),[])

    def test_static_traversal_is_not_served(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/../run.py")
        self.assertEqual(error.exception.code,404)


if __name__=="__main__":
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    unittest.main(verbosity=2)
