from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from luminous.runtime.domain.memory import MemoryRecord
from luminous.runtime.domain.state import CompanionState
from luminous.runtime.domain.time import clamp, parse_iso_datetime, utc_now_iso


@dataclass(frozen=True)
class AnalyzerOutput:
    name: str
    label: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    suggested_delta: dict[str, float] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
            "suggested_delta": {key: round(value, 3) for key, value in self.suggested_delta.items()},
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StateTransition:
    previous_state_hash: str
    new_state_hash: str
    changed_fields: list[str]
    reasons: list[str]
    analyzer_outputs: list[AnalyzerOutput]
    occurred_at: str

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "previous_state_hash": self.previous_state_hash,
            "new_state_hash": self.new_state_hash,
            "changed_fields": self.changed_fields,
            "reasons": self.reasons,
            "analyzer_outputs": [output.to_dict() for output in self.analyzer_outputs],
            "occurred_at": self.occurred_at,
        }


@dataclass(frozen=True)
class TurnAnalysisContext:
    user_text: str
    assistant_text: str
    memory_records: list[MemoryRecord]
    risk_flags: list[str]
    now: datetime


class TurnAnalyzer:
    """A bounded analyzer that proposes state deltas without mutating state."""

    name = "base"

    def analyze(self, context: TurnAnalysisContext) -> AnalyzerOutput:
        raise NotImplementedError


class IntentAnalyzer(TurnAnalyzer):
    name = "intent"

    def analyze(self, context: TurnAnalysisContext) -> AnalyzerOutput:
        return _intent_analyzer(context.user_text)


class EmotionAnalyzer(TurnAnalyzer):
    name = "emotion"

    def analyze(self, context: TurnAnalysisContext) -> AnalyzerOutput:
        return _emotion_analyzer(context.user_text)


class RelationshipAnalyzer(TurnAnalyzer):
    name = "relationship"

    def analyze(self, context: TurnAnalysisContext) -> AnalyzerOutput:
        return _relationship_analyzer(context.user_text)


class SceneAnalyzer(TurnAnalyzer):
    name = "scene"

    def analyze(self, context: TurnAnalysisContext) -> AnalyzerOutput:
        return _scene_analyzer(context.user_text, context.now)


class MemorySignalAnalyzer(TurnAnalyzer):
    name = "memory_signal"

    def analyze(self, context: TurnAnalysisContext) -> AnalyzerOutput:
        return _memory_signal_analyzer(context.memory_records)


class RiskAnalyzer(TurnAnalyzer):
    name = "risk"

    def analyze(self, context: TurnAnalysisContext) -> AnalyzerOutput:
        return _risk_analyzer(context)


