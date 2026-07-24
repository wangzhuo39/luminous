from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from collections.abc import Iterable
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from luminous.runtime.domain.events import ConversationEvent, make_event
from luminous.runtime.domain.memory import MemoryHit, MemoryQuery, MemoryRecord, score_memory
from luminous.runtime.domain.scheduling import CalendarEvent, Reminder, ReminderStatus
from luminous.runtime.domain.state import CompanionState
from luminous.runtime.domain.time import parse_iso_datetime, utc_now_iso


class CompanionRuntimeStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_dir / "runtime.sqlite3"
        self.state_path = self.base_dir / "state.json"
        self.memory_path = self.base_dir / "memory.jsonl"
        self.event_path = self.base_dir / "events.jsonl"
        self.outbox_path = self.base_dir / "outbox.jsonl"
        self._ensure_schema()

    @classmethod
    def for_project(cls, project_root: Path) -> "CompanionRuntimeStore":
        return cls((project_root / "outputs" / "companion_runtime").resolve())

    def load_state(self) -> CompanionState:
        row = self._fetch_one("SELECT payload FROM companion_state WHERE state_key = ?", ("default",))
        if row and row["payload"]:
            data = json.loads(row["payload"])
            if isinstance(data, dict):
                return CompanionState.from_dict(data)
        if self.state_path.exists():
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                state = CompanionState.from_dict(data)
                self.save_state(state)
                return state
        return CompanionState()

    def save_state(self, state: CompanionState) -> None:
        payload = json.dumps(state.to_dict(), ensure_ascii=False)
        self._execute(
            """
            INSERT INTO companion_state (state_key, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(state_key) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
            """,
            ("default", payload, utc_now_iso()),
        )
        _write_json_atomic(self.state_path, state.to_dict())

    def append_event(self, event: ConversationEvent) -> None:
        payload = event.to_dict()
        self._execute(
            """
            INSERT OR REPLACE INTO events (
                event_id, trace_id, event_type, created_at, summary,
                payload_json, schema_version, actor, privacy_level, source_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["event_id"],
                payload["trace_id"],
                payload["event_type"],
                payload["created_at"],
                payload["summary"],
                json.dumps(payload.get("payload", {}), ensure_ascii=False),
                int(payload.get("schema_version", 1)),
                payload.get("actor", "runtime"),
                payload.get("privacy_level", "internal"),
                json.dumps(payload.get("source_ids", []), ensure_ascii=False),
            ),
        )

    def append_memory(self, record: MemoryRecord) -> MemoryRecord:
        record = self.write_memory(record)
        return record

    def write_memory(
        self,
        record: MemoryRecord,
        *,
        apply_guard: bool = True,
        trace_id: str | None = None,
        emit_audit: bool = False,
    ) -> MemoryRecord:
        if apply_guard:
            record, should_write, guard_events = self._apply_memory_guard(record)
            if emit_audit and trace_id:
                self._append_memory_guard_events(
                    guard_events,
                    trace_id=trace_id,
                    now=parse_iso_datetime(record.created_at) or datetime.now(timezone.utc),
                )
            if not should_write:
                return record
        elif emit_audit and trace_id:
            self._append_memory_guard_events(
                [
                    {
                        "action": "write",
                        "reason": "guard_disabled",
                        "summary": f"记忆写入：{record.kind}",
                        "new_memory_id": record.memory_id,
                        "new_kind": record.kind,
                        "new_text": record.text,
                        "source_ids": [record.source_event_id] if record.source_event_id else [],
                    }
                ],
                trace_id=trace_id,
                now=parse_iso_datetime(record.created_at) or datetime.now(timezone.utc),
            )
        payload = record.to_dict()
        self._execute(
            """
            INSERT OR REPLACE INTO memory_items (
                memory_id, layer, kind, status, text, source_event_id, source_role,
                source_excerpt, evidence_quote, evidence_event_id, tags_json,
                importance, confidence, created_at, observed_at, last_accessed_at,
                access_count, superseded_by, supersedes_json, expires_at, metadata_json,
                schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["memory_id"],
                payload["layer"],
                payload["kind"],
                payload["status"],
                payload["text"],
                payload["source_event_id"],
                payload["source_role"],
                payload["source_excerpt"],
                payload["evidence_quote"],
                payload["evidence_event_id"],
                json.dumps(payload.get("tags", []), ensure_ascii=False),
                float(payload.get("importance", 0.5)),
                float(payload.get("confidence", 0.6)),
                payload.get("created_at", ""),
                payload.get("observed_at", ""),
                payload.get("last_accessed_at", ""),
                int(payload.get("access_count", 0)),
                payload.get("superseded_by", ""),
                json.dumps(payload.get("supersedes", []), ensure_ascii=False),
                payload.get("expires_at", ""),
                json.dumps(payload.get("metadata", {}), ensure_ascii=False),
                int(payload.get("schema_version", 2)),
            ),
        )
        self._attach_memory_to_thread(record)
        self._upsert_memory_fts(record)
        self._upsert_memory_evidence(record, trace_id=trace_id or "")
        if emit_audit and trace_id:
            self._append_memory_guard_events(
                [
                    {
                        "action": "write",
                        "reason": "accepted",
                        "summary": f"记忆写入：{record.kind}",
                        "new_memory_id": record.memory_id,
                        "new_kind": record.kind,
                        "new_text": record.text,
                        "source_ids": [record.source_event_id] if record.source_event_id else [],
                    }
                ],
                trace_id=trace_id,
                now=parse_iso_datetime(record.created_at) or datetime.now(timezone.utc),
            )
        return record

    def append_raw_message(
        self,
        *,
        message_id: str,
        trace_id: str,
        turn_id: str,
        role: str,
        content: str,
        created_at: str | None = None,
        source_event_id: str = "",
        privacy_level: str = "internal",
    ) -> None:
        self._execute(
            """
            INSERT OR REPLACE INTO raw_messages (
                message_id, trace_id, turn_id, role, content, created_at, source_event_id, privacy_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                trace_id,
                turn_id,
                role,
                content,
                created_at or utc_now_iso(),
                source_event_id,
                privacy_level,
            ),
        )

    def read_raw_messages(self, limit: int | None = None, role: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM raw_messages"
        params: list[Any] = []
        if role:
            sql += " WHERE role = ?"
            params.append(role)
        sql += " ORDER BY created_at ASC, message_id ASC"
        rows = self._fetch_all(sql, tuple(params))
        payloads = [_row_to_raw_message(row) for row in rows]
        if limit is not None and limit < len(payloads):
            payloads = payloads[-limit:]
        return payloads

    def append_outbox(self, payload: dict[str, Any]) -> str:
        message_id = str(payload.get("message_id") or payload.get("id") or payload.get("signal_id") or "")
        if not message_id:
            message_id = f"out_{utc_now_iso().replace(':', '').replace('-', '').replace('T', '_')}"
        created_at = str(payload.get("created_at", utc_now_iso()))
        self._execute(
            """
            INSERT OR REPLACE INTO outbox (
                message_id, signal_id, trace_id, channel, draft_text, status, score,
                reason, signal_type, anchor_memory_ids_json, created_at, sent_at,
                replied_at, payload_json, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                str(payload.get("signal_id", "")),
                str(payload.get("trace_id", "")),
                str(payload.get("channel", "internal")),
                str(payload.get("draft_text") or payload.get("message", "")),
                str(payload.get("status", "drafted")),
                float(payload.get("score", 0.0)),
                str(payload.get("reason", "")),
                str(payload.get("signal_type", "")),
                json.dumps(payload.get("anchor_memory_ids", []), ensure_ascii=False),
                created_at,
                str(payload.get("sent_at", "")),
                str(payload.get("replied_at", "")),
                json.dumps(payload, ensure_ascii=False),
                str(payload.get("idempotency_key", message_id)),
            ),
        )
        return message_id

    def read_memory_threads(self, limit: int | None = None) -> list[dict[str, Any]]:
        rows = self._fetch_all("SELECT * FROM memory_threads ORDER BY updated_at DESC, thread_id ASC")
        threads: list[dict[str, Any]] = []
        for row in rows:
            thread = _row_to_memory_thread(row)
            members = self._fetch_all(
                """
                SELECT m.thread_id, m.memory_id, m.position, m.relation, m.created_at, i.*
                FROM memory_thread_members AS m
                LEFT JOIN memory_items AS i ON i.memory_id = m.memory_id
                WHERE m.thread_id = ?
                ORDER BY m.position ASC, m.created_at ASC, m.memory_id ASC
                """,
                (thread["thread_id"],),
            )
            thread["members"] = [_row_to_thread_member(member) for member in members]
            thread["member_count"] = len(thread["members"])
            threads.append(thread)
        if limit is not None and limit < len(threads):
            threads = threads[:limit]
        return threads

    def read_memory_links(self, limit: int | None = None) -> list[dict[str, Any]]:
        rows = self._fetch_all("SELECT * FROM memory_links ORDER BY created_at DESC, link_id DESC")
        links = [_row_to_memory_link(row) for row in rows]
        if limit is not None and limit < len(links):
            links = links[:limit]
        return links

    def read_memory_evidence(
        self,
        limit: int | None = None,
        memory_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM memory_evidence"
        params: list[Any] = []
        clauses: list[str] = []
        if memory_id:
            clauses.append("memory_id = ?")
            params.append(memory_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC, created_at DESC, memory_id ASC"
        rows = self._fetch_all(sql, tuple(params))
        items = [_row_to_memory_evidence(row) for row in rows]
        if limit is not None and limit < len(items):
            items = items[:limit]
        return items

    def update_memory(self, memory_id: str, updates: dict[str, Any] | None = None) -> MemoryRecord | None:
        updates = updates or {}
        row = self._fetch_one("SELECT * FROM memory_items WHERE memory_id = ?", (memory_id,))
        if row is None:
            return None
        current = MemoryRecord.from_dict(_row_to_memory(row))
        metadata = dict(current.metadata or {})
        if "metadata" in updates and isinstance(updates["metadata"], dict):
            metadata.update(updates["metadata"])
        if "status" in updates and updates["status"]:
            status = str(updates["status"])
        else:
            status = current.status
        if status == "forgotten":
            metadata.setdefault("forgotten_at", utc_now_iso())
        text = str(updates.get("text", current.text) or current.text).strip() or current.text
        kind = str(updates.get("kind", current.kind) or current.kind)
        source_excerpt = str(updates.get("source_excerpt", current.source_excerpt) or current.source_excerpt)
        evidence_quote = str(updates.get("evidence_quote", current.evidence_quote) or current.evidence_quote)
        evidence_event_id = str(updates.get("evidence_event_id", current.evidence_event_id) or current.evidence_event_id)
        expires_at = str(updates.get("expires_at", current.expires_at) or current.expires_at)
        tags = updates.get("tags", current.tags)
        if not isinstance(tags, list):
            tags = list(current.tags)
        importance = float(updates.get("importance", current.importance))
        confidence = float(updates.get("confidence", current.confidence))
        self._execute(
            """
            UPDATE memory_items
            SET kind = ?, status = ?, text = ?, source_excerpt = ?, evidence_quote = ?,
                evidence_event_id = ?, tags_json = ?, importance = ?, confidence = ?,
                expires_at = ?, metadata_json = ?, updated_at = ?
            WHERE memory_id = ?
            """,
            (
                kind,
                status,
                text,
                source_excerpt,
                evidence_quote,
                evidence_event_id,
                json.dumps(tags, ensure_ascii=False),
                importance,
                confidence,
                expires_at,
                json.dumps(metadata, ensure_ascii=False),
                utc_now_iso(),
                memory_id,
            ),
        )
        if status != "active":
            self._execute("DELETE FROM memory_fts WHERE memory_id = ?", (memory_id,))
        else:
            refreshed = MemoryRecord.from_dict(
                {
                    **current.to_dict(),
                    "kind": kind,
                    "status": status,
                    "text": text,
                    "source_excerpt": source_excerpt,
                    "evidence_quote": evidence_quote,
                    "evidence_event_id": evidence_event_id,
                    "tags": tags,
                    "importance": importance,
                    "confidence": confidence,
                    "expires_at": expires_at,
                    "metadata": metadata,
                }
            )
            self._upsert_memory_fts(refreshed)
        self._sync_memory_evidence(memory_id)
        self.rebuild_memory_threads()
        updated = self._fetch_one("SELECT * FROM memory_items WHERE memory_id = ?", (memory_id,))
        if updated is None:
            return None
        return MemoryRecord.from_dict(_row_to_memory(updated))

    def forget_memory(self, memory_id: str, *, hard_delete: bool = False) -> MemoryRecord | None:
        row = self._fetch_one("SELECT * FROM memory_items WHERE memory_id = ?", (memory_id,))
        if row is None:
            return None
        if hard_delete:
            self._execute("DELETE FROM memory_items WHERE memory_id = ?", (memory_id,))
            self._execute("DELETE FROM memory_fts WHERE memory_id = ?", (memory_id,))
            self._execute("DELETE FROM memory_evidence WHERE memory_id = ?", (memory_id,))
            self._execute("DELETE FROM memory_thread_members WHERE memory_id = ?", (memory_id,))
            self._execute(
                "DELETE FROM memory_links WHERE source_memory_id = ? OR target_memory_id = ?",
                (memory_id, memory_id),
            )
            self.rebuild_memory_threads()
            return None
        current = MemoryRecord.from_dict(_row_to_memory(row))
        metadata = dict(current.metadata or {})
        metadata["forgotten_at"] = utc_now_iso()
        metadata["forgotten_mode"] = "soft"
        self._execute(
            """
            UPDATE memory_items
            SET status = 'forgotten', metadata_json = ?, updated_at = ?
            WHERE memory_id = ?
            """,
            (json.dumps(metadata, ensure_ascii=False), utc_now_iso(), memory_id),
        )
        self._execute("DELETE FROM memory_fts WHERE memory_id = ?", (memory_id,))
        self._sync_memory_evidence(memory_id)
        self.rebuild_memory_threads()
        updated = self._fetch_one("SELECT * FROM memory_items WHERE memory_id = ?", (memory_id,))
        if updated is None:
            return None
        return MemoryRecord.from_dict(_row_to_memory(updated))

    def export_bundle(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "generated_at": utc_now_iso(),
            "state": self.load_state().to_dict(),
            "events": [event.to_dict() for event in self.read_events()],
            "memories": [record.to_dict() for record in self.read_memories()],
            "memory_evidence": self.read_memory_evidence(),
            "raw_messages": self.read_raw_messages(),
            "outbox": self.read_outbox(),
            "jobs": self.read_jobs(),
            "memory_threads": self.read_memory_threads(),
            "memory_links": self.read_memory_links(),
            "reminders": [item.to_dict() for item in self.read_reminders()],
            "calendar_events": [item.to_dict() for item in self.read_calendar_events()],
            "notification_preferences": self.read_notification_preferences(),
        }

    def save_reminder(self, reminder: Reminder) -> Reminder:
        payload = reminder.to_dict()
        self._execute(
            """
            INSERT INTO reminders (
                reminder_id, user_scope, title, description, kind, status, due_at,
                timezone_name, source, source_ref, recurrence, delivery_count,
                last_delivered_at, created_at, updated_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(reminder_id) DO UPDATE SET
                title = excluded.title, description = excluded.description, kind = excluded.kind,
                status = excluded.status, due_at = excluded.due_at, timezone_name = excluded.timezone_name,
                source = excluded.source, source_ref = excluded.source_ref, recurrence = excluded.recurrence,
                delivery_count = excluded.delivery_count, last_delivered_at = excluded.last_delivered_at,
                updated_at = excluded.updated_at, metadata_json = excluded.metadata_json
            """,
            (
                reminder.reminder_id, reminder.user_scope, reminder.title, reminder.description,
                reminder.kind.value, reminder.status.value, reminder.due_at, reminder.timezone_name,
                reminder.source, reminder.source_ref, reminder.recurrence, reminder.delivery_count,
                reminder.last_delivered_at, reminder.created_at, reminder.updated_at,
                json.dumps(reminder.metadata, ensure_ascii=False),
            ),
        )
        return Reminder.from_dict(payload)

    def get_reminder(self, reminder_id: str) -> Reminder | None:
        row = self._fetch_one("SELECT * FROM reminders WHERE reminder_id = ?", (reminder_id,))
        return Reminder.from_dict(_row_to_reminder(row)) if row else None

    def read_reminders(
        self,
        *,
        user_scope: str = "default",
        status: str | None = None,
        limit: int | None = None,
    ) -> list[Reminder]:
        sql = "SELECT * FROM reminders WHERE user_scope = ?"
        params: list[Any] = [user_scope]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY due_at ASC, reminder_id ASC"
        rows = self._fetch_all(sql, tuple(params))
        values = [Reminder.from_dict(_row_to_reminder(row)) for row in rows]
        return values[:limit] if limit is not None else values

    def claim_due_reminders(self, *, now: datetime | None = None, limit: int = 20) -> list[Reminder]:
        now = now or datetime.now(timezone.utc)
        now_iso = utc_now_iso(now)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reminders
                WHERE status IN ('scheduled', 'snoozed', 'due') AND due_at <= ?
                ORDER BY due_at ASC, reminder_id ASC LIMIT ?
                """,
                (now_iso, limit),
            ).fetchall()
            claimed: list[Reminder] = []
            for row in rows:
                changed = conn.execute(
                    """
                    UPDATE reminders SET status = 'due', updated_at = ?
                    WHERE reminder_id = ? AND status IN ('scheduled', 'snoozed')
                    """,
                    (now_iso, row["reminder_id"]),
                ).rowcount
                if changed:
                    current = dict(row)
                    current.update({"status": "due", "updated_at": now_iso})
                    claimed.append(Reminder.from_dict(current))
                elif row["status"] == "due" and int(row["delivery_count"]) == 0:
                    claimed.append(Reminder.from_dict(_row_to_reminder(row)))
            conn.commit()
        return claimed

    def update_reminder(self, reminder_id: str, updates: dict[str, Any], *, now: datetime | None = None) -> Reminder | None:
        current = self.get_reminder(reminder_id)
        if current is None:
            return None
        status = ReminderStatus(str(updates.pop("status", current.status.value)))
        allowed = {
            "title", "description", "due_at", "timezone_name", "source", "source_ref",
            "recurrence", "metadata", "kind", "user_scope",
        }
        changes = {key: value for key, value in updates.items() if key in allowed}
        if "kind" in changes:
            changes["kind"] = str(changes["kind"])
        reminder = current.transition(status, now=now, **changes)
        return self.save_reminder(reminder)

    def mark_reminder_delivered(self, reminder_id: str, *, now: datetime | None = None) -> Reminder | None:
        current = self.get_reminder(reminder_id)
        if current is None:
            return None
        payload = current.to_dict()
        payload["delivery_count"] = current.delivery_count + 1
        payload["last_delivered_at"] = utc_now_iso(now)
        payload["updated_at"] = utc_now_iso(now)
        cadence_days = {"daily": 1, "weekly": 7}.get(current.recurrence)
        if cadence_days:
            next_due = parse_iso_datetime(current.due_at) or now or datetime.now(timezone.utc)
            reference = now or datetime.now(timezone.utc)
            while next_due <= reference:
                next_due += timedelta(days=cadence_days)
            payload["due_at"] = utc_now_iso(next_due)
            payload["status"] = ReminderStatus.SCHEDULED.value
        return self.save_reminder(Reminder.from_dict(payload))

    def save_calendar_event(self, event: CalendarEvent) -> CalendarEvent:
        self._execute(
            """
            INSERT INTO calendar_events (
                event_id, user_scope, title, starts_at, ends_at, all_day, timezone_name,
                reminder_ids_json, status, created_at, updated_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                title = excluded.title, starts_at = excluded.starts_at, ends_at = excluded.ends_at,
                all_day = excluded.all_day, timezone_name = excluded.timezone_name,
                reminder_ids_json = excluded.reminder_ids_json, status = excluded.status,
                updated_at = excluded.updated_at, metadata_json = excluded.metadata_json
            """,
            (
                event.event_id, event.user_scope, event.title, event.starts_at, event.ends_at,
                int(event.all_day), event.timezone_name, json.dumps(event.reminder_ids, ensure_ascii=False),
                event.status, event.created_at, event.updated_at, json.dumps(event.metadata, ensure_ascii=False),
            ),
        )
        return event

    def get_calendar_event(self, event_id: str) -> CalendarEvent | None:
        row = self._fetch_one("SELECT * FROM calendar_events WHERE event_id = ?", (event_id,))
        return CalendarEvent.from_dict(_row_to_calendar_event(row)) if row else None

    def read_calendar_events(self, *, user_scope: str = "default", limit: int | None = None) -> list[CalendarEvent]:
        rows = self._fetch_all(
            "SELECT * FROM calendar_events WHERE user_scope = ? AND status != 'deleted' ORDER BY starts_at ASC, event_id ASC",
            (user_scope,),
        )
        values = [CalendarEvent.from_dict(_row_to_calendar_event(row)) for row in rows]
        return values[:limit] if limit is not None else values

    def update_calendar_event(self, event_id: str, updates: dict[str, Any], *, now: datetime | None = None) -> CalendarEvent | None:
        current = self.get_calendar_event(event_id)
        if current is None:
            return None
        payload = current.to_dict()
        for key in {"title", "starts_at", "ends_at", "all_day", "timezone_name", "reminder_ids", "status", "metadata"}:
            if key in updates:
                payload[key] = updates[key]
        payload["updated_at"] = utc_now_iso(now)
        return self.save_calendar_event(CalendarEvent.from_dict(payload))

    def read_notification_preferences(self, user_scope: str = "default") -> dict[str, Any]:
        default = {
            "user_scope": user_scope,
            "enabled": True,
            "daily_limit": 3,
            "quiet_start": "",
            "quiet_end": "",
            "allowed_kinds": ["checkin", "open_loop_followup", "reminder", "anniversary", "routine", "repair"],
            "updated_at": "",
        }
        row = self._fetch_one("SELECT payload_json FROM notification_preferences WHERE user_scope = ?", (user_scope,))
        if row is None:
            return default
        payload = json.loads(row["payload_json"] or "{}")
        return {**default, **payload, "user_scope": user_scope}

    def save_notification_preferences(self, updates: dict[str, Any], *, user_scope: str = "default", now: datetime | None = None) -> dict[str, Any]:
        current = self.read_notification_preferences(user_scope)
        allowed = {"enabled", "daily_limit", "quiet_start", "quiet_end", "allowed_kinds"}
        payload = {**current, **{key: value for key, value in updates.items() if key in allowed}}
        payload["daily_limit"] = max(0, min(20, int(payload["daily_limit"])))
        if not isinstance(payload.get("allowed_kinds"), list):
            raise ValueError("allowed_kinds must be a list")
        payload["allowed_kinds"] = sorted({str(value) for value in payload["allowed_kinds"]})
        payload["updated_at"] = utc_now_iso(now)
        self._execute(
            """
            INSERT INTO notification_preferences (user_scope, payload_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_scope) DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
            """,
            (user_scope, json.dumps(payload, ensure_ascii=False), payload["updated_at"]),
        )
        return payload

    def count_outbox_since(self, since: datetime, *, signal_type: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS count FROM outbox WHERE status IN ('drafted', 'sent', 'delivered') AND created_at >= ?"
        params: list[Any] = [utc_now_iso(since)]
        if signal_type:
            sql += " AND signal_type = ?"
            params.append(signal_type)
        row = self._fetch_one(sql, tuple(params))
        return int(row["count"]) if row else 0

    def record_outbox_feedback(
        self,
        message_id: str,
        status: str,
        *,
        feedback_text: str = "",
        replied_at: str | None = None,
    ) -> dict[str, Any] | None:
        row = self._fetch_one("SELECT * FROM outbox WHERE message_id = ?", (message_id,))
        if row is None:
            return None
        current = _row_to_outbox(row)
        reply_at = replied_at or utc_now_iso()
        payload = dict(current.get("payload", {}) or {})
        payload.update(
            {
                "feedback_text": feedback_text,
                "feedback_status": status,
                "feedback_at": reply_at,
            }
        )
        self._execute(
            """
            UPDATE outbox
            SET status = ?, replied_at = ?, payload_json = ?
            WHERE message_id = ?
            """,
            (status, reply_at, json.dumps(payload, ensure_ascii=False), message_id),
        )
        updated = self._fetch_one("SELECT * FROM outbox WHERE message_id = ?", (message_id,))
        if updated is None:
            return None
        return _row_to_outbox(updated)

    def record_outbox_receipt(
        self,
        message_id: str,
        receipt_type: str,
        *,
        channel: str = "",
        payload: dict[str, Any] | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any] | None:
        row = self._fetch_one("SELECT * FROM outbox WHERE message_id = ?", (message_id,))
        if row is None:
            return None
        current = _row_to_outbox(row)
        current_payload = dict(current.get("payload", {}) or {})
        receipts = list(current_payload.get("delivery_receipts", []) or [])
        receipt = {
            "receipt_type": receipt_type,
            "channel": channel or current.get("channel", "internal"),
            "occurred_at": occurred_at or utc_now_iso(),
            "payload": payload or {},
        }
        receipts.append(receipt)
        current_payload["delivery_receipts"] = receipts[-30:]
        self._execute(
            """
            UPDATE outbox
            SET payload_json = ?
            WHERE message_id = ?
            """,
            (json.dumps(current_payload, ensure_ascii=False), message_id),
        )
        updated = self._fetch_one("SELECT * FROM outbox WHERE message_id = ?", (message_id,))
        if updated is None:
            return None
        return _row_to_outbox(updated)

    def enqueue_job(
        self,
        job_type: str,
        payload: dict[str, Any] | None = None,
        *,
        run_after: datetime | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 5,
    ) -> str:
        payload = payload or {}
        run_after_iso = utc_now_iso(run_after)
        idem = idempotency_key or f"{job_type}:{run_after_iso}"
        job_id = f"job_{job_type}_{hashlib.sha256(idem.encode('utf-8')).hexdigest()[:12]}"
        self._execute(
            """
            INSERT INTO jobs (
                job_id, job_type, payload_json, status, run_after, locked_until,
                attempts, max_attempts, idempotency_key, last_error, created_at, updated_at
            ) VALUES (?, ?, ?, 'queued', ?, '', 0, ?, ?, '', ?, ?)
            ON CONFLICT(idempotency_key) DO UPDATE SET
                payload_json = excluded.payload_json,
                run_after = excluded.run_after,
                status = CASE WHEN jobs.status = 'running' THEN jobs.status ELSE 'queued' END,
                updated_at = excluded.updated_at
            """,
            (
                job_id,
                job_type,
                json.dumps(payload, ensure_ascii=False),
                run_after_iso,
                max_attempts,
                idem,
                run_after_iso,
                utc_now_iso(),
            ),
        )
        row = self._fetch_one("SELECT job_id FROM jobs WHERE idempotency_key = ?", (idem,))
        return str(row["job_id"]) if row else job_id

    def claim_due_jobs(
        self,
        *,
        now: datetime | None = None,
        limit: int = 5,
        lease_seconds: int = 300,
    ) -> list[dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        now_iso = utc_now_iso(now)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE status = 'queued'
                  AND (run_after IS NULL OR run_after <= ?)
                  AND attempts < max_attempts
                  AND (locked_until = '' OR locked_until < ?)
                ORDER BY run_after ASC, created_at ASC
                LIMIT ?
                """,
                (now_iso, now_iso, limit),
            ).fetchall()
            claimed: list[dict[str, Any]] = []
            lease_until = utc_now_iso(now + _seconds_delta(lease_seconds))
            for row in rows:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'running', attempts = attempts + 1, locked_until = ?, updated_at = ?
                    WHERE job_id = ? AND status = 'queued'
                    """,
                    (lease_until, now_iso, row["job_id"]),
                )
                updated = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (row["job_id"],)).fetchone()
                if updated and updated["status"] == "running":
                    claimed.append(_row_to_job(updated))
            conn.commit()
        return claimed

    def complete_job(self, job_id: str, result: dict[str, Any] | None = None) -> None:
        payload = json.dumps(result or {}, ensure_ascii=False)
        self._execute(
            """
            UPDATE jobs
            SET status = 'succeeded', locked_until = '', last_error = '', updated_at = ?, payload_json = ?
            WHERE job_id = ?
            """,
            (utc_now_iso(), payload, job_id),
        )

    def fail_job(self, job_id: str, error: str) -> None:
        self._execute(
            """
            UPDATE jobs
            SET status = 'failed', last_error = ?, locked_until = '', updated_at = ?
            WHERE job_id = ?
            """,
            (error[:1000], utc_now_iso(), job_id),
        )

    def read_events(
        self,
        limit: int | None = None,
        trace_id: str | None = None,
        event_type: str | None = None,
    ) -> list[ConversationEvent]:
        sql = "SELECT * FROM events"
        params: list[Any] = []
        clauses: list[str] = []
        if trace_id:
            clauses.append("trace_id = ?")
            params.append(trace_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC, event_id ASC"
        rows = self._fetch_all(sql, tuple(params))
        events = [ConversationEvent.from_dict(_row_to_event(row)) for row in rows]
        if not events and self.event_path.exists():
            events = [ConversationEvent.from_dict(row) for row in _read_jsonl(self.event_path)]
            if trace_id:
                events = [event for event in events if event.trace_id == trace_id]
            if event_type:
                events = [event for event in events if event.event_type == event_type]
            for event in events:
                self.append_event(event)
        if limit is None or limit >= len(events):
            return events
        return events[-limit:]

    def read_trace(self, trace_id: str, limit: int | None = None) -> dict[str, Any]:
        events = self.read_events(limit=limit, trace_id=trace_id)
        event_ids = [event.event_id for event in events]
        event_id_set = set(event_ids)
        raw_messages = [item for item in self.read_raw_messages() if item.get("trace_id") == trace_id]
        outbox = [item for item in self.read_outbox() if item.get("trace_id") == trace_id]
        memories = [
            record.to_dict()
            for record in self.read_memories()
            if record.source_event_id in event_id_set or record.evidence_event_id in event_id_set
        ]
        related_jobs = [job for job in self.read_jobs() if str(job.get("payload", {}).get("trace_id", "")) == trace_id]
        return {
            "trace_id": trace_id,
            "count": len(events),
            "event_ids": event_ids,
            "events": [event.to_dict() for event in events],
            "raw_messages": raw_messages,
            "memories": memories,
            "outbox": outbox,
            "jobs": related_jobs,
        }

    def read_memories(self, limit: int | None = None) -> list[MemoryRecord]:
        records = self._db_memories()
        if not records and self.memory_path.exists():
            records = [MemoryRecord.from_dict(row) for row in _read_jsonl(self.memory_path)]
            for record in records:
                self.write_memory(record)
        if limit is None or limit >= len(records):
            return records
        return records[-limit:]

    def read_outbox(self, limit: int | None = None, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM outbox"
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at ASC, message_id ASC"
        rows = self._fetch_all(sql, tuple(params))
        payloads = [_row_to_outbox(row) for row in rows]
        if limit is not None and limit < len(payloads):
            payloads = payloads[-limit:]
        return payloads

    def read_jobs(self, limit: int | None = None, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM jobs"
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at ASC, job_id ASC"
        rows = self._fetch_all(sql, tuple(params))
        jobs = [_row_to_job(row) for row in rows]
        if limit is not None and limit < len(jobs):
            jobs = jobs[-limit:]
        return jobs

    def query_memories(self, query: str | MemoryQuery, limit: int | None = None) -> list[MemoryHit]:
        if isinstance(query, MemoryQuery):
            memory_query = query
        else:
            memory_query = MemoryQuery(text=query, limit=limit or 5)
        records = [record for record in self.read_memories() if record.status == "active"]
        if not memory_query.text.strip():
            hits = [MemoryHit(record=record, score=record.importance, reason="recent") for record in records]
            hits.sort(key=lambda hit: (-hit.score, hit.record.created_at, hit.record.memory_id))
            return hits[: memory_query.limit]

        candidate_ids = self._fts_candidates(memory_query.text, memory_query.limit * 5)
        hits: list[MemoryHit] = []
        for record in records:
            if memory_query.kinds and record.kind not in memory_query.kinds:
                continue
            if candidate_ids and record.memory_id not in candidate_ids and score_memory(memory_query.text, record)[0] < 0.18:
                continue
            score, reason = score_memory(memory_query.text, record)
            if score <= 0:
                continue
            hits.append(MemoryHit(record=record, score=score, reason=reason))
        hits.sort(key=lambda hit: (-hit.score, hit.record.created_at, hit.record.memory_id))
        for hit in hits[: memory_query.limit]:
            self._bump_memory_access(hit.record.memory_id)
        return hits[: memory_query.limit]

    def consolidate_memories(self) -> dict[str, Any]:
        records = self.read_memories()
        active = [record for record in records if record.status == "active"]
        seen: dict[tuple[str, str], MemoryRecord] = {}
        merged = 0
        for record in active:
            key = (record.kind, _normalize(record.text))
            if key not in seen:
                seen[key] = record
                continue
            merged += 1
            self._mark_superseded(record.memory_id, seen[key].memory_id)

        active_l1 = [record for record in self.read_memories() if record.status == "active" and record.layer == "L1"]
        l2_records = self._build_l2_memories(active_l1)
        l3_records = self._build_l3_memories(active_l1)
        written_l2 = [self.write_memory(record, apply_guard=False) for record in l2_records]
        written_l3 = [self.write_memory(record, apply_guard=False) for record in l3_records]
        archive_result = self._archive_l1_memories(active_l1)
        self.reindex_memories()
        self.rebuild_memory_threads()
        return {
            "merged": merged,
            "active_count": len(active),
            "kept_count": len(seen),
            "l2_written": len(written_l2),
            "l3_written": len(written_l3),
            "l4_written": archive_result["l4_written"],
            "archived_l1": archive_result["archived_l1"],
            "layers": {
                "L1_active": len(active_l1),
                "L2_written_ids": [record.memory_id for record in written_l2],
                "L3_written_ids": [record.memory_id for record in written_l3],
                "L4_written_ids": archive_result["l4_memory_ids"],
            },
        }

    def _build_l2_memories(self, records: list[MemoryRecord]) -> list[MemoryRecord]:
        groups: dict[str, list[MemoryRecord]] = {}
        for record in records:
            group_kind = _l2_group_kind(record.kind)
            if not group_kind:
                continue
            groups.setdefault(group_kind, []).append(record)

        now_iso = utc_now_iso()
        output: list[MemoryRecord] = []
        for group_kind, items in sorted(groups.items()):
            items = _important_first(items)[:12]
            if not items:
                continue
            source_ids = [item.memory_id for item in items]
            text = _consolidated_memory_text(_l2_title(group_kind), items, max_items=8)
            output.append(
                MemoryRecord(
                    memory_id=f"mem_l2_{_stable_slug(group_kind)}",
                    kind=group_kind,
                    text=text,
                    source_event_id=_first_event_id(items),
                    layer="L2",
                    source_role="system",
                    source_excerpt=_join_source_excerpts(items),
                    evidence_quote=_join_evidence_quotes(items),
                    evidence_event_id=_first_event_id(items),
                    tags=_merged_tags(["profile", "consolidated", group_kind], items),
                    importance=max(0.66, min(0.95, _avg([item.importance for item in items]) + 0.08)),
                    confidence=max(0.62, min(0.92, _avg([item.confidence for item in items]) + 0.06)),
                    created_at=now_iso,
                    observed_at=now_iso,
                    last_accessed_at=now_iso,
                    metadata={
                        "consolidation": "L2_profile",
                        "source_memory_ids": source_ids,
                        "source_event_ids": _source_event_ids(items),
                        "source_count": len(items),
                        "updated_at": now_iso,
                    },
                )
            )
        return output

    def _build_l3_memories(self, records: list[MemoryRecord]) -> list[MemoryRecord]:
        groups: dict[str, list[MemoryRecord]] = {}
        for record in records:
            if record.kind in {"identity", "boundary", "risk"}:
                continue
            topic = _memory_topic(record)
            if not topic:
                continue
            groups.setdefault(topic, []).append(record)

        now_iso = utc_now_iso()
        output: list[MemoryRecord] = []
        for topic, items in sorted(groups.items()):
            items = _important_first(items)[:14]
            if len(items) < 2 and not any(item.kind == "event" and item.importance >= 0.62 for item in items):
                continue
            source_ids = [item.memory_id for item in items]
            label = _topic_label(topic)
            output.append(
                MemoryRecord(
                    memory_id=f"mem_l3_{_stable_slug(topic)}",
                    kind="topic_thread",
                    text=_consolidated_memory_text(f"主题线程·{label}", items, max_items=9),
                    source_event_id=_first_event_id(items),
                    layer="L3",
                    source_role="system",
                    source_excerpt=_join_source_excerpts(items),
                    evidence_quote=_join_evidence_quotes(items),
                    evidence_event_id=_first_event_id(items),
                    tags=_merged_tags(["topic", "thread", topic], items),
                    importance=max(0.58, min(0.9, _avg([item.importance for item in items]) + 0.05)),
                    confidence=max(0.58, min(0.88, _avg([item.confidence for item in items]) + 0.04)),
                    created_at=now_iso,
                    observed_at=now_iso,
                    last_accessed_at=now_iso,
                    metadata={
                        "consolidation": "L3_topic_thread",
                        "topic": topic,
                        "source_memory_ids": source_ids,
                        "source_event_ids": _source_event_ids(items),
                        "source_count": len(items),
                        "updated_at": now_iso,
                    },
                )
            )
        return output

    def _archive_l1_memories(self, records: list[MemoryRecord]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        buckets: dict[str, list[MemoryRecord]] = {}
        for record in records:
            if not _should_archive_l1(record, now):
                continue
            bucket = _archive_bucket(record)
            buckets.setdefault(bucket, []).append(record)

        archive_ids: list[str] = []
        archived = 0
        now_iso = utc_now_iso(now)
        for bucket, items in sorted(buckets.items()):
            items = _important_first(items)[:20]
            if not items:
                continue
            archive_id = f"mem_l4_archive_{_stable_slug(bucket)}"
            archive_record = MemoryRecord(
                memory_id=archive_id,
                kind="archive_summary",
                text=_consolidated_memory_text(f"长期归档·{bucket}", items, max_items=12),
                source_event_id=_first_event_id(items),
                layer="L4",
                source_role="system",
                source_excerpt=_join_source_excerpts(items),
                evidence_quote=_join_evidence_quotes(items),
                evidence_event_id=_first_event_id(items),
                tags=_merged_tags(["archive", "long_term", bucket], items),
                importance=max(0.5, min(0.82, _avg([item.importance for item in items]) + 0.02)),
                confidence=max(0.55, min(0.86, _avg([item.confidence for item in items]))),
                created_at=now_iso,
                observed_at=now_iso,
                last_accessed_at=now_iso,
                metadata={
                    "consolidation": "L4_archive",
                    "archive_bucket": bucket,
                    "source_memory_ids": [item.memory_id for item in items],
                    "source_event_ids": _source_event_ids(items),
                    "source_count": len(items),
                    "updated_at": now_iso,
                },
            )
            self.write_memory(archive_record, apply_guard=False)
            archive_ids.append(archive_id)
            for item in items:
                self._mark_archived(item.memory_id, archive_id)
                self._record_memory_link(item.memory_id, archive_id, "archived_into", 1.0)
                archived += 1
        return {"l4_written": len(archive_ids), "archived_l1": archived, "l4_memory_ids": archive_ids}

    def reindex_memories(self) -> dict[str, Any]:
        if not self._fts_enabled:
            return {"indexed": len(self.read_memories()), "fts": False}
        with self._connect() as conn:
            conn.execute("DELETE FROM memory_fts")
            rows = conn.execute("SELECT memory_id, text, source_excerpt, tags_json FROM memory_items").fetchall()
            for row in rows:
                conn.execute(
                    "INSERT INTO memory_fts (memory_id, text, source_excerpt, tags) VALUES (?, ?, ?, ?)",
                    (
                        row["memory_id"],
                        row["text"],
                        row["source_excerpt"],
                        row["tags_json"],
                    ),
                )
            conn.commit()
        return {"indexed": len(rows), "fts": True}

    def rebuild_memory_threads(self) -> dict[str, Any]:
        records = self._db_memories()
        self._execute("DELETE FROM memory_thread_members", ())
        self._execute("DELETE FROM memory_links", ())
        self._execute("DELETE FROM memory_threads", ())

        thread_by_memory: dict[str, str] = {}
        created_threads = 0
        linked = 0
        for record in records:
            parent = self._find_related_parent(record, records, thread_by_memory)
            if parent and parent.memory_id in thread_by_memory:
                thread_id = thread_by_memory[parent.memory_id]
            else:
                root_id = parent.memory_id if parent else record.memory_id
                thread_id = _thread_id(root_id)
                created_threads += 1
                self._execute(
                    """
                    INSERT OR REPLACE INTO memory_threads (
                        thread_id, title, root_memory_id, latest_memory_id, thread_kind,
                        status, created_at, updated_at, memory_count, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        thread_id,
                        _thread_title(parent or record),
                        root_id,
                        record.memory_id,
                        (parent or record).kind,
                        "active",
                        (parent or record).created_at or utc_now_iso(),
                        record.created_at or utc_now_iso(),
                        0,
                        json.dumps({"source": "rebuild"}, ensure_ascii=False),
                    ),
                )
            thread_by_memory[record.memory_id] = thread_id
            self._execute(
                """
                INSERT OR REPLACE INTO memory_thread_members (
                    thread_id, memory_id, position, relation, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    record.memory_id,
                    self._thread_member_position(thread_id),
                    "root" if parent is None else _memory_relation(parent, record),
                    record.created_at or utc_now_iso(),
                ),
            )
            if parent is not None:
                self._record_memory_link(parent.memory_id, record.memory_id, _memory_relation(parent, record), 1.0)
                linked += 1
            archive_id = str(record.metadata.get("archive_id", "")) if isinstance(record.metadata, dict) else ""
            if record.status == "archived" and archive_id:
                self._record_memory_link(record.memory_id, archive_id, "archived_into", 1.0)
                linked += 1
            self._execute(
                """
                UPDATE memory_threads
                SET latest_memory_id = ?, updated_at = ?, memory_count = (
                    SELECT COUNT(*) FROM memory_thread_members WHERE thread_id = ?
                ), title = COALESCE(NULLIF(title, ''), ?)
                WHERE thread_id = ?
                """,
                (
                    record.memory_id,
                    record.created_at or utc_now_iso(),
                    thread_id,
                    _thread_title(parent or record),
                    thread_id,
                ),
            )
        return {"threads": len({value for value in thread_by_memory.values()}), "members": len(records), "linked": linked}

    def _find_related_parent(
        self,
        record: MemoryRecord,
        records: list[MemoryRecord],
        thread_by_memory: dict[str, str],
    ) -> MemoryRecord | None:
        candidates = [item for item in records if item.memory_id != record.memory_id and item.status != "deleted"]
        candidates.sort(key=lambda item: (item.created_at, item.memory_id), reverse=True)
        for candidate in candidates:
            if not _memory_related(candidate, record):
                continue
            return candidate
        for candidate in candidates:
            if candidate.kind == record.kind and _normalize(candidate.text) == _normalize(record.text):
                return candidate
        return None

    def _thread_member_position(self, thread_id: str) -> int:
        row = self._fetch_one(
            "SELECT MAX(position) AS position, COUNT(*) AS count FROM memory_thread_members WHERE thread_id = ?",
            (thread_id,),
        )
        if row is None or int(row["count"] or 0) == 0:
            return 0
        value = row["position"]
        if value in (None, ""):
            return 0
        return int(value) + 1

    def _attach_memory_to_thread(self, record: MemoryRecord) -> None:
        records = self._db_memories()
        parent = self._find_related_parent(record, records, {})
        if parent is None:
            thread_id = _thread_id(record.memory_id)
            relation = "root"
            root = record
        else:
            parent_thread = self._fetch_one("SELECT thread_id FROM memory_thread_members WHERE memory_id = ?", (parent.memory_id,))
            if parent_thread is None:
                parent_thread_id = _thread_id(parent.memory_id)
                self._execute(
                    """
                    INSERT OR IGNORE INTO memory_threads (
                        thread_id, title, root_memory_id, latest_memory_id, thread_kind,
                        status, created_at, updated_at, memory_count, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        parent_thread_id,
                        _thread_title(parent),
                        parent.memory_id,
                        parent.memory_id,
                        parent.kind,
                        "active",
                        parent.created_at or utc_now_iso(),
                        parent.created_at or utc_now_iso(),
                        0,
                        json.dumps({"source": "attach_parent"}, ensure_ascii=False),
                    ),
                )
                self._execute(
                    """
                    INSERT OR IGNORE INTO memory_thread_members (
                        thread_id, memory_id, position, relation, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        parent_thread_id,
                        parent.memory_id,
                        0,
                        "root",
                        parent.created_at or utc_now_iso(),
                    ),
                )
                thread_id = parent_thread_id
            else:
                thread_id = str(parent_thread["thread_id"])
            relation = _memory_relation(parent, record)
            root = parent
        self._execute(
            """
            INSERT OR IGNORE INTO memory_threads (
                thread_id, title, root_memory_id, latest_memory_id, thread_kind,
                status, created_at, updated_at, memory_count, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                _thread_title(root),
                root.memory_id,
                record.memory_id,
                root.kind,
                "active",
                root.created_at or utc_now_iso(),
                record.created_at or utc_now_iso(),
                0,
                json.dumps({"source": "write_memory"}, ensure_ascii=False),
            ),
        )
        self._execute(
            """
            INSERT OR REPLACE INTO memory_thread_members (
                thread_id, memory_id, position, relation, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                record.memory_id,
                self._thread_member_position(thread_id),
                relation,
                record.created_at or utc_now_iso(),
            ),
        )
        if parent is not None:
            self._record_memory_link(parent.memory_id, record.memory_id, relation, 1.0)
        self._execute(
            """
            UPDATE memory_threads
            SET latest_memory_id = ?, updated_at = ?, memory_count = (
                SELECT COUNT(*) FROM memory_thread_members WHERE thread_id = ?
            ), title = ?
            WHERE thread_id = ?
            """,
            (
                record.memory_id,
                record.created_at or utc_now_iso(),
                thread_id,
                _thread_title(root),
                thread_id,
            ),
        )

    def _record_memory_link(self, source_memory_id: str, target_memory_id: str, relation: str, score: float) -> None:
        link_id = _link_id(source_memory_id, target_memory_id, relation)
        self._execute(
            """
            INSERT OR REPLACE INTO memory_links (
                link_id, source_memory_id, target_memory_id, relation, score, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link_id,
                source_memory_id,
                target_memory_id,
                relation,
                score,
                utc_now_iso(),
                json.dumps({"source": "memory_runtime"}, ensure_ascii=False),
            ),
        )

    def snapshot(self) -> dict[str, Any]:
        state = self.load_state().to_dict()
        memories = self.read_memories()
        events = self.read_events(limit=20)
        outbox = self.read_outbox(limit=20)
        jobs = self.read_jobs(limit=20)
        threads = self.read_memory_threads(limit=10)
        links = self.read_memory_links(limit=10)
        return {
            "state": state,
            "memory_count": len(memories),
            "event_count": len(self.read_events()),
            "outbox_count": len(outbox),
            "job_count": len(jobs),
            "thread_count": len(self.read_memory_threads()),
            "link_count": len(self.read_memory_links()),
            "recent_events": [event.to_dict() for event in events],
            "recent_memories": [memory.to_dict() for memory in memories[-5:]],
            "recent_outbox": outbox[-5:],
            "recent_jobs": jobs[-5:],
            "recent_threads": threads,
            "recent_links": links,
        }

    def _apply_memory_guard(self, record: MemoryRecord) -> tuple[MemoryRecord, bool, list[dict[str, Any]]]:
        active = [item for item in self._db_memories() if item.status == "active"]
        normalized_text = _normalize(record.text)
        correction_like = any(word in f"{record.text} {record.source_excerpt}" for word in ("不喜欢", "不是", "改成", "其实", "别", "不要", "修正"))
        audit_entries: list[dict[str, Any]] = []
        for existing in active:
            if existing.kind != record.kind and not _same_memory_family(existing.kind, record.kind):
                continue
            if _normalize(existing.text) == normalized_text:
                self._bump_memory_access(existing.memory_id)
                existing.last_accessed_at = record.created_at
                existing.access_count += 1
                audit_entries.append(
                    _memory_guard_audit(
                        action="duplicate",
                        reason="duplicate_same_text",
                        existing=existing,
                        new_record=record,
                        summary=f"记忆去重：{existing.memory_id} ↔ {record.memory_id}",
                    )
                )
                return existing, False, audit_entries
            conflict_reason = _memory_conflict_reason(existing, record, correction_like)
            if conflict_reason:
                existing.status = "superseded"
                existing.superseded_by = record.memory_id
                existing.metadata = _merge_memory_guard_metadata(
                    existing.metadata,
                    {
                        "status": "superseded",
                        "superseded_by": record.memory_id,
                        "superseded_reason": conflict_reason,
                        "superseded_at": record.created_at or utc_now_iso(),
                    },
                )
                record.supersedes.append(existing.memory_id)
                record.metadata = _merge_memory_guard_metadata(
                    record.metadata,
                    {
                        "memory_guard": {
                            "action": "supersede",
                            "reason": conflict_reason,
                            "matched_memory_ids": [existing.memory_id],
                            "matched_kind": existing.kind,
                        }
                    },
                )
                self._persist_memory_status(existing, metadata_patch=existing.metadata)
                audit_entries.append(
                    _memory_guard_audit(
                        action="supersede",
                        reason=conflict_reason,
                        existing=existing,
                        new_record=record,
                        summary=f"记忆替换：{existing.memory_id} -> {record.memory_id}",
                    )
                )
        return record, True, audit_entries

    def _persist_memory_status(self, record: MemoryRecord, metadata_patch: dict[str, Any] | None = None) -> None:
        metadata = dict(record.metadata or {})
        if metadata_patch:
            metadata = _merge_memory_guard_metadata(metadata, metadata_patch)
        self._execute(
            """
            UPDATE memory_items
            SET status = ?, superseded_by = ?, access_count = ?, last_accessed_at = ?, metadata_json = ?, updated_at = ?
            WHERE memory_id = ?
            """,
            (
                record.status,
                record.superseded_by,
                record.access_count,
                record.last_accessed_at,
                json.dumps(metadata, ensure_ascii=False),
                utc_now_iso(),
                record.memory_id,
            ),
        )
        self._sync_memory_evidence(record.memory_id)

    def _mark_superseded(self, memory_id: str, superseded_by: str) -> None:
        self._execute(
            """
            UPDATE memory_items
            SET status = 'superseded', superseded_by = ?, updated_at = ?
            WHERE memory_id = ?
            """,
            (superseded_by, utc_now_iso(), memory_id),
        )
        self._sync_memory_evidence(memory_id)

    def _append_memory_guard_events(
        self,
        entries: list[dict[str, Any]],
        *,
        trace_id: str,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(timezone.utc)
        for entry in entries:
            event = make_event(
                "memory_guard_decision",
                str(entry.get("summary", entry.get("reason", "memory guard"))),
                entry,
                trace_id=trace_id,
                now=now,
                source_ids=list(entry.get("source_ids", []) or []),
            )
            self.append_event(event)

    def _mark_archived(self, memory_id: str, archive_id: str) -> None:
        row = self._fetch_one("SELECT * FROM memory_items WHERE memory_id = ?", (memory_id,))
        if row is None:
            return
        metadata = json.loads(row["metadata_json"] or "{}")
        metadata["archive_id"] = archive_id
        metadata["archived_at"] = utc_now_iso()
        self._execute(
            """
            UPDATE memory_items
            SET status = 'archived', metadata_json = ?, updated_at = ?
            WHERE memory_id = ? AND status = 'active'
            """,
            (json.dumps(metadata, ensure_ascii=False), utc_now_iso(), memory_id),
        )
        self._sync_memory_evidence(memory_id)

    def _bump_memory_access(self, memory_id: str) -> None:
        self._execute(
            """
            UPDATE memory_items
            SET access_count = access_count + 1, last_accessed_at = ?
            WHERE memory_id = ?
            """,
            (utc_now_iso(), memory_id),
        )

    def _fts_candidates(self, query: str, limit: int) -> set[str]:
        query = query.strip()
        if not query:
            return set()
        if not self._fts_enabled:
            return set()
        tokens = [token for token in query.replace("，", " ").replace("。", " ").split() if token]
        match_expr = " OR ".join(_escape_fts_token(token) for token in tokens[:6])
        if not match_expr:
            match_expr = _escape_fts_token(query[:24])
        try:
            rows = self._fetch_all(
                "SELECT memory_id FROM memory_fts WHERE memory_fts MATCH ? LIMIT ?",
                (match_expr, limit),
            )
            return {str(row["memory_id"]) for row in rows}
        except sqlite3.OperationalError:
            return set()

    def _upsert_memory_fts(self, record: MemoryRecord) -> None:
        if not self._fts_enabled:
            return
        self._execute("DELETE FROM memory_fts WHERE memory_id = ?", (record.memory_id,))
        self._execute(
            "INSERT INTO memory_fts (memory_id, text, source_excerpt, tags) VALUES (?, ?, ?, ?)",
            (
                record.memory_id,
                record.text,
                record.source_excerpt,
                json.dumps(record.tags, ensure_ascii=False),
            ),
        )

    def _upsert_memory_evidence(self, record: MemoryRecord, trace_id: str = "") -> None:
        evidence = self._memory_evidence_payload(record, trace_id=trace_id)
        self._execute(
            """
            INSERT INTO memory_evidence (
                evidence_id, memory_id, trace_id, source_event_id, source_role, kind, layer, status,
                source_excerpt, evidence_quote, quote_start, quote_end, importance, confidence,
                created_at, updated_at, metadata_json, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(memory_id) DO UPDATE SET
                trace_id = excluded.trace_id,
                source_event_id = excluded.source_event_id,
                source_role = excluded.source_role,
                kind = excluded.kind,
                layer = excluded.layer,
                status = excluded.status,
                source_excerpt = excluded.source_excerpt,
                evidence_quote = excluded.evidence_quote,
                quote_start = excluded.quote_start,
                quote_end = excluded.quote_end,
                importance = excluded.importance,
                confidence = excluded.confidence,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                metadata_json = excluded.metadata_json,
                schema_version = excluded.schema_version
            """,
            (
                evidence["evidence_id"],
                evidence["memory_id"],
                evidence["trace_id"],
                evidence["source_event_id"],
                evidence["source_role"],
                evidence["kind"],
                evidence["layer"],
                evidence["status"],
                evidence["source_excerpt"],
                evidence["evidence_quote"],
                evidence["quote_start"],
                evidence["quote_end"],
                evidence["importance"],
                evidence["confidence"],
                evidence["created_at"],
                evidence["updated_at"],
                json.dumps(evidence["metadata"], ensure_ascii=False),
                evidence["schema_version"],
            ),
        )

    def _memory_evidence_payload(self, record: MemoryRecord, trace_id: str = "") -> dict[str, Any]:
        existing = self._fetch_one("SELECT * FROM memory_evidence WHERE memory_id = ?", (record.memory_id,))
        existing_metadata = json.loads(existing["metadata_json"] or "{}") if existing else {}
        metadata = dict(existing_metadata)
        metadata.update(record.metadata or {})
        metadata.setdefault("memory_id", record.memory_id)
        metadata.setdefault("source_event_id", record.evidence_event_id or record.source_event_id)
        metadata.setdefault("source_role", record.source_role)
        metadata.setdefault("kind", record.kind)
        metadata.setdefault("layer", record.layer)
        metadata.setdefault("status", record.status)
        metadata.setdefault("quote_strategy", "substring" if record.evidence_quote else "empty")
        resolved_trace_id = trace_id or (str(existing["trace_id"]) if existing else "") or str(metadata.get("trace_id", ""))
        if not resolved_trace_id:
            resolved_trace_id = record.evidence_event_id or record.source_event_id
        source_excerpt = record.source_excerpt or (str(existing["source_excerpt"]) if existing else "")
        evidence_quote = record.evidence_quote or (str(existing["evidence_quote"]) if existing else "")
        quote_start, quote_end = _quote_span(source_excerpt, evidence_quote)
        created_at = str(existing["created_at"]) if existing else (record.created_at or utc_now_iso())
        schema_version = int(existing["schema_version"]) if existing else int(record.schema_version or 1)
        return {
            "evidence_id": str(existing["evidence_id"]) if existing else f"evidence_{record.memory_id}",
            "memory_id": record.memory_id,
            "trace_id": resolved_trace_id,
            "source_event_id": record.evidence_event_id or record.source_event_id,
            "source_role": record.source_role or "user",
            "kind": record.kind,
            "layer": record.layer,
            "status": record.status,
            "source_excerpt": source_excerpt,
            "evidence_quote": evidence_quote,
            "quote_start": quote_start,
            "quote_end": quote_end,
            "importance": float(record.importance),
            "confidence": float(record.confidence),
            "created_at": created_at,
            "updated_at": utc_now_iso(),
            "metadata": metadata,
            "schema_version": schema_version,
        }

    def _sync_memory_evidence(self, memory_id: str) -> None:
        row = self._fetch_one("SELECT * FROM memory_items WHERE memory_id = ?", (memory_id,))
        if row is None:
            return
        self._upsert_memory_evidence(MemoryRecord.from_dict(_row_to_memory(row)))

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS companion_state (
                    state_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    actor TEXT NOT NULL DEFAULT 'runtime',
                    privacy_level TEXT NOT NULL DEFAULT 'internal',
                    source_ids TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS raw_messages (
                    message_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    source_event_id TEXT NOT NULL DEFAULT '',
                    privacy_level TEXT NOT NULL DEFAULT 'internal'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_items (
                    memory_id TEXT PRIMARY KEY,
                    layer TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    text TEXT NOT NULL,
                    source_event_id TEXT NOT NULL,
                    source_role TEXT NOT NULL DEFAULT 'user',
                    source_excerpt TEXT NOT NULL DEFAULT '',
                    evidence_quote TEXT NOT NULL DEFAULT '',
                    evidence_event_id TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    importance REAL NOT NULL DEFAULT 0.5,
                    confidence REAL NOT NULL DEFAULT 0.6,
                    created_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL DEFAULT '',
                    last_accessed_at TEXT NOT NULL DEFAULT '',
                    access_count INTEGER NOT NULL DEFAULT 0,
                    superseded_by TEXT NOT NULL DEFAULT '',
                    supersedes_json TEXT NOT NULL DEFAULT '[]',
                    expires_at TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    schema_version INTEGER NOT NULL DEFAULT 2,
                    updated_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL UNIQUE,
                    trace_id TEXT NOT NULL DEFAULT '',
                    source_event_id TEXT NOT NULL DEFAULT '',
                    source_role TEXT NOT NULL DEFAULT 'user',
                    kind TEXT NOT NULL DEFAULT 'fact',
                    layer TEXT NOT NULL DEFAULT 'L1',
                    status TEXT NOT NULL DEFAULT 'active',
                    source_excerpt TEXT NOT NULL DEFAULT '',
                    evidence_quote TEXT NOT NULL DEFAULT '',
                    quote_start INTEGER NOT NULL DEFAULT -1,
                    quote_end INTEGER NOT NULL DEFAULT -1,
                    importance REAL NOT NULL DEFAULT 0.5,
                    confidence REAL NOT NULL DEFAULT 0.6,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    schema_version INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    message_id TEXT PRIMARY KEY,
                    signal_id TEXT NOT NULL DEFAULT '',
                    trace_id TEXT NOT NULL DEFAULT '',
                    channel TEXT NOT NULL DEFAULT 'internal',
                    draft_text TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'drafted',
                    score REAL NOT NULL DEFAULT 0.0,
                    reason TEXT NOT NULL DEFAULT '',
                    signal_type TEXT NOT NULL DEFAULT '',
                    anchor_memory_ids_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    sent_at TEXT NOT NULL DEFAULT '',
                    replied_at TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    idempotency_key TEXT NOT NULL UNIQUE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_threads (
                    thread_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    root_memory_id TEXT NOT NULL,
                    latest_memory_id TEXT NOT NULL,
                    thread_kind TEXT NOT NULL DEFAULT 'fact',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    memory_count INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_thread_members (
                    thread_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0,
                    relation TEXT NOT NULL DEFAULT 'root',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (thread_id, memory_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_links (
                    link_id TEXT PRIMARY KEY,
                    source_memory_id TEXT NOT NULL,
                    target_memory_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    score REAL NOT NULL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'queued',
                    run_after TEXT NOT NULL DEFAULT '',
                    locked_until TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    reminder_id TEXT PRIMARY KEY,
                    user_scope TEXT NOT NULL DEFAULT 'default',
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL DEFAULT 'reminder',
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    due_at TEXT NOT NULL,
                    timezone_name TEXT NOT NULL DEFAULT 'UTC',
                    source TEXT NOT NULL DEFAULT 'user',
                    source_ref TEXT NOT NULL DEFAULT '',
                    recurrence TEXT NOT NULL DEFAULT '',
                    delivery_count INTEGER NOT NULL DEFAULT 0,
                    last_delivered_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS reminders_due_idx ON reminders(status, due_at)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS calendar_events (
                    event_id TEXT PRIMARY KEY,
                    user_scope TEXT NOT NULL DEFAULT 'default',
                    title TEXT NOT NULL,
                    starts_at TEXT NOT NULL,
                    ends_at TEXT NOT NULL DEFAULT '',
                    all_day INTEGER NOT NULL DEFAULT 0,
                    timezone_name TEXT NOT NULL DEFAULT 'UTC',
                    reminder_ids_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_preferences (
                    user_scope TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._fts_enabled = self._ensure_fts(conn)
            conn.commit()

    def _ensure_fts(self, conn: sqlite3.Connection) -> bool:
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
                USING fts5(memory_id UNINDEXED, text, source_excerpt, tags)
                """
            )
            return True
        except sqlite3.OperationalError:
            return False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        with self._connect() as conn:
            conn.execute(sql, params)
            conn.commit()

    def _fetch_one(self, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
            return row

    def _fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return list(rows)

    def _db_memories(self) -> list[MemoryRecord]:
        rows = self._fetch_all("SELECT * FROM memory_items ORDER BY created_at ASC, memory_id ASC")
        return [MemoryRecord.from_dict(_row_to_memory(row)) for row in rows]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            handle.seek(0, 2)
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "trace_id": row["trace_id"],
        "event_type": row["event_type"],
        "created_at": row["created_at"],
        "summary": row["summary"],
        "payload": json.loads(row["payload_json"] or "{}"),
        "schema_version": row["schema_version"],
        "actor": row["actor"],
        "privacy_level": row["privacy_level"],
        "source_ids": json.loads(row["source_ids"] or "[]"),
    }


def _row_to_memory(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "memory_id": row["memory_id"],
        "layer": row["layer"],
        "kind": row["kind"],
        "status": row["status"],
        "text": row["text"],
        "source_event_id": row["source_event_id"],
        "source_role": row["source_role"],
        "source_excerpt": row["source_excerpt"],
        "evidence_quote": row["evidence_quote"],
        "evidence_event_id": row["evidence_event_id"],
        "tags": json.loads(row["tags_json"] or "[]"),
        "importance": row["importance"],
        "confidence": row["confidence"],
        "created_at": row["created_at"],
        "observed_at": row["observed_at"],
        "last_accessed_at": row["last_accessed_at"],
        "access_count": row["access_count"],
        "superseded_by": row["superseded_by"],
        "supersedes": json.loads(row["supersedes_json"] or "[]"),
        "expires_at": row["expires_at"],
        "metadata": json.loads(row["metadata_json"] or "{}"),
        "schema_version": row["schema_version"],
    }


def _row_to_memory_evidence(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "evidence_id": row["evidence_id"],
        "memory_id": row["memory_id"],
        "trace_id": row["trace_id"],
        "source_event_id": row["source_event_id"],
        "source_role": row["source_role"],
        "kind": row["kind"],
        "layer": row["layer"],
        "status": row["status"],
        "source_excerpt": row["source_excerpt"],
        "evidence_quote": row["evidence_quote"],
        "quote_start": row["quote_start"],
        "quote_end": row["quote_end"],
        "importance": row["importance"],
        "confidence": row["confidence"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "metadata": json.loads(row["metadata_json"] or "{}"),
        "schema_version": row["schema_version"],
    }


def _row_to_outbox(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "message_id": row["message_id"],
        "signal_id": row["signal_id"],
        "trace_id": row["trace_id"],
        "channel": row["channel"],
        "draft_text": row["draft_text"],
        "status": row["status"],
        "score": row["score"],
        "reason": row["reason"],
        "signal_type": row["signal_type"],
        "anchor_memory_ids": json.loads(row["anchor_memory_ids_json"] or "[]"),
        "created_at": row["created_at"],
        "sent_at": row["sent_at"],
        "replied_at": row["replied_at"],
        "payload": json.loads(row["payload_json"] or "{}"),
        "idempotency_key": row["idempotency_key"],
    }


def _row_to_reminder(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "reminder_id": row["reminder_id"], "user_scope": row["user_scope"], "title": row["title"],
        "description": row["description"], "kind": row["kind"], "status": row["status"],
        "due_at": row["due_at"], "timezone_name": row["timezone_name"], "source": row["source"],
        "source_ref": row["source_ref"], "recurrence": row["recurrence"],
        "delivery_count": row["delivery_count"], "last_delivered_at": row["last_delivered_at"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "metadata": json.loads(row["metadata_json"] or "{}"),
    }


def _row_to_calendar_event(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "event_id": row["event_id"], "user_scope": row["user_scope"], "title": row["title"],
        "starts_at": row["starts_at"], "ends_at": row["ends_at"], "all_day": bool(row["all_day"]),
        "timezone_name": row["timezone_name"], "reminder_ids": json.loads(row["reminder_ids_json"] or "[]"),
        "status": row["status"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        "metadata": json.loads(row["metadata_json"] or "{}"),
    }


def _row_to_job(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "job_id": row["job_id"],
        "job_type": row["job_type"],
        "payload": json.loads(row["payload_json"] or "{}"),
        "status": row["status"],
        "run_after": row["run_after"],
        "locked_until": row["locked_until"],
        "attempts": row["attempts"],
        "max_attempts": row["max_attempts"],
        "idempotency_key": row["idempotency_key"],
        "last_error": row["last_error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_raw_message(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "message_id": row["message_id"],
        "trace_id": row["trace_id"],
        "turn_id": row["turn_id"],
        "role": row["role"],
        "content": row["content"],
        "created_at": row["created_at"],
        "source_event_id": row["source_event_id"],
        "privacy_level": row["privacy_level"],
    }


def _row_to_memory_thread(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "thread_id": row["thread_id"],
        "title": row["title"],
        "root_memory_id": row["root_memory_id"],
        "latest_memory_id": row["latest_memory_id"],
        "thread_kind": row["thread_kind"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "memory_count": row["memory_count"],
        "metadata": json.loads(row["metadata_json"] or "{}"),
    }


def _row_to_thread_member(row: sqlite3.Row) -> dict[str, Any]:
    payload = {
        "thread_id": row["thread_id"],
        "memory_id": row["memory_id"],
        "position": row["position"],
        "relation": row["relation"],
        "created_at": row["created_at"],
    }
    if row["kind"] is not None:
        payload["memory"] = _row_to_memory(row)
    else:
        payload["memory"] = None
    return payload


def _row_to_memory_link(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "link_id": row["link_id"],
        "source_memory_id": row["source_memory_id"],
        "target_memory_id": row["target_memory_id"],
        "relation": row["relation"],
        "score": row["score"],
        "created_at": row["created_at"],
        "metadata": json.loads(row["metadata_json"] or "{}"),
    }


def _quote_span(source_excerpt: str, evidence_quote: str) -> tuple[int, int]:
    source = " ".join(source_excerpt.split())
    quote = " ".join(evidence_quote.split())
    if not source or not quote:
        return -1, -1
    start = source.find(quote)
    if start >= 0:
        return start, start + len(quote)
    for size in range(len(quote), 1, -1):
        candidate = quote[:size]
        start = source.find(candidate)
        if start >= 0:
            return start, start + size
    return -1, -1


def _normalize(text: str) -> str:
    return "".join(ch.lower() for ch in text if not ch.isspace())


def _same_memory_family(left: str, right: str) -> bool:
    preference_family = {"preference", "wish"}
    if left in preference_family and right in preference_family:
        return True
    return left == right or {left, right} <= {"fact", "event"}


def _memory_related(left: MemoryRecord, right: MemoryRecord) -> bool:
    if left.kind == right.kind:
        return True
    left_tags = set(left.tags)
    right_tags = set(right.tags)
    if left_tags & right_tags:
        return True
    left_tokens = set(_tokenize(left.text))
    right_tokens = set(_tokenize(right.text))
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
    return overlap >= 0.35


def _memory_conflict_reason(existing: MemoryRecord, new_record: MemoryRecord, correction_like: bool) -> str:
    if _normalize(existing.text) == _normalize(new_record.text):
        return "duplicate_same_text"
    if correction_like and _memory_related(existing, new_record):
        return "correction_supersedes_existing"
    if _memory_contradicts(existing, new_record):
        return "contradictory_update"
    if _memory_related(existing, new_record):
        return "related_update"
    return ""


def _memory_contradicts(left: MemoryRecord, right: MemoryRecord) -> bool:
    if not _memory_related(left, right):
        return False
    left_positive = _contains_any(left.text, ("喜欢", "希望", "想要", "需要", "愿意", "总是", "经常", "通常"))
    right_positive = _contains_any(right.text, ("喜欢", "希望", "想要", "需要", "愿意", "总是", "经常", "通常"))
    left_negative = _contains_any(left.text, ("不喜欢", "不要", "不想", "不需要", "讨厌", "别", "没", "不是", "不希望"))
    right_negative = _contains_any(right.text, ("不喜欢", "不要", "不想", "不需要", "讨厌", "别", "没", "不是", "不希望"))
    if (left_positive and right_negative) or (left_negative and right_positive):
        return True
    if left.kind in {"preference", "wish", "boundary", "relationship"} and right.kind == left.kind:
        if any(token in _normalize(left.text) for token in ("喜欢", "希望", "想要")) and any(
            token in _normalize(right.text) for token in ("不喜欢", "不要", "不想", "不需要", "讨厌")
        ):
            return True
    return False


def _memory_guard_audit(
    *,
    action: str,
    reason: str,
    existing: MemoryRecord,
    new_record: MemoryRecord,
    summary: str,
) -> dict[str, Any]:
    return {
        "action": action,
        "reason": reason,
        "summary": summary,
        "existing_memory_id": existing.memory_id,
        "existing_kind": existing.kind,
        "existing_status": existing.status,
        "existing_text": existing.text,
        "new_memory_id": new_record.memory_id,
        "new_kind": new_record.kind,
        "new_text": new_record.text,
        "same_family": _same_memory_family(existing.kind, new_record.kind),
        "source_ids": [item for item in [existing.source_event_id, new_record.source_event_id] if item],
        "metadata": {
            "existing_tags": existing.tags,
            "new_tags": new_record.tags,
        },
    }


def _merge_memory_guard_metadata(base: dict[str, Any] | None, patch: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(base or {})
    if not patch:
        return base
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            nested = dict(base.get(key, {}))
            nested.update(value)
            base[key] = nested
        else:
            base[key] = value
    return base


def _tokenize(text: str) -> list[str]:
    compact = _normalize(text)
    if len(compact) <= 2:
        return [compact] if compact else []
    return [compact[i : i + 2] for i in range(len(compact) - 1)]


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _escape_fts_token(token: str) -> str:
    token = token.strip()
    if not token:
        return ""
    return token.replace('"', '""')


def _seconds_delta(seconds: int) -> timedelta:
    return timedelta(seconds=seconds)


def _stable_slug(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    safe = "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")
    safe = safe[:28].strip("_") or "memory"
    return f"{safe}_{digest}"


def _avg(values: Iterable[float]) -> float:
    items = [float(value) for value in values]
    if not items:
        return 0.0
    return sum(items) / len(items)


def _important_first(items: list[MemoryRecord]) -> list[MemoryRecord]:
    return sorted(
        items,
        key=lambda item: (-item.importance, -item.confidence, item.created_at, item.memory_id),
    )


def _l2_group_kind(kind: str) -> str:
    mapping = {
        "identity": "user_profile",
        "preference": "user_preference_profile",
        "wish": "user_preference_profile",
        "boundary": "user_boundary_profile",
        "relationship": "relationship_profile",
        "recurring_topic": "recurring_pattern_profile",
    }
    return mapping.get(kind, "")


def _l2_title(kind: str) -> str:
    return {
        "user_profile": "用户画像",
        "user_preference_profile": "用户偏好画像",
        "user_boundary_profile": "用户边界画像",
        "relationship_profile": "关系画像",
        "recurring_pattern_profile": "反复出现的主题",
    }.get(kind, kind)


def _memory_topic(record: MemoryRecord) -> str:
    priority = (
        "work",
        "study",
        "project",
        "life",
        "emotion",
        "support",
        "timeline",
        "event",
        "relationship",
        "preference",
        "conversation",
        "state",
        "recurring_topic",
    )
    tags = [tag for tag in record.tags if tag]
    for tag in priority:
        if tag in tags:
            return tag
    if tags:
        return tags[0]
    return record.kind


def _topic_label(topic: str) -> str:
    return {
        "work": "工作",
        "study": "学习",
        "project": "项目",
        "life": "生活状态",
        "emotion": "情绪",
        "support": "支持需求",
        "timeline": "时间线",
        "event": "事件",
        "relationship": "关系",
        "preference": "偏好",
        "conversation": "对话",
        "state": "状态",
        "recurring_topic": "反复主题",
    }.get(topic, topic)


def _consolidated_memory_text(title: str, items: list[MemoryRecord], *, max_items: int) -> str:
    pieces: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _clip_text(item.text, 72)
        key = _normalize(text)
        if not text or key in seen:
            continue
        seen.add(key)
        pieces.append(text)
        if len(pieces) >= max_items:
            break
    if not pieces:
        return title
    return f"{title}：" + "；".join(pieces)


def _join_source_excerpts(items: list[MemoryRecord], limit: int = 520) -> str:
    excerpts = [item.source_excerpt or item.text for item in items if item.source_excerpt or item.text]
    return _clip_text(" / ".join(_dedupe_preserve_order(excerpts)), limit)


def _join_evidence_quotes(items: list[MemoryRecord], limit: int = 520) -> str:
    quotes = [item.evidence_quote or item.source_excerpt for item in items if item.evidence_quote or item.source_excerpt]
    return _clip_text(" / ".join(_dedupe_preserve_order(quotes)), limit)


def _merged_tags(seed: list[str], items: list[MemoryRecord], limit: int = 16) -> list[str]:
    tags: list[str] = []
    for tag in seed:
        if tag and tag not in tags:
            tags.append(tag)
    for item in items:
        for tag in item.tags:
            if tag and tag not in tags:
                tags.append(tag)
            if len(tags) >= limit:
                return tags
    return tags


def _first_event_id(items: list[MemoryRecord]) -> str:
    for item in items:
        if item.evidence_event_id:
            return item.evidence_event_id
        if item.source_event_id:
            return item.source_event_id
    return ""


def _source_event_ids(items: list[MemoryRecord]) -> list[str]:
    values = []
    for item in items:
        if item.evidence_event_id:
            values.append(item.evidence_event_id)
        elif item.source_event_id:
            values.append(item.source_event_id)
    return _dedupe_preserve_order(values)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _normalize(value)
        if not value or key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _clip_text(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "…"


def _should_archive_l1(record: MemoryRecord, now: datetime) -> bool:
    if record.layer != "L1" or record.status != "active":
        return False
    if record.kind in {"identity", "boundary", "risk", "preference", "relationship"}:
        return False
    if record.importance > 0.72:
        return False
    moment = parse_iso_datetime(record.observed_at) or parse_iso_datetime(record.created_at)
    if moment is None:
        return False
    return (now - moment).total_seconds() >= 30 * 24 * 3600


def _archive_bucket(record: MemoryRecord) -> str:
    moment = parse_iso_datetime(record.observed_at) or parse_iso_datetime(record.created_at)
    if moment is None:
        return "unknown"
    return moment.strftime("%Y-%m")


def _thread_id(root_memory_id: str) -> str:
    return f"thr_{hashlib.sha1(root_memory_id.encode('utf-8')).hexdigest()[:12]}"


def _link_id(source_memory_id: str, target_memory_id: str, relation: str) -> str:
    raw = "|".join([source_memory_id, target_memory_id, relation])
    return f"link_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def _thread_title(record: MemoryRecord) -> str:
    text = record.text.strip()
    if not text:
        return record.kind
    snippet = text[:18]
    if len(text) > 18:
        snippet += "…"
    return f"{record.kind}: {snippet}"


def _memory_relation(left: MemoryRecord, right: MemoryRecord) -> str:
    if right.memory_id in left.supersedes or left.memory_id in right.supersedes:
        return "supersedes"
    if left.kind == right.kind and _normalize(left.text) == _normalize(right.text):
        return "duplicate"
    if left.kind == right.kind:
        return "same_kind"
    left_tags = set(left.tags)
    right_tags = set(right.tags)
    if left_tags & right_tags:
        return "shared_tags"
    if _same_memory_family(left.kind, right.kind):
        return "same_family"
    return "followup"
