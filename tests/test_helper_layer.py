"""The plain-language help layer is served, wired in, and has no authority."""
import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import re
import threading
import unittest

from tideway.server import Application, STATIC, make_handler

ROOT = Path(__file__).resolve().parents[1]
HELPER = (ROOT / "web" / "helper.js").read_text(encoding="utf-8")


class HelpLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application(":memory:")
        class Quiet(make_handler(cls.app)):
            def log_message(self, *_args):
                pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.app.store.close()

    def get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        result = conn.getresponse()
        status, kind, body = result.status, result.getheader("Content-Type", ""), result.read().decode("utf-8")
        conn.close()
        return status, kind, body

    def test_assets_are_served_with_the_right_types(self):
        for path, kind in (("/helper.js", "text/javascript"), ("/helper.css", "text/css")):
            with self.subTest(path=path):
                status, served_kind, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertIn(kind, served_kind)
                self.assertTrue(body.strip())

    def test_shell_loads_the_layer_after_the_app(self):
        status, _, page = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn('href="/helper.css"', page)
        self.assertLess(page.index('src="/app.js"'), page.index('src="/helper.js"'))

    def test_layer_has_no_network_or_financial_authority(self):
        # It explains and navigates only: no API calls, no approvals, no execution, no eval.
        for forbidden in ("fetch(", "XMLHttpRequest", "/api/", "sendBeacon", "WebSocket", "eval(", "new Function",
                          'data-action="approve', 'data-action="execute', "approve(", "execute("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, HELPER)

    def test_every_main_page_has_plain_language_help(self):
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        views = set(re.findall(r'class="nav-item" data-view="([a-z]+)"', index))
        self.assertTrue(views)
        pages = set(re.findall(r"^    ([a-z]+): \{$", HELPER, re.M))
        self.assertLessEqual(views, pages, f"Pages without help: {sorted(views - pages)}")

    def test_glossary_entries_are_short_and_escaped_on_render(self):
        entries = re.findall(r'^    \[\[(.+?)\], "(.+?)", "(.+?)"\],$', HELPER, re.M)
        self.assertGreaterEqual(len(entries), 30)
        for _aliases, title, text in entries:
            with self.subTest(term=title):
                self.assertLessEqual(len(text), 160)
        self.assertIn("escape(entry.title)", HELPER)
        self.assertIn("escape(entry.text)", HELPER)
        self.assertIn("/helper.js", STATIC)


if __name__ == "__main__":
    unittest.main()