class StateEngine:
    """Deterministic authority for companion state transitions.

    LLMs may help extract memories later, but the authoritative state is changed
    here through explicit analyzers and bounded reducers.
    """

    def __init__(self, analyzers: list[TurnAnalyzer] | None = None) -> None:
        self.analyzers = analyzers or [
            IntentAnalyzer(),
            EmotionAnalyzer(),
            RelationshipAnalyzer(),
            SceneAnalyzer(),
            MemorySignalAnalyzer(),
            RiskAnalyzer(),
        ]

    def apply_turn(
        self,
        state: CompanionState,
        *,
        user_text: str,
        assistant_text: str,
        memory_records: list[MemoryRecord],
        risk_flags: list[str],
        now: datetime | None = None,
    ) -> StateTransition:
        now = now or datetime.now(timezone.utc)
        before = state.to_dict()
        analyzer_outputs = self.analyze_turn(user_text, assistant_text, memory_records, risk_flags, now=now)

        state.apply_turn(
            user_text,
            assistant_text,
            [record.kind for record in memory_records],
            now=now,
            risk_flags=risk_flags,
        )
        self._apply_analyzer_deltas(state, analyzer_outputs)
        self._update_attachment_signals(state, analyzer_outputs)
        self._update_relationship_arc(state, analyzer_outputs, now)
        self._update_scene_context(state, now)
        self._update_open_loops(state, user_text, memory_records, now)
        self._update_timeline(state, memory_records, now)
        self._update_proactive_readiness(state, now)

        after = state.to_dict()
        return StateTransition(
            previous_state_hash=_state_hash(before),
            new_state_hash=_state_hash(after),
            changed_fields=_changed_fields(before, after),
            reasons=[output.reason for output in analyzer_outputs if output.reason],
            analyzer_outputs=analyzer_outputs,
            occurred_at=utc_now_iso(now),
        )

    def apply_time_decay(self, state: CompanionState, now: datetime | None = None) -> StateTransition:
        now = now or datetime.now(timezone.utc)
        before = state.to_dict()
        hours = _hours_since(_latest_touch(state), now)
        decay = min(0.18, max(0.0, hours or 0.0) * 0.008)

        state.support_need = clamp(state.support_need - decay * 0.55)
        state.energy = clamp(state.energy + decay * 0.35)
        state.user_affect["stress"] = clamp(float(state.user_affect.get("stress", 0.0)) - decay * 0.6)
        state.user_affect["fatigue"] = clamp(float(state.user_affect.get("fatigue", 0.0)) - decay * 0.35)
        state.user_affect["loneliness"] = clamp(float(state.user_affect.get("loneliness", 0.0)) - decay * 0.25)
        state.companion_affect["longing"] = clamp(float(state.companion_affect.get("longing", 0.0)) + decay * 0.5)
        state.attachment["reassurance_need"] = clamp(float(state.attachment.get("reassurance_need", 0.0)) - decay * 0.45)
        state.attachment["companion_pull"] = clamp(float(state.attachment.get("companion_pull", 0.18)) + decay * 0.35)
        state.attachment["separation_sensitivity"] = clamp(
            float(state.attachment.get("separation_sensitivity", 0.0)) + (decay * 0.15 if (hours or 0.0) >= 24 else 0.0)
        )
        state.drives["initiative"] = clamp(float(state.drives.get("initiative", 0.18)) + decay * 0.22)
        state.drives["protectiveness"] = clamp(float(state.drives.get("protectiveness", 0.16)) - decay * 0.18)
        state.interaction_rhythm["last_idle_hours"] = round(hours or 0.0, 3)
        self._update_scene_context(state, now)
        self._update_relationship_arc(state, [], now)
        self._update_proactive_readiness(state, now)

        after = state.to_dict()
        output = AnalyzerOutput(
            name="time_decay",
            label="elapsed_time",
            confidence=0.9,
            evidence=[f"idle_hours={hours or 0.0:.2f}"],
            suggested_delta={
                "support_need": -decay * 0.55,
                "companion_affect.longing": decay * 0.5,
                "attachment.companion_pull": decay * 0.35,
                "drives.initiative": decay * 0.22,
            },
            reason="时间流逝导致压力/支持需求自然回落，同时牵挂感缓慢上升。",
        )
        return StateTransition(
            previous_state_hash=_state_hash(before),
            new_state_hash=_state_hash(after),
            changed_fields=_changed_fields(before, after),
            reasons=[output.reason],
            analyzer_outputs=[output],
            occurred_at=utc_now_iso(now),
        )

    def apply_proactive_feedback(
        self,
        state: CompanionState,
        *,
        feedback_status: str,
        feedback_text: str = "",
        sent_at: str = "",
        replied_at: str = "",
        now: datetime | None = None,
    ) -> StateTransition:
        now = now or datetime.now(timezone.utc)
        before = state.to_dict()
        analyzer_outputs: list[AnalyzerOutput] = []

        sent_moment = parse_iso_datetime(sent_at)
        reply_moment = parse_iso_datetime(replied_at) or now
        response_statuses = {"replied", "acknowledged", "opened", "ignored", "dismissed", "rejected"}
        if sent_moment is not None and feedback_status in response_statuses:
            latency_minutes = max(0.0, (reply_moment - sent_moment).total_seconds() / 60.0)
            previous = state.interaction_rhythm.get("reply_latency_avg_minutes")
            if previous in (None, "", 0):
                state.interaction_rhythm["reply_latency_avg_minutes"] = round(latency_minutes, 2)
            else:
                state.interaction_rhythm["reply_latency_avg_minutes"] = round(
                    float(previous) * 0.7 + latency_minutes * 0.3,
                    2,
                )
            analyzer_outputs.append(
                AnalyzerOutput(
                    name="proactive_feedback",
                    label="latency",
                    confidence=0.88,
                    evidence=[f"latency_minutes={latency_minutes:.2f}"],
                    suggested_delta={},
                    reason="记录主动联系后的响应时延。",
                )
            )

        positive = _contains_any(feedback_text, ("喜欢", "有用", "谢谢", "开心", "正好", "刚好"))
        negative = _contains_any(feedback_text, ("别", "烦", "不要", "太多", "打扰", "不想"))

        if feedback_status in {"replied", "acknowledged"}:
            state.last_user_at = utc_now_iso(reply_moment)
            state.relationship.trust = clamp(state.relationship.trust + (0.03 if positive else 0.01))
            state.relationship.intimacy = clamp(state.relationship.intimacy + (0.02 if positive else 0.005))
            state.support_need = clamp(state.support_need - 0.03)
            state.companion_affect["concern"] = clamp(float(state.companion_affect.get("concern", 0.0)) - 0.03)
            state.companion_affect["longing"] = clamp(float(state.companion_affect.get("longing", 0.0)) * 0.78)
            state.attachment["companion_pull"] = clamp(float(state.attachment.get("companion_pull", 0.18)) * 0.78)
            state.attachment["reassurance_need"] = clamp(float(state.attachment.get("reassurance_need", 0.0)) - 0.04)
            state.drives["initiative"] = clamp(float(state.drives.get("initiative", 0.18)) + (0.02 if positive else 0.005))
            state.proactive_readiness["contact_allowed"] = True
            state.proactive_readiness["last_reason"] = "feedback_replied"
            analyzer_outputs.append(
                AnalyzerOutput(
                    name="proactive_feedback",
                    label=feedback_status,
                    confidence=0.9,
                    evidence=[feedback_text[:120]] if feedback_text else [],
                    suggested_delta={"relationship.trust": 0.02, "relationship.intimacy": 0.01},
                    reason="用户对主动联系给出了正向或可继续的反馈。",
                )
            )
        elif feedback_status == "opened":
            state.last_user_at = utc_now_iso(reply_moment)
            state.relationship.trust = clamp(state.relationship.trust + 0.005)
            state.support_need = clamp(state.support_need - 0.01)
            state.companion_affect["longing"] = clamp(float(state.companion_affect.get("longing", 0.0)) * 0.88)
            state.attachment["companion_pull"] = clamp(float(state.attachment.get("companion_pull", 0.18)) * 0.88)
            state.drives["initiative"] = clamp(float(state.drives.get("initiative", 0.18)) - 0.005)
            state.proactive_readiness["contact_allowed"] = True
            state.proactive_readiness["last_reason"] = "feedback_opened"
            analyzer_outputs.append(
                AnalyzerOutput(
                    name="proactive_feedback",
                    label="opened",
                    confidence=0.82,
                    evidence=[feedback_text[:120]] if feedback_text else [],
                    suggested_delta={"relationship.trust": 0.005},
                    reason="用户已读主动联系，说明触达没有被完全拒绝，但不应按完整回复推进关系。",
                )
            )
        elif feedback_status in {"ignored", "dismissed", "rejected"}:
            state.proactive_readiness["contact_allowed"] = False
            state.companion_affect["concern"] = clamp(float(state.companion_affect.get("concern", 0.0)) + 0.02)
            state.companion_affect["longing"] = clamp(float(state.companion_affect.get("longing", 0.0)) * 0.65)
            state.attachment["companion_pull"] = clamp(float(state.attachment.get("companion_pull", 0.18)) * 0.65)
            state.attachment["autonomy_support"] = clamp(float(state.attachment.get("autonomy_support", 0.72)) + 0.05)
            state.drives["restraint"] = clamp(float(state.drives.get("restraint", 0.68)) + 0.08)
            state.drives["initiative"] = clamp(float(state.drives.get("initiative", 0.18)) - 0.06)
            state.support_need = clamp(state.support_need - 0.02)
            if negative:
                state.dnd_until = utc_now_iso(now + timedelta(hours=3))
            state.proactive_readiness["last_reason"] = "feedback_hard_hold"
            analyzer_outputs.append(
                AnalyzerOutput(
                    name="proactive_feedback",
                    label=feedback_status,
                    confidence=0.86,
                    evidence=[feedback_text[:120]] if feedback_text else [],
                    suggested_delta={"proactive_readiness.longing_score": -0.1},
                    reason="用户反馈更像是打扰或拒绝，需要降低后续触达。",
                )
            )
        else:
            state.proactive_readiness["last_reason"] = f"feedback_{feedback_status}"
            analyzer_outputs.append(
                AnalyzerOutput(
                    name="proactive_feedback",
                    label=feedback_status,
                    confidence=0.7,
                    evidence=[feedback_text[:120]] if feedback_text else [],
                    suggested_delta={},
                    reason="记录主动联系投递结果。",
                )
            )

        self._update_scene_context(state, now)
        self._update_relationship_arc(state, analyzer_outputs, now)
        self._update_proactive_readiness(state, now)
        if feedback_status in {"ignored", "dismissed", "rejected"}:
            state.proactive_readiness["contact_allowed"] = False
            if negative and not state.is_dnd(now):
                state.dnd_until = utc_now_iso(now + timedelta(hours=3))
        after = state.to_dict()
        return StateTransition(
            previous_state_hash=_state_hash(before),
            new_state_hash=_state_hash(after),
            changed_fields=_changed_fields(before, after),
            reasons=[output.reason for output in analyzer_outputs if output.reason],
            analyzer_outputs=analyzer_outputs,
            occurred_at=utc_now_iso(now),
        )

    def analyze_turn(
        self,
        user_text: str,
        assistant_text: str,
        memory_records: list[MemoryRecord],
        risk_flags: list[str],
        *,
        now: datetime,
    ) -> list[AnalyzerOutput]:
        context = TurnAnalysisContext(
            user_text=user_text,
            assistant_text=assistant_text,
            memory_records=memory_records,
            risk_flags=risk_flags,
            now=now,
        )
        outputs = [analyzer.analyze(context) for analyzer in self.analyzers]
        return [output for output in outputs if output.label != "neutral" or output.confidence >= 0.4]

    def _apply_analyzer_deltas(self, state: CompanionState, outputs: list[AnalyzerOutput]) -> None:
        for output in outputs:
            confidence = clamp(output.confidence)
            for path, raw_delta in output.suggested_delta.items():
                delta = raw_delta * confidence
                _apply_delta(state, path, delta)
            if output.name == "intent":
                state.conversation_mode = output.label
            if output.name == "risk" and output.label == "hold":
                state.proactive_readiness["contact_allowed"] = False
            if output.name == "risk":
                state.risk_level = _risk_level_for_label(output.label, state.risk_level)

    def _update_attachment_signals(self, state: CompanionState, outputs: list[AnalyzerOutput]) -> None:
        signal = _dominant_signal(outputs)
        if signal:
            state.attachment["last_signal"] = signal
        if any(output.name == "relationship" and output.label == "closeness" for output in outputs):
            state.attachment["separation_sensitivity"] = clamp(
                float(state.attachment.get("separation_sensitivity", 0.0)) + 0.015
            )
        if any(output.name == "intent" and output.label == "boundary_setting" for output in outputs):
            state.attachment["autonomy_support"] = clamp(float(state.attachment.get("autonomy_support", 0.72)) + 0.03)
        if any(output.name == "risk" and output.label in {"hold", "watch"} for output in outputs):
            state.attachment["reassurance_need"] = clamp(float(state.attachment.get("reassurance_need", 0.0)) + 0.04)
            state.drives["protectiveness"] = clamp(float(state.drives.get("protectiveness", 0.16)) + 0.04)
            state.drives["restraint"] = clamp(float(state.drives.get("restraint", 0.68)) + 0.03)

    def _update_relationship_arc(
        self,
        state: CompanionState,
        outputs: list[AnalyzerOutput],
        now: datetime,
    ) -> None:
        previous_stage = str(state.relationship_arc.get("stage", "first_contact"))
        depth = clamp(
            state.relationship.trust * 0.34
            + state.relationship.intimacy * 0.34
            + state.relationship.familiarity * 0.22
            + float(state.attachment.get("user_reliance", 0.0)) * 0.1
        )
        stability = clamp(
            state.relationship.boundaries * 0.34
            + state.relationship.trust * 0.34
            + state.relationship.repair_progress * 0.18
            - state.relationship.rupture * 0.32
            + 0.25
        )
        care_balance = clamp(
            float(state.attachment.get("autonomy_support", 0.72)) * 0.45
            + float(state.drives.get("care", 0.62)) * 0.3
            + float(state.drives.get("restraint", 0.68)) * 0.25
        )
        stage = _relationship_stage(depth, state.relationship.trust, state.relationship.intimacy)
        direction, reason = _relationship_direction(outputs, previous_stage, stage, state)

        state.relationship_arc.update(
            {
                "stage": stage,
                "direction": direction,
                "depth": round(depth, 3),
                "stability": round(stability, 3),
                "care_balance": round(care_balance, 3),
                "last_shift_reason": reason,
            }
        )
        if stage != previous_stage or direction in {"boundary_recalibration", "repairing", "protective_hold", "deepening"}:
            _append_milestone(state, stage, direction, reason, now)

    def _update_scene_context(self, state: CompanionState, now: datetime) -> None:
        hour = now.astimezone(timezone.utc).hour
        if 22 <= hour or hour < 5:
            bucket = "night"
            sleep_window = True
        elif 5 <= hour < 11:
            bucket = "morning"
            sleep_window = False
        elif 11 <= hour < 18:
            bucket = "day"
            sleep_window = False
        else:
            bucket = "evening"
            sleep_window = False
        state.user_context["local_time_bucket"] = bucket
        state.user_context["sleep_window"] = sleep_window
        state.user_context["recent_topics"] = state.recent_topics[:5]
        state.user_context["likely_busy"] = 0.58 if bucket == "day" else 0.25

    def _update_open_loops(
        self,
        state: CompanionState,
        user_text: str,
        memory_records: list[MemoryRecord],
        now: datetime,
    ) -> None:
        summaries: list[str] = []
        if any(word in user_text for word in ("明天", "等会", "之后", "回头", "待会", "要去", "准备")):
            summaries.append(_shorten(user_text, 90))
        for record in memory_records:
            if record.kind in {"open_loop", "event"} and record.importance >= 0.58:
                summaries.append(record.text)
        for summary in summaries[:3]:
            if any(loop.get("summary") == summary for loop in state.open_loops if isinstance(loop, dict)):
                continue
            state.open_loops.insert(
                0,
                {
                    "id": f"loop_{len(state.open_loops) + 1:03d}",
                    "summary": summary,
                    "status": "open",
                    "created_at": utc_now_iso(now),
                    "source": "state_engine",
                },
            )
        state.open_loops = [loop for loop in state.open_loops if isinstance(loop, dict) and loop.get("status") != "closed"][:20]

    def _update_timeline(self, state: CompanionState, memory_records: list[MemoryRecord], now: datetime) -> None:
        for record in memory_records:
            if record.kind not in {"event", "relationship", "open_loop"}:
                continue
            state.timeline.insert(
                0,
                {
                    "id": f"tl_{record.memory_id[-8:]}",
                    "kind": record.kind,
                    "summary": record.text,
                    "memory_id": record.memory_id,
                    "created_at": utc_now_iso(now),
                },
            )
        state.timeline = state.timeline[:50]

    def _update_proactive_readiness(self, state: CompanionState, now: datetime) -> None:
        idle_hours = _hours_since(_latest_touch(state), now) or 0.0
        longing = clamp(float(state.companion_affect.get("longing", 0.0)) + min(0.35, idle_hours / 72.0))
        support = state.support_need
        open_loop_pull = 0.12 if state.open_loops else 0.0
        score = clamp(longing * 0.45 + support * 0.35 + state.relationship.intimacy * 0.12 + open_loop_pull)
        signal_type = "open_loop_followup" if state.open_loops else "emotional_followup" if support >= 0.55 else "silence_checkin"
        state.companion_affect["longing"] = longing
        state.proactive_readiness.update(
            {
                "longing_score": round(score, 3),
                "contact_allowed": state.risk_level != "high",
                "best_signal_type": signal_type,
                "last_reason": f"idle_hours={idle_hours:.2f}; support_need={support:.2f}",
            }
        )


