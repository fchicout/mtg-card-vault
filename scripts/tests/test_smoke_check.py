"""Unit tests of scripts/smoke_check.py: a fake fetcher for the logic, a real local server for I/O."""

from __future__ import annotations

import contextlib
import http.server
import io
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import smoke_check as sc  # noqa: E402

GOOD = {
    "content-security-policy": "default-src 'self'; script-src 'self' 'nonce-abc'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "camera=(self), microphone=()",
    "strict-transport-security": "max-age=31536000",
    "x-frame-options": "DENY",
}


def fake(headers=None, redirect=True, health=200, ready=200):
    headers = GOOD if headers is None else headers

    def fetch(origin, method, path):
        if origin.startswith("http://") and not origin.endswith(":8080") and "127.0.0.1" not in origin:
            return (301, {"location": "https://x/"}) if redirect else (200, {})
        if path == "/healthz":
            return health, {}
        if path == "/readyz":
            return ready, {}
        return 200, dict(headers)

    return fetch


class LogicTests(unittest.TestCase):
    def failed(self, results):
        return [r.name for r in results if not r.ok]

    def test_everything_good_passes(self):
        self.assertEqual(self.failed(sc.run(fake(), "https://mtg.example")), [])

    def test_missing_redirect_fails(self):
        self.assertIn("HTTP redirects to HTTPS", self.failed(sc.run(fake(redirect=False), "https://mtg.example")))

    def test_non_standard_port_skips_the_redirect_unless_given(self):
        results = sc.run(fake(), "https://localhost:8443")
        self.assertTrue(next(r for r in results if "redirects" in r.name).ok)
        given = sc.run(fake(redirect=False), "https://localhost:8443", http_origin="http://127.0.0.1:8080")
        self.assertIn("HTTP redirects to HTTPS", self.failed(given))

    def test_unready_service_fails(self):
        self.assertIn("GET /readyz answers 200", self.failed(sc.run(fake(ready=503), "https://mtg.example")))

    def test_each_removed_header_is_reported(self):
        expectations = {
            "content-security-policy": "Content-Security-Policy",
            "x-content-type-options": "X-Content-Type-Options: nosniff",
            "referrer-policy": "Referrer-Policy",
            "permissions-policy": "Permissions-Policy: camera for self only",
            "strict-transport-security": "Strict-Transport-Security",
        }
        for header, name in expectations.items():
            headers = {k: v for k, v in GOOD.items() if k != header}
            self.assertIn(name, self.failed(sc.run(fake(headers), "https://mtg.example")), header)

    def test_unsafe_inline_scripts_and_wildcard_camera_fail(self):
        bad_csp = dict(GOOD, **{"content-security-policy": "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'"})
        self.assertIn("Content-Security-Policy", self.failed(sc.run(fake(bad_csp), "https://mtg.example")))
        bad_camera = dict(GOOD, **{"permissions-policy": "camera=*"})
        self.assertIn("Permissions-Policy: camera for self only", self.failed(sc.run(fake(bad_camera), "https://mtg.example")))

    def test_unsafe_inline_is_tolerated_with_a_nonce_only(self):
        csp = "script-src 'nonce-a' 'unsafe-inline'"  # browsers ignore unsafe-inline when a nonce exists
        self.assertTrue(sc._csp_ok(csp)[0])

    def test_version_leak_fails(self):
        leaky = dict(GOOD, server="nginx/1.27.0")
        self.assertIn("no version in Server / X-Powered-By", self.failed(sc.run(fake(leaky), "https://mtg.example")))

    def test_plain_http_is_refused_unless_allowed(self):
        self.assertIn("served over HTTPS", self.failed(sc.run(fake(), "http://127.0.0.1:8080")))
        allowed = sc.run(fake(), "http://127.0.0.1:8080", allow_http=True)
        self.assertEqual(self.failed(allowed), [])
        self.assertFalse(any(r.name == "Strict-Transport-Security" for r in allowed))


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "fake"
    sys_version = ""

    def do_GET(self):  # noqa: N802
        self.send_response(200 if self.path in ("/", "/healthz", "/readyz") else 404)
        for key, value in GOOD.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_):
        pass


class IoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = sc.main(list(args))
        return code, out.getvalue()

    def test_real_server_passes_with_allow_http(self):
        code, out = self.run_main(f"http://127.0.0.1:{self.port}", "--allow-http")
        self.assertEqual(code, 0, out)
        self.assertIn("checks passed", out)

    def test_http_is_a_failure_by_default(self):
        code, out = self.run_main(f"http://127.0.0.1:{self.port}")
        self.assertEqual(code, 1)
        self.assertIn("served over HTTPS", out)

    def test_unreachable_host_fails_cleanly(self):
        code, out = self.run_main("http://127.0.0.1:1", "--allow-http")
        self.assertEqual(code, 1)
        self.assertIn("not reachable", out)

    def test_unusable_url_is_exit_2(self):
        self.assertEqual(self.run_main("ftp://x")[0], 2)


if __name__ == "__main__":
    unittest.main()
