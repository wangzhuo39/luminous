from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any, Sequence

from luminous.runtime.domain.events import ConversationEvent, ProactiveSignal, new_event_id
from luminous.runtime.domain.memory import MemoryHit
from luminous.runtime.domain.state import CompanionState
from luminous.runtime.domain.time import parse_iso_datetime, utc_now_iso


@dataclass(frozen=True)
class UserAvailabilityEstimate:
    label: str
    busy_probability: float
    sleep_probability: float
    available_probability: float
    support_probability: float
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "busy_probability": round(self.busy_probability, 3),
            "sleep_probability": round(self.sleep_probability, 3),
            "available_probability": round(self.available_probability, 3),
            "support_probability": round(self.support_probability, 3),
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence[:8],
        }


@dataclass(frozen=True)
class ProactiveDecision:
    signal: ProactiveSignal
    hold_reasons: list[str] = field(default_factory=list)
    anchor_memory_ids: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)
    availability: UserAvailabilityEstimate | None = None

    def to_trace_dict(self) -> dict[str, Any]:
        return {
            "signal": self.signal.to_dict(),
            "hold_reasons": self.hold_reasons,
            "anchor_memory_ids": self.anchor_memory_ids,
            "evidence": self.evidence,
            "components": {key: round(value, 3) for key, value in self.components.items()},
            "availability": self.availability.to_dict() if self.availability else {},
        }