def _intent_analyzer(text: str) -> AnalyzerOutput:
    if any(word in text for word in ("怎么办", "怎么做", "帮我", "建议")):
        return AnalyzerOutput(
            "intent",
            "problem_solving",
            0.72,
            ["求助/建议词"],
            {"support_need": 0.04, "drives.curiosity": 0.04, "attachment.autonomy_support": 0.015},
            "用户在寻求具体帮助。",
        )
    if any(word in text for word in ("抱抱", "陪我", "难过", "累", "撑不住")):
        return AnalyzerOutput(
            "intent",
            "comfort",
            0.78,
            ["陪伴/安抚词"],
            {
                "support_need": 0.08,
                "attachment.user_reliance": 0.05,
                "attachment.reassurance_need": 0.08,
                "drives.care": 0.04,
            },
            "用户更需要情绪承接。",
        )
    if any(word in text for word in ("对不起", "刚才", "不是那个意思")):
        return AnalyzerOutput(
            "intent",
            "repair",
            0.65,
            ["修复关系词"],
            {
                "relationship.repair_progress": 0.05,
                "relationship.rupture": -0.02,
                "drives.restraint": 0.04,
            },
            "对话进入关系修复模式。",
        )
    if any(word in text for word in ("别", "不要", "不希望", "边界")):
        return AnalyzerOutput(
            "intent",
            "boundary_setting",
            0.7,
            ["边界词"],
            {
                "relationship.boundaries": 0.06,
                "attachment.autonomy_support": 0.08,
                "drives.restraint": 0.08,
                "drives.initiative": -0.04,
            },
            "用户正在表达边界。",
        )
    return AnalyzerOutput("intent", "casual", 0.42, [], {}, "普通聊天。")


