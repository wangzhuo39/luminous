import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

from luminous.runtime.application.runtime import CompanionRuntime
from luminous.runtime.config import BackendConfig
from luminous.runtime.infrastructure.http import make_handler
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore
from luminous.runtime.worker import CompanionWorker


FORBIDDEN_KEYS = {
    "trace_id",
    "turn_id",
    "role_thinking",
    "role_action",
    "system_thinking",
    "analysis",
    "prompt",
    "ledger",
    "recent_events",
    "raw_messages",
    "job_count",
    "jobs",
}


def _find_forbidden(value):
    found = set()
    if isinstance(value, dict):
        found.update(set(value).intersection(FORBIDDEN_KEYS))
        for item in value.values():
            found.update(_find_forbidden(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_forbidden(item))
    return found


class I1HTTPTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.config = BackendConfig(
            project_root=root,
            env_path=root / ".env",
            frontend_dir=Path(__file__).resolve().parents[2] / "apps/companion-web/companion-ui",
            mock=True,
        )
        self._start_server()

    def tearDown(self):
        self._stop_server()
        self.temp_dir.cleanup()

    def _start_server(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.config))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def _stop_server(self):
        if getattr(self, "server", None):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)

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
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def assert_public(self, payload):
        self.assertEqual(_find_forbidden(payload), set(), payload)

    def test_public_dto_validation_idempotency_and_restart(self):
        status, health = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(set(health), {"ok", "status"})

        status, chat = self.request("POST", "/api/chat", {"message": "我喜欢雨天散步，请记住。", "history": []})
        self.assertEqual(status, 200)
        self.assert_public(chat)
        self.assertEqual(set(chat), {"reply", "presence", "state"})

        status, state = self.request("GET", "/api/state?include=history")
        self.assertEqual(status, 200)
        self.assert_public(state)
        self.assertEqual(set(state), {"state", "history"})
        self.assertEqual(len(state["history"]["items"]), 2)

        status, memories = self.request("GET", f"/api/memory?q={urllib.parse.quote('雨天')}&limit=10")
        self.assertEqual(status, 200)
        self.assertTrue(memories["hits"])
        memory_id = memories["hits"][0]["memory_id"]
        status, updated_memory = self.request(
            "POST",
            "/api/memory/update",
            {"memory_id": memory_id, "updates": {"text": "我喜欢雨后散步。"}},
            {"Idempotency-Key": "i1-memory-update"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated_memory["memory"]["text"], "我喜欢雨后散步。")
        self.assert_public(updated_memory)

        key = "i1-task-create"
        payload = {"title": "只创建一次", "priority": "normal"}
        first_status, first = self.request("POST", "/api/tasks", payload, {"Idempotency-Key": key})
        second_status, second = self.request("POST", "/api/tasks", payload, {"Idempotency-Key": key})
        self.assertEqual((first_status, second_status), (201, 201))
        self.assertEqual(first, second)
        self.assert_public(first)

        status, tasks = self.request("GET", "/api/tasks?limit=0")
        self.assertEqual(status, 400)
        self.assertEqual(tasks["error"]["code"], "invalid_request")
        self.assertIn("retryable", tasks["error"])

        for path in ("/api/ledger", "/api/trace", "/api/jobs", "/api/export", "/api/memory/threads"):
            status, body = self.request("GET", path)
            self.assertEqual(status, 404, path)
            self.assert_public(body)

        self._stop_server()
        self._start_server()
        status, restored = self.request("GET", "/api/tasks?limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(len(restored["items"]), 1)
        status, history = self.request("GET", "/api/chat/history?limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(len(history["items"]), 2)
        self.assert_public(history)
        status, memories = self.request("GET", f"/api/memory?q={urllib.parse.quote('雨后')}&limit=10")
        self.assertEqual(status, 200)
        self.assertTrue(memories["hits"])
        status, forgotten = self.request(
            "POST",
            "/api/memory/forget",
            {"memory_id": memory_id, "hard_delete": False},
            {"Idempotency-Key": "i1-memory-forget"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(forgotten["ok"])
        self.assert_public(forgotten)

    def test_life_flow_and_action_preview_confirm(self):
        created = {}
        cases = {
            "task": ("/api/tasks", {"title": "联调任务", "description": "描述", "priority": "normal"}),
            "routine": ("/api/routines", {"title": "联调例行", "schedule": "daily", "reminder_policy": "none"}),
            "activity": ("/api/activities", {"title": "联调活动"}),
            "diary": ("/api/diary-entries", {"title": "联调日记", "body": "今天完成联调", "date": "2026-07-26"}),
            "reminder": ("/api/reminders", {"title": "联调提醒", "due_at": "2026-07-27T09:00:00+00:00"}),
            "event": ("/api/calendar-events", {"title": "联调日历", "starts_at": "2026-07-27T10:00:00+00:00"}),
        }
        for name, (path, payload) in cases.items():
            status, body = self.request("POST", path, payload, {"Idempotency-Key": f"i1-{name}"})
            self.assertEqual(status, 201, (name, body))
            self.assertTrue(body.get("ok"), (name, body))
            self.assert_public(body)
            created[name] = body

        routine_id = created["routine"]["routine"]["routine_id"]
        status, checkin = self.request(
            "POST",
            f"/api/routines/{routine_id}/checkins",
            {"period_key": "2026-07-26", "note": "完成"},
            {"Idempotency-Key": "i1-routine-checkin"},
        )
        self.assertEqual(status, 200, checkin)
        self.assert_public(checkin)

        for path in ("/api/today", "/api/timeline", "/api/tasks", "/api/routines", "/api/activities", "/api/diary-entries", "/api/reminders", "/api/calendar-events", "/api/outbox"):
            status, body = self.request("GET", path)
            self.assertEqual(status, 200, path)
            self.assert_public(body)

        self.server.RequestHandlerClass.service.runtime.store.append_outbox({
            "message_id": "i1-outbox",
            "draft_text": "一封真实来信",
            "status": "drafted",
            "idempotency_key": "i1-outbox-once",
        })
        status, receipt = self.request(
            "POST",
            "/api/outbox/receipt",
            {"message_id": "i1-outbox", "receipt_type": "read"},
            {"Idempotency-Key": "i1-outbox-read"},
        )
        self.assertEqual(status, 200)
        self.assert_public(receipt)
        status, feedback = self.request(
            "POST",
            "/api/outbox/feedback",
            {"message_id": "i1-outbox", "status": "helpful"},
            {"Idempotency-Key": "i1-outbox-helpful"},
        )
        self.assertEqual(status, 200)
        self.assert_public(feedback)

        status, preferences = self.request("GET", "/api/settings/notifications")
        self.assertEqual(status, 200)
        self.assert_public(preferences)
        status, preferences = self.request("PATCH", "/api/settings/notifications", {"enabled": False}, {"Idempotency-Key": "i1-notifications"})
        self.assertEqual(status, 200)
        self.assertFalse(preferences["enabled"])
        self.assert_public(preferences)

        status, preview = self.request("POST", "/api/actions/preview", {"action": "create_task", "payload": {"title": "预览任务"}})
        self.assertEqual(status, 200)
        self.assertTrue(preview["confirmation_required"])
        self.assert_public(preview)
        status, confirmed = self.request(
            "POST",
            "/api/actions/confirm",
            {"action": preview["action"], "payload": preview["payload"], "confirmed": True},
            {"Idempotency-Key": "i1-action-confirm"},
        )
        self.assertEqual(status, 200, confirmed)
        self.assertTrue(confirmed["ok"])
        self.assert_public(confirmed)

    def test_public_mode_requires_bearer_and_origin(self):
        self._stop_server()
        self.config = BackendConfig(
            project_root=self.config.project_root,
            env_path=self.config.env_path,
            frontend_dir=self.config.frontend_dir,
            mock=True,
            deployment_mode="public",
            auth_token="test-token",
            cors_origins=("https://app.example",),
        )
        self._start_server()
        status, _ = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        status, body = self.request("GET", "/api/state")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "authentication_required")
        status, state = self.request("GET", "/api/state", headers={"Authorization": "Bearer test-token", "Origin": "https://app.example"})
        self.assertEqual(status, 200)
        self.assert_public(state)
        status, body = self.request("GET", "/api/state", headers={"Authorization": "Bearer test-token", "Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "origin_not_allowed")


class I1WorkerTest(unittest.TestCase):
    def test_due_proactive_and_outbox_delivery_jobs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = BackendConfig(
                project_root=root,
                env_path=root / ".env",
                frontend_dir=Path(__file__).resolve().parents[2] / "apps/companion-web/companion-ui",
                mock=True,
            )
            store = CompanionRuntimeStore(root / "runtime")
            now = datetime.now(timezone.utc)
            runtime = CompanionRuntime(config, store=store)
            runtime.create_reminder({
                "title": "到期提醒",
                "due_at": (now - timedelta(minutes=1)).isoformat(),
            })
            worker = CompanionWorker(config, runtime=runtime, store=store)
            for job_type in ("reminder_due_tick", "proactive_tick", "outbox_delivery"):
                result = worker.run_once(job_type, now=now, idempotency_key=f"i1:{job_type}")
                self.assertEqual(result["status"], "succeeded", result)
            messages = store.read_outbox(limit=10)
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["status"], "sent")

    def test_job_idempotency_retry_and_outbox_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = CompanionRuntimeStore(root / "runtime")
            now = datetime.now(timezone.utc)
            job_id = store.enqueue_job("unknown_job", {}, run_after=now, idempotency_key="job-once")
            self.assertEqual(store.enqueue_job("unknown_job", {}, run_after=now, idempotency_key="job-once"), job_id)
            store.complete_job(job_id, {})
            config = BackendConfig(project_root=root, env_path=root / ".env", frontend_dir=Path(__file__).resolve().parents[2] / "apps/companion-web/companion-ui", mock=True)
            worker = CompanionWorker(config, store=store, runtime=CompanionRuntime(config, store=store))
            result = worker.run_once("unknown_job", now=now, idempotency_key="worker-once")
            self.assertEqual(result["status"], "succeeded")

            retry_job = store.enqueue_job("unknown_job", {}, run_after=now, max_attempts=2, idempotency_key="retry-once")
            job = next(item for item in store.claim_due_jobs(now=now, limit=10) if item["job_id"] == retry_job)
            self.assertTrue(store.fail_job(job["job_id"], "temporary"))
            retried = next(item for item in store.read_jobs(limit=20) if item["job_id"] == retry_job)
            self.assertEqual(retried["status"], "queued")
            self.assertEqual(retried["attempts"], 1)

            outbox = {"message_id": "out-once", "draft_text": "hello", "status": "queued", "idempotency_key": "outbox-once"}
            store.append_outbox(outbox)
            store.record_outbox_feedback("out-once", "sent")
            store.append_outbox(outbox)
            self.assertEqual(store.read_outbox(limit=10)[0]["status"], "sent")


if __name__ == "__main__":
    unittest.main()
