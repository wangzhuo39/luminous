from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable


def public_health(*, ready: bool) -> dict[str, object]:
    return {"ok": True, "status": "ready" if ready else "degraded"}


def public_state_snapshot(raw: Mapping[str, Any] | None) -> dict[str, object]:
    source = _mapping(raw)
    state = _mapping(source.get("state", source))
    result: dict[str, object] = {"state": public_state(state)}
    if "history" in source:
        result["history"] = public_chat_history(source.get("history"))
    return result


def public_state(raw: Mapping[str, Any] | None) -> dict[str, object]:
    source = _mapping(raw)
    relationship = _mapping(source.get("relationship"))
    return {
        "persona_name": _text(source.get("persona_name"), 80),
        "user_name": _text(source.get("user_name"), 80),
        "mood": _text(source.get("mood"), 32),
        "energy": _number(source.get("energy")),
        "support_need": _number(source.get("support_need")),
        "risk_level": _text(source.get("risk_level"), 32),
        "conversation_count": _integer(source.get("conversation_count")),
        "last_user_at": _text(source.get("last_user_at"), 40),
        "last_assistant_at": _text(source.get("last_assistant_at"), 40),
        "last_proactive_at": _text(source.get("last_proactive_at"), 40),
        "dnd_until": _text(source.get("dnd_until"), 40),
        "recent_topics": _texts(source.get("recent_topics"), 10, 120),
        "relationship": {
            "trust": _number(relationship.get("trust")),
            "intimacy": _number(relationship.get("intimacy")),
            "boundaries": _number(relationship.get("boundaries")),
            "familiarity": _number(relationship.get("familiarity")),
        },
        "conversation_mode": _text(source.get("conversation_mode"), 40),
        "open_loops": [_public_open_loop(item) for item in _mappings(source.get("open_loops"))],
    }


def public_chat(raw: Mapping[str, Any] | None) -> dict[str, object]:
    source = _mapping(raw)
    reply = _text(source.get("reply"), 12_000)
    if not reply:
        raise ValueError("chat response did not include a reply")
    presence = _mapping(source.get("presence"))
    return {
        "reply": reply,
        "presence": {
            "caption": _text(presence.get("caption"), 240),
            "activity": _text(presence.get("activity"), 240),
        },
        "state": public_state(source.get("state")),
    }

def public_chat_history(raw: Mapping[str, Any] | None) -> dict[str, object]:
    source = _mapping(raw)
    return {
        "limit": _integer(source.get("limit")),
        "count": _integer(source.get("count")),
        "items": [
            {
                "message_id": _text(item.get("message_id"), 120),
                "role": _text(item.get("role"), 16),
                "content": _text(item.get("content"), 12_000),
                "created_at": _text(item.get("created_at"), 40),
            }
            for item in _mappings(source.get("items"))
            if _text(item.get("role"), 16) in {"user", "assistant"}
            and _text(item.get("content"), 12_000)
        ],
    }


def public_memory_query(raw: Mapping[str, Any] | None) -> dict[str, object]:
    source = _mapping(raw)
    return {
        "ok": bool(source.get("ok", True)),
        "query": _text(source.get("query"), 2_000),
        "limit": _integer(source.get("limit")),
        "hits": [_public_memory(item) for item in _mappings(source.get("hits"))],
    }


def public_outbox_list(raw: Mapping[str, Any] | None) -> dict[str, object]:
    source = _mapping(raw)
    return {
        "ok": bool(source.get("ok", True)),
        "limit": _integer(source.get("limit")),
        "status": _text(source.get("status"), 32),
        "count": _integer(source.get("count")),
        "items": [_public_outbox(item) for item in _mappings(source.get("items"))],
    }


def public_outbox_mutation(raw: Mapping[str, Any] | None) -> dict[str, object]:
    source = _mapping(raw)
    result: dict[str, object] = {
        "ok": bool(source.get("ok", False)),
        "message_id": _text(source.get("message_id"), 120),
    }
    if "outbox" in source:
        result["outbox"] = _public_outbox(source.get("outbox"))
    if source.get("ok") is False:
        result["reason"] = _text(source.get("reason"), 80)
    return result