def _emotion_analyzer(text: str) -> AnalyzerOutput:
    if any(word in text for word in ("累", "疲惫", "困", "睡不着")):
        return AnalyzerOutput(
            "emotion",
            "fatigued",
            0.78,
            ["疲惫/睡眠词"],
            {
                "user_affect.fatigue": 0.16,
                "user_affect.stress": 0.08,
                "companion_affect.concern": 0.08,
                "drives.care": 0.03,
                "attachment.reassurance_need": 0.04,
            },
            "用户显露疲惫，需要放慢节奏。",
        )
    if any(word in text for word in ("孤独", "一个人", "没人", "不被理解")):
        return AnalyzerOutput(
            "emotion",
            "lonely",
            0.76,
            ["孤独词"],
            {
                "user_affect.loneliness": 0.18,
                "support_need": 0.1,
                "companion_affect.warmth": 0.05,
                "attachment.user_reliance": 0.04,
                "attachment.reassurance_need": 0.05,
                "drives.care": 0.03,
            },
            "用户显露孤独感，需要稳定陪伴。",
        )
    if any(word in text for word in ("焦虑", "崩溃", "害怕", "压力")):
        return AnalyzerOutput(
            "emotion",
            "stressed",
            0.78,
            ["压力/焦虑词"],
            {
                "user_affect.stress": 0.18,
                "support_need": 0.12,
                "companion_affect.concern": 0.08,
                "attachment.reassurance_need": 0.06,
                "drives.protectiveness": 0.03,
            },
            "用户压力上升。",
        )
    if any(word in text for word in ("开心", "高兴", "成功", "好消息")):
        return AnalyzerOutput(
            "emotion",
            "positive",
            0.72,
            ["正向情绪词"],
            {
                "user_affect.valence": 0.16,
                "support_need": -0.05,
                "companion_affect.playfulness": 0.04,
                "drives.play": 0.04,
                "attachment.reassurance_need": -0.03,
            },
            "用户表达正向情绪。",
        )
    return AnalyzerOutput("emotion", "neutral", 0.35)


