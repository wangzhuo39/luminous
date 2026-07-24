from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from luminous.runtime.application.scheduling_service import SchedulingService
from luminous.runtime.domain.activity import (
    ActivitySession,
    CheckinStatus,
    DiaryEntry,
    DiaryStatus,
    Routine,
    RoutineCheckin,
    SessionStatus,
    Task,
    TaskStatus,
    TaskStep,
)
from luminous.runtime.domain.events import make_event, new_event_id
from luminous.runtime.domain.time import parse_iso_datetime, utc_now_iso
from luminous.runtime.infrastructure.life_flow_store import LifeFlowStore
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore


class LifeFlowService:
    """Application boundary for shared day-to-day companion activities."""

    def __init__(
        self,
        store: LifeFlowStore,
        runtime_store: CompanionRuntimeStore,
        scheduling: SchedulingService,
        *,
        clock: callable | None = None,
    ) -> None:
        self.store = store
        self.runtime_store = runtime_store
        self.scheduling = scheduling
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = self._now()
        task = Task.create({**payload, "source": str(payload.get("source", "manual"))}, now=utc_now_iso(now))
        self.store.save_task(task)
        task = self._attach_schedule(task, payload, now=now)
        self.store.save_task(task)
        self._audit("task_created", task.title, {"task": task.to_dict()}, source_ids=[task.task_id], now=now)
        return {"ok": True, "task": self._task_payload(task)}

    def read_tasks(self, *, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        return {"ok": True, "items": [self._task_payload(task) for task in self.store.read_tasks(status=status, limit=limit)]}

    def get_task(self, task_id: str) -> dict[str, Any]:
        return {"ok": True, "task": self._task_payload(self._require_task(task_id))}

    def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self._require_task(task_id)
        now = self._now()
        target = str(updates.pop("status", current.status))
        allowed = {"title", "description", "due_at", "priority", "metadata", "calendar_event_id", "reminder_ids"}
        clean = {key: value for key, value in updates.items() if key in allowed}
        task = current.transition(target, now=utc_now_iso(now), **clean)
        self.store.save_task(task)
        self._audit("task_updated", task.title, {"task": task.to_dict(), "updates": clean}, source_ids=[task_id], now=now)
        return {"ok": True, "task": self._task_payload(task)}

    def transition_task(self, task_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        target = {"start": TaskStatus.IN_PROGRESS.value, "complete": TaskStatus.COMPLETED.value, "block": TaskStatus.BLOCKED.value, "cancel": TaskStatus.CANCELLED.value}.get(action)
        if target is None:
            raise ValueError("unsupported task action")
        current = self._require_task(task_id)
        now = self._now()
        task = current.transition(target, now=utc_now_iso(now), **dict(payload or {}))
        self.store.save_task(task)
        if target in {TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value}:
            for reminder_id in task.reminder_ids:
                self.scheduling.cancel_reminder(reminder_id)
        self._audit(f"task_{action}", task.title, {"task": task.to_dict(), "action": action}, source_ids=[task_id, *task.reminder_ids], now=now)
        return {"ok": True, "task": self._task_payload(task)}

    def add_task_step(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        task = self._require_task(task_id)
        now = self._now()
        steps = self.store.read_task_steps(task.task_id)
        step = TaskStep.create({**payload, "task_id": task_id, "position": payload.get("position", len(steps))}, now=utc_now_iso(now))
        self.store.save_task_step(step)
        self._audit("task_step_created", step.title, {"task_id": task_id, "step": step.to_dict()}, source_ids=[task_id, step.step_id], now=now)
        return {"ok": True, "step": step.to_dict()}

    def update_task_step(self, task_id: str, step_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        self._require_task(task_id)
        current = self.store.get_task_step(step_id)
        if current is None or current.task_id != task_id:
            raise ValueError("task step not found")
        now = utc_now_iso(self._now())
        status = str(updates.get("status", current.status))
        if status not in {TaskStatus.OPEN.value, TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value}:
            raise ValueError("invalid task step status")
        step = TaskStep.create({**current.to_dict(), **{key: value for key, value in updates.items() if key in {"title", "position", "status"}}, "updated_at": now, "completed_at": now if status == TaskStatus.COMPLETED.value else current.completed_at})
        self.store.save_task_step(step)
        self._audit("task_step_updated", step.title, {"task_id": task_id, "step": step.to_dict()}, source_ids=[task_id, step_id], now=self._now())
        return {"ok": True, "step": step.to_dict()}

    def create_routine(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = self._now()
        routine = Routine.create(payload, now=utc_now_iso(now))
        self.store.save_routine(routine)
        self._audit("routine_created", routine.title, {"routine": routine.to_dict()}, source_ids=[routine.routine_id], now=now)
        return {"ok": True, "routine": self._routine_payload(routine)}

    def read_routines(self, *, active_only: bool = False, limit: int = 100) -> dict[str, Any]:
        return {"ok": True, "items": [self._routine_payload(item) for item in self.store.read_routines(active_only=active_only, limit=limit)]}

    def get_routine(self, routine_id: str) -> dict[str, Any]:
        return {"ok": True, "routine": self._routine_payload(self._require_routine(routine_id))}

    def update_routine(self, routine_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self._require_routine(routine_id)
        now = self._now()
        allowed = {"title", "schedule", "active", "reminder_policy", "metadata"}
        routine = Routine.create({**current.to_dict(), **{key: value for key, value in updates.items() if key in allowed}, "updated_at": utc_now_iso(now)})
        self.store.save_routine(routine)
        self._audit("routine_updated", routine.title, {"routine": routine.to_dict()}, source_ids=[routine_id], now=now)
        return {"ok": True, "routine": self._routine_payload(routine)}

    def checkin_routine(self, routine_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        routine = self._require_routine(routine_id)
        now = self._now()
        values = dict(payload or {})
        period_key = str(values.get("period_key") or self.period_key(routine, now))
        status = str(values.get("status", CheckinStatus.COMPLETED.value))
        existing = self.store.get_checkin(routine_id, period_key)
        if existing and existing.status == status and existing.note == str(values.get("note", "")):
            return {"ok": True, "idempotent": True, "checkin": existing.to_dict(), "streak": self._streak(routine)}
        checkin = RoutineCheckin.create({
            "checkin_id": existing.checkin_id if existing else new_event_id("checkin"),
            "routine_id": routine_id, "period_key": period_key, "status": status,
            "note": str(values.get("note", "")), "occurred_at": utc_now_iso(now),
            "created_at": existing.created_at if existing else utc_now_iso(now), "updated_at": utc_now_iso(now),
        })
        saved = self.store.save_checkin(checkin)
        self._audit("routine_checked_in", routine.title, {"routine_id": routine_id, "checkin": saved.to_dict()}, source_ids=[routine_id, saved.checkin_id], now=now)
        return {"ok": True, "checkin": saved.to_dict(), "streak": self._streak(routine)}

    def create_activity(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = self._now()
        if payload.get("task_id"):
            self._require_task(str(payload["task_id"]))
        session = ActivitySession.create(payload, now=utc_now_iso(now))
        self.store.save_session(session)
        self._audit("activity_created", session.title, {"activity": session.to_dict()}, source_ids=[session.session_id, *([session.task_id] if session.task_id else [])], now=now)
        return {"ok": True, "activity": session.to_dict()}

    def read_activities(self, *, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        return {"ok": True, "items": [item.to_dict() for item in self.store.read_sessions(status=status, limit=limit)]}

    def get_activity(self, session_id: str) -> dict[str, Any]:
        return {"ok": True, "activity": self._require_session(session_id).to_dict()}

    def transition_activity(self, session_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        target = {"start": SessionStatus.ACTIVE.value, "pause": SessionStatus.PAUSED.value, "resume": SessionStatus.ACTIVE.value, "complete": SessionStatus.COMPLETED.value, "cancel": SessionStatus.CANCELLED.value}.get(action)
        if target is None:
            raise ValueError("unsupported activity action")
        current = self._require_session(session_id)
        now = self._now()
        session = current.transition(target, now=utc_now_iso(now), **{key: value for key, value in dict(payload or {}).items() if key in {"summary", "content_ref", "metadata"}})
        self.store.save_session(session)
        self._audit(f"activity_{action}", session.title, {"activity": session.to_dict(), "action": action}, source_ids=[session_id, *([session.task_id] if session.task_id else [])], now=now)
        return {"ok": True, "activity": session.to_dict()}

    def create_diary_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = self._now()
        entry = DiaryEntry.create(payload, now=utc_now_iso(now))
        self.store.save_diary_entry(entry)
        self._audit("diary_entry_created", entry.title, {"diary_entry": entry.to_dict()}, source_ids=[entry.entry_id, *entry.source_event_ids], now=now)
        return {"ok": True, "diary_entry": entry.to_dict()}

    def read_diary_entries(self, *, date: str = "", limit: int = 100) -> dict[str, Any]:
        return {"ok": True, "items": [item.to_dict() for item in self.store.read_diary_entries(date=date, limit=limit)]}

    def get_diary_entry(self, entry_id: str) -> dict[str, Any]:
        entry = self.store.get_diary_entry(entry_id)
        if entry is None:
            raise ValueError("diary entry not found")
        return {"ok": True, "diary_entry": entry.to_dict()}

    def update_diary_entry(self, entry_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.store.get_diary_entry(entry_id)
        if current is None:
            raise ValueError("diary entry not found")
        now = self._now()
        allowed = {"date", "title", "body", "source_event_ids", "status"}
        entry = DiaryEntry.create({**current.to_dict(), **{key: value for key, value in updates.items() if key in allowed}, "updated_at": utc_now_iso(now)})
        self.store.save_diary_entry(entry)
        self._audit("diary_entry_updated", entry.title, {"diary_entry": entry.to_dict()}, source_ids=[entry.entry_id, *entry.source_event_ids], now=now)
        return {"ok": True, "diary_entry": entry.to_dict()}

    def draft_diary_entry(self, *, date: str = "") -> dict[str, Any]:
        day = date or self._now().date().isoformat()
        existing = next((item for item in self.store.read_diary_entries(date=day, include_deleted=True, limit=20) if item.status == DiaryStatus.DRAFT.value), None)
        if existing:
            return {"ok": True, "idempotent": True, "diary_entry": existing.to_dict()}
        timeline = self.read_timeline(from_date=day, to_date=day, limit=200)["items"]
        source_ids = [str(item["source_id"]) for item in timeline if item.get("source_id")]
        lines = [f"- {item['title']}" for item in timeline[:30]] or ["- 今天还没有记录，留下一句给未来的自己吧。"]
        return self.create_diary_entry({"date": day, "title": f"{day} 的回顾", "body": "\n".join(lines), "source_event_ids": source_ids, "status": DiaryStatus.DRAFT.value})

    def read_today(self, *, date: str = "") -> dict[str, Any]:
        day = date or self._now().date().isoformat()
        now = self._now()
        tasks = self.store.read_tasks(limit=500)
        open_tasks = [self._task_payload(task) for task in tasks if task.status in {TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value, TaskStatus.BLOCKED.value}]
        overdue = [task for task in open_tasks if task.get("due_at") and str(task["due_at"])[:10] < day]
        due_today = [task for task in open_tasks if str(task.get("due_at", ""))[:10] == day]
        routines = [self._routine_payload(item) for item in self.store.read_routines(active_only=True, limit=500)]
        routine_items = []
        for routine in routines:
            period = self.period_key(Routine.create(routine), now)
            checkin = self.store.get_checkin(str(routine["routine_id"]), period)
            routine_items.append({**routine, "period_key": period, "checkin": checkin.to_dict() if checkin else None})
        calendars = self.scheduling.read_calendar_events(limit=500).get("items", [])
        calendar_today = [item for item in calendars if str(item.get("starts_at", ""))[:10] == day]
        return {
            "ok": True, "date": day, "calendar_events": calendar_today, "overdue_tasks": overdue,
            "due_tasks": due_today, "open_tasks": open_tasks, "routines": routine_items,
            "active_activities": [item.to_dict() for item in self.store.read_sessions(status=SessionStatus.ACTIVE.value, limit=100)],
            "completed_tasks": [self._task_payload(task) for task in tasks if task.status == TaskStatus.COMPLETED.value and task.completed_at[:10] == day],
        }

    def read_timeline(self, *, from_date: str = "", to_date: str = "", kind: str = "", limit: int = 200) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for event in self.runtime_store.read_events(limit=1000):
            items.append({"item_id": f"event:{event.event_id}", "occurred_at": event.created_at, "kind": event.event_type, "title": event.summary, "source_type": "event", "source_id": event.event_id, "action_url": "#"})
        for event in self.scheduling.read_calendar_events(limit=500).get("items", []):
            event_id = str(event.get("event_id", ""))
            items.append({"item_id": f"calendar:{event_id}", "occurred_at": str(event.get("starts_at", "")), "kind": "calendar", "title": f"日程：{event.get('title', '')}", "source_type": "calendar_event", "source_id": event_id, "action_url": f"#calendar-{event_id}"})
        for reminder in self.scheduling.read_reminders(limit=500).get("items", []):
            reminder_id = str(reminder.get("reminder_id", ""))
            items.append({"item_id": f"reminder:{reminder_id}", "occurred_at": str(reminder.get("due_at", "")), "kind": "reminder", "title": f"提醒：{reminder.get('title', '')}", "source_type": "reminder", "source_id": reminder_id, "action_url": f"#reminder-{reminder_id}"})
        for message in self.runtime_store.read_outbox(limit=500):
            message_id = str(message.get("message_id", ""))
            items.append({"item_id": f"outbox:{message_id}", "occurred_at": str(message.get("created_at", "")), "kind": "outbox", "title": f"主动联系：{str(message.get('draft_text', ''))[:80]}", "source_type": "outbox", "source_id": message_id, "action_url": "#outboxSection"})
        for task in self.store.read_tasks(limit=500):
            items.append({"item_id": f"task:{task.task_id}:created", "occurred_at": task.created_at, "kind": "task", "title": f"创建任务：{task.title}", "source_type": "task", "source_id": task.task_id, "action_url": f"#task-{task.task_id}"})
            if task.status in {TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value}:
                items.append({"item_id": f"task:{task.task_id}:{task.status}", "occurred_at": task.completed_at or task.updated_at, "kind": "task", "title": f"{task.status == TaskStatus.COMPLETED.value and '完成' or '取消'}任务：{task.title}", "source_type": "task", "source_id": task.task_id, "action_url": f"#task-{task.task_id}"})
        for session in self.store.read_sessions(limit=500):
            items.append({"item_id": f"activity:{session.session_id}", "occurred_at": session.started_at or session.created_at, "kind": "activity", "title": f"{session.kind}：{session.title}", "source_type": "activity", "source_id": session.session_id, "action_url": f"#activity-{session.session_id}"})
        for routine in self.store.read_routines(limit=500):
            for checkin in self.store.read_checkins(routine.routine_id):
                if checkin.status != CheckinStatus.PENDING.value:
                    items.append({"item_id": f"checkin:{checkin.checkin_id}", "occurred_at": checkin.occurred_at or checkin.updated_at, "kind": "routine", "title": f"{checkin.status == CheckinStatus.COMPLETED.value and '完成打卡' or '跳过打卡'}：{routine.title}", "source_type": "routine_checkin", "source_id": checkin.checkin_id, "action_url": f"#routine-{routine.routine_id}"})
        for entry in self.store.read_diary_entries(limit=500):
            items.append({"item_id": f"diary:{entry.entry_id}", "occurred_at": entry.updated_at, "kind": "diary", "title": entry.title, "source_type": "diary", "source_id": entry.entry_id, "action_url": f"#diary-{entry.entry_id}"})
        filtered = [item for item in items if (not from_date or str(item["occurred_at"])[:10] >= from_date) and (not to_date or str(item["occurred_at"])[:10] <= to_date) and (not kind or item["kind"] == kind)]
        filtered.sort(key=lambda item: (str(item["occurred_at"]), str(item["item_id"])), reverse=True)
        return {"ok": True, "items": filtered[:max(1, min(limit, 500))]}

    def process_due_routines(self, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or self._now()
        created: list[dict[str, Any]] = []
        for routine in self.store.read_routines(active_only=True, limit=500):
            period = self.period_key(routine, now)
            if self.store.get_checkin(routine.routine_id, period):
                continue
            pending = RoutineCheckin.create({"routine_id": routine.routine_id, "period_key": period, "status": CheckinStatus.PENDING.value, "occurred_at": utc_now_iso(now)})
            self.store.save_checkin(pending)
            reminder: dict[str, Any] = {}
            if routine.reminder_policy == "remind":
                result = self.scheduling.create_reminder({"title": routine.title, "description": "今天别忘了完成这次打卡。", "due_at": utc_now_iso(now), "source": "routine", "source_ref": routine.routine_id, "kind": "routine", "metadata": {"routine_id": routine.routine_id, "period_key": period}})
                reminder = dict(result.get("reminder", {}) or {})
            created.append({"routine_id": routine.routine_id, "checkin": pending.to_dict(), "reminder": reminder})
            self._audit("routine_due", routine.title, {"routine_id": routine.routine_id, "period_key": period, "reminder": reminder}, source_ids=[routine.routine_id, pending.checkin_id], now=now)
        return {"ok": True, "items": created}

    def expire_activities(self, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or self._now()
        expired: list[dict[str, Any]] = []
        for session in self.store.read_sessions(limit=500):
            if session.status not in {SessionStatus.ACTIVE.value, SessionStatus.PAUSED.value}:
                continue
            expires_at = str(session.metadata.get("expires_at", ""))
            expiry = parse_iso_datetime(expires_at)
            if expiry is None or expiry > now:
                continue
            updated = session.transition(SessionStatus.EXPIRED.value, now=utc_now_iso(now))
            self.store.save_session(updated)
            expired.append(updated.to_dict())
            self._audit("activity_expired", updated.title, {"activity": updated.to_dict()}, source_ids=[updated.session_id], now=now)
        return {"ok": True, "items": expired}

    def preview_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action", ""))
        allowed = {"create_task", "complete_task", "start_focus_session", "checkin_routine", "draft_diary"}
        if action not in allowed:
            raise ValueError("unsupported life-flow action")
        data = dict(payload.get("payload", {}) or {})
        preview_id = hashlib.sha256(json.dumps({"action": action, "payload": data}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:20]
        return {"ok": True, "preview_id": preview_id, "action": action, "payload": data, "confirmation_required": True}

    def confirm_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("confirmed") is not True:
            raise ValueError("confirmed must be true")
        action = str(payload.get("action", ""))
        data = dict(payload.get("payload", {}) or {})
        if action == "create_task":
            return self.create_task({**data, "source": "action_confirm"})
        if action == "complete_task":
            return self.transition_task(str(data.get("task_id", "")), "complete")
        if action == "start_focus_session":
            created = self.create_activity({**data, "kind": "focus"})
            return self.transition_activity(str(created["activity"]["session_id"]), "start")
        if action == "checkin_routine":
            return self.checkin_routine(str(data.get("routine_id", "")), data)
        if action == "draft_diary":
            return self.draft_diary_entry(date=str(data.get("date", "")))
        raise ValueError("unsupported life-flow action")

    @staticmethod
    def period_key(routine: Routine, now: datetime) -> str:
        if routine.schedule == "weekly":
            anchor = now.date() - timedelta(days=now.weekday())
            return anchor.isoformat()
        return now.date().isoformat()

    def _attach_schedule(self, task: Task, payload: dict[str, Any], *, now: datetime) -> Task:
        values = task.to_dict()
        reminder_ids = list(task.reminder_ids)
        if bool(payload.get("create_calendar")) and task.due_at:
            result = self.scheduling.create_calendar_event({"title": task.title, "starts_at": task.due_at, "ends_at": str(payload.get("ends_at", "")), "source": "task", "metadata": {"task_id": task.task_id}})
            values["calendar_event_id"] = str(dict(result.get("calendar_event", {}) or {}).get("event_id", ""))
        reminder_at = str(payload.get("reminder_at", "")) or task.due_at
        if bool(payload.get("create_reminder")) and reminder_at:
            result = self.scheduling.create_reminder({"title": task.title, "description": task.description, "due_at": reminder_at, "source": "task", "source_ref": task.task_id, "kind": "reminder", "metadata": {"task_id": task.task_id}})
            reminder = dict(result.get("reminder", {}) or {})
            if reminder.get("reminder_id"):
                reminder_ids.append(str(reminder["reminder_id"]))
        values["reminder_ids"] = reminder_ids
        values["updated_at"] = utc_now_iso(now)
        return Task.create(values)

    def _task_payload(self, task: Task) -> dict[str, Any]:
        return {**task.to_dict(), "steps": [step.to_dict() for step in self.store.read_task_steps(task.task_id)]}

    def _routine_payload(self, routine: Routine) -> dict[str, Any]:
        return {**routine.to_dict(), "streak": self._streak(routine)}

    def _streak(self, routine: Routine) -> int:
        completed = {item.period_key for item in self.store.read_checkins(routine.routine_id) if item.status == CheckinStatus.COMPLETED.value}
        if not completed:
            return 0
        cursor = self._now().date()
        if routine.schedule == "weekly":
            cursor = cursor - timedelta(days=cursor.weekday())
            delta = timedelta(days=7)
        else:
            delta = timedelta(days=1)
        count = 0
        while cursor.isoformat() in completed:
            count += 1
            cursor -= delta
        return count

    def _require_task(self, task_id: str) -> Task:
        task = self.store.get_task(task_id)
        if task is None:
            raise ValueError("task not found")
        return task

    def _require_routine(self, routine_id: str) -> Routine:
        routine = self.store.get_routine(routine_id)
        if routine is None:
            raise ValueError("routine not found")
        return routine

    def _require_session(self, session_id: str) -> ActivitySession:
        session = self.store.get_session(session_id)
        if session is None:
            raise ValueError("activity not found")
        return session

    def _audit(self, event_type: str, summary: str, payload: dict[str, Any], *, source_ids: list[str], now: datetime) -> None:
        self.runtime_store.append_event(make_event(event_type, summary, payload, trace_id=new_event_id("trace"), now=now, source_ids=source_ids))

    def _now(self) -> datetime:
        value = self.clock()
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
