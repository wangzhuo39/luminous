import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from luminous.runtime.application.runtime import CompanionRuntime
from luminous.runtime.config import BackendConfig
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore
from luminous.runtime.worker import CompanionWorker


class RuntimeMaintenanceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.config = BackendConfig(
            project_root=root,
            env_path=root / ".env",
            frontend_dir=Path(__file__).resolve().parents[2] / "apps/companion-web/companion-ui",
            mock=True,
        )
        self.store = CompanionRuntimeStore(self.config.runtime_data_dir)
        self.runtime = CompanionRuntime(self.config, store=self.store)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_daily_maintenance_bounds_operational_records_only(self):
        now = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
        old = now - timedelta(days=40)
        old_iso = old.isoformat()

        succeeded_id = self.store.enqueue_job("old_success", run_after=old, idempotency_key="old-success")
        succeeded = self.store.claim_job(succeeded_id, now=old)
        self.assertIsNotNone(succeeded)
        self.store.complete_job(succeeded_id, {}, lease_token=succeeded["_job_lock_token"])
        failed_id = self.store.enqueue_job(
            "old_failure", run_after=old, idempotency_key="old-failure", max_attempts=1,
        )
        failed = self.store.claim_job(failed_id, now=old)
        self.assertIsNotNone(failed)
        self.store.fail_job(failed_id, "expected", lease_token=failed["_job_lock_token"])
        queued_id = self.store.enqueue_job("old_queued", run_after=old, idempotency_key="old-queued")
        self.store._execute(
            "UPDATE jobs SET updated_at = ? WHERE job_id IN (?, ?, ?)",
            (old_iso, succeeded_id, failed_id, queued_id),
        )

        completed = self.store.reserve_api_idempotency(
            "old-completed", "POST", "/api/tasks", now=old,
        )
        self.store.complete_api_idempotency(
            "old-completed", 201, "{}", reservation_token=completed["reservation_token"],
        )
        self.store.reserve_api_idempotency("old-abandoned", "POST", "/api/tasks", now=old)
        self.store._execute(
            "UPDATE api_idempotency SET updated_at = ? WHERE idempotency_key IN (?, ?)",
            (old_iso, "old-completed", "old-abandoned"),
        )

        self.store.create_auth_session("expired-session", old_iso, (old + timedelta(days=1)).isoformat())
        device = self.store.upsert_notification_device(token="old-disabled-device", now=old)
        self.store._execute(
            "UPDATE notification_devices SET status = 'disabled', updated_at = ? WHERE device_id = ?",
            (old_iso, str(device["device_id"])),
        )

        life_store = self.runtime.life_flow.store
        life_store.enqueue_audit_event({"event_id": "old-audit", "created_at": old_iso})
        life_store.mark_audit_delivered("old-audit", now=old)
        life_store.enqueue_effect("old-effect", "cancel_reminder", {"reminder_id": "none"}, now=old)
        life_store.mark_effect_delivered("old-effect", now=old)

        worker = CompanionWorker(self.config, runtime=self.runtime, store=self.store)
        result = worker.run_once(
            "runtime_maintenance", now=now, idempotency_key="test:runtime-maintenance",
        )

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["result"]["runtime"]["succeeded_jobs"], 1)
        self.assertEqual(result["result"]["runtime"]["failed_jobs"], 1)
        self.assertEqual(result["result"]["runtime"]["completed_idempotency"], 1)
        self.assertEqual(result["result"]["runtime"]["abandoned_idempotency"], 1)
        self.assertEqual(result["result"]["runtime"]["expired_sessions"], 1)
        self.assertEqual(result["result"]["runtime"]["disabled_devices"], 1)
        self.assertEqual(result["result"]["life_flow"], {"audit_outbox": 1, "effect_outbox": 1})
        self.assertIsNotNone(next((job for job in self.store.read_jobs() if job["job_id"] == queued_id), None))


if __name__ == "__main__":
    unittest.main()