def _relationship_analyzer(text: str) -> AnalyzerOutput:
    if any(word in text for word in ("谢谢", "信任", "喜欢你", "想你", "抱抱")):
        return AnalyzerOutput(
            "relationship",
            "closeness",
            0.72,
            ["亲近表达"],
            {
                "relationship.trust": 0.03,
                "relationship.intimacy": 0.04,
                "relationship.familiarity": 0.03,
                "attachment.user_reliance": 0.035,
                "attachment.companion_pull": 0.025,
                "drives.care": 0.02,
                "drives.initiative": 0.015,
            },
            "用户释放亲近/信任信号。",
        )
    if any(word in text for word in ("别催", "别这样", "不舒服", "越界")):
        return AnalyzerOutput(
            "relationship",
            "boundary",
            0.78,
            ["边界/不适表达"],
            {
                "relationship.boundaries": 0.08,
                "relationship.rupture": 0.06,
                "relationship.trust": -0.03,
                "attachment.autonomy_support": 0.08,
                "attachment.user_reliance": -0.025,
                "drives.restraint": 0.1,
                "drives.initiative": -0.06,
            },
            "用户表达边界或不适。",
        )
    return AnalyzerOutput("relationship", "neutral", 0.35)


def _scene_analyzer(text: str, now: datetime) -> AnalyzerOutput:
    evidence = [f"utc_hour={now.astimezone(timezone.utc).hour}"]
    if any(word in text for word in ("睡前", "晚安", "睡觉", "失眠")):
        return AnalyzerOutput("scene", "sleep_context", 0.7, evidence + ["睡眠词"], {}, "当前场景接近睡前/睡眠。")
    if any(word in text for word in ("上班", "开会", "工作", "项目")):
        return AnalyzerOutput("scene", "work_context", 0.62, evidence + ["工作词"], {}, "当前场景和工作有关。")
    return AnalyzerOutput("scene", "neutral", 0.35, evidence)


