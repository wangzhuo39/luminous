import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from luminous.runtime.application.runtime import CompanionRuntime
from luminous.runtime.config import BackendConfig
from luminous.runtime.domain.state import CompanionState
from luminous.runtime.infrastructure.http import make_handler


class CompanionSettingsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.frontend = Path(__file__).resolve().parents[2] / "apps/companion-web/companion-ui"

    def tearDown(self):
        self.temp_dir.cleanup()

    def config(self, **updates):
        values = {
            "project_root": self.root,
            "env_path": self.root / ".env",
            "frontend_dir": self.frontend,
            "data_dir": self.root / "runtime",
            "mock": True,
        }
        values.update(updates)
        return BackendConfig(**values)

    def test_settings_persist_apply_to_prompt_and_never_return_api_key(self):
        secret = "sk-user-secret-that-must-not-leak"
        runtime = CompanionRuntime(self.config())
        result = runtime.update_companion_settings({
            "base_url": "https://llm.example.test/v1",
            "api_key": secret,
            "model": "companion-model",
            "temperature": 0.4,
            "max_tokens": 1200,
            "companion_prompt": "叫我阿澈，说话简短、诚实，不替我做决定。",
        })

        self.assertNotIn(secret, json.dumps(result, ensure_ascii=False))
        self.assertTrue(result["llm"]["api_key_configured"])
        self.assertTrue(result["llm"]["configured"])
        self.assertEqual(result["companion"]["instructions"], "叫我阿澈，说话简短、诚实，不替我做决定。")

        restarted = CompanionRuntime(self.config())
        self.assertEqual(restarted.config.base_url, "https://llm.example.test/v1")
        self.assertEqual(restarted.config.api_key, secret)
        self.assertEqual(restarted.config.model, "companion-model")
        package = restarted.prompt_builder.build(
            user_text="晚上好",
            history=[],
            state=CompanionState(),
            memory_hits=[],
            recent_events=[],
        )
        system_text = "\n".join(message["content"] for message in package.messages if message["role"] == "system")
        self.assertIn("叫我阿澈", system_text)
        self.assertNotIn(secret, system_text)

    def test_settings_validate_url_ranges_and_explicit_key_clear(self):
        runtime = CompanionRuntime(self.config(api_key="server-default-key"))
        with self.assertRaisesRegex(ValueError, "http or https"):
            runtime.update_companion_settings({"base_url": "file:///tmp/model"})
        with self.assertRaisesRegex(ValueError, "between 0 and 2"):
            runtime.update_companion_settings({"temperature": 3})
        with self.assertRaisesRegex(ValueError, "between 1 and 32768"):
            runtime.update_companion_settings({"max_tokens": 0})
        result = runtime.update_companion_settings({"clear_api_key": True})
        self.assertFalse(result["llm"]["api_key_configured"])

    def test_http_get_and_patch_are_persistent_and_redacted(self):
        config = self.config(
            deployment_mode="public",
            auth_token="android-test-token",
            cors_origins=("https://localhost",),
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"

        def request(method, body=None):
            payload = None if body is None else json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url}/api/settings/companion",
                data=payload,
                method=method,
                headers={
                    "Authorization": "Bearer android-test-token",
                    "Content-Type": "application/json",
                    "Origin": "https://localhost",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read()), dict(response.headers.items())

        try:
            secret = "sk-http-secret"
            preflight = urllib.request.Request(
                f"{base_url}/api/settings/companion",
                method="OPTIONS",
                headers={
                    "Origin": "https://localhost",
                    "Access-Control-Request-Method": "PATCH",
                },
            )
            with urllib.request.urlopen(preflight, timeout=10) as response:
                self.assertEqual(response.status, 204)
                self.assertEqual(response.headers["Access-Control-Allow-Origin"], "https://localhost")

            status, saved, headers = request("PATCH", {
                "base_url": "https://gateway.example/v1",
                "api_key": secret,
                "model": "model-v2",
                "companion_prompt": "温柔，但不要假装知道我没说过的事。",
            })
            self.assertEqual(status, 200)
            self.assertEqual(headers["Access-Control-Allow-Origin"], "https://localhost")
            self.assertNotIn(secret, json.dumps(saved, ensure_ascii=False))
            status, loaded, headers = request("GET")
            self.assertEqual(status, 200)
            self.assertEqual(headers["Access-Control-Allow-Origin"], "https://localhost")
            self.assertEqual(loaded["llm"]["model"], "model-v2")
            self.assertTrue(loaded["llm"]["api_key_configured"])
            self.assertNotIn(secret, json.dumps(loaded, ensure_ascii=False))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
