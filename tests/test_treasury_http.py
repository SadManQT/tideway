"""Authenticated HTTP checks for the tenant-scoped Treasury routes and the 13-week cash-flow export."""
import csv
import http.client
import io
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from tideway.security import RateLimiter
from tideway.server import Application, make_handler

B = "shapla-services"


class TreasuryHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application(":memory:")
        cls.app.login_limiter = RateLimiter(capacity=1000, refill_per_second=100)
        cls.app.post_limiter = RateLimiter(capacity=1000, refill_per_second=100)

        class Quiet(make_handler(cls.app)):
            def log_message(self, *_args):
                pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.owner = cls.login("nadia", "2468")
        cls.accountant = cls.login("imran", "1357")
        cls.viewer = cls.login("guest", "0000")
        # A second tenant the demo operators are not members of.
        status, data, cookie = cls.call("POST", "/api/signup", {
            "business_name": "Kestrel Roasters", "currency": "EUR", "country": "DE", "sector": "Food",
            "opening_cash": "42000", "reserve_floor": "10000", "owner_name": "Lena Vogel", "username": "lena.treasury",
            "pin": "582914", "plan": "starter"})
        assert status == 200, data
        cls.other_business, cls.other = data["business_id"], cookie

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.app.store.close()

    @classmethod
    def call(cls, method, path, body=None, cookie=None, csrf=True):
        conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=30)
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
            if csrf:
                headers["X-Tideway-Token"] = cls.app.csrf
        if cookie:
            headers["Cookie"] = cookie
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse()
        raw = response.read()
        set_cookie = response.getheader("Set-Cookie")
        content_type = response.getheader("Content-Type", "")
        conn.close()
        data = json.loads(raw) if content_type.startswith("application/json") else raw.decode("utf-8")
        return response.status, data, set_cookie.split(";", 1)[0] if set_cookie else None

    @classmethod
    def login(cls, identifier, pin):
        status, data, cookie = cls.call("POST", "/api/session/login", {"operator_id": identifier, "pin": pin})
        assert status == 200, data
        return cookie

    def post(self, route, body, cookie):
        status, data, _ = self.call("POST", "/api/treasury/" + route, body, cookie)
        return status, data

    def test_routes_require_session_csrf_and_membership(self):
        body = {"business_id": B}
        self.assertEqual(self.call("POST", "/api/treasury/twcf", body)[0], 401)
        self.assertEqual(self.call("POST", "/api/treasury/twcf", body, self.owner, csrf=False)[0], 403)
        for route in ("twcf", "health", "scan", "passport/verify"):
            payload = {"business_id": self.other_business, **({"passport": {}} if route == "passport/verify" else {})}
            self.assertEqual(self.post(route, payload, self.owner)[0], 403, route)  # Nadia is not a member
            self.assertEqual(self.post(route, {**payload, "business_id": B}, self.other)[0], 403, route)  # Lena is not either
        self.assertEqual(self.post("passport/issue", {"business_id": B, "pin": "582914"}, self.other)[0], 403)
        self.assertEqual(self.post("twcf", {}, self.owner)[0], 400)
        self.assertEqual(self.post("nope", body, self.owner)[0], 404)
        status, _data, _ = self.call("GET", f"/api/export?kind=twcf&business_id={B}", cookie=self.other)
        self.assertEqual(status, 403)

    def test_unexpected_fields_and_types_are_rejected(self):
        self.assertEqual(self.post("twcf", {"business_id": B, "scenario": "likely"}, self.owner)[0], 400)
        self.assertEqual(self.post("health", {"business_id": B, "extra": 1}, self.owner)[0], 400)
        self.assertEqual(self.post("scan", {"business_id": B, "synthetic_sample": "yes"}, self.owner)[0], 400)
        self.assertEqual(self.post("passport/issue", {"business_id": B, "pin": "2468", "days": 365}, self.owner)[0], 400)
        self.assertEqual(self.post("passport/issue", {"business_id": B}, self.owner)[0], 400)
        self.assertEqual(self.post("passport/verify", {"business_id": B, "passport": {}, "trust": True}, self.owner)[0], 400)

    def test_viewer_reads_but_cannot_issue(self):
        for route, body in (("twcf", {}), ("health", {}), ("scan", {"synthetic_sample": True})):
            status, data = self.post(route, {"business_id": B, **body}, self.viewer)
            self.assertEqual(status, 200, (route, data))
            self.assertTrue(data["read_only"])
        before = len(self.app.store.evidence(B)["entries"])
        status, data = self.post("passport/issue", {"business_id": B, "pin": "0000"}, self.viewer)
        self.assertEqual(status, 403, data)
        self.assertEqual(len([e for e in self.app.store.evidence(B)["entries"][before:] if e["action"] == "treasury.passport.issue"]), 0)

    def test_issue_needs_correct_pin_then_verifies_for_any_member(self):
        self.assertEqual(self.post("passport/issue", {"business_id": B, "pin": "9999"}, self.accountant)[0], 400)
        status, data = self.post("passport/issue", {"business_id": B, "pin": "1357"}, self.accountant)
        self.assertEqual(status, 200, data)
        passport = data["passport"]
        self.assertEqual(passport["issuer"]["issued_by"], "accountant:imran")
        status, result = self.post("passport/verify", {"business_id": B, "passport": passport}, self.viewer)
        self.assertEqual(status, 200)
        self.assertTrue(result["valid"])
        tampered = json.loads(json.dumps(passport))
        tampered["twcf"]["likely"]["closing_cash_minor"] += 5_000_000
        status, result = self.post("passport/verify", {"business_id": B, "passport": tampered}, self.viewer)
        self.assertEqual((status, result["valid"], result["reason"]), (200, False, "signature_mismatch"))
        status, result = self.post("passport/verify", {"business_id": "lotus-print", "passport": passport}, self.owner)
        self.assertEqual((status, result["valid"], result["reason"]), (200, False, "wrong_business"))
        status, result = self.post("passport/verify", {"business_id": self.other_business, "passport": passport}, self.other)
        self.assertEqual((status, result["reason"]), (200, "wrong_business"))
        self.assertNotIn("Shapla", json.dumps(result))  # another tenant learns nothing about the passport's contents

    def test_twcf_export_is_formula_safe_csv_with_bom(self):
        opening = self.app.store.snapshot(self.other_business)["business"]["opening_date"]
        self.app.store.import_records(self.other_business, {"invoices": [{
            "id": "inv-formula", "customer": "=HYPERLINK(\"http://x\")", "description": "Order 1", "issue_date": opening,
            "due_date": opening, "expected_collection_date": opening,
            "status": "confirmed", "amount": "100", "currency": "EUR"}]}, "operator:lena.treasury")
        status, text, _ = self.call("GET", f"/api/export?kind=twcf&business_id={self.other_business}", cookie=self.other)
        self.assertEqual(status, 200, text)
        self.assertTrue(text.startswith("﻿"))
        rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
        self.assertEqual(len(rows), 1 + 3 * 13)
        self.assertIn("receipts_from:'=HYPERLINK(\"http://x\")", rows[0])
        self.assertFalse(any(cell.startswith(("=", "+", "-", "@")) for cell in rows[0]))
        status, text, _ = self.call("GET", f"/api/export?kind=twcf&business_id={B}&scenario=likely", cookie=self.viewer)
        self.assertEqual(status, 200)
        rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
        self.assertEqual(len(rows), 14)
        header = rows[0]
        last = dict(zip(header, rows[-1]))
        plan = self.app.treasury.twcf(B)["scenarios"]["likely"]["totals"]
        self.assertEqual(int(last["closing_cash_minor"]), plan["closing_cash_minor"])
        self.assertEqual(self.call("GET", f"/api/export?kind=twcf&business_id={B}&scenario=bogus", cookie=self.viewer)[0], 400)


if __name__ == "__main__":
    unittest.main()
