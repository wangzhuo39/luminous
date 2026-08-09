from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from luminous.runtime.application.runtime import CompanionRuntime
from luminous.runtime.application.voice_service import VoiceService
from luminous.runtime.config import BackendConfig
from luminous.runtime.infrastructure.client import ModelClient
from luminous.runtime.infrastructure.public_api import (
    public_action_preview,
    public_action_result,
    public_activity,
    public_calendar_event,
    public_checkin,
    public_chat,
    public_chat_history,
    public_diary,
    public_list,
    public_memory_mutation,
    public_memory_query,
    public_notifications,
    public_outbox_list,
    public_outbox_mutation,
    public_reminder,
    public_resource,
    public_routine,
    public_state_snapshot,
    public_step,
    public_task,
    public_today,
    public_timeline,
)
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore


class CompanionService:
    def __init__(
        self,
        config: BackendConfig,
        client: ModelClient | None = None,
        store: CompanionRuntimeStore | None = None,
        clock: callable | None = None,
        voice_service: VoiceService | None = None,
    ) -> None:
        self.config = config
        self.runtime = CompanionRuntime(config, client=client, store=store, clock=clock)
        self.voice = voice_service or VoiceService(config)

    def chat(self, user_text: str, history: Sequence[dict[str, object]] | None = None) -> dict[str, object]:
        return public_chat(self.runtime.chat(user_text, history))

    def read_chat_history(self, limit: int = 10) -> dict[str, object]:
        items = self.runtime.store.read_raw_messages(limit=limit)
        return public_chat_history({"limit": limit, "count": len(items), "items": items})

    def get_state(self, *, include_history: bool = False) -> dict[str, object]:
        raw = self.runtime.get_state()
        if include_history:
            items = self.runtime.store.read_raw_messages(limit=10)
            raw = {**raw, "history": {"limit": 10, "count": len(items), "items": items}}
        return public_state_snapshot(raw)

    def query_memory(self, query: str, limit: int = 5) -> dict[str, object]:
        return public_memory_query(self.runtime.query_memory(query, limit=limit))

    def read_ledger(self, limit: int = 50, trace_id: str | None = None) -> dict[str, object]:
        return self.runtime.read_ledger(limit=limit, trace_id=trace_id)

    def read_trace(self, trace_id: str, limit: int = 50) -> dict[str, object]:
        return self.runtime.read_trace(trace_id, limit=limit)

    def proactive_tick(self, send: bool = False, now: Any | None = None) -> dict[str, object]:
        return self.runtime.proactive_tick(send=send, now=now)

    def read_outbox(self, limit: int = 50, status: str | None = None) -> dict[str, object]:
        items = self.runtime.store.read_outbox(limit=limit, status=status)
        return public_outbox_list({"limit": limit, "status": status or "", "count": len(items), "items": items})

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
        return public_memory_mutation(self.runtime.update_memory(memory_id, updates=updates))

    def forget_memory(self, memory_id: str, *, hard_delete: bool = False) -> dict[str, object]:
        return public_memory_mutation(self.runtime.forget_memory(memory_id, hard_delete=hard_delete))

    def export_data(self) -> dict[str, object]:
        return self.runtime.export_data()

    def create_reminder(self, payload: dict[str, Any]) -> dict[str, object]:
        return public_resource(self.runtime.create_reminder(payload), "reminder", public_reminder)

    def read_reminders(self, *, status: str | None = None, limit: int = 100) -> dict[str, object]:
        return public_list(self.runtime.read_reminders(status=status, limit=limit), "items", public_reminder)

    def update_reminder(self, reminder_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return public_resource(self.runtime.update_reminder(reminder_id, updates), "reminder", public_reminder)

    def snooze_reminder(self, reminder_id: str, due_at: str) -> dict[str, object]:
        return public_resource(self.runtime.snooze_reminder(reminder_id, due_at), "reminder", public_reminder)

    def complete_reminder(self, reminder_id: str) -> dict[str, object]:
        return public_resource(self.runtime.complete_reminder(reminder_id), "reminder", public_reminder)

    def cancel_reminder(self, reminder_id: str) -> dict[str, object]:
        return public_resource(self.runtime.cancel_reminder(reminder_id), "reminder", public_reminder)

    def create_calendar_event(self, payload: dict[str, Any]) -> dict[str, object]:
        return public_resource(self.runtime.create_calendar_event(payload), "calendar_event", public_calendar_event)

    def read_calendar_events(self, *, limit: int = 100) -> dict[str, object]:
        return public_list(self.runtime.read_calendar_events(limit=limit), "items", public_calendar_event)

    def update_calendar_event(self, event_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return public_resource(self.runtime.update_calendar_event(event_id, updates), "calendar_event", public_calendar_event)

    def notification_preferences(self) -> dict[str, object]:
        return public_notifications(self.runtime.notification_preferences())

    def update_notification_preferences(self, updates: dict[str, Any]) -> dict[str, object]:
        return public_notifications(self.runtime.update_notification_preferences(updates))

    def companion_settings(self) -> dict[str, object]:
        return self.runtime.companion_settings()

    def update_companion_settings(self, updates: dict[str, Any]) -> dict[str, object]:
        return self.runtime.update_companion_settings(updates)

    def transcribe_voice(
        self, audio: bytes, *, content_type: str, duration_ms: int, filename: str = "recording",
    ) -> dict[str, object]:
        return self.voice.transcribe(
            audio, content_type=content_type, duration_ms=duration_ms, filename=filename,
        )

    def synthesize_voice(
        self, text: str, *, voice_id: str | None = None, speaking_rate: float | None = None,
    ):
        settings = self.runtime.companion_settings()["voice"]
        return self.voice.synthesize(
            text,
            voice_id=voice_id or str(settings["voice_id"]),
            speaking_rate=float(speaking_rate if speaking_rate is not None else settings["speaking_rate"]),
        )

    def register_notification_device(
        self, payload: dict[str, Any], *, session_digest: str = "",
    ) -> dict[str, object]:
        token = payload.get("token", "")
        platform = payload.get("platform", "android")
        provider = payload.get("provider", "fcm")
        installation_id = payload.get("installation_id", "")
        if not all(isinstance(value, str) for value in (token, platform, provider, installation_id)):
            raise ValueError("invalid notification device")
        device = self.runtime.store.upsert_notification_device(
            token=token, platform=platform.strip().lower(), provider=provider.strip().lower(),
            installation_id=installation_id, session_digest=session_digest,
        )
        return {
            "registered": True,
            "device": {
                "device_id": str(device.get("device_id", "")),
                "platform": str(device.get("platform", "")),
                "provider": str(device.get("provider", "")),
                "status": str(device.get("status", "")),
                "updated_at": str(device.get("updated_at", "")),
            },
        }

    def unregister_notification_device(
        self, device_id: str, *, session_digest: str = "",
    ) -> dict[str, object]:
        return {
            "unregistered": self.runtime.store.disable_notification_device_by_id(
                device_id, session_digest=session_digest,
            ),
            "device_id": device_id,
        }

    def today(self, *, date: str = "") -> dict[str, object]:
        return public_today(self.runtime.read_today(date=date))

    def timeline(self, *, from_date: str = "", to_date: str = "", kind: str = "", limit: int = 200) -> dict[str, object]:
        return public_timeline(self.runtime.read_timeline(from_date=from_date, to_date=to_date, kind=kind, limit=limit))

    def create_task(self, payload: dict[str, Any]) -> dict[str, object]:
        return public_resource(self.runtime.create_task(payload), "task", public_task)

    def read_tasks(self, *, status: str | None = None, limit: int = 100) -> dict[str, object]:
        return public_list(self.runtime.read_tasks(status=status, limit=limit), "items", public_task)

    def get_task(self, task_id: str) -> dict[str, object]:
        return public_resource(self.runtime.get_task(task_id), "task", public_task)

    def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return public_resource(self.runtime.update_task(task_id, updates), "task", public_task)

    def transition_task(self, task_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
        return public_resource(self.runtime.transition_task(task_id, action, payload), "task", public_task)

    def add_task_step(self, task_id: str, payload: dict[str, Any]) -> dict[str, object]:
        return public_resource(self.runtime.add_task_step(task_id, payload), "step", public_step)

    def update_task_step(self, task_id: str, step_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return public_resource(self.runtime.update_task_step(task_id, step_id, updates), "step", public_step)

    def create_routine(self, payload: dict[str, Any]) -> dict[str, object]:
        return public_resource(self.runtime.create_routine(payload), "routine", public_routine)

    def read_routines(self, *, active_only: bool = False, limit: int = 100) -> dict[str, object]:
        return public_list(self.runtime.read_routines(active_only=active_only, limit=limit), "items", public_routine)

    def get_routine(self, routine_id: str) -> dict[str, object]:
        return public_resource(self.runtime.get_routine(routine_id), "routine", public_routine)

    def update_routine(self, routine_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return public_resource(self.runtime.update_routine(routine_id, updates), "routine", public_routine)

    def checkin_routine(self, routine_id: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
        return public_resource(self.runtime.checkin_routine(routine_id, payload), "checkin", public_checkin)

    def create_activity(self, payload: dict[str, Any]) -> dict[str, object]:
        return public_resource(self.runtime.create_activity(payload), "activity", public_activity)

    def read_activities(self, *, status: str | None = None, limit: int = 100) -> dict[str, object]:
        return public_list(self.runtime.read_activities(status=status, limit=limit), "items", public_activity)

    def get_activity(self, session_id: str) -> dict[str, object]:
        return public_resource(self.runtime.get_activity(session_id), "activity", public_activity)

    def transition_activity(self, session_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
        return public_resource(self.runtime.transition_activity(session_id, action, payload), "activity", public_activity)

    def create_diary_entry(self, payload: dict[str, Any]) -> dict[str, object]:
        return public_resource(self.runtime.create_diary_entry(payload), "diary_entry", public_diary)

    def read_diary_entries(self, *, date: str = "", limit: int = 100) -> dict[str, object]:
        return public_list(self.runtime.read_diary_entries(date=date, limit=limit), "items", public_diary)

    def get_diary_entry(self, entry_id: str) -> dict[str, object]:
        return public_resource(self.runtime.get_diary_entry(entry_id), "diary_entry", public_diary)

    def update_diary_entry(self, entry_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return public_resource(self.runtime.update_diary_entry(entry_id, updates), "diary_entry", public_diary)

    def draft_diary_entry(self, *, date: str = "") -> dict[str, object]:
        return public_resource(self.runtime.draft_diary_entry(date=date), "diary_entry", public_diary)

    def preview_life_action(self, payload: dict[str, Any]) -> dict[str, object]:
        return public_action_preview(self.runtime.preview_life_action(payload))

    def confirm_life_action(self, payload: dict[str, Any]) -> dict[str, object]:
        return public_action_result(self.runtime.confirm_life_action(payload))

    def record_outbox_feedback(
        self,
        message_id: str,
        status: str,
        feedback_text: str = "",
        replied_at: str | None = None,
    ) -> dict[str, object]:
        return public_outbox_mutation(self.runtime.record_outbox_feedback(
            message_id,
            status,
            feedback_text=feedback_text,
            replied_at=replied_at,
        ))

    def record_outbox_receipt(
        self,
        message_id: str,
        receipt_type: str,
        *,
        channel: str = "",
        payload: dict[str, object] | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, object]:
        return public_outbox_mutation(self.runtime.record_outbox_receipt(
            message_id,
            receipt_type,
            channel=channel,
            payload=payload,
            occurred_at=occurred_at,
        ))

    def tick_worker(self) -> dict[str, object]:
        from luminous.runtime.worker import CompanionWorker

        worker = CompanionWorker(self.config, runtime=self.runtime, store=self.runtime.store, clock=self.runtime.clock)
        return worker.tick()