class ProactiveEngine:
    def evaluate(
        self,
        *,
        state: CompanionState,
        recent_events: Sequence[ConversationEvent],
        memory_hits: Sequence[MemoryHit] | None = None,
        now: datetime | None = None,
        trace_id: str | None = None,
    ) -> ProactiveDecision:
        now = now or datetime.now(timezone.utc)
        trace_id = trace_id or new_event_id("trace")
        memory_hits = list(memory_hits or [])
        hold_reasons: list[str] = []

        if state.is_dnd(now):
            hold_reasons.append("dnd")
        if _quiet_hours(now):
            hold_reasons.append("quiet_hours")
        if _recent_proactive_cooldown(state, now) < 6.0:
            hold_reasons.append("cooldown")
        if state.risk_level == "high":
            hold_reasons.append("high_risk")

        anchor_memory_ids = [hit.record.memory_id for hit in memory_hits[:3]]
        support = state.support_need
        relationship = state.relationship
        idle_hours = _idle_hours(state, now)
        longing = float(state.companion_affect.get("longing", 0.0))
        open_loop_pull = min(0.22, len(state.open_loops) * 0.05)
        recent_support = _recent_support_score(recent_events)
        availability = _estimate_user_availability(state, recent_events, now=now, recent_support=recent_support)
        support_urgency = max(support, recent_support, availability.support_probability)
        if availability.sleep_probability >= 0.82 and support_urgency < 0.68 and "quiet_hours" not in hold_reasons:
            hold_reasons.append("likely_sleeping")
        if availability.busy_probability >= 0.72 and support_urgency < 0.58 and idle_hours < 24:
            hold_reasons.append("likely_busy")
        opportunity = 1.0 - math.exp(-max(0.0, idle_hours) / 12.0) if idle_hours else 0.0
        relationship_permission = (
            relationship.trust * 0.24
            + relationship.intimacy * 0.36
            + relationship.familiarity * 0.2
            + relationship.boundaries * 0.08
        )
        value = support * 0.3 + longing * 0.2 + open_loop_pull + recent_support
        risk_penalty = 0.55 if "high_risk" in hold_reasons else 0.0
        cooldown_penalty = 0.14 if "cooldown" in hold_reasons else 0.0
        quiet_penalty = 0.24 if "quiet_hours" in hold_reasons else 0.0
        dnd_penalty = 0.4 if "dnd" in hold_reasons else 0.0
        duplicate_penalty = _duplicate_penalty(recent_events)
        busy_penalty = availability.busy_probability * (0.09 if idle_hours < 24 else 0.025)
        sleep_penalty = availability.sleep_probability * (0.13 if support_urgency < 0.68 else 0.045)

        score = (
            opportunity * 0.33
            + relationship_permission * 0.33
            + value * 0.23
            + recent_support * 0.05
            + availability.available_probability * 0.075
            + availability.support_probability * 0.045
            + float(state.proactive_readiness.get("longing_score", 0.0)) * 0.12
            - risk_penalty
            - cooldown_penalty
            - quiet_penalty
            - dnd_penalty
            - duplicate_penalty
            - busy_penalty
            - sleep_penalty
        )
        score = max(0.0, min(1.0, score))

        due_threshold = 0.60 if idle_hours >= 24 else 0.64
        signal_type = _signal_type(state, idle_hours)
        touch_probability = _touch_probability(
            score=score,
            due_threshold=due_threshold,
            opportunity=opportunity,
            value=value,
            relationship_permission=relationship_permission,
            availability=availability,
            idle_hours=idle_hours,
            state=state,
        )
        probability_roll = _deterministic_roll(
            trace_id=trace_id,
            state=state,
            now=now,
            signal_type=signal_type,
            anchor_memory_ids=anchor_memory_ids,
        )
        probability_floor = max(0.36, due_threshold - 0.12)
        sure_threshold = min(0.9, due_threshold + 0.02)
        sure_gate_open = score >= sure_threshold
        probability_gate_open = score >= probability_floor and probability_roll <= touch_probability
        due = not hold_reasons and (sure_gate_open or probability_gate_open)
        draft = ""
        if due:
            draft = _template_message(state, signal_type, recent_events, anchor_memory_ids)
        next_check_minutes = 30 if due else max(30, int((1.0 - touch_probability) * 180 + max(0.0, due_threshold - score) * 120))
        reason = _proactive_reason(
            hold_reasons=hold_reasons,
            due=due,
            sure_gate_open=sure_gate_open,
            probability_gate_open=probability_gate_open,
        )
        signal = ProactiveSignal(
            due=due,
            score=score,
            reason=reason,
            next_check_minutes=next_check_minutes,
            draft_message=draft,
            trace_id=trace_id,
            created_at=utc_now_iso(now),
            signal_type=signal_type,
            anchor_memory_ids=tuple(anchor_memory_ids),
            hold_reasons=tuple(hold_reasons),
        )
        return ProactiveDecision(
            signal=signal,
            hold_reasons=hold_reasons,
            anchor_memory_ids=anchor_memory_ids,
            evidence=[event.summary for event in list(recent_events)[-6:]],
            components={
                "opportunity": opportunity,
                "relationship_permission": relationship_permission,
                "value": value,
                "recent_support": recent_support,
                "idle_hours": idle_hours,
                "score": score,
                "busy_probability": availability.busy_probability,
                "sleep_probability": availability.sleep_probability,
                "available_probability": availability.available_probability,
                "support_probability": availability.support_probability,
                "busy_penalty": busy_penalty,
                "sleep_penalty": sleep_penalty,
                "due_threshold": due_threshold,
                "sure_threshold": sure_threshold,
                "probability_floor": probability_floor,
                "touch_probability": touch_probability,
                "probability_roll": probability_roll,
                "sure_gate_open": 1.0 if sure_gate_open else 0.0,
                "probability_gate_open": 1.0 if probability_gate_open else 0.0,
            },
            availability=availability,
        )

    def draft_message(
        self,
        *,
        state: CompanionState,
        signal_type: str,
        recent_events: Sequence[ConversationEvent],
        memory_hits: Sequence[MemoryHit] | None = None,
        now: datetime | None = None,
        trace_id: str | None = None,
    ) -> str:
        now = now or datetime.now(timezone.utc)
        anchor_memory_ids = [hit.record.memory_id for hit in list(memory_hits or [])[:3]]
        return _template_message(state, signal_type, recent_events, anchor_memory_ids, now=now, trace_id=trace_id)