def public_memory_mutation(raw: Mapping[str, Any] | None) -> dict[str, object]:
    source = _mapping(raw)
    result: dict[str, object] = {"ok": bool(source.get("ok", False))}
    if "memory" in source:
        result["memory"] = _public_memory(_mapping(source.get("memory")))
    if "memory_id" in source:
        result["memory_id"] = _text(source.get("memory_id"), 120)
    if source.get("ok") is False:
        result["reason"] = _text(source.get("reason"), 80)
    return result


def public_notifications(raw: Mapping[str, Any] | None) -> dict[str, object]:
    source = _mapping(raw)
    preferences = _mapping(source.get("preferences", source))
    return {
        "enabled": bool(preferences.get("enabled", True)),
        "daily_limit": max(0, min(20, _integer(preferences.get("daily_limit"), 3))),
        "quiet_start": _text(preferences.get("quiet_start"), 5),
        "quiet_end": _text(preferences.get("quiet_end"), 5),
        "allowed_kinds": _texts(preferences.get("allowed_kinds"), 12, 48),
    }


def public_today(raw: Mapping[str, Any] | None) -> dict[str, object]:
    source = _mapping(raw)
    return {
        "ok": bool(source.get("ok", True)),
        "date": _text(source.get("date"), 10),
        "calendar_events": [_public_calendar_event(item) for item in _mappings(source.get("calendar_events"))],
        "overdue_tasks": [_public_task(item) for item in _mappings(source.get("overdue_tasks"))],
        "due_tasks": [_public_task(item) for item in _mappings(source.get("due_tasks"))],
        "open_tasks": [_public_task(item) for item in _mappings(source.get("open_tasks"))],
        "routines": [_public_routine(item) for item in _mappings(source.get("routines"))],
        "active_activities": [_public_activity(item) for item in _mappings(source.get("active_activities"))],
        "completed_tasks": [_public_task(item) for item in _mappings(source.get("completed_tasks"))],
    }


def public_timeline(raw: Mapping[str, Any] | None) -> dict[str, object]:
    source = _mapping(raw)
    return {
        "ok": bool(source.get("ok", True)),
        "items": [_public_timeline_item(item) for item in _mappings(source.get("items"))],
    }


def public_list(raw: Mapping[str, Any] | None, key: str, mapper: Callable[[Mapping[str, Any]], dict[str, object]]) -> dict[str, object]:
    source = _mapping(raw)
    return {
        "ok": bool(source.get("ok", True)),
        "items": [mapper(item) for item in _mappings(source.get("items"))],
        **({"count": _integer(source.get("count"))} if "count" in source else {}),
        **({"limit": _integer(source.get("limit"))} if "limit" in source else {}),
        **({"status": _text(source.get("status"), 32)} if "status" in source else {}),
    }


def public_resource(raw: Mapping[str, Any] | None, key: str, mapper: Callable[[Mapping[str, Any]], dict[str, object]]) -> dict[str, object]:
    source = _mapping(raw)
    result: dict[str, object] = {"ok": bool(source.get("ok", True))}
    if key in source:
        result[key] = mapper(_mapping(source.get(key)))
    if "idempotent" in source:
        result["idempotent"] = bool(source.get("idempotent"))
    if "streak" in source:
        result["streak"] = _integer(source.get("streak"))
    if source.get("ok") is False:
        result["reason"] = _text(source.get("reason"), 80)
        if "memory_id" in source:
            result["memory_id"] = _text(source.get("memory_id"), 120)
        if "reminder_id" in source:
            result["reminder_id"] = _text(source.get("reminder_id"), 120)
        if "event_id" in source:
            result["event_id"] = _text(source.get("event_id"), 120)
    return result


def public_action_preview(raw: Mapping[str, Any] | None) -> dict[str, object]:
    source = _mapping(raw)
    action = _text(source.get("action"), 48)
    return {
        "ok": bool(source.get("ok", True)),
        "preview_id": _text(source.get("preview_id"), 120),
        "action": action,
        "payload": _public_action_payload(action, source.get("payload")),
        "confirmation_required": bool(source.get("confirmation_required", True)),
    }


