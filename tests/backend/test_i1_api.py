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
from luminous.runtime.application.notification_bridge import NotificationDelivery
from luminous.runtime.application.proactive_engine import ProactiveDecision
from luminous.runtime.config import BackendConfig
from luminous.runtime.domain.events import ProactiveSignal
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

    def test_android_notification_device_registration_is_private_and_idempotent(self):
        token = "android-fcm-token-for-test"
        status, first = self.request(
            "POST", "/api/notification-devices",
            {"token": token, "platform": "android", "provider": "fcm"},
        )
        self.assertEqual(status, 201)
        self.assertTrue(first["registered"])
        self.assertEqual(first["device"]["platform"], "android")
        self.assertNotIn(token, json.dumps(first))

        status, second = self.request(
            "POST", "/api/notification-devices",
            {"token": token, "platform": "android", "provider": "fcm"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(second["device"]["device_id"], first["device"]["device_id"])
        devices = self.server.RequestHandlerClass.service.runtime.store.read_notification_devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["token"], token)

    def test_android_notification_token_rotation_and_unregister(self):
        installation_id = "android-installation-test"
        status, first = self.request(
            "POST", "/api/notification-devices",
            {
                "token": "old-fcm-token", "platform": "android", "provider": "fcm",
                "installation_id": installation_id,
            },
        )
        self.assertEqual(status, 201)
        status, second = self.request(
            "POST", "/api/notification-devices",
            {
                "token": "new-fcm-token", "platform": "android", "provider": "fcm",
                "installation_id": installation_id,
            },
        )
        self.assertEqual(status, 201)
        store = self.server.RequestHandlerClass.service.runtime.store
        active = store.read_notification_devices(status="active")
        disabled = store.read_notification_devices(status="disabled")
        self.assertEqual([item["token"] for item in active], ["new-fcm-token"])
        self.assertEqual([item["token"] for item in disabled], ["old-fcm-token"])
        self.assertEqual(disabled[0]["last_error"], "token_rotated")

        device_id = second["device"]["device_id"]
        status, result = self.request("DELETE", f"/api/notification-devices/{device_id}")
        self.assertEqual(status, 200)
        self.assertTrue(result["unregistered"])
        self.assertNotIn("new-fcm-token", json.dumps(result))
        self.assertEqual(store.read_notification_devices(status="active"), [])

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
        conflict_status, conflict = self.request(
            "POST", "/api/tasks", {"title": "不同请求体", "priority": "normal"},
            {"Idempotency-Key": key},
        )
        self.assertEqual(conflict_status, 409)
        self.assertEqual(conflict["error"]["code"], "idempotency_conflict")

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

        with urllib.request.urlopen(self.base_url + "/", timeout=10) as response:
            landing = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("已迁移至 Android App", landing)
            self.assertIn("/downloads/luminous-android-debug.apk", landing)
            self.assertEqual(response.headers.get("Clear-Site-Data"), '"cache", "storage"')
        apk_path = "/downloads/luminous-android-debug.apk"
        with urllib.request.urlopen(urllib.request.Request(self.base_url + apk_path, method="HEAD"), timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get("Accept-Ranges"), "bytes")
            apk_size = int(response.headers["Content-Length"])
            self.assertGreater(apk_size, 0)
            self.assertEqual(response.read(), b"")
        with urllib.request.urlopen(
            urllib.request.Request(self.base_url + apk_path, headers={"Range": "bytes=0-15"}), timeout=10
        ) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers.get("Content-Range"), f"bytes 0-15/{apk_size}")
            self.assertEqual(len(response.read()), 16)
        with self.assertRaises(urllib.error.HTTPError) as retired:
            urllib.request.urlopen(self.base_url + "/js/main.js", timeout=10)
        self.assertEqual(retired.exception.code, 410)


class _FakeNotificationBridge:
    def __init__(self, delivery):
        self.delivery = delivery
        self.call_count = 0

    def deliver(self, **_kwargs):
        self.call_count += 1
        return self.delivery


