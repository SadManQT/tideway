"""Actual HTTP access control, strict input schemas and read-only exports."""
import http.client
from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from tideway.server import Application, make_handler


class OwnerViewHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application(":memory:")
        class Quiet(make_handler(cls.app)):
            def log_message(self,*_args):pass
        cls.server = ThreadingHTTPServer(("127.0.0.1",0),Quiet)
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.owner = cls.login("nadia","2468")
        cls.viewer = cls.login("guest","0000")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.app.store.close()

    @classmethod
    def login(cls,identifier,pin):
        conn = http.client.HTTPConnection("127.0.0.1",cls.port,timeout=20)
        conn.request("POST","/api/session/login",json.dumps(dict(operator_id=identifier,pin=pin)),
                     {"Content-Type":"application/json","X-Tideway-Token":cls.app.csrf})
        response = conn.getresponse()
        assert response.status == 200,response.read()
        cookie = response.getheader("Set-Cookie").split(";",1)[0]
        response.read();conn.close()
        return cookie

    def request(self,route,body,cookie=None,csrf=True):
        conn = http.client.HTTPConnection("127.0.0.1",self.port,timeout=30)
        headers = {"Content-Type":"application/json"}
        if csrf:headers["X-Tideway-Token"] = self.app.csrf
        if cookie:headers["Cookie"] = cookie
        conn.request("POST","/api/owner/"+route,json.dumps(body),headers)
        response = conn.getresponse()
        status,data = response.status,json.loads(response.read())
        conn.close()
        return status,data

    def test_session_csrf_and_exact_business_membership_are_required(self):
        body = dict(business_id="shapla-services")
        self.assertEqual(self.request("analyze",body)[0],401)
        self.assertEqual(self.request("analyze",body,self.owner,False)[0],403)
        self.assertEqual(self.request("analyze",dict(business_id="foreign"),self.owner)[0],403)
        self.assertEqual(self.request("analyze",{},self.owner)[0],400)

    def test_viewer_can_analyze_compare_and_export_but_cannot_save(self):
        body = dict(business_id="shapla-services")
        for route in ("analyze","brief","coach"):
            status,r = self.request(route,body,self.viewer)
            self.assertEqual(status,200,r)
            self.assertTrue(r["read_only"])
            self.assertFalse(r["executed"])
        body.update(priority="lowest_cost",option_id="a"*64,expected_snapshot="a"*64,request_id="viewer-request")
        self.assertEqual(self.request("propose",body,self.viewer)[0],403)

    def test_untrusted_fields_and_malformed_amounts_cannot_reach_the_planner(self):
        for name,value in (("execute",True),("operator_id","nadia"),("role","owner"),("expense_minor",True),("expense_minor",1.2),("expense_date",False)):
            with self.subTest(name=name,value=value):
                status,_ = self.request("analyze",dict(business_id="shapla-services",**{name:value}),self.owner)
                self.assertEqual(status,400)

    def test_stale_export_is_refused_and_brief_is_bound_to_real_report(self):
        body = dict(business_id="shapla-services",expense_minor=100)
        status,r = self.request("analyze",body,self.owner)
        self.assertEqual(status,200)
        status,brief = self.request("brief",dict(body,expected_snapshot=r["snapshot_hash"]),self.owner)
        self.assertEqual(status,200)
        self.assertEqual(brief["snapshot_hash"],r["snapshot_hash"])
        self.assertIn(r["snapshot_hash"],brief["html"])
        self.assertNotIn('<script',brief["html"])
        self.assertEqual(self.request("brief",dict(body,expected_snapshot="0"*64),self.owner)[0],400)


if __name__ == "__main__":unittest.main()
