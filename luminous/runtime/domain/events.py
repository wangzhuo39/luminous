from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from luminous.runtime.domain.time import utc_now_iso


def new_event_id(prefix: str = "evt") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class ConversationEvent:
    event_id: str
    trace_id: str
    event_type: str
    created_at: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 2
    actor: str = "runtime"
    privacy_level: str = "internal"
    source_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "event_type": self.event_type,
            "created_at": self.created_at,
            "summary": self.summary,
            "payload": self.payload,
            "schema_version": self.schema_version,
            "actor": self.actor,
            "privacy_level": self.privacy_level,
            "source_ids": self.source_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationEvent":
        return cls(
            event_id=str(data.get("event_id", "")),
            trace_id=str(data.get("trace_id", "")),
            event_type=str(data.get("event_type", "event")),
            created_at=str(data.get("created_at", "")),
            summary=str(data.get("summary", "")),
            payload=dict(data.get("payload", {}) or {}),
            schema_version=int(data.get("schema_version", 1)),
            actor=str(data.get("actor", "runtime")),
            privacy_level=str(data.get("privacy_level", "internal")),
            source_ids=list(data.get("source_ids", []) or []),
        )


@dataclass(frozen=True)
class ProactiveSignal:
    due: bool
    score: float
    reason: str
    next_check_minutes: int
    draft_message: str = ""
    trace_id: str = ""
    created_at: str = ""
    signal_type: str = "silence_checkin"
    anchor_memory_ids: tuple[str, ...] = ()
    hold_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "due": self.due,
            "score": round(self.score, 3),
            "reason": self.reason,
            "next_check_minutes": self.next_check_minutes,
            "draft_message": self.draft_message,
            "trace_id": self.trace_id,
            "created_at": self.created_at,
            "signal_type": self.signal_type,
            "anchor_memory_ids": list(self.anchor_memory_ids),
            "hold_reasons": list(self.hold_reasons),
        }


def make_event(
    event_type: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    trace_id: str | None = None,
    *,
    now: datetime | None = None,
    actor: str = "runtime",
    privacy_level: str = "internal",
    source_ids: list[str] | None = None,
) -> ConversationEvent:
    return ConversationEvent(
        event_id=new_event_id(),
        trace_id=trace_id or new_event_id("trace"),
        event_type=event_type,
        created_at=utc_now_iso(now),
        summary=summary,
        payload=payload or {},
        actor=actor,
        privacy_level=privacy_level,
        source_ids=source_ids or [],
    )
