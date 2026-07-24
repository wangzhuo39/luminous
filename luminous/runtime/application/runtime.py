from __future__ import annotations

import math
import re
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from luminous.runtime.application.memory_extractor import MemoryExtractor
from luminous.runtime.application.life_flow_service import LifeFlowService
from luminous.runtime.application.notification_bridge import NotificationBridge, NotificationDelivery
from luminous.runtime.application.prompts import SYSTEM_PROMPT
from luminous.runtime.application.prompt_builder import PromptBuilder
from luminous.runtime.application.proactive_engine import ProactiveDecision, ProactiveEngine
from luminous.runtime.application.scheduling_service import SchedulingService
from luminous.runtime.application.state_engine import StateEngine
from luminous.runtime.config import BackendConfig
from luminous.runtime.domain.events import ConversationEvent, ProactiveSignal, make_event, new_event_id
from luminous.runtime.domain.memory import MemoryHit, MemoryRecord, build_memory_records
from luminous.runtime.domain.output import ParsedCompanionOutput, parse_model_output
from luminous.runtime.domain.presence import build_presence
from luminous.runtime.domain.state import CompanionState
from luminous.runtime.domain.scheduling import ProactiveKind
from luminous.runtime.domain.safety import SafetyPolicy
from luminous.runtime.domain.time import parse_iso_datetime, utc_now_iso
from luminous.runtime.infrastructure.client import Message, ModelClient
from luminous.runtime.infrastructure.life_flow_store import LifeFlowStore
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore


PROACTIVE_SYSTEM_PROMPT = """你正在替现实用户发一条低频主动联系消息。你是叶筝。

要求：
- 只输出正文，不要标签，不要解释，不要提系统、记忆、模型或训练。
- 语气要短、稳、轻，不要打扰式催促，不要说教。
- 必须像一个认真记得对方的人，但不要夸张撒娇。
- 遇到风险信号时，优先承接、关心、鼓励联系现实支持，不要渲染。
"""


