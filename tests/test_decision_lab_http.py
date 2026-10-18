"""Actual authenticated HTTP checks for the new tenant-scoped decision support routes."""
import http.client
from http.server import ThreadingHTTPServer
import json
import threading
import unittest

from tideway.server import Application, make_handler


class DecisionLabHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application(":memory:")
        class Quiet(make_handler(cls.app)):
            def log_message(self, *_args):
                pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.owner = cls.login("nadia", "2468")
        cls.viewer = cls.login("guest", "0000")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.app.store.close()

    @classmethod
    def login(cls, identifier, pin):
        conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=15)
        conn.request("POST", "/api/session/login", json.dumps({"operator_id": identifier, "pin": pin}),
                     {"Content-Type": "application/json", "X-Tideway-Token": cls.app.csrf})
        response = conn.getresponse()
        assert response.status == 200, response.read()
        cookie = response.getheader("Set-Cookie").split(";", 1)[0]
        response.read()
        conn.close()
        return cookie

    def request(self, route, body, cookie=None, csrf=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        headers = {"Content-Type": "application/json"}
        if csrf:
            headers["X-Tideway-Token"] = self.app.csrf
        if cookie:
            headers["Cookie"] = cookie
        conn.request("POST", "/api/lab/" + route, json.dumps(body), headers)
        response = conn.getresponse()
        result = response.status, json.loads(response.read())
        conn.close()
        return result

    def test_routes_require_session_csrf_and_membership(self):
        body = {"business_id": "shapla-services", "kind": "reverse"}
        self.assertEqual(self.request("analyze", body)[0], 401)
        self.assertEqual(self.request("analyze", body, self.owner, False)[0], 403)
        self.assertEqual(self.request("analyze", {**body, "business_id": "no-membership"}, self.owner)[0], 403)

    def test_viewer_can_read_but_cannot_arm_inject_or_propose(self):
        status, result = self.request("analyze", {"business_id": "shapla-services", "kind": "reverse"}, self.viewer)
        self.assertEqual(status, 200)
        self.assertTrue(result["read_only"])
        for path, fields in (("watch", {"enabled": True, "pin": "0000"}),
                             ("event", {"event": {}, "expected_snapshot": "0" * 64, "request_id": "viewer-0001", "pin": "0000"}),
                             ("bilateral/propose", {"bill_id": "anything", "supplier_ledger": {}, "quote_id": "x", "expected_snapshot": "0" * 64})):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, {"business_id": "shapla-services", **fields}, self.viewer)[0], 403)

    def test_unknown_fields_cannot_smuggle_execution_or_another_tenant(self):
        for key in ("execute", "operator_id", "role", "sql"):
            with self.subTest(key=key):
                status, _ = self.request("analyze", {"business_id": "shapla-services", "kind": "reverse", key: True}, self.owner)
                self.assertEqual(status, 400)

    def test_capsule_is_private_scoped_and_malformed_values_return_validation(self):
        status, capsule = self.request("capsule", {"business_id": "shapla-services"}, self.owner)
        self.assertEqual(status, 200)
        status, answer = self.request("replay", {"business_id": "shapla-services", "capsule": capsule}, self.owner)
        self.assertEqual(status, 200)
        self.assertTrue(answer["passed"])
        for value in (None, [], {"snapshot": None}, {"snapshot": {"business": None}},
                      {"snapshot": {"business": {"business_id": "foreign-tenant"}}}):
            with self.subTest(value=value):
                self.assertEqual(self.request("replay", {"business_id": "shapla-services", "capsule": value}, self.owner)[0], 400)

    def test_preview_is_available_without_cloud_key_or_consent(self):
        status, answer = self.request("privacy", {"business_id": "shapla-services", "message": "What data leaves?"}, self.viewer)
        self.assertEqual(status, 200)
        self.assertFalse(answer["network_call_made"])
        self.assertFalse(answer["consent_granted"])


if __name__ == "__main__":
    unittest.main()
