from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from luminous.runtime.domain.events import new_event_id
from luminous.runtime.domain.time import utc_now_iso


class TaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class SessionStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class CheckinStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class DiaryStatus(StrEnum):
    DRAFT = "draft"
    SAVED = "saved"
    DELETED = "deleted"


def _status(value: str | StrEnum, enum_type: type[StrEnum]) -> str:
    try:
        return enum_type(str(value)).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ValueError(f"invalid {enum_type.__name__}: {value}; allowed: {allowed}") from exc


@dataclass(frozen=True)
class Task:
    task_id: str
    title: str
    description: str = ""
    status: str = TaskStatus.OPEN.value
    due_at: str = ""
    priority: str = "normal"
    source: str = "manual"
    calendar_event_id: str = ""
    reminder_ids: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    completed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    user_scope: str = "default"

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValueError("task_id is required")
        if not self.title.strip():
            raise ValueError("task title is required")
        _status(self.status, TaskStatus)
        if self.priority not in {"low", "normal", "high"}:
            raise ValueError("task priority must be low, normal, or high")

    @classmethod
    def create(cls, payload: dict[str, Any], *, now: str | None = None) -> "Task":
        timestamp = now or utc_now_iso()
        return cls(
            task_id=str(payload.get("task_id") or new_event_id("task")),
            title=str(payload.get("title", "")).strip(),
            description=str(payload.get("description", "")).strip(),
            status=str(payload.get("status", TaskStatus.OPEN.value)),
            due_at=str(payload.get("due_at", "")),
            priority=str(payload.get("priority", "normal")),
            source=str(payload.get("source", "manual")),
            calendar_event_id=str(payload.get("calendar_event_id", "")),
            reminder_ids=tuple(str(value) for value in payload.get("reminder_ids", []) or []),
            created_at=str(payload.get("created_at", timestamp)),
            updated_at=str(payload.get("updated_at", timestamp)),
            completed_at=str(payload.get("completed_at", "")),
            metadata=dict(payload.get("metadata", {}) or {}),
            user_scope=str(payload.get("user_scope", "default")),
        )

    def transition(self, target: str, *, now: str | None = None, **updates: Any) -> "Task":
        target = _status(target, TaskStatus)
        allowed = {
            TaskStatus.OPEN.value: {TaskStatus.IN_PROGRESS.value, TaskStatus.BLOCKED.value, TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value, TaskStatus.ARCHIVED.value},
            TaskStatus.IN_PROGRESS.value: {TaskStatus.BLOCKED.value, TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value, TaskStatus.ARCHIVED.value},
            TaskStatus.BLOCKED.value: {TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value, TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value, TaskStatus.ARCHIVED.value},
            TaskStatus.COMPLETED.value: {TaskStatus.ARCHIVED.value},
            TaskStatus.CANCELLED.value: {TaskStatus.ARCHIVED.value},
            TaskStatus.ARCHIVED.value: set(),
        }
        if target != self.status and target not in allowed[self.status]:
            raise ValueError(f"cannot transition task from {self.status} to {target}")
        payload = self.to_dict()
        payload.update(updates)
        payload["status"] = target
        payload["updated_at"] = now or utc_now_iso()
        if target == TaskStatus.COMPLETED.value and not payload.get("completed_at"):
            payload["completed_at"] = payload["updated_at"]
        if target != TaskStatus.COMPLETED.value and self.status != TaskStatus.COMPLETED.value:
            payload["completed_at"] = ""
        return Task.create(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "title": self.title, "description": self.description,
            "status": self.status, "due_at": self.due_at, "priority": self.priority,
            "source": self.source, "calendar_event_id": self.calendar_event_id,
            "reminder_ids": list(self.reminder_ids), "created_at": self.created_at,
            "updated_at": self.updated_at, "completed_at": self.completed_at,
            "metadata": self.metadata, "user_scope": self.user_scope,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Task":
        return cls.create(payload)


@dataclass(frozen=True)
class TaskStep:
    step_id: str
    task_id: str
    title: str
    position: int
    status: str = TaskStatus.OPEN.value
    completed_at: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.step_id or not self.task_id or not self.title.strip():
            raise ValueError("step_id, task_id, and title are required")
        if self.status not in {TaskStatus.OPEN.value, TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value}:
            raise ValueError("task step status must be open, completed, or cancelled")

    @classmethod
    def create(cls, payload: dict[str, Any], *, now: str | None = None) -> "TaskStep":
        timestamp = now or utc_now_iso()
        return cls(
            step_id=str(payload.get("step_id") or new_event_id("step")),
            task_id=str(payload.get("task_id", "")),
            title=str(payload.get("title", "")).strip(),
            position=max(0, int(payload.get("position", 0))),
            status=str(payload.get("status", TaskStatus.OPEN.value)),
            completed_at=str(payload.get("completed_at", "")),
            created_at=str(payload.get("created_at", timestamp)),
            updated_at=str(payload.get("updated_at", timestamp)),
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class Routine:
    routine_id: str
    title: str
    schedule: str = "daily"
    active: bool = True
    reminder_policy: str = "none"
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    user_scope: str = "default"

    def __post_init__(self) -> None:
        if not self.routine_id or not self.title.strip():
            raise ValueError("routine_id and title are required")
        if self.schedule not in {"daily", "weekly"}:
            raise ValueError("routine schedule must be daily or weekly")
        if self.reminder_policy not in {"none", "remind"}:
            raise ValueError("routine reminder_policy must be none or remind")

    @classmethod
    def create(cls, payload: dict[str, Any], *, now: str | None = None) -> "Routine":
        timestamp = now or utc_now_iso()
        return cls(
            routine_id=str(payload.get("routine_id") or new_event_id("routine")),
            title=str(payload.get("title", "")).strip(),
            schedule=str(payload.get("schedule", "daily")),
            active=bool(payload.get("active", True)),
            reminder_policy=str(payload.get("reminder_policy", "none")),
            created_at=str(payload.get("created_at", timestamp)),
            updated_at=str(payload.get("updated_at", timestamp)),
            metadata=dict(payload.get("metadata", {}) or {}),
            user_scope=str(payload.get("user_scope", "default")),
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class RoutineCheckin:
    checkin_id: str
    routine_id: str
    period_key: str
    status: str = CheckinStatus.PENDING.value
    note: str = ""
    occurred_at: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.checkin_id or not self.routine_id or not self.period_key:
            raise ValueError("checkin_id, routine_id, and period_key are required")
        _status(self.status, CheckinStatus)

    @classmethod
    def create(cls, payload: dict[str, Any], *, now: str | None = None) -> "RoutineCheckin":
        timestamp = now or utc_now_iso()
        return cls(
            checkin_id=str(payload.get("checkin_id") or new_event_id("checkin")),
            routine_id=str(payload.get("routine_id", "")),
            period_key=str(payload.get("period_key", "")),
            status=str(payload.get("status", CheckinStatus.PENDING.value)),
            note=str(payload.get("note", "")),
            occurred_at=str(payload.get("occurred_at", "")),
            created_at=str(payload.get("created_at", timestamp)),
            updated_at=str(payload.get("updated_at", timestamp)),
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class ActivitySession:
    session_id: str
    kind: str
    title: str
    status: str = SessionStatus.PLANNED.value
    started_at: str = ""
    ended_at: str = ""
    task_id: str = ""
    content_ref: str = ""
    summary: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    user_scope: str = "default"

    def __post_init__(self) -> None:
        if not self.session_id or not self.title.strip():
            raise ValueError("session_id and title are required")
        if self.kind not in {"focus", "checkin", "planning", "reflection"}:
            raise ValueError("unsupported activity session kind")
        _status(self.status, SessionStatus)

    @classmethod
    def create(cls, payload: dict[str, Any], *, now: str | None = None) -> "ActivitySession":
        timestamp = now or utc_now_iso()
        return cls(
            session_id=str(payload.get("session_id") or new_event_id("activity")),
            kind=str(payload.get("kind", "focus")),
            title=str(payload.get("title", "")).strip(),
            status=str(payload.get("status", SessionStatus.PLANNED.value)),
            started_at=str(payload.get("started_at", "")),
            ended_at=str(payload.get("ended_at", "")),
            task_id=str(payload.get("task_id", "")),
            content_ref=str(payload.get("content_ref", "")),
            summary=str(payload.get("summary", "")),
            created_at=str(payload.get("created_at", timestamp)),
            updated_at=str(payload.get("updated_at", timestamp)),
            metadata=dict(payload.get("metadata", {}) or {}),
            user_scope=str(payload.get("user_scope", "default")),
        )

    def transition(self, target: str, *, now: str | None = None, **updates: Any) -> "ActivitySession":
        target = _status(target, SessionStatus)
        allowed = {
            SessionStatus.PLANNED.value: {SessionStatus.ACTIVE.value, SessionStatus.CANCELLED.value},
            SessionStatus.ACTIVE.value: {SessionStatus.PAUSED.value, SessionStatus.COMPLETED.value, SessionStatus.CANCELLED.value, SessionStatus.EXPIRED.value},
            SessionStatus.PAUSED.value: {SessionStatus.ACTIVE.value, SessionStatus.COMPLETED.value, SessionStatus.CANCELLED.value, SessionStatus.EXPIRED.value},
            SessionStatus.COMPLETED.value: set(), SessionStatus.CANCELLED.value: set(), SessionStatus.EXPIRED.value: set(),
        }
        if target != self.status and target not in allowed[self.status]:
            raise ValueError(f"cannot transition activity session from {self.status} to {target}")
        timestamp = now or utc_now_iso()
        payload = self.to_dict()
        payload.update(updates)
        payload.update({"status": target, "updated_at": timestamp})
        if target == SessionStatus.ACTIVE.value and not payload.get("started_at"):
            payload["started_at"] = timestamp
        if target in {SessionStatus.COMPLETED.value, SessionStatus.CANCELLED.value, SessionStatus.EXPIRED.value} and not payload.get("ended_at"):
            payload["ended_at"] = timestamp
        return ActivitySession.create(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id, "kind": self.kind, "title": self.title,
            "status": self.status, "started_at": self.started_at, "ended_at": self.ended_at,
            "task_id": self.task_id, "content_ref": self.content_ref, "summary": self.summary,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "metadata": self.metadata, "user_scope": self.user_scope,
        }


@dataclass(frozen=True)
class DiaryEntry:
    entry_id: str
    date: str
    title: str
    body: str
    source_event_ids: tuple[str, ...] = ()
    status: str = DiaryStatus.DRAFT.value
    created_at: str = ""
    updated_at: str = ""
    user_scope: str = "default"

    def __post_init__(self) -> None:
        if not self.entry_id or not self.date or not self.title.strip():
            raise ValueError("entry_id, date, and title are required")
        _status(self.status, DiaryStatus)

    @classmethod
    def create(cls, payload: dict[str, Any], *, now: str | None = None) -> "DiaryEntry":
        timestamp = now or utc_now_iso()
        return cls(
            entry_id=str(payload.get("entry_id") or new_event_id("diary")),
            date=str(payload.get("date", "")),
            title=str(payload.get("title", "")).strip(),
            body=str(payload.get("body", "")),
            source_event_ids=tuple(str(value) for value in payload.get("source_event_ids", []) or []),
            status=str(payload.get("status", DiaryStatus.DRAFT.value)),
            created_at=str(payload.get("created_at", timestamp)),
            updated_at=str(payload.get("updated_at", timestamp)),
            user_scope=str(payload.get("user_scope", "default")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id, "date": self.date, "title": self.title,
            "body": self.body, "source_event_ids": list(self.source_event_ids),
            "status": self.status, "created_at": self.created_at,
            "updated_at": self.updated_at, "user_scope": self.user_scope,
        }