def _signal_type(state: CompanionState, idle_hours: float) -> str:
    if state.open_loops:
        return "open_loop_followup"
    if state.support_need >= 0.55:
        return "emotional_followup"
    if idle_hours >= 24:
        return "silence_checkin"
    if state.relationship.rupture >= 0.28:
        return "repair_after_rupture"
    return "silence_checkin"


def _template_message(
    state: CompanionState,
    signal_type: str,
    recent_events: Sequence[ConversationEvent],
    anchor_memory_ids: Sequence[str],
    *,
    now: datetime | None = None,
    trace_id: str | None = None,
) -> str:
    trace_id = trace_id or new_event_id("trace")
    now = now or datetime.now(timezone.utc)
    if state.risk_level == "high":
        return "我在。先别一个人扛着，如果现实里有能联系的人，先去找他们。"
    if signal_type == "repair_after_rupture":
        return "我刚刚又想了一下，可能前面那句让你不舒服了。要是你愿意，我想重新来过。"
    if signal_type == "open_loop_followup" and state.open_loops:
        summary = str(state.open_loops[0].get("summary", "")).strip()
        if summary:
            return f"我刚刚想起你之前提过的那件事：{summary[:18]}。有进展了吗？"
    if signal_type == "emotional_followup":
        return "我想到你了。今天如果还是有点重，就先放慢一点，我在。"
    if any(event.event_type == "assistant_message" and "累" in event.summary for event in recent_events[-3:]):
        return "我想起你刚刚好像有点累。先别急着回我，去歇一会儿也可以。"
    if anchor_memory_ids:
        return "我忽然想起一点以前的事，所以来轻轻问你一句：今天还好吗？"
    return f"我想起你了。{trace_id[:6]} 这一刻如果你有空，来和我说两句也行。"


def _idle_hours(state: CompanionState, now: datetime) -> float:
    moments = [state.last_user_at, state.last_assistant_at, state.last_proactive_at]
    parsed = [parse_iso_datetime(value) for value in moments if value]
    parsed = [moment for moment in parsed if moment is not None]
    if not parsed:
        return 0.0
    recent = max(parsed)
    return max(0.0, (now.astimezone(timezone.utc) - recent).total_seconds() / 3600)


def _recent_support_score(events: Sequence[ConversationEvent]) -> float:
    score = 0.0
    for event in list(events)[-8:]:
        text = f"{event.summary} {event.payload if isinstance(event.payload, dict) else ''}"
        if any(word in text for word in ("累", "难过", "孤独", "焦虑", "撑不住", "自杀", "自伤")):
            score += 0.14
        if any(word in text for word in ("谢谢", "喜欢", "开心", "好消息", "成功")):
            score -= 0.03
    return max(0.0, min(0.35, score))


def _duplicate_penalty(events: Sequence[ConversationEvent]) -> float:
    recent = list(events)[-3:]
    if not recent:
        return 0.0
    if sum(1 for event in recent if event.event_type == "proactive_message_sent") >= 1:
        return 0.16
    return 0.0


def _recent_proactive_cooldown(state: CompanionState, now: datetime) -> float:
    if not state.last_proactive_at:
        return 999.0
    moment = parse_iso_datetime(state.last_proactive_at)
    if moment is None:
        return 999.0
    return max(0.0, (now.astimezone(timezone.utc) - moment).total_seconds() / 3600)


