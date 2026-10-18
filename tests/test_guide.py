"""Personal preparation must never be exposed through the product or release."""
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
import unittest

from tideway.server import Application, STATIC, make_handler
from scripts.build_submission_package import allowed_source

ROOT = Path(__file__).resolve().parents[1]


class GuideIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application(":memory:")
        class Quiet(make_handler(cls.app)):
            def log_message(self, *_args):
                pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=5)
        conn.request("POST", "/api/session/login", json.dumps({"operator_id": "nadia", "pin": "2468"}),
                     {"Content-Type": "application/json", "X-Tideway-Token": cls.app.csrf})
        result = conn.getresponse()
        assert result.status == 200
        cls.cookie = result.getheader("Set-Cookie").split(";", 1)[0]
        result.read()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.app.store.close()

    def get(self, path, signed_in=False):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path, headers={"Cookie": self.cookie} if signed_in else {})
        result = conn.getresponse()
        status, body = result.status, result.read().decode("utf-8")
        conn.close()
        return status, body

    def test_guide_and_personal_paths_return_404_even_after_sign_in(self):
        for path in ("/guide", "/guide.html", "/guide.css", "/guide.js", "/guide/",
                     "/personal-prep/project-guide/guide.html", "/personal-prep/project-guide/guide.js"):
            for signed_in in (False, True):
                with self.subTest(path=path, signed_in=signed_in):
                    status, body = self.get(path, signed_in)
                    self.assertEqual(status, 404)
                    self.assertEqual(json.loads(body), {"error": "Not found."})

    def test_landing_shell_and_quick_start_do_not_link_to_prep(self):
        for path in ("/", "/quick-start.js"):
            status, body = self.get(path)
            self.assertEqual(status, 200)
            self.assertNotIn("/guide", body)
            self.assertNotIn("Project guide", body)

    def test_prep_assets_are_outside_the_web_root_and_static_allowlist(self):
        for name in ("guide.html", "guide.css", "guide.js"):
            self.assertFalse((ROOT / "web" / name).exists())
            self.assertNotIn("/" + name, STATIC)
            self.assertNotIn(name, STATIC.values())
        self.assertNotIn("/guide", STATIC)

    def test_submission_and_container_exclude_personal_prep(self):
        for name in ("personal-prep/project-guide/guide.html", "personal-prep/README.md", "web/guide.js",
                     "evidence/screens/23-guide-mobile.png", "evidence/upgrade-v11/browser-integration/24-guide-desktop.png"):
            with self.subTest(name=name):
                self.assertFalse(allowed_source(name))
        self.assertTrue(allowed_source("web/index.html"))
        self.assertIn("personal-prep", (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())


if __name__ == "__main__":
    unittest.main()
