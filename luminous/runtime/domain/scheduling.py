from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from luminous.runtime.domain.time import parse_iso_datetime, utc_now_iso


class ReminderStatus(StrEnum):
    SCHEDULED = "scheduled"
    DUE = "due"
    SNOOZED = "snoozed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ProactiveKind(StrEnum):
    CHECKIN = "checkin"
    OPEN_LOOP_FOLLOWUP = "open_loop_followup"
    REMINDER = "reminder"
    ANNIVERSARY = "anniversary"
    ROUTINE = "routine"
    REPAIR = "repair"


_ACTIVE = {ReminderStatus.SCHEDULED, ReminderStatus.DUE, ReminderStatus.SNOOZED}
_TRANSITIONS = {
    ReminderStatus.SCHEDULED: {ReminderStatus.DUE, ReminderStatus.SNOOZED, ReminderStatus.COMPLETED, ReminderStatus.CANCELLED, ReminderStatus.EXPIRED},
    ReminderStatus.DUE: {ReminderStatus.SNOOZED, ReminderStatus.COMPLETED, ReminderStatus.CANCELLED, ReminderStatus.EXPIRED},
    ReminderStatus.SNOOZED: {ReminderStatus.DUE, ReminderStatus.COMPLETED, ReminderStatus.CANCELLED, ReminderStatus.EXPIRED},
    ReminderStatus.COMPLETED: set(),
    ReminderStatus.CANCELLED: set(),
    ReminderStatus.EXPIRED: set(),
}


@dataclass(frozen=True)
class Reminder:
    reminder_id: str
    title: str
    due_at: str
    timezone_name: str = "UTC"
    description: str = ""
    kind: ProactiveKind = ProactiveKind.REMINDER
    status: ReminderStatus = ReminderStatus.SCHEDULED
    user_scope: str = "default"
    source: str = "user"
    source_ref: str = ""
    recurrence: str = ""
    delivery_count: int = 0
    last_delivered_at: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Reminder":
        return cls(
            reminder_id=str(value["reminder_id"]),
            title=str(value["title"]),
            due_at=str(value["due_at"]),
            timezone_name=str(value.get("timezone_name", "UTC")),
            description=str(value.get("description", "")),
            kind=ProactiveKind(str(value.get("kind", ProactiveKind.REMINDER))),
            status=ReminderStatus(str(value.get("status", ReminderStatus.SCHEDULED))),
            user_scope=str(value.get("user_scope", "default")),
            source=str(value.get("source", "user")),
            source_ref=str(value.get("source_ref", "")),
            recurrence=str(value.get("recurrence", "")),
            delivery_count=int(value.get("delivery_count", 0)),
            last_delivered_at=str(value.get("last_delivered_at", "")),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
            metadata=dict(value.get("metadata", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reminder_id": self.reminder_id,
            "title": self.title,
            "due_at": self.due_at,
            "timezone_name": self.timezone_name,
            "description": self.description,
            "kind": self.kind.value,
            "status": self.status.value,
            "user_scope": self.user_scope,
            "source": self.source,
            "source_ref": self.source_ref,
            "recurrence": self.recurrence,
            "delivery_count": self.delivery_count,
            "last_delivered_at": self.last_delivered_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    def is_due(self, now: datetime | None = None) -> bool:
        if self.status not in {ReminderStatus.SCHEDULED, ReminderStatus.SNOOZED}:
            return False
        due_at = parse_iso_datetime(self.due_at)
        now = now or datetime.now(timezone.utc)
        return due_at is not None and due_at <= now

    def transition(self, status: ReminderStatus, *, now: datetime | None = None, **changes: Any) -> "Reminder":
        if status != self.status and status not in _TRANSITIONS[self.status]:
            raise ValueError(f"cannot transition reminder from {self.status} to {status}")
        payload = self.to_dict()
        payload.update(changes)
        payload["status"] = status.value
        payload["updated_at"] = utc_now_iso(now)
        return Reminder.from_dict(payload)


@dataclass(frozen=True)
class CalendarEvent:
    event_id: str
    title: str
    starts_at: str
    ends_at: str = ""
    all_day: bool = False
    user_scope: str = "default"
    timezone_name: str = "UTC"
    reminder_ids: tuple[str, ...] = ()
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CalendarEvent":
        return cls(
            event_id=str(value["event_id"]),
            title=str(value["title"]),
            starts_at=str(value["starts_at"]),
            ends_at=str(value.get("ends_at", "")),
            all_day=bool(value.get("all_day", False)),
            user_scope=str(value.get("user_scope", "default")),
            timezone_name=str(value.get("timezone_name", "UTC")),
            reminder_ids=tuple(str(item) for item in value.get("reminder_ids", []) or []),
            status=str(value.get("status", "active")),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
            metadata=dict(value.get("metadata", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "starts_at": self.starts_at,
            "ends_at": self.ends_at,
            "all_day": self.all_day,
            "user_scope": self.user_scope,
            "timezone_name": self.timezone_name,
            "reminder_ids": list(self.reminder_ids),
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


def active_reminder_statuses() -> set[ReminderStatus]:
    return set(_ACTIVE)
