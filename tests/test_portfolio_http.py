"""Portfolio radar route: signed-in only, strict query validation, synthetic data only."""
import http.client
from http.server import ThreadingHTTPServer
import json
import threading
import unittest

from tideway.server import Application, STATIC, make_handler


class PortfolioRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application(":memory:")
        class Quiet(make_handler(cls.app)):
            def log_message(self, *_args):
                pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=10)
        conn.request("POST", "/api/session/login", json.dumps({"operator_id": "guest", "pin": "0000"}),
                     {"Content-Type": "application/json", "X-Tideway-Token": cls.app.csrf})
        result = conn.getresponse()
        assert result.status == 200, result.read()
        cls.cookie = result.getheader("Set-Cookie").split(";", 1)[0]
        result.read()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.app.store.close()

    def get(self, path, signed_in=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        conn.request("GET", path, headers={"Cookie": self.cookie} if signed_in else {})
        result = conn.getresponse()
        status, body = result.status, json.loads(result.read().decode("utf-8"))
        conn.close()
        return status, body

    def test_sign_in_is_required(self):
        status, body = self.get("/api/portfolio/radar", signed_in=False)
        self.assertIn(status, (401, 403))
        self.assertNotIn("smes", body)

    def test_viewer_gets_a_labelled_synthetic_portfolio(self):
        status, body = self.get("/api/portfolio/radar")
        self.assertEqual(status, 200)
        self.assertIs(body["synthetic"], True)
        self.assertTrue(body["label"])
        self.assertNotIn("shapla-services", json.dumps(body))  # never a tenant workspace

    def test_query_is_strictly_validated(self):
        for query in ("shock_days=61", "shock_days=-1", "shock_days=abc", "sector=crypto",
                      "business_id=shapla-services", "shock_days=1&shock_days=2"):
            with self.subTest(query=query):
                status, body = self.get(f"/api/portfolio/radar?{query}")
                self.assertEqual(status, 400)
                self.assertIn("error", body)

    def test_script_is_served(self):
        self.assertEqual(STATIC["/portfolio.js"], "portfolio.js")


if __name__ == "__main__":
    unittest.main()
