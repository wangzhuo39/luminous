import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from luminous.runtime.config import BackendConfig
from luminous.runtime.infrastructure.http import make_handler


class CookieAuthHTTPTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.config = BackendConfig(
            project_root=root,
            env_path=root / ".env",
            frontend_dir=Path(__file__).resolve().parents[2] / "apps/companion-web/companion-ui",
            data_dir=root / "private-data",
            mock=True,
            deployment_mode="public",
            tester_access_code="one-time-test-code",
            session_secret="session-secret-with-enough-entropy-for-tests",
            cors_origins=("https://test.example",),
        )
        self._start_server()

    def tearDown(self):
        self._stop_server()
        self.temp_dir.cleanup()

    def _start_server(self):
        self.config.validate_server_boundary()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.config))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def _stop_server(self):
        if getattr(self, "server", None):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
            self.server = None

    def request(self, method, path, body=None, headers=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read()), dict(response.headers.items())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read()), dict(error.headers.items())

    def test_login_cookie_survives_restart_and_logout_revokes_it(self):
        status, _, _ = self.request("GET", "/api/auth/session", headers={"Origin": "https://test.example"})
        self.assertEqual(status, 401)

        status, body, _ = self.request(
            "POST",
            "/api/auth/login",
            {"access_code": "wrong"},
            {"Origin": "https://test.example"},
        )
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "invalid_access_code")

        status, body, headers = self.request(
            "POST",
            "/api/auth/login",
            {"access_code": "one-time-test-code"},
            {"Origin": "https://test.example"},
        )
        self.assertEqual(status, 200, body)
        cookie_header = headers["Set-Cookie"]
        self.assertIn("__Host-luminous_session=", cookie_header)
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("Secure", cookie_header)
        self.assertIn("SameSite=Lax", cookie_header)
        cookie = cookie_header.split(";", 1)[0]

        status, state, _ = self.request(
            "GET",
            "/api/state",
            headers={"Origin": "https://test.example", "Cookie": cookie},
        )
        self.assertEqual(status, 200, state)
        self.assertTrue((self.config.runtime_data_dir / "runtime.sqlite3").exists())

        self._stop_server()
        self._start_server()
        status, session, _ = self.request(
            "GET",
            "/api/auth/session",
            headers={"Origin": "https://test.example", "Cookie": cookie},
        )
        self.assertEqual(status, 200, session)
        self.assertTrue(session["authenticated"])

        status, _, headers = self.request(
            "POST",
            "/api/auth/logout",
            {},
            {"Origin": "https://test.example", "Cookie": cookie},
        )
        self.assertEqual(status, 200)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        status, _, _ = self.request(
            "GET",
            "/api/state",
            headers={"Origin": "https://test.example", "Cookie": cookie},
        )
        self.assertEqual(status, 401)

    def test_login_rejects_unlisted_origin(self):
        status, body, _ = self.request(
            "POST",
            "/api/auth/login",
            {"access_code": "one-time-test-code"},
            {"Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "origin_not_allowed")

    def test_repeated_invalid_codes_are_rate_limited(self):
        headers = {"Origin": "https://test.example"}
        for _ in range(5):
            status, _, _ = self.request("POST", "/api/auth/login", {"access_code": "wrong"}, headers)
            self.assertEqual(status, 401)
        status, body, response_headers = self.request(
            "POST",
            "/api/auth/login",
            {"access_code": "one-time-test-code"},
            headers,
        )
        self.assertEqual(status, 429)
        self.assertEqual(body["error"]["code"], "login_rate_limited")
        self.assertGreater(int(response_headers["Retry-After"]), 0)


if __name__ == "__main__":
    unittest.main()
