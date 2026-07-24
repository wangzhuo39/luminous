from __future__ import annotations

from datetime import datetime
from typing import Any

from luminous.runtime.domain.events import make_event, new_event_id
from luminous.runtime.domain.safety import SafetyPolicy
from luminous.runtime.domain.scheduling import CalendarEvent, ProactiveKind, Reminder, ReminderStatus
from luminous.runtime.domain.time import parse_iso_datetime, utc_now_iso
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore


class SchedulingService:
    """Application boundary for user-owned schedules and notification controls."""

    def __init__(self, store: CompanionRuntimeStore, *, clock: callable, safety_policy: SafetyPolicy | None = None) -> None:
        self.store = store
        self.clock = clock
        self.safety_policy = safety_policy or SafetyPolicy()

    def create_reminder(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = self.clock()
        title = str(payload.get("title", "")).strip()
        due_at = str(payload.get("due_at", "")).strip()
        if not title:
            raise ValueError("title is required")
        if parse_iso_datetime(due_at) is None:
            raise ValueError("due_at must be an ISO-8601 datetime")
        try:
            kind = ProactiveKind(str(payload.get("kind", ProactiveKind.REMINDER)))
        except ValueError as exc:
            raise ValueError("invalid reminder kind") from exc
        reminder = Reminder(
            reminder_id=str(payload.get("reminder_id") or new_event_id("reminder")),
            title=title,
            due_at=due_at,
            timezone_name=str(payload.get("timezone_name", "UTC")),
            description=str(payload.get("description", "")),
            kind=kind,
            user_scope=str(payload.get("user_scope", "default")),
            source=str(payload.get("source", "user")),
            source_ref=str(payload.get("source_ref", "")),
            recurrence=str(payload.get("recurrence", "")),
            created_at=utc_now_iso(now),
            updated_at=utc_now_iso(now),
            metadata=dict(payload.get("metadata", {}) or {}),
        )
        reminder = self.store.save_reminder(reminder)
        event = make_event(
            "reminder_created", reminder.title, {"reminder": reminder.to_dict()},
            trace_id=new_event_id("trace"), now=now, actor="user", source_ids=[reminder.reminder_id],
        )
        self.store.append_event(event)
        return {"ok": True, "reminder": reminder.to_dict(), "event": event.to_dict()}

    def read_reminders(self, *, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        items = self.store.read_reminders(status=status, limit=limit)
        return {"count": len(items), "status": status or "", "items": [item.to_dict() for item in items]}

    def update_reminder(self, reminder_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        now = self.clock()
        if "due_at" in updates and parse_iso_datetime(str(updates["due_at"])) is None:
            raise ValueError("due_at must be an ISO-8601 datetime")
        updated = self.store.update_reminder(reminder_id, dict(updates), now=now)
        if updated is None:
            return {"ok": False, "reason": "not_found", "reminder_id": reminder_id}
        event = make_event(
            "reminder_updated", updated.title, {"reminder": updated.to_dict(), "updates": updates},
            trace_id=new_event_id("trace"), now=now, actor="user", source_ids=[reminder_id],
        )
        self.store.append_event(event)
        return {"ok": True, "reminder": updated.to_dict(), "event": event.to_dict()}

    def snooze_reminder(self, reminder_id: str, due_at: str) -> dict[str, Any]:
        if parse_iso_datetime(due_at) is None:
            raise ValueError("due_at must be an ISO-8601 datetime")
        return self.update_reminder(reminder_id, {"status": ReminderStatus.SNOOZED.value, "due_at": due_at})

    def complete_reminder(self, reminder_id: str) -> dict[str, Any]:
        return self.update_reminder(reminder_id, {"status": ReminderStatus.COMPLETED.value})

    def cancel_reminder(self, reminder_id: str) -> dict[str, Any]:
        return self.update_reminder(reminder_id, {"status": ReminderStatus.CANCELLED.value})

    def create_calendar_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = self.clock()
        title = str(payload.get("title", "")).strip()
        starts_at = str(payload.get("starts_at", "")).strip()
        if not title:
            raise ValueError("title is required")
        if parse_iso_datetime(starts_at) is None:
            raise ValueError("starts_at must be an ISO-8601 datetime")
        ends_at = str(payload.get("ends_at", ""))
        if ends_at and parse_iso_datetime(ends_at) is None:
            raise ValueError("ends_at must be an ISO-8601 datetime")
        event = CalendarEvent(
            event_id=str(payload.get("event_id") or new_event_id("calendar")), title=title, starts_at=starts_at,
            ends_at=ends_at, all_day=bool(payload.get("all_day", False)),
            user_scope=str(payload.get("user_scope", "default")), timezone_name=str(payload.get("timezone_name", "UTC")),
            reminder_ids=tuple(str(value) for value in payload.get("reminder_ids", []) or []),
            created_at=utc_now_iso(now), updated_at=utc_now_iso(now), metadata=dict(payload.get("metadata", {}) or {}),
        )
        event = self.store.save_calendar_event(event)
        audit = make_event("calendar_event_created", event.title, {"calendar_event": event.to_dict()}, trace_id=new_event_id("trace"), now=now, actor="user", source_ids=[event.event_id])
        self.store.append_event(audit)
        return {"ok": True, "calendar_event": event.to_dict(), "event": audit.to_dict()}

    def read_calendar_events(self, *, limit: int = 100) -> dict[str, Any]:
        items = self.store.read_calendar_events(limit=limit)
        return {"count": len(items), "items": [item.to_dict() for item in items]}

    def update_calendar_event(self, event_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        now = self.clock()
        updated = self.store.update_calendar_event(event_id, updates, now=now)
        if updated is None:
            return {"ok": False, "reason": "not_found", "event_id": event_id}
        audit = make_event("calendar_event_updated", updated.title, {"calendar_event": updated.to_dict(), "updates": updates}, trace_id=new_event_id("trace"), now=now, actor="user", source_ids=[event_id])
        self.store.append_event(audit)
        return {"ok": True, "calendar_event": updated.to_dict(), "event": audit.to_dict()}

    def notification_preferences(self) -> dict[str, Any]:
        return self.store.read_notification_preferences()

    def update_notification_preferences(self, updates: dict[str, Any]) -> dict[str, Any]:
        now = self.clock()
        preferences = self.store.save_notification_preferences(updates, now=now)
        audit = make_event("notification_preferences_updated", "notification preferences", {"preferences": preferences}, trace_id=new_event_id("trace"), now=now, actor="user")
        self.store.append_event(audit)
        return {"ok": True, "preferences": preferences, "event": audit.to_dict()}

    def outbound_permitted(self, *, proactive_kind: str, now: datetime, risk_level: str = "") -> tuple[bool, list[str], dict[str, Any]]:
        preferences = self.store.read_notification_preferences()
        holds: list[str] = []
        if not preferences.get("enabled", True):
            holds.append("notifications_disabled")
        if proactive_kind not in set(preferences.get("allowed_kinds", [])):
            holds.append("kind_disabled")
        start = str(preferences.get("quiet_start", ""))
        end = str(preferences.get("quiet_end", ""))
        if start and end and _is_quiet_time(now, start, end):
            holds.append("quiet_hours_preference")
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.store.count_outbox_since(day_start) >= int(preferences.get("daily_limit", 3)):
            holds.append("daily_limit")
        permitted, policy_hold = self.safety_policy.permits(risk_level=risk_level, proactive_kind=proactive_kind)
        if not permitted:
            holds.append(policy_hold)
        return not holds, holds, preferences


def _is_quiet_time(now: datetime, start: str, end: str) -> bool:
    try:
        start_hour, start_minute = (int(value) for value in start.split(":", 1))
        end_hour, end_minute = (int(value) for value in end.split(":", 1))
    except ValueError:
        return False
    current = now.hour * 60 + now.minute
    start_value = start_hour * 60 + start_minute
    end_value = end_hour * 60 + end_minute
    return start_value <= current < end_value if start_value < end_value else current >= start_value or current < end_value
