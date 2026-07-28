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
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore
from luminous.runtime.worker import CompanionWorker


class RuntimeHealthTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config = BackendConfig(
            project_root=self.root,
            env_path=self.root / ".env",
            frontend_dir=Path(__file__).resolve().parents[2] / "apps/companion-web/companion-ui",
            data_dir=self.root / "runtime",
            mock=True,
            deployment_mode="public",
            auth_token="admin-health-token",
            tester_access_code="tester-code",
            session_secret="session-secret",
            cors_origins=("https://test.example",),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_worker_tick_persists_a_successful_heartbeat(self):
        worker = CompanionWorker(self.config)
        result = worker.tick(enqueue_periodic=False, limit=0)
        health = worker.store.read_runtime_health("worker")
        self.assertEqual(result["claimed"], [])
        self.assertIsNotNone(health)
        self.assertEqual(health["consecutive_failures"], 0)
        self.assertTrue(health["last_success_at"])

    def test_deep_health_requires_admin_token_and_checks_worker(self):
        store = CompanionRuntimeStore(self.config.runtime_data_dir)
        store.record_runtime_health("worker", success=True)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.config))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/api/health/deep"
        try:
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(url, timeout=10)
            self.assertEqual(rejected.exception.code, 401)
            request = urllib.request.Request(url, headers={"Authorization": "Bearer admin-health-token"})
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["checks"]["database"]["writable"])
            self.assertTrue(payload["checks"]["worker"]["ready"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