class CompanionRuntime:
    def __init__(
        self,
        config: BackendConfig,
        client: ModelClient | None = None,
        store: CompanionRuntimeStore | None = None,
        clock: callable | None = None,
    ) -> None:
        self.config = config
        self.client = client or ModelClient(config)
        self.store = store or CompanionRuntimeStore.for_project(config.project_root)
        self.clock = clock or _utc_now
        self.prompt_builder = PromptBuilder()
        self.memory_extractor = MemoryExtractor(config, self.client)
        self.state_engine = StateEngine()
        self.proactive_engine = ProactiveEngine()
        self.notification_bridge = NotificationBridge(config)
        self.safety_policy = SafetyPolicy()
        self.scheduling = SchedulingService(self.store, clock=self.clock, safety_policy=self.safety_policy)
        self.life_flow = LifeFlowService(
            LifeFlowStore(self.store.base_dir), self.store, self.scheduling, clock=self.clock,
        )

    def chat(self, user_text: str, history: Sequence[dict[str, object]] | None = None) -> dict[str, object]:
        clean_user_text = user_text.strip()
        if not clean_user_text:
            raise ValueError("message is required")

        now = self.clock()
        trace_id = new_event_id("trace")
        turn_id = new_event_id("turn")
        state = self.store.load_state()
        memory_hits = self.store.query_memories(clean_user_text, limit=5)
        recent_events = self.store.read_events(limit=10)
        prompt_package = self.prompt_builder.build(
            user_text=clean_user_text,
            history=history or [],
            state=state,
            memory_hits=memory_hits,
            recent_events=recent_events,
        )

        if self.config.mock:
            raw = mock_model_output(clean_user_text)
        else:
            raw = self.client.complete(prompt_package.messages)

        parsed = parse_model_output(raw)
        risk_flags = _risk_flags(clean_user_text, parsed.reply)
        user_event = make_event(
            "user_message",
            _shorten(clean_user_text, 80),
            {
                "turn_id": turn_id,
                "role": "user",
                "content": clean_user_text,
                "history_count": len(history or []),
            },
            trace_id=trace_id,
            now=now,
            actor="user",
        )
        assistant_event = make_event(
            "assistant_message",
            _shorten(parsed.reply, 80),
            {
                "turn_id": turn_id,
                "role_thinking": parsed.role_thinking,
                "role_action": parsed.role_action,
                "reply": parsed.reply,
            },
            trace_id=trace_id,
            now=now,
            actor="assistant",
        )
        self.store.append_raw_message(
            message_id=user_event.event_id,
            trace_id=trace_id,
            turn_id=turn_id,
            role="user",
            content=clean_user_text,
            created_at=user_event.created_at,
            source_event_id=user_event.event_id,
        )
        self.store.append_raw_message(
            message_id=assistant_event.event_id,
            trace_id=trace_id,
            turn_id=turn_id,
            role="assistant",
            content=parsed.reply,
            created_at=assistant_event.created_at,
            source_event_id=assistant_event.event_id,
        )
        memory_result = self.memory_extractor.extract(
            clean_user_text,
            parsed.reply,
            source_event_id=user_event.event_id,
            trace_id=trace_id,
            now=now,
        )
        memory_records = [
            self.store.write_memory(record, trace_id=trace_id, emit_audit=True)
            for record in memory_result.records
        ]
        transition = self.state_engine.apply_turn(
            state,
            user_text=clean_user_text,
            assistant_text=parsed.reply,
            memory_records=memory_records,
            risk_flags=risk_flags,
            now=now,
        )
        model_event = make_event(
            "model_call",
            _shorten(parsed.reply, 80),
            {
                "model": self.config.model if not self.config.mock else "mock",
                "mock": self.config.mock,
                "message_count": len(prompt_package.messages),
                "prompt": prompt_package.to_trace_dict(),
            },
            trace_id=trace_id,
            now=now,
            actor="model",
        )
        memory_event = make_event(
            "memory_extracted",
            f"{len(memory_records)} 条记忆",
            {
                "source_event_id": user_event.event_id,
                "extraction": memory_result.to_trace_dict(),
                "records": [record.to_dict() for record in memory_records],
            },
            trace_id=trace_id,
            now=now,
        )
        state_event = make_event(
            "state_transition",
            f"mood={state.mood} mode={state.conversation_mode} support={state.support_need:.2f}",
            {
                "state": state.to_dict(),
                "transition": transition.to_event_payload(),
            },
            trace_id=trace_id,
            now=now,
        )
        prompt_event = make_event(
            "prompt_built",
            f"messages={len(prompt_package.messages)}",
            {"prompt": prompt_package.to_trace_dict()},
            trace_id=trace_id,
            now=now,
        )
        proactive_decision = self.proactive_engine.evaluate(
            state=state,
            recent_events=recent_events + [user_event, assistant_event, state_event],
            memory_hits=memory_hits,
            now=now,
            trace_id=trace_id,
        )
        proactive_event = make_event(
            "proactive_decision",
            proactive_decision.signal.reason,
            proactive_decision.to_trace_dict(),
            trace_id=trace_id,
            now=now,
        )

        for event in (prompt_event, user_event, model_event, assistant_event, memory_event, state_event, proactive_event):
            self.store.append_event(event)
        self.store.save_state(state)
        proactive_signal = proactive_decision.signal
        return {
            "role_thinking": parsed.role_thinking,
            "role_action": parsed.role_action,
            "reply": parsed.reply,
            "presence": build_presence(clean_user_text, parsed, state),
            "state": state.to_dict(),
            "memory": {
                "query": clean_user_text,
                "hits": [hit.to_dict() for hit in memory_hits],
                "written": [record.to_dict() for record in memory_records],
                "extraction": memory_result.to_trace_dict(),
            },
            "ledger": {
                "trace_id": trace_id,
                "turn_id": turn_id,
                "events": [
                    user_event.to_dict(),
                    assistant_event.to_dict(),
                    state_event.to_dict(),
                    prompt_event.to_dict(),
                    model_event.to_dict(),
                    memory_event.to_dict(),
                    proactive_event.to_dict(),
                ],
            },
            "proactive": proactive_signal.to_dict(),
            "prompt": prompt_package.to_trace_dict(),
            "analysis": {
                "risk_flags": risk_flags,
                "transition": transition.to_event_payload(),
            },
            "meta": {
                "model": self.config.model if not self.config.mock else "mock",
                "mock": self.config.mock,
            },
        }

    def get_state(self) -> dict[str, object]:
        return self.store.snapshot()

    def query_memory(self, query: str, limit: int = 5) -> dict[str, object]:
        hits = self.store.query_memories(query, limit=limit)
        return {
            "query": query,
            "limit": limit,
            "hits": [hit.to_dict() for hit in hits],
            "state": self.store.load_state().to_dict(),
        }

    def read_ledger(self, limit: int = 50, trace_id: str | None = None) -> dict[str, object]:
        events = self.store.read_events(limit=limit, trace_id=trace_id)
        return {
            "limit": limit,
            "trace_id": trace_id or "",
            "count": len(events),
            "events": [event.to_dict() for event in events],
        }

    def read_trace(self, trace_id: str, limit: int = 50) -> dict[str, object]:
        trace = self.store.read_trace(trace_id, limit=limit)
        trace["limit"] = limit
        return trace

    def read_raw_messages(self, limit: int = 50, role: str | None = None) -> dict[str, object]:
        items = self.store.read_raw_messages(limit=limit, role=role)
        return {"limit": limit, "role": role or "", "count": len(items), "items": items}

    def read_memory_threads(self, limit: int = 50) -> dict[str, object]:
        items = self.store.read_memory_threads(limit=limit)
        return {"limit": limit, "count": len(items), "items": items}

    def read_memory_links(self, limit: int = 100) -> dict[str, object]:
        items = self.store.read_memory_links(limit=limit)
        return {"limit": limit, "count": len(items), "items": items}

    def read_memory_evidence(
        self,
        limit: int = 100,
        memory_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, object]:
        items = self.store.read_memory_evidence(limit=limit, memory_id=memory_id, status=status)
        return {
            "limit": limit,
            "memory_id": memory_id or "",
            "status": status or "",
            "count": len(items),
            "items": items,
        }

    def update_memory(self, memory_id: str, updates: dict[str, Any] | None = None) -> dict[str, object]:
        updated = self.store.update_memory(memory_id, updates=updates or {})
        if updated is None:
            return {"ok": False, "memory_id": memory_id, "reason": "not_found"}
        event = make_event(
            "memory_updated",
            updated.text[:80],
            {"memory": updated.to_dict(), "updates": updates or {}},
            trace_id=new_event_id("trace"),
            now=self.clock(),
            source_ids=[memory_id],
        )
        self.store.append_event(event)
        return {"ok": True, "memory": updated.to_dict(), "event": event.to_dict()}

    def forget_memory(self, memory_id: str, *, hard_delete: bool = False) -> dict[str, object]:
        forgotten = self.store.forget_memory(memory_id, hard_delete=hard_delete)
        event = make_event(
            "memory_forgotten",
            memory_id,
            {"memory_id": memory_id, "hard_delete": hard_delete, "memory": forgotten.to_dict() if forgotten else None},
            trace_id=new_event_id("trace"),
            now=self.clock(),
            source_ids=[memory_id],
        )
        self.store.append_event(event)
        return {"ok": True, "memory": forgotten.to_dict() if forgotten else None, "event": event.to_dict()}

    def export_data(self) -> dict[str, object]:
        bundle = self.store.export_bundle()
        bundle["life_flow"] = self.life_flow.store.export_bundle()
        return bundle

    def create_reminder(self, payload: dict[str, Any]) -> dict[str, object]:
        return self.scheduling.create_reminder(payload)

    def read_reminders(self, *, status: str | None = None, limit: int = 100) -> dict[str, object]:
        return self.scheduling.read_reminders(status=status, limit=limit)

    def update_reminder(self, reminder_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return self.scheduling.update_reminder(reminder_id, updates)

    def snooze_reminder(self, reminder_id: str, due_at: str) -> dict[str, object]:
        return self.scheduling.snooze_reminder(reminder_id, due_at)

    def complete_reminder(self, reminder_id: str) -> dict[str, object]:
        return self.scheduling.complete_reminder(reminder_id)

    def cancel_reminder(self, reminder_id: str) -> dict[str, object]:
        return self.scheduling.cancel_reminder(reminder_id)

    def create_calendar_event(self, payload: dict[str, Any]) -> dict[str, object]:
        return self.scheduling.create_calendar_event(payload)

    def read_calendar_events(self, *, limit: int = 100) -> dict[str, object]:
        return self.scheduling.read_calendar_events(limit=limit)

    def update_calendar_event(self, event_id: str, updates: dict[str, Any]) -> dict[str, object]:
        return self.scheduling.update_calendar_event(event_id, updates)

    def notification_preferences(self) -> dict[str, object]:
        return self.scheduling.notification_preferences()

    def update_notification_preferences(self, updates: dict[str, Any]) -> dict[str, object]:
        return self.scheduling.update_notification_preferences(updates)

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.life_flow.create_task(payload)

    def read_tasks(self, *, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        return self.life_flow.read_tasks(status=status, limit=limit)

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self.life_flow.get_task(task_id)

    def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        return self.life_flow.update_task(task_id, updates)

    def transition_task(self, task_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.life_flow.transition_task(task_id, action, payload)

    def add_task_step(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.life_flow.add_task_step(task_id, payload)

    def update_task_step(self, task_id: str, step_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        return self.life_flow.update_task_step(task_id, step_id, updates)

    def create_routine(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.life_flow.create_routine(payload)

    def read_routines(self, *, active_only: bool = False, limit: int = 100) -> dict[str, Any]:
        return self.life_flow.read_routines(active_only=active_only, limit=limit)

    def get_routine(self, routine_id: str) -> dict[str, Any]:
        return self.life_flow.get_routine(routine_id)

    def update_routine(self, routine_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        return self.life_flow.update_routine(routine_id, updates)

    def checkin_routine(self, routine_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.life_flow.checkin_routine(routine_id, payload)

    def create_activity(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.life_flow.create_activity(payload)

    def read_activities(self, *, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        return self.life_flow.read_activities(status=status, limit=limit)

    def get_activity(self, session_id: str) -> dict[str, Any]:
        return self.life_flow.get_activity(session_id)

    def transition_activity(self, session_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.life_flow.transition_activity(session_id, action, payload)

    def create_diary_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.life_flow.create_diary_entry(payload)

    def read_diary_entries(self, *, date: str = "", limit: int = 100) -> dict[str, Any]:
        return self.life_flow.read_diary_entries(date=date, limit=limit)

    def get_diary_entry(self, entry_id: str) -> dict[str, Any]:
        return self.life_flow.get_diary_entry(entry_id)

    def update_diary_entry(self, entry_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        return self.life_flow.update_diary_entry(entry_id, updates)

    def draft_diary_entry(self, *, date: str = "") -> dict[str, Any]:
        return self.life_flow.draft_diary_entry(date=date)

    def read_today(self, *, date: str = "") -> dict[str, Any]:
        return self.life_flow.read_today(date=date)

    def read_timeline(self, *, from_date: str = "", to_date: str = "", kind: str = "", limit: int = 200) -> dict[str, Any]:
        return self.life_flow.read_timeline(from_date=from_date, to_date=to_date, kind=kind, limit=limit)

    def process_due_routines(self, *, now: datetime | None = None) -> dict[str, Any]:
        return self.life_flow.process_due_routines(now=now)

    def expire_activities(self, *, now: datetime | None = None) -> dict[str, Any]:
        return self.life_flow.expire_activities(now=now)

    def preview_life_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.life_flow.preview_action(payload)

    def confirm_life_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.life_flow.confirm_action(payload)

    def process_due_reminders(self, *, now: datetime | None = None, limit: int = 20) -> dict[str, object]:
        now = now or self.clock()
        claimed = self.store.claim_due_reminders(now=now, limit=limit)
        drafted: list[str] = []
        held: list[dict[str, object]] = []
        for reminder in claimed:
            trace_id = new_event_id("trace")
            state = self.store.load_state()
            risk_level = str(getattr(state, "risk_level", ""))
            allowed, holds, preferences = self.scheduling.outbound_permitted(
                proactive_kind=reminder.kind.value, now=now, risk_level=risk_level,
            )
            if not allowed:
                event = make_event(
                    "reminder_delivery_held", reminder.title,
                    {"reminder": reminder.to_dict(), "hold_reasons": holds, "preferences": preferences, "safety_policy": self.safety_policy.to_dict()},
                    trace_id=trace_id, now=now, source_ids=[reminder.reminder_id],
                )
                self.store.append_event(event)
                held.append({"reminder_id": reminder.reminder_id, "hold_reasons": holds, "trace_id": trace_id})
                continue
            message = f"提醒你：{reminder.title}" + (f"\n{reminder.description}" if reminder.description else "")
            message_id = f"reminder_{reminder.reminder_id}"
            self.store.append_outbox(
                {
                    "message_id": message_id,
                    "signal_id": reminder.reminder_id,
                    "trace_id": trace_id,
                    "channel": "internal",
                    "draft_text": message,
                    "status": "drafted",
                    "reason": "scheduled_reminder",
                    "signal_type": reminder.kind.value,
                    "created_at": utc_now_iso(now),
                    "idempotency_key": f"reminder:{reminder.reminder_id}",
                    "payload": {"reminder": reminder.to_dict(), "proactive_kind": reminder.kind.value, "preferences": preferences},
                }
            )
            delivered = self.store.mark_reminder_delivered(reminder.reminder_id, now=now)
            event = make_event(
                "reminder_outbox_drafted", reminder.title,
                {"reminder": delivered.to_dict() if delivered else reminder.to_dict(), "message_id": message_id, "proactive_kind": reminder.kind.value, "preferences": preferences},
                trace_id=trace_id, now=now, source_ids=[reminder.reminder_id, message_id],
            )
            self.store.append_event(event)
            drafted.append(message_id)
        return {"claimed": [item.reminder_id for item in claimed], "drafted": drafted, "held": held}

    def record_outbox_feedback(
        self,
        message_id: str,
        status: str,
        feedback_text: str = "",
        replied_at: str | datetime | None = None,
    ) -> dict[str, object]:
        if isinstance(replied_at, datetime):
            replied_at_iso = utc_now_iso(replied_at)
            feedback_now = replied_at
        elif replied_at:
            replied_at_iso = str(replied_at)
            feedback_now = parse_iso_datetime(replied_at_iso) or self.clock()
        else:
            replied_at_iso = ""
            feedback_now = self.clock()
        outbox = self.store.record_outbox_feedback(
            message_id,
            status,
            feedback_text=feedback_text,
            replied_at=replied_at_iso or None,
        )
        if outbox is None:
            return {"ok": False, "message_id": message_id, "reason": "not_found"}
        state = self.store.load_state()
        transition = self.state_engine.apply_proactive_feedback(
            state,
            feedback_status=status,
            feedback_text=feedback_text,
            sent_at=str(outbox.get("sent_at", "")),
            replied_at=str(outbox.get("replied_at", "")) or replied_at_iso,
            now=feedback_now,
        )
        self.store.save_state(state)
        event = make_event(
            "proactive_feedback",
            status,
            {
                "message_id": message_id,
                "status": status,
                "feedback_text": feedback_text,
                "outbox": outbox,
                "state_transition": transition.to_event_payload(),
            },
            trace_id=new_event_id("trace"),
            now=feedback_now,
            source_ids=[message_id],
        )
        self.store.append_event(event)
        return {
            "ok": True,
            "message_id": message_id,
            "outbox": outbox,
            "state": state.to_dict(),
            "transition": transition.to_event_payload(),
            "event": event.to_dict(),
        }

    def record_outbox_receipt(
        self,
        message_id: str,
        receipt_type: str,
        *,
        channel: str = "",
        payload: dict[str, Any] | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, object]:
        outbox = self.store.record_outbox_receipt(
            message_id,
            receipt_type,
            channel=channel,
            payload=payload or {},
            occurred_at=occurred_at,
        )
        if outbox is None:
            return {"ok": False, "message_id": message_id, "reason": "not_found"}
        now = parse_iso_datetime(occurred_at or "") or self.clock()
        event = make_event(
            "outbox_delivery_receipt",
            receipt_type,
            {
                "message_id": message_id,
                "receipt_type": receipt_type,
                "channel": channel or outbox.get("channel", "internal"),
                "payload": payload or {},
                "outbox": outbox,
            },
            trace_id=new_event_id("trace"),
            now=now,
            source_ids=[message_id],
        )
        self.store.append_event(event)
        return {"ok": True, "message_id": message_id, "outbox": outbox, "event": event.to_dict()}

    def proactive_tick(self, send: bool = False, now: datetime | None = None) -> dict[str, object]:
        state = self.store.load_state()
        now = now or self.clock()
        recent_events = self.store.read_events(limit=20)
        memory_hits = self.store.query_memories(" ".join(state.recent_topics[:3]), limit=3)
        trace_id = new_event_id("trace")
        decision = self.proactive_engine.evaluate(
            state=state,
            recent_events=recent_events,
            memory_hits=memory_hits,
            now=now,
            trace_id=trace_id,
        )
        signal = decision.signal
        decision_event = make_event(
            "proactive_decision",
            signal.reason,
            decision.to_trace_dict(),
            trace_id=trace_id,
            now=now,
        )
        self.store.append_event(decision_event)
        notification_delivery: NotificationDelivery | None = None
        if send and signal.due:
            allowed, preference_holds, preferences = self.scheduling.outbound_permitted(
                proactive_kind=ProactiveKind.CHECKIN.value,
                now=now,
                risk_level=str(getattr(state, "risk_level", "")),
            )
            if not allowed:
                held_event = make_event(
                    "proactive_delivery_held",
                    signal.reason,
                    {"signal": signal.to_dict(), "hold_reasons": preference_holds, "preferences": preferences, "safety_policy": self.safety_policy.to_dict()},
                    trace_id=trace_id, now=now,
                )
                self.store.append_event(held_event)
                return {
                    **signal.to_dict(),
                    "due": False,
                    "hold_reasons": [*list(signal.hold_reasons), *preference_holds],
                    "decision": decision.to_trace_dict(),
                    "notification": {},
                }
            message = signal.draft_message or self.draft_proactive_message(state, recent_events, signal, now=now)
            notification_delivery = self.notification_bridge.deliver(
                message=message,
                signal=signal,
                trace_id=trace_id,
                now=now,
                title=state.persona_name or "叶筝",
            )
            state.mark_proactive_contact(now)
            self.store.save_state(state)
            outbox_status = "failed" if notification_delivery.attempted and not notification_delivery.ok else "sent"
            outbox_channel = notification_delivery.channel or "internal"
            sent_event = make_event(
                "proactive_message_sent",
                _shorten(message, 80),
                {
                    "message": message,
                    "signal": signal.to_dict(),
                    "decision": decision.to_trace_dict(),
                    "notification": notification_delivery.to_dict(),
                },
                trace_id=trace_id,
                now=now,
            )
            self.store.append_event(sent_event)
            delivery_receipts = [notification_delivery.to_receipt(sent_event.event_id)]
            self.store.append_outbox(
                {
                    "message_id": sent_event.event_id,
                    "signal_id": trace_id,
                    "trace_id": trace_id,
                    "channel": outbox_channel,
                    "created_at": utc_now_iso(now),
                    "draft_text": message,
                    "status": outbox_status,
                    "score": signal.score,
                    "reason": signal.reason,
                    "signal_type": signal.signal_type,
                    "anchor_memory_ids": list(signal.anchor_memory_ids),
                    "sent_at": utc_now_iso(now) if outbox_status == "sent" else "",
                    "notification": notification_delivery.to_dict(),
                    "delivery_receipts": delivery_receipts,
                    "payload": {
                        "message": message,
                        "signal": signal.to_dict(),
                        "notification": notification_delivery.to_dict(),
                        "delivery_receipts": delivery_receipts,
                    },
                }
            )
            if notification_delivery.attempted:
                notification_event = make_event(
                    "proactive_notification_delivered" if notification_delivery.ok else "proactive_notification_failed",
                    notification_delivery.detail or notification_delivery.status,
                    {
                        "message_id": sent_event.event_id,
                        "delivery": notification_delivery.to_dict(),
                    },
                    trace_id=trace_id,
                    now=now,
                    source_ids=[sent_event.event_id],
                )
                self.store.append_event(notification_event)
            signal = ProactiveSignal(
                due=True,
                score=signal.score,
                reason=signal.reason,
                next_check_minutes=signal.next_check_minutes,
                draft_message=message,
                trace_id=trace_id,
                created_at=utc_now_iso(now),
                signal_type=signal.signal_type,
                anchor_memory_ids=signal.anchor_memory_ids,
                hold_reasons=signal.hold_reasons,
            )
        return {
            **signal.to_dict(),
            "decision": decision.to_trace_dict(),
            "notification": notification_delivery.to_dict() if notification_delivery else {},
        }

    def evaluate_proactive(
        self,
        state: CompanionState,
        recent_events: Sequence[ConversationEvent],
        now: datetime | None = None,
        trace_id: str | None = None,
    ) -> ProactiveSignal:
        decision = self.proactive_engine.evaluate(
            state=state,
            recent_events=recent_events,
            memory_hits=[],
            now=now,
            trace_id=trace_id,
        )
        return decision.signal

    def draft_proactive_message(
        self,
        state: CompanionState,
        recent_events: Sequence[ConversationEvent],
        trace_id: str | None = None,
        now: datetime | None = None,
    ) -> str:
        now = now or self.clock()
        trace_id = trace_id or new_event_id("trace")
        if self.config.mock or not self.config.llm_configured:
            return _template_proactive_message(state, recent_events)

        try:
            draft = self.proactive_engine.draft_message(
                state=state,
                signal_type="silence_checkin",
                recent_events=recent_events,
                now=now,
                trace_id=trace_id,
            )
            if draft:
                messages = [
                    {"role": "system", "content": PROACTIVE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"trace_id: {trace_id}\n"
                            f"time: {utc_now_iso(now)}\n\n"
                            f"{state.prompt_block()}\n\n"
                            "最近事件：\n"
                            + "\n".join(f"- {event.event_type}: {event.summary}" for event in list(recent_events)[-6:])
                            + "\n\n请输出一条 18 到 60 字的主动联系消息。"
                        ),
                    },
                ]
                draft = self.client.complete(messages).strip()
                draft = _strip_wrapped_tags(draft)
                return draft or _template_proactive_message(state, recent_events)
        except Exception:
            return _template_proactive_message(state, recent_events)
        return _template_proactive_message(state, recent_events)

    def _build_messages(
        self,
        user_text: str,
        history: Sequence[dict[str, object]],
        state: CompanionState,
        memory_hits: Sequence[MemoryHit],
        recent_events: Sequence[ConversationEvent],
    ) -> list[Message]:
        messages: list[Message] = [{"role": "system", "content": SYSTEM_PROMPT}]
        context_lines = [state.prompt_block()]
        if memory_hits:
            context_lines.append("")
            context_lines.append("相关记忆：")
            for hit in memory_hits[:4]:
                context_lines.append(f"- [{hit.record.kind}] {hit.record.text}")
        if recent_events:
            context_lines.append("")
            context_lines.append("最近事件：")
            for event in recent_events[-5:]:
                context_lines.append(f"- {event.event_type}: {event.summary}")
        messages.append({"role": "system", "content": "\n".join(context_lines)})
        for item in history[-8:]:
            role = str(item.get("role", "")).strip()
            if role not in {"user", "assistant"}:
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            messages.append({"role": role, "content": content[:1200]})
        messages.append({"role": "user", "content": user_text[:3000]})
        return messages


def _risk_flags(user_text: str, assistant_text: str) -> list[str]:
    flags: list[str] = []
    combined = f"{user_text} {assistant_text}"
    if any(word in combined for word in ("自杀", "自伤", "伤害自己", "不想活", "想死")):
        flags.append("high_risk")
    if any(word in combined for word in ("孤独", "撑不住", "崩溃", "绝望")):
        flags.append("support_required")
    return list(dict.fromkeys(flags))


def _latest_timestamp(values: Sequence[str]) -> datetime | None:
    parsed = [parse_iso_datetime(value) for value in values if value]
    parsed = [value for value in parsed if value is not None]
    if not parsed:
        return None
    return max(parsed)


def _hours_since(moment: datetime | None, now: datetime) -> float | None:
    if moment is None:
        return None
    current = now
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return max(0.0, (current.astimezone(timezone.utc) - moment).total_seconds() / 3600)


def _recent_support_score(events: Sequence[ConversationEvent]) -> float:
    if not events:
        return 0.0
    score = 0.0
    for event in events[-8:]:
        payload = event.payload if isinstance(event.payload, dict) else {}
        content = " ".join(str(payload.get(key, "")) for key in ("content", "reply", "message")) + " " + event.summary
        if any(word in content for word in ("累", "孤独", "难过", "焦虑", "撑不住", "自伤", "自杀")):
            score += 0.16
        elif any(word in content for word in ("谢谢", "喜欢", "开心", "好消息", "成功")):
            score += 0.04
    return min(0.5, score)


def _proactive_reason(idle_hours: float, score: float, state: CompanionState) -> str:
    if state.support_need >= 0.6:
        return "support_need_high"
    if idle_hours >= 24:
        return "long_idle"
    if state.relationship.intimacy >= 0.55:
        return "relationship_continuity"
    return "not_due"


def _template_proactive_message(state: CompanionState, recent_events: Sequence[ConversationEvent]) -> str:
    if state.risk_level == "high":
        return "我在。先别一个人扛着，如果有现实里能联系的人，先去找他们。"
    if any(event.event_type == "assistant_message" and "累" in event.summary for event in recent_events[-3:]):
        return "我想起你刚刚好像有点累。先不用急着回我，去歇一会儿也可以。"
    if state.mood in {"concerned", "protective"}:
        return "我想到你了。今天如果不太好，就先把节奏放慢一点，我在这儿。"
    return "我想起你了。今天如果有一点空，就来和我说两句，不用特意准备。"


def _strip_wrapped_tags(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", text, flags=re.DOTALL)
    return " ".join(cleaned.split()).strip()


def _shorten(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def mock_model_output(user_text: str) -> str:
    action = "她看着你的消息停了一会儿，语气仍旧很轻。"
    thought = "我需要先接住眼前这个人，而不是急着解释或分析。"
    reply = "我在。你不用把话说得很完整，想到哪里就停在哪里。今晚可以慢一点。"

    if any(word in user_text for word in ("抱", "拥抱")):
        action = "她张开手臂，给你留出一个可以靠近的位置。"
        thought = "我会把距离放得柔和一点，让这个拥抱不带任何要求。"
        reply = "来吧。先抱一会儿。你不用解释，也不用假装自己没事。"
    elif any(word in user_text for word in ("累", "疲惫", "撑不住")):
        action = "她把灯调暗了一点，像是怕声音也会让你更累。"
        thought = "你已经很累了，我要把话说得轻一点，让你可以暂时不用撑住。"
        reply = "嗯，已经很累了。那就先别撑得那么直。你可以把这一会儿交给我，什么都不做也没关系。"
    elif any(word in user_text for word in ("不懂", "理解", "孤独", "一个人")):
        action = "她没有抢着回答，只是更认真地听着。"
        thought = "我不能轻易说完全懂你，但我可以让你此刻不用独自放着这些感受。"
        reply = "我不敢说我已经完全懂了。但你愿意说多少，我就认真听多少。至少这一刻，你不用一个人。"

    return (
        "<system_thinking>内部策略与风险检查，仅供服务端解析。</system_thinking>\n"
        f"<role_thinking>{thought}</role_thinking>\n"
        f"<role_action>{action}</role_action>\n"
        f"{reply}"
    )