def public_action_result(raw: Mapping[str, Any] | None) -> dict[str, object]:
    source = _mapping(raw)
    result: dict[str, object] = {"ok": bool(source.get("ok", True))}
    for key, mapper in (
        ("task", _public_task),
        ("routine", _public_routine),
        ("checkin", _public_checkin),
        ("activity", _public_activity),
        ("diary_entry", _public_diary),
    ):
        if key in source:
            result[key] = mapper(_mapping(source.get(key)))
    if "streak" in source:
        result["streak"] = _integer(source.get("streak"))
    if "idempotent" in source:
        result["idempotent"] = bool(source.get("idempotent"))
    return result


def _public_task(raw: Mapping[str, Any]) -> dict[str, object]:
    return {
        "task_id": _text(raw.get("task_id"), 120),
        "title": _text(raw.get("title"), 240),
        "description": _text(raw.get("description"), 2_000),
        "status": _text(raw.get("status"), 32),
        "due_at": _text(raw.get("due_at"), 40),
        "priority": _text(raw.get("priority"), 32),
        "steps": [_public_step(item) for item in _mappings(raw.get("steps"))],
        "created_at": _text(raw.get("created_at"), 40),
        "updated_at": _text(raw.get("updated_at"), 40),
        "completed_at": _text(raw.get("completed_at"), 40),
    }


def _public_step(raw: Mapping[str, Any]) -> dict[str, object]:
    return {
        "step_id": _text(raw.get("step_id"), 120),
        "task_id": _text(raw.get("task_id"), 120),
        "title": _text(raw.get("title"), 240),
        "position": _integer(raw.get("position")),
        "status": _text(raw.get("status"), 32),
        "completed_at": _text(raw.get("completed_at"), 40),
    }


def _public_routine(raw: Mapping[str, Any]) -> dict[str, object]:
    result: dict[str, object] = {
        "routine_id": _text(raw.get("routine_id"), 120),
        "title": _text(raw.get("title"), 240),
        "schedule": _text(raw.get("schedule"), 32),
        "active": bool(raw.get("active", True)),
        "reminder_policy": _text(raw.get("reminder_policy"), 32),
        "created_at": _text(raw.get("created_at"), 40),
        "updated_at": _text(raw.get("updated_at"), 40),
    }
    if "streak" in raw:
        result["streak"] = _integer(raw.get("streak"))
    if "period_key" in raw:
        result["period_key"] = _text(raw.get("period_key"), 32)
    if raw.get("checkin") is not None:
        result["checkin"] = _public_checkin(_mapping(raw.get("checkin")))
    return result


def _public_checkin(raw: Mapping[str, Any]) -> dict[str, object]:
    return {
        "checkin_id": _text(raw.get("checkin_id"), 120),
        "routine_id": _text(raw.get("routine_id"), 120),
        "period_key": _text(raw.get("period_key"), 32),
        "status": _text(raw.get("status"), 32),
        "note": _text(raw.get("note"), 2_000),
        "occurred_at": _text(raw.get("occurred_at"), 40),
    }


def _public_activity(raw: Mapping[str, Any]) -> dict[str, object]:
    return {
        "session_id": _text(raw.get("session_id"), 120),
        "kind": _text(raw.get("kind"), 48),
        "title": _text(raw.get("title"), 240),
        "status": _text(raw.get("status"), 32),
        "started_at": _text(raw.get("started_at"), 40),
        "ended_at": _text(raw.get("ended_at"), 40),
        "summary": _text(raw.get("summary"), 2_000),
        "created_at": _text(raw.get("created_at"), 40),
        "updated_at": _text(raw.get("updated_at"), 40),
    }


def _public_diary(raw: Mapping[str, Any]) -> dict[str, object]:
    return {
        "entry_id": _text(raw.get("entry_id"), 120),
        "date": _text(raw.get("date"), 10),
        "title": _text(raw.get("title"), 240),
        "body": _text(raw.get("body"), 20_000, preserve_whitespace=True),
        "status": _text(raw.get("status"), 32),
        "created_at": _text(raw.get("created_at"), 40),
        "updated_at": _text(raw.get("updated_at"), 40),
    }