class _DueProactiveEngine:
    def evaluate(self, *, now, trace_id, **_kwargs):
        return ProactiveDecision(
            signal=ProactiveSignal(
                due=True,
                score=0.9,
                reason="test_due_signal",
                next_check_minutes=30,
                draft_message="刚刚想起你，来看看你。",
                trace_id=trace_id,
                created_at=now.isoformat(),
            )
        )


class _FailAfterStateStore(CompanionRuntimeStore):
    fail_after_state = False

    def save_state(self, state):
        super().save_state(state)
        if self.fail_after_state:
            raise RuntimeError("injected_after_state_write")


class _FailAfterReminderRawStore(CompanionRuntimeStore):
    fail_reminder_raw = False

    def append_raw_message(self, **payload):
        super().append_raw_message(**payload)
        if self.fail_reminder_raw and str(payload.get("content", "")).startswith("提醒你："):
            raise RuntimeError("injected_after_reminder_raw")


class I1WorkerTest(unittest.TestCase):
    def test_notification_devices_stop_delivery_when_the_bound_session_expires(self):
        with tempfile.TemporaryDirectory() as td:
            store = CompanionRuntimeStore(Path(td) / "runtime")
            now = datetime.now(timezone.utc)
            store.create_auth_session(
                "session-digest",
                now.isoformat(),
                (now + timedelta(hours=1)).isoformat(),
            )
            store.upsert_notification_device(
                token="session-device-token",
                installation_id="session-device-installation",
                session_digest="session-digest",
                now=now,
            )
            self.assertEqual(len(store.read_notification_devices(now=now, session_idle_seconds=60)), 1)
            self.assertEqual(
                store.read_notification_devices(
                    now=now + timedelta(seconds=61), session_idle_seconds=60,
                ),
                [],
            )

    def test_chat_turn_rolls_back_all_persistence_on_late_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = BackendConfig(
                project_root=root,
                env_path=root / ".env",
                frontend_dir=Path(__file__).resolve().parents[2] / "apps/companion-web/companion-ui",
                mock=True,
            )
            store = _FailAfterStateStore(root / "runtime")
            initial_state = store.load_state().to_dict()
            store.fail_after_state = True
            runtime = CompanionRuntime(config, store=store)

            with self.assertRaisesRegex(RuntimeError, "injected_after_state_write"):
                runtime.chat("我喜欢雨天散步")

            self.assertEqual(store.read_raw_messages(), [])
            self.assertEqual(store.read_events(), [])
            self.assertEqual(store.read_memories(), [])
            self.assertEqual(store.load_state().to_dict(), initial_state)
            self.assertFalse(store.state_path.exists())

            store.fail_after_state = False
            result = runtime.chat("我喜欢雨天散步")
            self.assertTrue(result["reply"])
            self.assertEqual(len(store.read_raw_messages()), 2)
            self.assertGreater(len(store.read_events()), 0)
            self.assertGreater(len(store.read_memories()), 0)
            self.assertTrue(store.state_path.exists())

    def test_atomic_outbox_write_rolls_back_with_related_records(self):
        with tempfile.TemporaryDirectory() as td:
            store = CompanionRuntimeStore(Path(td) / "runtime")
            now = datetime.now(timezone.utc)
            event = NotificationDelivery(
                channel="internal", status="queued", attempted=False, ok=False,
                receipt_type="notification_queued", occurred_at=now.isoformat(),
            )
            with self.assertRaisesRegex(RuntimeError, "injected_outbox_failure"):
                with store.atomic():
                    store.append_outbox({
                        "message_id": "atomic-outbox",
                        "idempotency_key": "atomic-outbox",
                        "status": "queued",
                        "draft_text": "atomic",
                        "notification": event.to_dict(),
                    })
                    raise RuntimeError("injected_outbox_failure")
            self.assertEqual(store.read_outbox(), [])

    def test_reminder_queue_rolls_back_outbox_event_and_message_together(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = BackendConfig(
                project_root=root,
                env_path=root / ".env",
                frontend_dir=Path(__file__).resolve().parents[2] / "apps/companion-web/companion-ui",
                mock=True,
            )
            store = _FailAfterReminderRawStore(root / "runtime")
            runtime = CompanionRuntime(config, store=store)
            now = datetime.now(timezone.utc)
            runtime.create_reminder({
                "title": "事务提醒",
                "due_at": (now - timedelta(minutes=1)).isoformat(),
            })
            baseline_events = len(store.read_events())
            baseline_messages = len(store.read_raw_messages())
            store.fail_reminder_raw = True

            with self.assertRaisesRegex(RuntimeError, "injected_after_reminder_raw"):
                runtime.process_due_reminders(now=now)

            self.assertEqual(store.read_outbox(), [])
            self.assertEqual(len(store.read_events()), baseline_events)
            self.assertEqual(len(store.read_raw_messages()), baseline_messages)

            store.fail_reminder_raw = False
            result = runtime.process_due_reminders(now=now)
            self.assertEqual(len(result["queued"]), 1)
            self.assertEqual(len(store.read_outbox()), 1)

    def test_proactive_tick_persists_before_worker_delivers_once(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = BackendConfig(
                project_root=root,
                env_path=root / ".env",
                frontend_dir=Path(__file__).resolve().parents[2] / "apps/companion-web/companion-ui",
                mock=True,
            )
            store = CompanionRuntimeStore(root / "runtime")
            now = datetime(2026, 8, 5, 6, 0, tzinfo=timezone.utc)
            runtime = CompanionRuntime(config, store=store)
            runtime.proactive_engine = _DueProactiveEngine()
            bridge = _FakeNotificationBridge(NotificationDelivery(
                channel="fcm", status="delivered", attempted=True, ok=True,
                receipt_type="notification_delivered", occurred_at=now.isoformat(), provider="fcm",
            ))
            runtime.notification_bridge = bridge

            result = runtime.proactive_tick(send=True, now=now)

            self.assertTrue(result["due"])
            self.assertEqual(result["notification"]["status"], "queued")
            self.assertEqual(bridge.call_count, 0)
            queued = store.read_outbox(limit=10)
            self.assertEqual(len(queued), 1)
            self.assertEqual(queued[0]["status"], "queued")
            self.assertEqual(queued[0]["delivery_attempts"], 0)

            worker = CompanionWorker(config, runtime=runtime, store=store)
            delivery_result = worker.run_once(
                "outbox_delivery", now=now, idempotency_key="proactive:delivery:test",
            )

            self.assertEqual(delivery_result["status"], "succeeded")
            self.assertEqual(bridge.call_count, 1)
            delivered = store.read_outbox(limit=10)
            self.assertEqual(delivered[0]["status"], "delivered")
            self.assertEqual(delivered[0]["delivery_attempts"], 1)

    def test_concurrent_store_initialization_serializes_schema_migrations(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            barrier = threading.Barrier(6)
            errors = []

            def initialize():
                try:
                    barrier.wait(timeout=5)
                    CompanionRuntimeStore(runtime_dir)
                except Exception as exc:  # noqa: BLE001 - asserted below.
                    errors.append(exc)

            threads = [threading.Thread(target=initialize) for _ in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            self.assertEqual(errors, [])
            self.assertTrue((runtime_dir / "runtime.sqlite3").is_file())

    def test_outbox_claim_lease_is_exclusive_and_recoverable(self):
        with tempfile.TemporaryDirectory() as td:
            store = CompanionRuntimeStore(Path(td) / "runtime")
            now = datetime.now(timezone.utc)
            store.append_outbox({
                "message_id": "lease-message",
                "draft_text": "只应由一个 worker 领取",
                "status": "queued",
                "created_at": now.isoformat(),
                "idempotency_key": "lease-message-once",
            })

            first = store.claim_deliverable_outbox(now=now, lease_seconds=120)
            second = store.claim_deliverable_outbox(now=now, lease_seconds=120)
            self.assertEqual([item["message_id"] for item in first], ["lease-message"])
            self.assertEqual(second, [])

            recovered = store.claim_deliverable_outbox(
                now=now + timedelta(seconds=121), lease_seconds=120,
            )
            self.assertEqual([item["message_id"] for item in recovered], ["lease-message"])
            self.assertNotEqual(
                first[0]["_delivery_lock_token"],
                recovered[0]["_delivery_lock_token"],
            )
            delivery = NotificationDelivery(
                channel="fcm", status="delivered", attempted=True, ok=True,
                receipt_type="notification_delivered", occurred_at=now.isoformat(), provider="fcm",
            ).to_dict()
            self.assertIsNone(store.update_outbox_delivery(
                "lease-message", delivery, now=now,
                lease_token=first[0]["_delivery_lock_token"],
            ))
            updated = store.update_outbox_delivery(
                "lease-message", delivery, now=now + timedelta(seconds=121),
                lease_token=recovered[0]["_delivery_lock_token"],
            )
            self.assertIsNotNone(updated)
            self.assertEqual(updated["status"], "delivered")

    def test_daily_reminder_queues_each_occurrence_once(self):
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
            created = runtime.create_reminder({
                "title": "每天喝水",
                "due_at": (now - timedelta(minutes=1)).isoformat(),
                "recurrence": "daily",
            })
            reminder_id = str(created["reminder"]["reminder_id"])
            first_result = runtime.process_due_reminders(now=now)
            self.assertEqual(len(first_result["queued"]), 1)

            runtime.notification_bridge = _FakeNotificationBridge(NotificationDelivery(
                channel="fcm", status="delivered", attempted=True, ok=True,
                receipt_type="notification_delivered", occurred_at=now.isoformat(), provider="fcm",
            ))
            worker = CompanionWorker(config, runtime=runtime, store=store)
            worker.run_once("outbox_delivery", now=now, idempotency_key="daily:first")
            rescheduled = store.get_reminder(reminder_id)
            self.assertIsNotNone(rescheduled)
            self.assertEqual(rescheduled.delivery_count, 1)

            second_now = datetime.fromisoformat(rescheduled.due_at) + timedelta(minutes=1)
            second_result = runtime.process_due_reminders(now=second_now)
            self.assertEqual(len(second_result["queued"]), 1)
            messages = store.read_outbox(limit=10)
            self.assertEqual(len(messages), 2)
            self.assertEqual(len({item["message_id"] for item in messages}), 2)
            self.assertEqual(len({item["idempotency_key"] for item in messages}), 2)

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
            self.assertEqual(messages[0]["status"], "queued")
            self.assertEqual(messages[0]["delivery_attempts"], 0)
            self.assertEqual(store.read_reminders(limit=10)[0].delivery_count, 0)
            self.assertIn("提醒你：到期提醒", store.read_raw_messages(limit=10, role="assistant")[0]["content"])

    def test_outbox_marks_reminder_delivered_only_after_provider_success(self):
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
            reminder = runtime.create_reminder({
                "title": "真实投递提醒",
                "due_at": (now - timedelta(minutes=1)).isoformat(),
            })
            runtime.process_due_reminders(now=now)
            runtime.notification_bridge = _FakeNotificationBridge(
                NotificationDelivery(
                    channel="fcm", status="delivered", attempted=True, ok=True,
                    receipt_type="notification_delivered", occurred_at=now.isoformat(), provider="fcm",
                )
            )
            worker = CompanionWorker(config, runtime=runtime, store=store)
            result = worker.run_once("outbox_delivery", now=now, idempotency_key="i1:delivery-success")
            self.assertEqual(result["status"], "succeeded", result)
            message = store.read_outbox(limit=1)[0]
            self.assertEqual(message["status"], "delivered")
            self.assertEqual(message["delivery_attempts"], 1)
            self.assertTrue(message["delivered_at"])
            delivered_reminder = store.get_reminder(str(reminder["reminder"]["reminder_id"]))
            self.assertIsNotNone(delivered_reminder)
            self.assertEqual(delivered_reminder.delivery_count, 1)

    def test_outbox_retries_attempted_provider_failure(self):
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
            runtime.create_reminder({"title": "稍后重试", "due_at": (now - timedelta(minutes=1)).isoformat()})
            runtime.process_due_reminders(now=now)
            runtime.notification_bridge = _FakeNotificationBridge(
                NotificationDelivery(
                    channel="fcm", status="failed", attempted=True, ok=False,
                    receipt_type="notification_failed", detail="temporary", occurred_at=now.isoformat(), provider="fcm",
                )
            )
            worker = CompanionWorker(config, runtime=runtime, store=store)
            worker.run_once("outbox_delivery", now=now, idempotency_key="i1:delivery-failure")
            message = store.read_outbox(limit=1)[0]
            self.assertEqual(message["status"], "retrying")
            self.assertEqual(message["delivery_attempts"], 1)
            self.assertEqual(message["last_error"], "temporary")
            self.assertTrue(message["next_attempt_at"])

    def test_outbox_persists_per_device_delivery_progress_for_retry(self):
        with tempfile.TemporaryDirectory() as td:
            store = CompanionRuntimeStore(Path(td) / "runtime")
            now = datetime.now(timezone.utc)
            store.append_outbox({
                "message_id": "multi-device-message",
                "draft_text": "你好",
                "status": "queued",
                "created_at": now.isoformat(),
                "idempotency_key": "multi-device-message",
            })
            claimed = store.claim_deliverable_outbox(now=now)
            updated = store.update_outbox_delivery(
                "multi-device-message",
                NotificationDelivery(
                    channel="fcm", status="failed", attempted=True, ok=False,
                    receipt_type="notification_failed", detail="one device timed out",
                    occurred_at=now.isoformat(), provider="fcm",
                    metadata={"delivered_device_ids": ["device-safe-id"]},
                ).to_dict(),
                now=now,
                lease_token=claimed[0]["_delivery_lock_token"],
            )
            self.assertEqual(updated["status"], "retrying")
            self.assertEqual(
                updated["payload"]["delivery_progress"]["delivered_device_ids"],
                ["device-safe-id"],
            )
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

    def test_job_lease_recovers_after_worker_crash_and_rejects_stale_completion(self):
        with tempfile.TemporaryDirectory() as td:
            store = CompanionRuntimeStore(Path(td) / "runtime")
            now = datetime.now(timezone.utc)
            job_id = store.enqueue_job(
                "unknown_job", {}, run_after=now, max_attempts=2,
                idempotency_key="crash-recovery",
            )
            first = store.claim_job(job_id, now=now, lease_seconds=1)
            self.assertIsNotNone(first)
            self.assertIsNone(store.claim_job(job_id, now=now, lease_seconds=1))

            recovered = store.claim_job(
                job_id, now=now + timedelta(seconds=2), lease_seconds=30,
            )
            self.assertIsNotNone(recovered)
            self.assertEqual(recovered["attempts"], 2)
            self.assertFalse(store.complete_job(
                job_id, {"worker": "stale"},
                lease_token=first["_job_lock_token"],
            ))
            self.assertTrue(store.complete_job(
                job_id, {"worker": "recovered"},
                lease_token=recovered["_job_lock_token"],
            ))

            exhausted_id = store.enqueue_job(
                "unknown_job", {}, run_after=now, max_attempts=1,
                idempotency_key="crash-exhausted",
            )
            exhausted = store.claim_job(exhausted_id, now=now, lease_seconds=1)
            self.assertIsNotNone(exhausted)
            self.assertEqual(
                store.claim_due_jobs(now=now + timedelta(seconds=2), limit=10),
                [],
            )
            exhausted_row = next(
                item for item in store.read_jobs(limit=10) if item["job_id"] == exhausted_id
            )
            self.assertEqual(exhausted_row["status"], "failed")
            self.assertEqual(exhausted_row["last_error"], "worker_lease_expired")

    def test_completed_job_idempotency_key_does_not_requeue(self):
        with tempfile.TemporaryDirectory() as td:
            store = CompanionRuntimeStore(Path(td) / "runtime")
            now = datetime.now(timezone.utc)
            job_id = store.enqueue_job(
                "unknown_job", {}, run_after=now, idempotency_key="completed-once",
            )
            claimed = store.claim_job(job_id, now=now)
            self.assertIsNotNone(claimed)
            self.assertTrue(store.complete_job(
                job_id, {}, lease_token=claimed["_job_lock_token"],
            ))
            self.assertEqual(
                store.enqueue_job(
                    "unknown_job", {"second": True}, run_after=now,
                    idempotency_key="completed-once",
                ),
                job_id,
            )
            self.assertIsNone(store.claim_job(job_id, now=now))
            current = next(item for item in store.read_jobs(limit=10) if item["job_id"] == job_id)
            self.assertEqual(current["status"], "succeeded")

    def test_api_idempotency_lease_recovers_and_rejects_stale_completion(self):
        with tempfile.TemporaryDirectory() as td:
            store = CompanionRuntimeStore(Path(td) / "runtime")
            now = datetime.now(timezone.utc)
            first = store.reserve_api_idempotency("request-key", "POST", "/api/tasks", now=now)
            self.assertEqual(first["state"], "reserved")
            self.assertEqual(
                store.reserve_api_idempotency(
                    "request-key", "POST", "/api/tasks", now=now + timedelta(seconds=30),
                )["state"],
                "in_flight",
            )
            recovered = store.reserve_api_idempotency(
                "request-key", "POST", "/api/tasks", now=now + timedelta(seconds=121),
            )
            self.assertEqual(recovered["state"], "reserved")
            self.assertNotEqual(first["reservation_token"], recovered["reservation_token"])
            self.assertFalse(store.complete_api_idempotency(
                "request-key", 201, '{"stale":true}',
                reservation_token=first["reservation_token"],
            ))
            self.assertTrue(store.complete_api_idempotency(
                "request-key", 201, '{"ok":true}',
                reservation_token=recovered["reservation_token"],
            ))
            completed = store.reserve_api_idempotency(
                "request-key", "POST", "/api/tasks", now=now + timedelta(seconds=122),
            )
            self.assertEqual(completed["state"], "completed")
            self.assertEqual(completed["response_json"], '{"ok":true}')
            self.assertEqual(
                store.reserve_api_idempotency(
                    "request-key", "POST", "/api/reminders", now=now + timedelta(seconds=300),
                )["state"],
                "conflict",
            )
            body_bound = store.reserve_api_idempotency(
                "body-key", "POST", "/api/tasks",
                request_fingerprint="body-a", now=now,
            )
            self.assertEqual(body_bound["state"], "reserved")
            self.assertEqual(
                store.reserve_api_idempotency(
                    "body-key", "POST", "/api/tasks",
                    request_fingerprint="body-b", now=now + timedelta(seconds=300),
                )["state"],
                "conflict",
            )

    def test_run_once_claims_its_exact_job_not_older_backlog(self):
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
            backlog_id = store.enqueue_job(
                "unknown_job", {"backlog": True},
                run_after=now - timedelta(minutes=1), idempotency_key="older-backlog",
            )
            worker = CompanionWorker(config, store=store, runtime=CompanionRuntime(config, store=store))
            result = worker.run_once(
                "unknown_job", {"manual": True}, now=now, idempotency_key="exact-manual",
            )
            self.assertNotEqual(result["job_id"], backlog_id)
            self.assertEqual(result["status"], "succeeded")
            backlog = next(item for item in store.read_jobs(limit=10) if item["job_id"] == backlog_id)
            self.assertEqual(backlog["status"], "queued")

    def test_periodic_jobs_coalesce_without_consuming_manual_jobs(self):
        with tempfile.TemporaryDirectory() as td:
            store = CompanionRuntimeStore(Path(td) / "runtime")
            now = datetime.now(timezone.utc)
            manual_id = store.enqueue_job(
                "outbox_delivery", {"manual": True},
                run_after=now - timedelta(minutes=2), idempotency_key="manual-outbox",
            )
            old_id = store.enqueue_job(
                "outbox_delivery", {"scheduled": True, "cadence_minutes": 1},
                run_after=now - timedelta(minutes=1), idempotency_key="outbox_delivery:old",
            )
            new_id = store.enqueue_job(
                "outbox_delivery", {"scheduled": True, "cadence_minutes": 1},
                run_after=now, idempotency_key="outbox_delivery:new",
            )
            jobs = {item["job_id"]: item for item in store.read_jobs(limit=10)}
            self.assertEqual(jobs[manual_id]["status"], "queued")
            self.assertEqual(jobs[old_id]["status"], "succeeded")
            self.assertEqual(
                jobs[old_id]["payload"],
                {"skipped": True, "reason": "superseded_by_newer_periodic_job"},
            )
            self.assertEqual(jobs[new_id]["status"], "queued")


if __name__ == "__main__":
    unittest.main()