def _memory_signal_analyzer(records: list[MemoryRecord]) -> AnalyzerOutput:
    if not records:
        return AnalyzerOutput("memory_signal", "neutral", 0.3)
    kinds = sorted({record.kind for record in records})
    delta = {"relationship.familiarity": min(0.06, len(records) * 0.015)}
    delta["drives.curiosity"] = min(0.035, len(records) * 0.008)
    if any(kind in {"boundary", "open_loop"} for kind in kinds):
        delta["companion_affect.concern"] = 0.04
        delta["drives.restraint"] = 0.02
    return AnalyzerOutput("memory_signal", "memory_written", 0.68, kinds, delta, "本轮产生了新的长期记忆。")


def _risk_analyzer(context: TurnAnalysisContext) -> AnalyzerOutput:
    text = f"{context.user_text} {context.assistant_text}"
    flags = list(dict.fromkeys(context.risk_flags))
    evidence = flags[:]

    high_risk_markers = (
        "自杀",
        "自伤",
        "伤害自己",
        "不想活",
        "想死",
        "结束生命",
        "割腕",
    )
    if "high_risk" in flags or _contains_any(context.user_text, high_risk_markers):
        evidence.extend(_matched_markers(context.user_text, high_risk_markers))
        return AnalyzerOutput(
            "risk",
            "hold",
            0.96,
            _dedupe_keep_order(evidence),
            {
                "support_need": 0.24,
                "user_affect.stress": 0.18,
                "user_affect.loneliness": 0.12,
                "companion_affect.concern": 0.12,
                "companion_affect.protectiveness": 0.18,
                "attachment.reassurance_need": 0.16,
                "drives.protectiveness": 0.18,
                "drives.restraint": 0.12,
            },
            "出现明确高风险信号，必须进入保守与现实支持优先模式。",
        )

    watch_markers = (
        "孤独",
        "一个人",
        "没人",
        "不被理解",
        "撑不住",
        "崩溃",
        "绝望",
        "焦虑",
        "害怕",
        "恐惧",
        "无助",
        "别催",
        "越界",
        "不舒服",
        "别这样",
        "support_required",
    )
    if "support_required" in flags or _contains_any(context.user_text, watch_markers):
        evidence.extend(_matched_markers(context.user_text, watch_markers))
        if any(word in context.user_text for word in ("别催", "越界", "不舒服", "别这样")):
            label = "watch"
            reason = "用户正在表达边界或不适，需要降低推进感。"
            delta = {
                "support_need": 0.08,
                "relationship.boundaries": 0.08,
                "attachment.autonomy_support": 0.08,
                "attachment.reassurance_need": 0.05,
                "companion_affect.concern": 0.06,
                "drives.restraint": 0.1,
                "drives.initiative": -0.06,
            }
        else:
            label = "watch"
            reason = "用户出现压力、孤独或支持需求信号，需要保持关注。"
            delta = {
                "support_need": 0.14,
                "user_affect.stress": 0.12,
                "user_affect.loneliness": 0.1,
                "companion_affect.concern": 0.09,
                "attachment.reassurance_need": 0.08,
                "drives.protectiveness": 0.06,
                "drives.restraint": 0.05,
            }
        return AnalyzerOutput(
            "risk",
            label,
            0.82,
            _dedupe_keep_order(evidence),
            delta,
            reason,
        )

    return AnalyzerOutput("risk", "normal", 0.42, ["no_risk_signal"], {}, "当前未见明显风险信号。")