def _public_reminder(raw: Mapping[str, Any]) -> dict[str, object]:
    return {
        "reminder_id": _text(raw.get("reminder_id"), 120),
        "title": _text(raw.get("title"), 240),
        "due_at": _text(raw.get("due_at"), 40),
        "timezone_name": _text(raw.get("timezone_name"), 80),
        "description": _text(raw.get("description"), 2_000),
        "kind": _text(raw.get("kind"), 48),
        "status": _text(raw.get("status"), 32),
        "recurrence": _text(raw.get("recurrence"), 120),
        "created_at": _text(raw.get("created_at"), 40),
        "updated_at": _text(raw.get("updated_at"), 40),
    }


def _public_calendar_event(raw: Mapping[str, Any]) -> dict[str, object]:
    return {
        "event_id": _text(raw.get("event_id"), 120),
        "title": _text(raw.get("title"), 240),
        "starts_at": _text(raw.get("starts_at"), 40),
        "ends_at": _text(raw.get("ends_at"), 40),
        "all_day": bool(raw.get("all_day", False)),
        "timezone_name": _text(raw.get("timezone_name"), 80),
        "status": _text(raw.get("status"), 32),
        "created_at": _text(raw.get("created_at"), 40),
        "updated_at": _text(raw.get("updated_at"), 40),
    }


def _public_outbox(raw: Mapping[str, Any]) -> dict[str, object]:
    return {
        "message_id": _text(raw.get("message_id"), 120),
        "channel": _text(raw.get("channel"), 48),
        "draft_text": _text(raw.get("draft_text"), 4_000),
        "status": _text(raw.get("status"), 32),
        "signal_type": _text(raw.get("signal_type"), 48),
        "created_at": _text(raw.get("created_at"), 40),
        "sent_at": _text(raw.get("sent_at"), 40),
        "replied_at": _text(raw.get("replied_at"), 40),
    }


def _public_memory(raw: Mapping[str, Any]) -> dict[str, object]:
    return {
        "memory_id": _text(raw.get("memory_id"), 120),
        "kind": _text(raw.get("kind"), 48),
        "text": _text(raw.get("text"), 4_000),
        "status": _text(raw.get("status"), 32),
        "tags": _texts(raw.get("tags"), 16, 80),
        "created_at": _text(raw.get("created_at"), 40),
        "observed_at": _text(raw.get("observed_at"), 40),
        **({"score": _number(raw.get("score"))} if "score" in raw else {}),
        **({"reason": _text(raw.get("reason"), 240)} if "reason" in raw else {}),
    }


def _public_timeline_item(raw: Mapping[str, Any]) -> dict[str, object]:
    return {
        "item_id": _text(raw.get("item_id"), 160),
        "occurred_at": _text(raw.get("occurred_at"), 40),
        "kind": _text(raw.get("kind"), 48),
        "title": _text(raw.get("title"), 240),
    }


def _public_open_loop(raw: Mapping[str, Any]) -> dict[str, object]:
    return {
        "summary": _text(raw.get("summary"), 240),
        "status": _text(raw.get("status"), 32),
        "due_at": _text(raw.get("due_at"), 40),
    }


def _public_action_payload(action: str, value: Any) -> dict[str, object]:
    source = _mapping(value)
    fields = {
        "create_task": ("title", "description", "due_at", "priority"),
        "complete_task": ("task_id",),
        "start_focus_session": ("title", "summary"),
        "checkin_routine": ("routine_id", "period_key", "note"),
        "draft_diary": ("date",),
    }.get(action, ())
    result: dict[str, object] = {}
    for field in fields:
        if field in source:
            result[field] = _text(source.get(field), 2_000)
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_mapping(item) for item in value]


def _text(value: Any, limit: int, preserve_whitespace: bool = False) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value if preserve_whitespace else " ".join(value.split())
    return normalized[:limit]


def _texts(value: Any, limit: int, item_limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item, item_limit) for item in value if isinstance(item, str)][:limit]


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


public_task = _public_task
public_step = _public_step
public_routine = _public_routine
public_checkin = _public_checkin
public_activity = _public_activity
public_diary = _public_diary
public_reminder = _public_reminder
public_calendar_event = _public_calendar_event