def _touch_probability(
    *,
    score: float,
    due_threshold: float,
    opportunity: float,
    value: float,
    relationship_permission: float,
    availability: UserAvailabilityEstimate,
    idle_hours: float,
    state: CompanionState,
) -> float:
    margin_probability = _sigmoid((score - due_threshold) * 8.0)
    base_rate = 0.012 + clampish(value, 0.0, 1.0) * 0.045 + clampish(relationship_permission, 0.0, 1.0) * 0.025
    poisson_probability = 1.0 - math.exp(-base_rate * max(0.0, idle_hours))
    readiness = clampish(float(state.proactive_readiness.get("longing_score", 0.0)), 0.0, 1.0)
    attachment_pull = clampish(float(state.attachment.get("companion_pull", 0.0)), 0.0, 1.0)
    initiative = clampish(float(state.drives.get("initiative", 0.0)), 0.0, 1.0)
    probability = (
        margin_probability * 0.46
        + poisson_probability * 0.32
        + opportunity * 0.1
        + availability.available_probability * 0.06
        + availability.support_probability * 0.045
        + readiness * 0.06
        + attachment_pull * 0.035
        + initiative * 0.025
    )
    probability *= 0.56 + availability.available_probability * 0.34 + availability.support_probability * 0.18
    if score >= due_threshold + 0.12 and idle_hours >= 24:
        probability = 1.0
    return clampish(probability, 0.02, 1.0)