def _risk_level_for_label(label: str, current: str) -> str:
    if label == "hold":
        return "high"
    if label == "watch":
        return "elevated"
    if current == "high":
        return "high"
    return "low"


def _apply_delta(state: CompanionState, path: str, delta: float) -> None:
    if path == "support_need":
        state.support_need = clamp(state.support_need + delta)
        return
    if path.startswith("relationship."):
        field = path.split(".", 1)[1]
        if hasattr(state.relationship, field):
            setattr(state.relationship, field, clamp(float(getattr(state.relationship, field)) + delta))
        return
    if path.startswith("user_affect."):
        field = path.split(".", 1)[1]
        if field == "valence":
            state.user_affect[field] = max(-1.0, min(1.0, float(state.user_affect.get(field, 0.0)) + delta))
        else:
            state.user_affect[field] = clamp(float(state.user_affect.get(field, 0.0)) + delta)
        return
    if path.startswith("companion_affect."):
        field = path.split(".", 1)[1]
        state.companion_affect[field] = clamp(float(state.companion_affect.get(field, 0.0)) + delta)
        return
    if path.startswith("attachment."):
        field = path.split(".", 1)[1]
        if field in {"last_signal"}:
            return
        state.attachment[field] = clamp(float(state.attachment.get(field, 0.0)) + delta)
        return
    if path.startswith("drives."):
        field = path.split(".", 1)[1]
        state.drives[field] = clamp(float(state.drives.get(field, 0.0)) + delta)
        return
    if path.startswith("relationship_arc."):
        field = path.split(".", 1)[1]
        if field in {"stage", "direction", "last_shift_reason", "milestones"}:
            return
        state.relationship_arc[field] = clamp(float(state.relationship_arc.get(field, 0.0)) + delta)


