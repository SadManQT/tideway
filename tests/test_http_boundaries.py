"""Actual loopback HTTP attacks, including malformed and slowly streamed input."""
import http.client
from http.server import ThreadingHTTPServer
import json
import socket
import threading
import time
import unittest
from unittest.mock import patch

from tideway.server import Application, make_handler


class HttpBoundaries(unittest.TestCase):
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

    def request(self, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("POST" if body is not None else "GET", path, body,
                               {"Content-Type": "application/json", "X-Tideway-Token": self.app.csrf, **(headers or {})})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_malformed_cookie_is_unauthenticated_not_a_connection_crash(self):
        self.assertEqual(self.request("/api/dashboard?business_id=shapla",
                                     headers={"Cookie": "tideway_session=x; bad@key=y"})[0], 401)
        self.assertEqual(self.request("/api/config")[0], 200)

    def test_duplicate_fields_cannot_choose_a_different_identity(self):
        for body in ('{"operator_id":"guest","operator_id":"nadia","pin":"2468"}',
                     '{"operator_id":"guest","operator_\\u0069d":"nadia","pin":"2468"}'):
            with self.subTest(body=body):
                status, result = self.request("/api/session/login", body)
                self.assertEqual(status, 400)
                self.assertIn("Duplicate", result["error"])

    def test_random_invalid_session_cookies_share_anonymous_rate_limit(self):
        for index in range(12):
            self.request("/api/unknown", "{}", {"Cookie": f"tideway_session=invalid{index}"})
        self.assertFalse(any(key.startswith("invalid") for key in self.app.post_limiter.buckets))
        self.assertIn("127.0.0.1", self.app.post_limiter.buckets)

    def raw(self, headers, body=b""):
        connection = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        connection.sendall((f"POST /api/session/login HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                            f"Content-Type: application/json\r\nX-Tideway-Token: {self.app.csrf}\r\n"
                            + headers + "\r\n").encode() + body)
        return connection

    def test_ambiguous_body_framing_is_rejected(self):
        for headers in ("Content-Length: 2\r\nContent-Length: 2\r\n",
                        "Content-Length: 2\r\nTransfer-Encoding: chunked\r\n"):
            with self.subTest(headers=headers), self.raw(headers, b"{}") as connection:
                self.assertIn(b"400", connection.recv(4096).split(b"\r\n", 1)[0])

    def test_stalled_body_gets_a_bounded_timeout_and_server_stays_available(self):
        with patch("tideway.server.BODY_TIMEOUT_SECONDS", .25):
            start = time.monotonic()
            with self.raw("Content-Length: 20\r\n", b"{") as connection:
                self.assertIn(b"408", connection.recv(4096).split(b"\r\n", 1)[0])
            self.assertLess(time.monotonic() - start, 2)
        self.assertEqual(self.request("/api/config")[0], 200)

    def test_trickled_bytes_do_not_restart_total_body_deadline(self):
        with patch("tideway.server.BODY_TIMEOUT_SECONDS", .3):
            with self.raw("Content-Length: 200\r\n", b"{") as connection:
                for _ in range(3):
                    time.sleep(.075)
                    connection.sendall(b" ")
                self.assertIn(b"408", connection.recv(4096).split(b"\r\n", 1)[0])

    def test_nested_duplicate_fields_are_rejected_before_dispatch(self):
        status, _ = self.request("/api/unknown", '{"nested":{"amount":1,"amount":2}}')
        self.assertEqual(status, 400)

    def test_normal_login_still_works(self):
        status, result = self.request("/api/session/login", '{"operator_id":"nadia","pin":"2468"}')
        self.assertEqual(status, 200)
        self.assertEqual(result["operator"]["id"], "nadia")

    def test_multiple_host_headers_are_rejected(self):
        with self.raw("Content-Length: 2\r\nHost: hostile.example\r\n", b"{}") as connection:
            self.assertIn(b"403", connection.recv(4096).split(b"\r\n", 1)[0])

    def test_invalid_unicode_keys_and_values_get_a_response_not_a_crash(self):
        for body in ('{"operator_id":"guest","pin":"0000","\\ud800":"extra"}',
                     '{"operator_id":"\\udfff","pin":"0000"}'):
            with self.subTest(body=body):
                status, result = self.request("/api/session/login", body)
                self.assertEqual(status, 400)
                self.assertIn("Unicode", result["error"])
        self.assertEqual(self.request("/api/config")[0], 200)

    def test_exponent_overflow_is_rejected_before_dispatch(self):
        self.assertEqual(self.request("/api/unknown", '{"amount":1e9999}')[0], 400)


if __name__ == "__main__":
    unittest.main()