def _deterministic_roll(
    *,
    trace_id: str,
    state: CompanionState,
    now: datetime,
    signal_type: str,
    anchor_memory_ids: Sequence[str],
) -> float:
    bucket = int(now.astimezone(timezone.utc).timestamp() // (30 * 60))
    seed = "|".join(
        [
            trace_id,
            signal_type,
            str(bucket),
            state.last_user_at,
            state.last_assistant_at,
            state.last_proactive_at,
            ",".join(anchor_memory_ids[:3]),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return int(digest, 16) / float(0xFFFFFFFFFFFF)


def _proactive_reason(
    *,
    hold_reasons: list[str],
    due: bool,
    sure_gate_open: bool,
    probability_gate_open: bool,
) -> str:
    if hold_reasons:
        return ";".join(hold_reasons)
    if not due:
        return "probability_wait"
    if sure_gate_open:
        return "high_utility_ready"
    if probability_gate_open:
        return "probabilistic_touch"
    return "idle_and_relationship_ready"


def _estimate_user_availability(
    state: CompanionState,
    recent_events: Sequence[ConversationEvent],
    *,
    now: datetime,
    recent_support: float,
) -> UserAvailabilityEstimate:
    local_hour = now.astimezone().hour
    evidence: list[str] = [f"local_hour={local_hour}"]
    context_busy = clampish(float(state.user_context.get("likely_busy", 0.0)))
    context_sleep = 1.0 if bool(state.user_context.get("sleep_window", False)) else 0.0
    if context_busy:
        evidence.append(f"context_busy={context_busy:.2f}")
    if context_sleep:
        evidence.append("context_sleep_window")

    if 0 <= local_hour < 6:
        time_busy = 0.08
        time_sleep = 0.82
        evidence.append("time_prior=deep_night")
    elif 6 <= local_hour < 8:
        time_busy = 0.36
        time_sleep = 0.34
        evidence.append("time_prior=early_morning")
    elif 8 <= local_hour < 12:
        time_busy = 0.56
        time_sleep = 0.05
        evidence.append("time_prior=morning_work")
    elif 12 <= local_hour < 14:
        time_busy = 0.42
        time_sleep = 0.04
        evidence.append("time_prior=noon")
    elif 14 <= local_hour < 18:
        time_busy = 0.62
        time_sleep = 0.03
        evidence.append("time_prior=afternoon_work")
    elif 18 <= local_hour < 23:
        time_busy = 0.24
        time_sleep = 0.08
        evidence.append("time_prior=evening")
    else:
        time_busy = 0.12
        time_sleep = 0.56
        evidence.append("time_prior=late_night")

    latency = state.interaction_rhythm.get("reply_latency_avg_minutes")
    latency_busy = 0.0
    if latency not in (None, ""):
        latency_minutes = max(0.0, float(latency))
        if latency_minutes >= 180:
            latency_busy = 0.72
            evidence.append(f"slow_reply_latency={latency_minutes:.0f}m")
        elif latency_minutes >= 60:
            latency_busy = 0.46
            evidence.append(f"medium_reply_latency={latency_minutes:.0f}m")
        elif latency_minutes <= 15:
            latency_busy = -0.18
            evidence.append(f"fast_reply_latency={latency_minutes:.0f}m")

    feedback_bias = _availability_feedback_bias(recent_events, evidence)
    affect_support = (
        float(state.user_affect.get("stress", 0.0)) * 0.24
        + float(state.user_affect.get("loneliness", 0.0)) * 0.22
        + float(state.user_affect.get("fatigue", 0.0)) * 0.12
    )
    support_probability = clampish(state.support_need * 0.55 + recent_support * 0.65 + affect_support)
    if support_probability >= 0.55:
        evidence.append(f"support_probability={support_probability:.2f}")

    busy_probability = clampish(
        time_busy * 0.42
        + context_busy * 0.34
        + max(0.0, latency_busy) * 0.16
        + feedback_bias["busy"] * 0.18
        - support_probability * 0.14
        - max(0.0, -latency_busy) * 0.25
    )
    sleep_probability = clampish(
        time_sleep * 0.62
        + context_sleep * 0.3
        + feedback_bias["sleep"] * 0.18
        + float(state.user_affect.get("fatigue", 0.0)) * 0.08
        - support_probability * 0.08
    )
    available_probability = clampish(
        1.0
        - busy_probability * 0.58
        - sleep_probability * 0.72
        + support_probability * 0.18
        + feedback_bias["available"] * 0.16
    )
    label = _availability_label(
        busy_probability=busy_probability,
        sleep_probability=sleep_probability,
        available_probability=available_probability,
        support_probability=support_probability,
    )
    confidence = clampish(
        0.48
        + abs(available_probability - 0.5) * 0.28
        + abs(busy_probability - sleep_probability) * 0.16
        + min(0.12, len(evidence) * 0.02)
    )
    return UserAvailabilityEstimate(
        label=label,
        busy_probability=busy_probability,
        sleep_probability=sleep_probability,
        available_probability=available_probability,
        support_probability=support_probability,
        confidence=confidence,
        evidence=evidence,
    )


def _availability_feedback_bias(
    recent_events: Sequence[ConversationEvent],
    evidence: list[str],
) -> dict[str, float]:
    bias = {"busy": 0.0, "sleep": 0.0, "available": 0.0}
    for event in list(recent_events)[-8:]:
        text = f"{event.event_type} {event.summary} {event.payload if isinstance(event.payload, dict) else ''}"
        if any(word in text for word in ("replied", "acknowledged", "谢谢", "刚好", "喜欢")):
            bias["available"] += 0.12
        if any(word in text for word in ("opened", "已读")):
            bias["available"] += 0.04
        if any(word in text for word in ("ignored", "dismissed", "rejected", "打扰", "太多", "别")):
            bias["busy"] += 0.16
        if any(word in text for word in ("睡", "晚安", "困")):
            bias["sleep"] += 0.08
    for key in list(bias):
        bias[key] = clampish(bias[key], 0.0, 0.42)
    if bias["available"]:
        evidence.append(f"feedback_available={bias['available']:.2f}")
    if bias["busy"]:
        evidence.append(f"feedback_busy={bias['busy']:.2f}")
    if bias["sleep"]:
        evidence.append(f"feedback_sleep={bias['sleep']:.2f}")
    return bias


def _availability_label(
    *,
    busy_probability: float,
    sleep_probability: float,
    available_probability: float,
    support_probability: float,
) -> str:
    if sleep_probability >= 0.72 and support_probability < 0.68:
        return "likely_sleeping"
    if busy_probability >= 0.72 and support_probability < 0.58:
        return "likely_busy"
    if support_probability >= 0.62:
        return "needs_support"
    if available_probability >= 0.62:
        return "likely_available"
    return "uncertain"


def _sigmoid(value: float) -> float:
    if value >= 40:
        return 1.0
    if value <= -40:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value))


def clampish(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _quiet_hours(now: datetime) -> bool:
    local = now.astimezone().time()
    start = dt_time(23, 0)
    end = dt_time(7, 30)
    return local >= start or local < end
