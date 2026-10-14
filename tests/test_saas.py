"""SaaS workspaces over HTTP: sign-up, tenant isolation, invites with seat limits, roles per business."""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from tideway.security import RateLimiter
from tideway.server import Application, make_handler

SIGNUP = {"business_name": "Kestrel Coffee Roasters", "currency": "EUR", "country": "DE", "sector": "Food & drink",
          "opening_cash": "42000", "reserve_floor": "10000", "owner_name": "Lena Vogel", "username": "lena.v",
          "pin": "582914", "plan": "starter"}


class SaaS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application(":memory:")
        cls.app.login_limiter = RateLimiter(capacity=1000, refill_per_second=100)  # many accounts from one test client
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def call(self, method, path, body=None, cookie=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if body is not None:
            headers.update({"Content-Type": "application/json", "X-Tideway-Token": self.app.csrf,
                            "Origin": f"http://127.0.0.1:{self.port}"})
        if cookie:
            headers["Cookie"] = cookie
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse()
        data = json.loads(response.read() or b"{}")
        set_cookie = response.getheader("Set-Cookie")
        conn.close()
        return response.status, data, set_cookie.split(";")[0] if set_cookie else None

    def signup(self, **changes):
        status, data, cookie = self.call("POST", "/api/signup", {**SIGNUP, **changes})
        self.assertEqual(status, 200, data)
        return data["business_id"], cookie

    def test_signup_creates_an_isolated_workspace(self):
        business, owner = self.signup(username="lena.a", business_name="Kestrel A")
        _, config, _ = self.call("GET", "/api/config", cookie=owner)
        self.assertEqual([item["business_id"] for item in config["businesses"]], [business])
        self.assertNotIn("operators", config)
        self.assertEqual(self.call("GET", f"/api/dashboard?business_id={business}", cookie=owner)[0], 200)
        _, _, nadia = self.call("POST", "/api/session/login", {"operator_id": "nadia", "pin": "2468"})
        self.assertEqual(self.call("GET", f"/api/dashboard?business_id={business}", cookie=nadia)[0], 403)
        self.assertEqual(self.call("GET", "/api/dashboard?business_id=shapla-services", cookie=owner)[0], 403)
        self.assertEqual(self.call("POST", "/api/plan/propose", {"business_id": "shapla-services"}, cookie=owner)[0], 403)

    def test_invite_join_role_and_seat_limit(self):
        business, owner = self.signup(username="lena.b", business_name="Kestrel B")
        status, invite, _ = self.call("POST", "/api/team/invite", {"business_id": business, "role": "viewer", "name": "Max"}, owner)
        self.assertEqual(status, 200, invite)
        status, joined, viewer = self.call("POST", "/api/team/join", {"code": invite["code"], "username": "max.b",
                                                                      "name": "Max", "pin": "730261"})
        self.assertEqual((status, joined["business_id"]), (200, business), joined)
        self.assertEqual(self.call("POST", "/api/plan/propose", {"business_id": business}, viewer)[0], 403)
        self.assertEqual(self.call("POST", "/api/team/join", {"code": invite["code"], "username": "max.c", "pin": "730261"})[0], 400)
        self.assertEqual(self.call("POST", "/api/team/invite", {"business_id": business, "role": "accountant", "name": "Ana"}, owner)[0], 200)
        status, data, _ = self.call("POST", "/api/team/invite", {"business_id": business, "role": "viewer", "name": "Too many"}, owner)
        self.assertEqual(status, 400)
        self.assertIn("3 seats", data["error"])
        self.assertEqual(self.call("POST", "/api/team/invite", {"business_id": business, "role": "viewer", "name": "X"}, viewer)[0], 400)
        _, team, _ = self.call("GET", f"/api/team?business_id={business}", cookie=owner)
        self.assertEqual(len(team["members"]), 2)
        self.assertEqual(team["subscription"]["seats"], 3)

    def test_last_owner_cannot_be_removed_and_weak_pins_are_refused(self):
        business, owner = self.signup(username="lena.c", business_name="Kestrel C")
        self.assertEqual(self.call("POST", "/api/team/remove", {"business_id": business, "operator_id": "lena.c"}, owner)[0], 400)
        for pin in ("111111", "123456", "987654", "1234"):
            self.assertEqual(self.call("POST", "/api/signup", {**SIGNUP, "username": "weak.pin", "pin": pin})[0], 400, pin)
        self.assertEqual(self.call("POST", "/api/signup", {**SIGNUP, "username": "lena.c"})[0], 400)  # username taken


if __name__ == "__main__":
    unittest.main()


class Feedback(unittest.TestCase):
    def test_feedback_keeps_only_a_hash_of_the_question(self):
        from tideway.service import Tideway
        app = Tideway(":memory:")
        operator = {"id": "nadia", "name": "Nadia", "role": "owner"}
        summary = app.store.add_feedback("shapla-services", operator, "tidelm", True, "Can I pay payroll? secret-text")
        self.assertEqual(summary["by_mode"]["tidelm"], {"helpful": 1, "total": 1})
        with app.store.connect() as db:
            stored = " ".join(str(value) for row in db.execute("SELECT * FROM feedback") for value in tuple(row))
        self.assertNotIn("secret-text", stored)
