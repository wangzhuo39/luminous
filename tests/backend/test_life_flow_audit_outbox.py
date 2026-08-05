import tempfile
import unittest
from pathlib import Path

from luminous.runtime.application.runtime import CompanionRuntime
from luminous.runtime.config import BackendConfig
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore
from luminous.runtime.worker import CompanionWorker


class FailingAuditRuntimeStore(CompanionRuntimeStore):
    def __init__(self, base_dir: Path) -> None:
        super().__init__(base_dir)
        self.fail_life_flow_audits = True

    def append_event(self, event):
        if self.fail_life_flow_audits and event.event_type == "task_created":
            raise RuntimeError("injected runtime audit failure")
        return super().append_event(event)


class LifeFlowAuditOutboxTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.config = BackendConfig(
            project_root=root,
            env_path=root / ".env",
            frontend_dir=Path(__file__).resolve().parents[2] / "apps/companion-web/companion-ui",
            mock=True,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_domain_mutation_rolls_back_when_audit_intent_cannot_be_persisted(self):
        runtime = CompanionRuntime(self.config)
        store = runtime.life_flow.store
        original_enqueue = store.enqueue_audit_event

        def fail_enqueue(_event):
            raise RuntimeError("injected audit outbox failure")

        store.enqueue_audit_event = fail_enqueue
        with self.assertRaisesRegex(RuntimeError, "audit outbox failure"):
            runtime.create_task({
                "title": "must roll back",
                "due_at": "2026-08-06T09:00:00+00:00",
                "create_reminder": True,
            })
        store.enqueue_audit_event = original_enqueue

        self.assertEqual(store.read_tasks(), [])
        self.assertEqual(store.read_pending_audit_events(), [])
        self.assertEqual(store.read_pending_effects(), [])
        self.assertEqual(runtime.store.read_reminders(), [])

    def test_worker_replays_audit_after_runtime_store_recovers_and_restart(self):
        failing_store = FailingAuditRuntimeStore(self.config.runtime_data_dir)
        runtime = CompanionRuntime(self.config, store=failing_store)

        result = runtime.create_task({"title": "durable task"})

        self.assertTrue(result["ok"])
        self.assertEqual(len(runtime.life_flow.store.read_tasks()), 1)
        pending = runtime.life_flow.store.read_pending_audit_events()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["status"], "retrying")
        self.assertEqual(pending[0]["attempts"], 1)
        self.assertEqual(pending[0]["last_error"], "RuntimeError")

        recovered_store = CompanionRuntimeStore(self.config.runtime_data_dir)
        recovered_runtime = CompanionRuntime(self.config, store=recovered_store)
        worker = CompanionWorker(self.config, runtime=recovered_runtime, store=recovered_store)
        delivery = worker.run_once(
            "life_flow_audit_delivery",
            idempotency_key="test:life-flow-audit-recovery",
        )

        self.assertEqual(delivery["status"], "succeeded")
        self.assertEqual(delivery["result"]["attempted"], 1)
        self.assertEqual(len(delivery["result"]["delivered"]), 1)
        self.assertEqual(recovered_runtime.life_flow.store.read_pending_audit_events(), [])
        task_events = [
            event for event in recovered_store.read_events(limit=50)
            if event.event_type == "task_created"
        ]
        self.assertEqual(len(task_events), 1)

        duplicate = recovered_runtime.life_flow.flush_audit_outbox()
        self.assertEqual(duplicate["attempted"], 0)
        task_events = [
            event for event in recovered_store.read_events(limit=50)
            if event.event_type == "task_created"
        ]
        self.assertEqual(len(task_events), 1)

    def test_scheduling_effect_survives_failure_and_worker_replays_once(self):
        runtime = CompanionRuntime(self.config)
        original_create_reminder = runtime.scheduling.create_reminder

        def fail_create_reminder(_payload):
            raise RuntimeError("injected scheduling failure")

        runtime.scheduling.create_reminder = fail_create_reminder
        result = runtime.create_task({
            "title": "replay my reminder",
            "due_at": "2026-08-06T09:00:00+00:00",
            "create_reminder": True,
        })

        self.assertTrue(result["ok"])
        reminder_id = result["task"]["reminder_ids"][0]
        self.assertIsNone(runtime.store.get_reminder(reminder_id))
        pending = runtime.life_flow.store.read_pending_effects()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["status"], "retrying")
        self.assertEqual(pending[0]["last_error"], "RuntimeError")

        runtime.scheduling.create_reminder = original_create_reminder
        worker = CompanionWorker(self.config, runtime=runtime, store=runtime.store)
        delivery = worker.run_once(
            "life_flow_effect_delivery",
            idempotency_key="test:life-flow-effect-recovery",
        )

        self.assertEqual(delivery["status"], "succeeded")
        self.assertEqual(delivery["result"]["attempted"], 1)
        self.assertEqual(len(delivery["result"]["delivered"]), 1)
        self.assertEqual(runtime.life_flow.store.read_pending_effects(), [])
        self.assertIsNotNone(runtime.store.get_reminder(reminder_id))
        reminder_events = runtime.store.read_events(event_type="reminder_created")
        self.assertEqual(len(reminder_events), 1)

        duplicate = runtime.life_flow.flush_effect_outbox()
        self.assertEqual(duplicate["attempted"], 0)
        self.assertEqual(len(runtime.store.read_events(event_type="reminder_created")), 1)


if __name__ == "__main__":
    unittest.main()
