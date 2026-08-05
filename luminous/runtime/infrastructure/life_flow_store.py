from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import local
from typing import Any, Iterator

from luminous.runtime.domain.activity import ActivitySession, DiaryEntry, Routine, RoutineCheckin, Task, TaskStep
from luminous.runtime.domain.time import utc_now_iso


class LifeFlowStore:
    """Dedicated persistence for life-flow records.

    It intentionally shares the runtime output directory, while keeping activity
    data out of the already broad companion runtime store. Domain writes and
    their durable audit intents are committed in one transaction; a worker
    later projects those intents into the companion runtime store.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_dir / "life_flow.sqlite3"
        self._transaction_state = local()
        self._ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        active = getattr(self._transaction_state, "connection", None)
        if active is not None:
            yield active
            return

        connection = sqlite3.connect(self.db_path)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            self._transaction_state.connection = connection
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            self._transaction_state.connection = None
            connection.close()

    @contextmanager
    def atomic(self) -> Iterator[None]:
        """Commit nested life-flow reads and writes as one transaction."""

        with self._connect():
            yield

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    user_scope TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    due_at TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    source TEXT NOT NULL DEFAULT 'manual',
                    calendar_event_id TEXT NOT NULL DEFAULT '',
                    reminder_ids_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS tasks_scope_status_due_idx ON tasks(user_scope, status, due_at, task_id);

                CREATE TABLE IF NOT EXISTS task_steps (
                    step_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS task_steps_task_position_idx ON task_steps(task_id, position, step_id);

                CREATE TABLE IF NOT EXISTS routines (
                    routine_id TEXT PRIMARY KEY,
                    user_scope TEXT NOT NULL,
                    title TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    reminder_policy TEXT NOT NULL DEFAULT 'none',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS routines_scope_active_idx ON routines(user_scope, active, routine_id);

                CREATE TABLE IF NOT EXISTS routine_checkins (
                    checkin_id TEXT PRIMARY KEY,
                    routine_id TEXT NOT NULL REFERENCES routines(routine_id) ON DELETE CASCADE,
                    period_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    occurred_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(routine_id, period_key)
                );
                CREATE INDEX IF NOT EXISTS routine_checkins_period_idx ON routine_checkins(period_key, routine_id);

                CREATE TABLE IF NOT EXISTS activity_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_scope TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    ended_at TEXT NOT NULL DEFAULT '',
                    task_id TEXT NOT NULL DEFAULT '',
                    content_ref TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS activity_sessions_scope_status_idx ON activity_sessions(user_scope, status, updated_at, session_id);

                CREATE TABLE IF NOT EXISTS diary_entries (
                    entry_id TEXT PRIMARY KEY,
                    user_scope TEXT NOT NULL,
                    date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    source_event_ids_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS diary_entries_scope_date_idx ON diary_entries(user_scope, date, status, entry_id);

                CREATE TABLE IF NOT EXISTS life_flow_audit_outbox (
                    event_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    delivered_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS life_flow_audit_outbox_status_created_idx
                    ON life_flow_audit_outbox(status, created_at, event_id);

                CREATE TABLE IF NOT EXISTS life_flow_effect_outbox (
                    effect_id TEXT PRIMARY KEY,
                    effect_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    delivered_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS life_flow_effect_outbox_status_created_idx
                    ON life_flow_effect_outbox(status, created_at, effect_id);
                """
            )

    def enqueue_audit_event(self, event: dict[str, Any]) -> str:
        event_id = str(event.get("event_id", "")).strip()
        if not event_id:
            raise ValueError("audit event_id is required")
        timestamp = str(event.get("created_at", "")) or utc_now_iso()
        payload_json = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO life_flow_audit_outbox (
                    event_id, payload_json, status, attempts, last_error,
                    created_at, updated_at, delivered_at
                ) VALUES (?, ?, 'queued', 0, '', ?, ?, '')
                """,
                (event_id, payload_json, timestamp, timestamp),
            )
        return event_id

    def read_pending_audit_events(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, payload_json, status, attempts, last_error,
                       created_at, updated_at, delivered_at
                FROM life_flow_audit_outbox
                WHERE status IN ('queued', 'retrying')
                ORDER BY created_at, event_id
                LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [
            {
                "event_id": str(row["event_id"]),
                "event": json.loads(str(row["payload_json"])),
                "status": str(row["status"]),
                "attempts": int(row["attempts"]),
                "last_error": str(row["last_error"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "delivered_at": str(row["delivered_at"]),
            }
            for row in rows
        ]

    def mark_audit_delivered(self, event_id: str, *, now: datetime | None = None) -> bool:
        timestamp = utc_now_iso(now)
        with self._connect() as conn:
            changed = conn.execute(
                """
                UPDATE life_flow_audit_outbox
                SET status = 'delivered', attempts = attempts + 1,
                    last_error = '', updated_at = ?, delivered_at = ?
                WHERE event_id = ? AND status IN ('queued', 'retrying')
                """,
                (timestamp, timestamp, event_id),
            ).rowcount
        return bool(changed)

    def mark_audit_failed(
        self,
        event_id: str,
        error_code: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        timestamp = utc_now_iso(now)
        with self._connect() as conn:
            changed = conn.execute(
                """
                UPDATE life_flow_audit_outbox
                SET status = 'retrying', attempts = attempts + 1,
                    last_error = ?, updated_at = ?
                WHERE event_id = ? AND status IN ('queued', 'retrying')
                """,
                (error_code[:120], timestamp, event_id),
            ).rowcount
        return bool(changed)

    def enqueue_effect(
        self,
        effect_id: str,
        effect_type: str,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> str:
        clean_id = effect_id.strip()
        clean_type = effect_type.strip()
        if not clean_id or not clean_type:
            raise ValueError("effect_id and effect_type are required")
        timestamp = utc_now_iso(now)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO life_flow_effect_outbox (
                    effect_id, effect_type, payload_json, status, attempts,
                    last_error, created_at, updated_at, delivered_at
                ) VALUES (?, ?, ?, 'queued', 0, '', ?, ?, '')
                """,
                (
                    clean_id,
                    clean_type,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    timestamp,
                    timestamp,
                ),
            )
        return clean_id

    def read_pending_effects(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT effect_id, effect_type, payload_json, status, attempts,
                       last_error, created_at, updated_at, delivered_at
                FROM life_flow_effect_outbox
                WHERE status IN ('queued', 'retrying')
                ORDER BY created_at, effect_id
                LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [
            {
                "effect_id": str(row["effect_id"]),
                "effect_type": str(row["effect_type"]),
                "payload": json.loads(str(row["payload_json"])),
                "status": str(row["status"]),
                "attempts": int(row["attempts"]),
                "last_error": str(row["last_error"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "delivered_at": str(row["delivered_at"]),
            }
            for row in rows
        ]

    def mark_effect_delivered(self, effect_id: str, *, now: datetime | None = None) -> bool:
        timestamp = utc_now_iso(now)
        with self._connect() as conn:
            changed = conn.execute(
                """
                UPDATE life_flow_effect_outbox
                SET status = 'delivered', attempts = attempts + 1,
                    last_error = '', updated_at = ?, delivered_at = ?
                WHERE effect_id = ? AND status IN ('queued', 'retrying')
                """,
                (timestamp, timestamp, effect_id),
            ).rowcount
        return bool(changed)

    def mark_effect_failed(
        self,
        effect_id: str,
        error_code: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        timestamp = utc_now_iso(now)
        with self._connect() as conn:
            changed = conn.execute(
                """
                UPDATE life_flow_effect_outbox
                SET status = 'retrying', attempts = attempts + 1,
                    last_error = ?, updated_at = ?
                WHERE effect_id = ? AND status IN ('queued', 'retrying')
                """,
                (error_code[:120], timestamp, effect_id),
            ).rowcount
        return bool(changed)

    def prune_delivered_outboxes(self, *, before: datetime) -> dict[str, int]:
        """Remove projected intents after their authoritative records exist."""

        cutoff = utc_now_iso(before)
        with self._connect() as conn:
            audit_count = conn.execute(
                "DELETE FROM life_flow_audit_outbox WHERE status = 'delivered' AND delivered_at < ?",
                (cutoff,),
            ).rowcount
            effect_count = conn.execute(
                "DELETE FROM life_flow_effect_outbox WHERE status = 'delivered' AND delivered_at < ?",
                (cutoff,),
            ).rowcount
        return {"audit_outbox": int(audit_count), "effect_outbox": int(effect_count)}

    def save_task(self, task: Task) -> Task:
        payload = task.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (task_id, user_scope, title, description, status, due_at, priority, source,
                    calendar_event_id, reminder_ids_json, created_at, updated_at, completed_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET title=excluded.title, description=excluded.description,
                    status=excluded.status, due_at=excluded.due_at, priority=excluded.priority, source=excluded.source,
                    calendar_event_id=excluded.calendar_event_id, reminder_ids_json=excluded.reminder_ids_json,
                    updated_at=excluded.updated_at, completed_at=excluded.completed_at, metadata_json=excluded.metadata_json
                """,
                (
                    payload["task_id"], payload["user_scope"], payload["title"], payload["description"],
                    payload["status"], payload["due_at"], payload["priority"], payload["source"],
                    payload["calendar_event_id"], json.dumps(payload["reminder_ids"], ensure_ascii=False),
                    payload["created_at"], payload["updated_at"], payload["completed_at"],
                    json.dumps(payload["metadata"], ensure_ascii=False),
                ),
            )
        return task

    def get_task(self, task_id: str) -> Task | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return _task(row) if row else None

    def read_tasks(self, *, user_scope: str = "default", status: str | None = None, limit: int = 100) -> list[Task]:
        sql = "SELECT * FROM tasks WHERE user_scope = ?"
        params: list[Any] = [user_scope]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY CASE WHEN due_at = '' THEN 1 ELSE 0 END, due_at ASC, created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_task(row) for row in rows]

    def save_task_step(self, step: TaskStep) -> TaskStep:
        payload = step.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO task_steps (step_id, task_id, title, position, status, completed_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(step_id) DO UPDATE SET title=excluded.title, position=excluded.position,
                    status=excluded.status, completed_at=excluded.completed_at, updated_at=excluded.updated_at
                """,
                (payload["step_id"], payload["task_id"], payload["title"], payload["position"], payload["status"],
                 payload["completed_at"], payload["created_at"], payload["updated_at"]),
            )
        return step

    def get_task_step(self, step_id: str) -> TaskStep | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM task_steps WHERE step_id = ?", (step_id,)).fetchone()
        return _step(row) if row else None

    def read_task_steps(self, task_id: str) -> list[TaskStep]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM task_steps WHERE task_id = ? ORDER BY position, step_id", (task_id,)).fetchall()
        return [_step(row) for row in rows]

    def save_routine(self, routine: Routine) -> Routine:
        payload = routine.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO routines (routine_id, user_scope, title, schedule, active, reminder_policy, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(routine_id) DO UPDATE SET title=excluded.title, schedule=excluded.schedule, active=excluded.active,
                    reminder_policy=excluded.reminder_policy, updated_at=excluded.updated_at, metadata_json=excluded.metadata_json
                """,
                (payload["routine_id"], payload["user_scope"], payload["title"], payload["schedule"], int(payload["active"]),
                 payload["reminder_policy"], payload["created_at"], payload["updated_at"], json.dumps(payload["metadata"], ensure_ascii=False)),
            )
        return routine

    def get_routine(self, routine_id: str) -> Routine | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM routines WHERE routine_id = ?", (routine_id,)).fetchone()
        return _routine(row) if row else None

    def read_routines(self, *, user_scope: str = "default", active_only: bool = False, limit: int = 100) -> list[Routine]:
        sql = "SELECT * FROM routines WHERE user_scope = ?"
        params: list[Any] = [user_scope]
        if active_only:
            sql += " AND active = 1"
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_routine(row) for row in rows]

    def save_checkin(self, checkin: RoutineCheckin) -> RoutineCheckin:
        payload = checkin.to_dict()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM routine_checkins WHERE routine_id = ? AND period_key = ?",
                (payload["routine_id"], payload["period_key"]),
            ).fetchone()
            if existing and existing["status"] == payload["status"] and existing["note"] == payload["note"]:
                return _checkin(existing)
            conn.execute(
                """
                INSERT INTO routine_checkins (checkin_id, routine_id, period_key, status, note, occurred_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(routine_id, period_key) DO UPDATE SET status=excluded.status, note=excluded.note,
                    occurred_at=excluded.occurred_at, updated_at=excluded.updated_at
                """,
                (payload["checkin_id"], payload["routine_id"], payload["period_key"], payload["status"], payload["note"],
                 payload["occurred_at"], payload["created_at"], payload["updated_at"]),
            )
            row = conn.execute("SELECT * FROM routine_checkins WHERE routine_id = ? AND period_key = ?", (payload["routine_id"], payload["period_key"])).fetchone()
        return _checkin(row)

    def get_checkin(self, routine_id: str, period_key: str) -> RoutineCheckin | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM routine_checkins WHERE routine_id = ? AND period_key = ?", (routine_id, period_key)).fetchone()
        return _checkin(row) if row else None

    def read_checkins(self, routine_id: str, *, limit: int = 365) -> list[RoutineCheckin]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM routine_checkins WHERE routine_id = ? ORDER BY period_key DESC LIMIT ?", (routine_id, max(1, min(limit, 1000)))).fetchall()
        return [_checkin(row) for row in rows]

    def save_session(self, session: ActivitySession) -> ActivitySession:
        payload = session.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO activity_sessions (session_id, user_scope, kind, title, status, started_at, ended_at, task_id,
                    content_ref, summary, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET kind=excluded.kind, title=excluded.title, status=excluded.status,
                    started_at=excluded.started_at, ended_at=excluded.ended_at, task_id=excluded.task_id,
                    content_ref=excluded.content_ref, summary=excluded.summary, updated_at=excluded.updated_at,
                    metadata_json=excluded.metadata_json
                """,
                (payload["session_id"], payload["user_scope"], payload["kind"], payload["title"], payload["status"],
                 payload["started_at"], payload["ended_at"], payload["task_id"], payload["content_ref"], payload["summary"],
                 payload["created_at"], payload["updated_at"], json.dumps(payload["metadata"], ensure_ascii=False)),
            )
        return session

    def get_session(self, session_id: str) -> ActivitySession | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM activity_sessions WHERE session_id = ?", (session_id,)).fetchone()
        return _session(row) if row else None

    def read_sessions(self, *, user_scope: str = "default", status: str | None = None, limit: int = 100) -> list[ActivitySession]:
        sql = "SELECT * FROM activity_sessions WHERE user_scope = ?"
        params: list[Any] = [user_scope]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_session(row) for row in rows]

    def save_diary_entry(self, entry: DiaryEntry) -> DiaryEntry:
        payload = entry.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO diary_entries (entry_id, user_scope, date, title, body, source_event_ids_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entry_id) DO UPDATE SET date=excluded.date, title=excluded.title, body=excluded.body,
                    source_event_ids_json=excluded.source_event_ids_json, status=excluded.status, updated_at=excluded.updated_at
                """,
                (payload["entry_id"], payload["user_scope"], payload["date"], payload["title"], payload["body"],
                 json.dumps(payload["source_event_ids"], ensure_ascii=False), payload["status"], payload["created_at"], payload["updated_at"]),
            )
        return entry

    def get_diary_entry(self, entry_id: str) -> DiaryEntry | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM diary_entries WHERE entry_id = ?", (entry_id,)).fetchone()
        return _diary(row) if row else None

    def read_diary_entries(self, *, user_scope: str = "default", date: str = "", include_deleted: bool = False, limit: int = 100) -> list[DiaryEntry]:
        sql = "SELECT * FROM diary_entries WHERE user_scope = ?"
        params: list[Any] = [user_scope]
        if date:
            sql += " AND date = ?"
            params.append(date)
        if not include_deleted:
            sql += " AND status != 'deleted'"
        sql += " ORDER BY date DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_diary(row) for row in rows]

    def export_bundle(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "generated_at": utc_now_iso(),
            "tasks": [item.to_dict() for item in self.read_tasks(limit=500)],
            "task_steps": [step.to_dict() for task in self.read_tasks(limit=500) for step in self.read_task_steps(task.task_id)],
            "routines": [item.to_dict() for item in self.read_routines(limit=500)],
            "routine_checkins": [checkin.to_dict() for routine in self.read_routines(limit=500) for checkin in self.read_checkins(routine.routine_id)],
            "activity_sessions": [item.to_dict() for item in self.read_sessions(limit=500)],
            "diary_entries": [item.to_dict() for item in self.read_diary_entries(include_deleted=True, limit=500)],
        }


def _payload(row: sqlite3.Row, key: str, default: Any) -> Any:
    try:
        value = json.loads(row[key] or "")
    except (KeyError, json.JSONDecodeError):
        value = default
    return value if isinstance(value, type(default)) else default


def _task(row: sqlite3.Row) -> Task:
    return Task.create({**dict(row), "reminder_ids": _payload(row, "reminder_ids_json", []), "metadata": _payload(row, "metadata_json", {})})


def _step(row: sqlite3.Row) -> TaskStep:
    return TaskStep.create(dict(row))


def _routine(row: sqlite3.Row) -> Routine:
    return Routine.create({**dict(row), "active": bool(row["active"]), "metadata": _payload(row, "metadata_json", {})})


def _checkin(row: sqlite3.Row) -> RoutineCheckin:
    return RoutineCheckin.create(dict(row))


def _session(row: sqlite3.Row) -> ActivitySession:
    return ActivitySession.create({**dict(row), "metadata": _payload(row, "metadata_json", {})})


def _diary(row: sqlite3.Row) -> DiaryEntry:
    return DiaryEntry.create({**dict(row), "source_event_ids": _payload(row, "source_event_ids_json", [])})
