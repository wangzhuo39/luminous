from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from luminous.runtime.application.runtime import CompanionRuntime
from luminous.runtime.config import BackendConfig
from luminous.runtime.infrastructure.client import ModelClient
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore


class CompanionService:
    def __init__(
        self,
        config: BackendConfig,
        client: ModelClient | None = None,
        store: CompanionRuntimeStore | None = None,
        clock: callable | None = None,
    ) -> None:
        self.config = config
        self.runtime = CompanionRuntime(config, client=client, store=store, clock=clock)

    def chat(self, user_text: str, history: Sequence[dict[str, object]] | None = None) -> dict[str, object]:
        return self.runtime.chat(user_text, history)

    def get_state(self) -> dict[str, object]:
        return self.runtime.get_state()

    def query_memory(self, query: str, limit: int = 5) -> dict[str, object]:
        return self.runtime.query_memory(query, limit=limit)

    def read_ledger(self, limit: int = 50, trace_id: str | None = None) -> dict[str, object]:
        return self.runtime.read_ledger(limit=limit, trace_id=trace_id)

    def read_trace(self, trace_id: str, limit: int = 50) -> dict[str, object]:
        return self.runtime.read_trace(trace_id, limit=limit)

    def proactive_tick(self, send: bool = False, now: Any | None = None) -> dict[str, object]:
        return self.runtime.proactive_tick(send=send, now=now)

    def read_outbox(self, limit: int = 50, status: str | None = None) -> dict[str, object]:
        items = self.runtime.store.read_outbox(limit=limit, status=status)
        return {"limit": limit, "status": status or "", "count": len(items), "items": items}

    def read_jobs(self, limit: int = 50, status: str | None = None) -> dict[str, object]:
        items = self.runtime.store.read_jobs(limit=limit, status=status)
        return {"limit": limit, "status": status or "", "count": len(items), "items": items}

    def read_raw_messages(self, limit: int = 50, role: str | None = None) -> dict[str, object]:
        return self.runtime.read_raw_messages(limit=limit, role=role)

    def read_memory_threads(self, limit: int = 50) -> dict[str, object]:
        return self.runtime.read_memory_threads(limit=limit)

    def read_memory_links(self, limit: int = 100) -> dict[str, object]:
        return self.runtime.read_memory_links(limit=limit)

    def read_memory_evidence(
        self,
        limit: int = 100,
        memory_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, object]:
        return self.runtime.read_memory_evidence(limit=limit, memory_id=memory_id, status=status)

    def update_memory(self, memory_id: str, updates: dict[str, object] | None = None) -> dict[str, object]:
        return self.runtime.update_memory(memory_id, updates=updates)

    def forget_memory(self, memory_id: str, *, hard_delete: bool = False) -> dict[str, object]:
        return self.runtime.forget_memory(memory_id, hard_delete=hard_delete)

    def export_data(self) -> dict[str, object]:
        return self.runtime.export_data()

    def create_reminder(self, payload: dict[str, Any]) -> dict[str, object]:
        return self.runtime.create_reminder(payload)

    def read_reminders(self, *, status: str | None = None, limit: int = 100) -> dict[str, object]:
        return self.runtime.read_reminders(status=status, limit=limit)

    def update_reminder(self, reminder_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return self.runtime.update_reminder(reminder_id, updates)

    def snooze_reminder(self, reminder_id: str, due_at: str) -> dict[str, object]:
        return self.runtime.snooze_reminder(reminder_id, due_at)

    def complete_reminder(self, reminder_id: str) -> dict[str, object]:
        return self.runtime.complete_reminder(reminder_id)

    def cancel_reminder(self, reminder_id: str) -> dict[str, object]:
        return self.runtime.cancel_reminder(reminder_id)

    def create_calendar_event(self, payload: dict[str, Any]) -> dict[str, object]:
        return self.runtime.create_calendar_event(payload)

    def read_calendar_events(self, *, limit: int = 100) -> dict[str, object]:
        return self.runtime.read_calendar_events(limit=limit)

    def update_calendar_event(self, event_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return self.runtime.update_calendar_event(event_id, updates)

    def notification_preferences(self) -> dict[str, object]:
        return self.runtime.notification_preferences()

    def update_notification_preferences(self, updates: dict[str, Any]) -> dict[str, object]:
        return self.runtime.update_notification_preferences(updates)

    def today(self, *, date: str = "") -> dict[str, object]:
        return self.runtime.read_today(date=date)

    def timeline(self, *, from_date: str = "", to_date: str = "", kind: str = "", limit: int = 200) -> dict[str, object]:
        return self.runtime.read_timeline(from_date=from_date, to_date=to_date, kind=kind, limit=limit)

    def create_task(self, payload: dict[str, Any]) -> dict[str, object]:
        return self.runtime.create_task(payload)

    def read_tasks(self, *, status: str | None = None, limit: int = 100) -> dict[str, object]:
        return self.runtime.read_tasks(status=status, limit=limit)

    def get_task(self, task_id: str) -> dict[str, object]:
        return self.runtime.get_task(task_id)

    def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return self.runtime.update_task(task_id, updates)

    def transition_task(self, task_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
        return self.runtime.transition_task(task_id, action, payload)

    def add_task_step(self, task_id: str, payload: dict[str, Any]) -> dict[str, object]:
        return self.runtime.add_task_step(task_id, payload)

    def update_task_step(self, task_id: str, step_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return self.runtime.update_task_step(task_id, step_id, updates)

    def create_routine(self, payload: dict[str, Any]) -> dict[str, object]:
        return self.runtime.create_routine(payload)

    def read_routines(self, *, active_only: bool = False, limit: int = 100) -> dict[str, object]:
        return self.runtime.read_routines(active_only=active_only, limit=limit)

    def get_routine(self, routine_id: str) -> dict[str, object]:
        return self.runtime.get_routine(routine_id)

    def update_routine(self, routine_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return self.runtime.update_routine(routine_id, updates)

    def checkin_routine(self, routine_id: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
        return self.runtime.checkin_routine(routine_id, payload)

    def create_activity(self, payload: dict[str, Any]) -> dict[str, object]:
        return self.runtime.create_activity(payload)

    def read_activities(self, *, status: str | None = None, limit: int = 100) -> dict[str, object]:
        return self.runtime.read_activities(status=status, limit=limit)

    def get_activity(self, session_id: str) -> dict[str, object]:
        return self.runtime.get_activity(session_id)

    def transition_activity(self, session_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
        return self.runtime.transition_activity(session_id, action, payload)

    def create_diary_entry(self, payload: dict[str, Any]) -> dict[str, object]:
        return self.runtime.create_diary_entry(payload)

    def read_diary_entries(self, *, date: str = "", limit: int = 100) -> dict[str, object]:
        return self.runtime.read_diary_entries(date=date, limit=limit)

    def get_diary_entry(self, entry_id: str) -> dict[str, object]:
        return self.runtime.get_diary_entry(entry_id)

    def update_diary_entry(self, entry_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return self.runtime.update_diary_entry(entry_id, updates)

    def draft_diary_entry(self, *, date: str = "") -> dict[str, object]:
        return self.runtime.draft_diary_entry(date=date)

    def preview_life_action(self, payload: dict[str, Any]) -> dict[str, object]:
        return self.runtime.preview_life_action(payload)

    def confirm_life_action(self, payload: dict[str, Any]) -> dict[str, object]:
        return self.runtime.confirm_life_action(payload)

    def record_outbox_feedback(
        self,
        message_id: str,
        status: str,
        feedback_text: str = "",
        replied_at: str | None = None,
    ) -> dict[str, object]:
        return self.runtime.record_outbox_feedback(
            message_id,
            status,
            feedback_text=feedback_text,
            replied_at=replied_at,
        )

    def record_outbox_receipt(
        self,
        message_id: str,
        receipt_type: str,
        *,
        channel: str = "",
        payload: dict[str, object] | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, object]:
        return self.runtime.record_outbox_receipt(
            message_id,
            receipt_type,
            channel=channel,
            payload=payload,
            occurred_at=occurred_at,
        )

    def tick_worker(self) -> dict[str, object]:
        from luminous.runtime.worker import CompanionWorker

        worker = CompanionWorker(self.config, runtime=self.runtime, store=self.runtime.store, clock=self.runtime.clock)
        return worker.tick()