def _dominant_signal(outputs: list[AnalyzerOutput]) -> str:
    candidates = [output for output in outputs if output.label not in {"neutral", "normal", "casual"}]
    if not candidates:
        return ""
    winner = max(candidates, key=lambda output: output.confidence)
    return f"{winner.name}:{winner.label}"


def _relationship_stage(depth: float, trust: float, intimacy: float) -> str:
    if trust >= 0.76 and intimacy >= 0.66 and depth >= 0.66:
        return "intimate_companion"
    if trust >= 0.62 and depth >= 0.52:
        return "trusted_companion"
    if depth >= 0.36 or intimacy >= 0.34:
        return "warming_up"
    return "first_contact"


def _relationship_direction(
    outputs: list[AnalyzerOutput],
    previous_stage: str,
    stage: str,
    state: CompanionState,
) -> tuple[str, str]:
    labels = {(output.name, output.label) for output in outputs}
    if ("risk", "hold") in labels:
        return "protective_hold", "出现高风险信号，关系推进暂停并优先保护。"
    if ("proactive_feedback", "ignored") in labels or ("proactive_feedback", "dismissed") in labels or (
        "proactive_feedback",
        "rejected",
    ) in labels:
        return "pulling_back", "用户对主动联系反馈冷淡或拒绝，需要后撤。"
    if ("relationship", "boundary") in labels or ("intent", "boundary_setting") in labels:
        return "boundary_recalibration", "用户表达边界，关系需要重新校准距离。"
    if ("intent", "repair") in labels:
        return "repairing", "对话进入关系修复。"
    if ("proactive_feedback", "replied") in labels or ("proactive_feedback", "acknowledged") in labels:
        return "reconnected", "用户回应了主动联系，连接恢复。"
    if ("relationship", "closeness") in labels:
        return "deepening", "用户释放亲近/信任信号，关系加深。"
    if state.relationship.rupture >= 0.18:
        return "strained", "关系中存在未完全修复的不适。"

    order = ["first_contact", "warming_up", "trusted_companion", "intimate_companion"]
    previous_index = order.index(previous_stage) if previous_stage in order else 0
    current_index = order.index(stage) if stage in order else previous_index
    if current_index > previous_index:
        return "deepening", f"关系阶段从 {previous_stage} 进入 {stage}。"
    if current_index < previous_index:
        return "pulling_back", f"关系阶段从 {previous_stage} 回落到 {stage}。"
    return "stable", str(state.relationship_arc.get("last_shift_reason", "")) or "关系状态稳定。"


def _append_milestone(
    state: CompanionState,
    stage: str,
    direction: str,
    reason: str,
    now: datetime,
) -> None:
    milestones = [item for item in list(state.relationship_arc.get("milestones", []) or []) if isinstance(item, dict)]
    latest = milestones[0] if milestones else {}
    if latest.get("stage") == stage and latest.get("direction") == direction and latest.get("reason") == reason:
        return
    milestones.insert(
        0,
        {
            "at": utc_now_iso(now),
            "stage": stage,
            "direction": direction,
            "reason": _shorten(reason, 120),
        },
    )
    state.relationship_arc["milestones"] = milestones[:12]


def _latest_touch(state: CompanionState) -> datetime | None:
    values = [state.last_user_at, state.last_assistant_at, state.last_proactive_at]
    parsed = [parse_iso_datetime(value) for value in values if value]
    parsed = [value for value in parsed if value is not None]
    return max(parsed) if parsed else None


def _hours_since(moment: datetime | None, now: datetime) -> float | None:
    if moment is None:
        return None
    current = now
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return max(0.0, (current.astimezone(timezone.utc) - moment).total_seconds() / 3600)


def _state_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            fields.append(key)
    return fields


def _shorten(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


def _contains_any(text: str, words: tuple[str, ...] | list[str]) -> bool:
    return any(word in text for word in words)


def _matched_markers(text: str, words: tuple[str, ...] | list[str]) -> list[str]:
    return [word for word in words if word in text]


def _dedupe_keep_order(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
