from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from luminous.runtime.domain.time import clamp, parse_iso_datetime, utc_now_iso


@dataclass
class RelationshipState:
    trust: float = 0.35
    intimacy: float = 0.2
    boundaries: float = 0.7
    familiarity: float = 0.25
    rupture: float = 0.0
    repair_progress: float = 0.0
    last_update_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trust": round(self.trust, 3),
            "intimacy": round(self.intimacy, 3),
            "boundaries": round(self.boundaries, 3),
            "familiarity": round(self.familiarity, 3),
            "rupture": round(self.rupture, 3),
            "repair_progress": round(self.repair_progress, 3),
            "last_update_at": self.last_update_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RelationshipState":
        data = data or {}
        return cls(
            trust=float(data.get("trust", 0.35)),
            intimacy=float(data.get("intimacy", 0.2)),
            boundaries=float(data.get("boundaries", 0.7)),
            familiarity=float(data.get("familiarity", 0.25)),
            rupture=float(data.get("rupture", 0.0)),
            repair_progress=float(data.get("repair_progress", 0.0)),
            last_update_at=str(data.get("last_update_at", "")),
        )


@dataclass
class CompanionState:
    persona_name: str = "叶筝"
    user_name: str = ""
    mood: str = "steady"
    energy: float = 0.75
    support_need: float = 0.0
    risk_level: str = "low"
    conversation_count: int = 0
    last_user_at: str = ""
    last_assistant_at: str = ""
    last_proactive_at: str = ""
    dnd_until: str = ""
    recent_topics: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    relationship: RelationshipState = field(default_factory=RelationshipState)
    user_affect: dict[str, float] = field(default_factory=lambda: {
        "valence": 0.0,
        "arousal": 0.2,
        "stress": 0.0,
        "loneliness": 0.0,
        "fatigue": 0.0,
        "confidence": 0.35,
    })
    user_context: dict[str, Any] = field(default_factory=lambda: {
        "local_time_bucket": "",
        "likely_busy": 0.0,
        "sleep_window": False,
        "recent_topics": [],
    })
    companion_affect: dict[str, float] = field(default_factory=lambda: {
        "concern": 0.2,
        "warmth": 0.65,
        "longing": 0.0,
        "protectiveness": 0.15,
        "playfulness": 0.2,
    })
    interaction_rhythm: dict[str, Any] = field(default_factory=lambda: {
        "last_idle_hours": 0.0,
        "conversation_frequency": 0.0,
        "reply_latency_avg_minutes": None,
    })
    conversation_mode: str = "casual"
    open_loops: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    proactive_readiness: dict[str, Any] = field(default_factory=lambda: {
        "longing_score": 0.0,
        "contact_allowed": True,
        "best_signal_type": "",
        "last_reason": "",
    })
    relationship_arc: dict[str, Any] = field(default_factory=lambda: {
        "stage": "first_contact",
        "direction": "stable",
        "depth": 0.2,
        "stability": 0.72,
        "care_balance": 0.5,
        "last_shift_reason": "",
        "milestones": [],
    })
    attachment: dict[str, Any] = field(default_factory=lambda: {
        "user_reliance": 0.0,
        "companion_pull": 0.18,
        "reassurance_need": 0.0,
        "separation_sensitivity": 0.0,
        "autonomy_support": 0.72,
        "last_signal": "",
    })
    drives: dict[str, float] = field(default_factory=lambda: {
        "care": 0.62,
        "curiosity": 0.45,
        "play": 0.24,
        "protectiveness": 0.16,
        "restraint": 0.68,
        "initiative": 0.18,
    })

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_name": self.persona_name,
            "user_name": self.user_name,
            "mood": self.mood,
            "energy": round(self.energy, 3),
            "support_need": round(self.support_need, 3),
            "risk_level": self.risk_level,
            "conversation_count": self.conversation_count,
            "last_user_at": self.last_user_at,
            "last_assistant_at": self.last_assistant_at,
            "last_proactive_at": self.last_proactive_at,
            "dnd_until": self.dnd_until,
            "recent_topics": self.recent_topics[:10],
            "flags": self.flags[:20],
            "relationship": self.relationship.to_dict(),
            "user_affect": _rounded_mapping(self.user_affect),
            "user_context": self.user_context,
            "companion_affect": _rounded_mapping(self.companion_affect),
            "interaction_rhythm": self.interaction_rhythm,
            "conversation_mode": self.conversation_mode,
            "open_loops": self.open_loops[:20],
            "timeline": self.timeline[:50],
            "proactive_readiness": self.proactive_readiness,
            "relationship_arc": _relationship_arc_snapshot(self.relationship_arc),
            "attachment": _attachment_snapshot(self.attachment),
            "drives": _rounded_mapping(self.drives),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CompanionState":
        data = data or {}
        return cls(
            persona_name=str(data.get("persona_name", "叶筝")),
            user_name=str(data.get("user_name", "")),
            mood=str(data.get("mood", "steady")),
            energy=float(data.get("energy", 0.75)),
            support_need=float(data.get("support_need", 0.0)),
            risk_level=str(data.get("risk_level", "low")),
            conversation_count=int(data.get("conversation_count", 0)),
            last_user_at=str(data.get("last_user_at", "")),
            last_assistant_at=str(data.get("last_assistant_at", "")),
            last_proactive_at=str(data.get("last_proactive_at", "")),
            dnd_until=str(data.get("dnd_until", "")),
            recent_topics=list(data.get("recent_topics", []) or []),
            flags=list(data.get("flags", []) or []),
            relationship=RelationshipState.from_dict(data.get("relationship")),
            user_affect=dict(data.get("user_affect", {}) or {
                "valence": 0.0,
                "arousal": 0.2,
                "stress": 0.0,
                "loneliness": 0.0,
                "fatigue": 0.0,
                "confidence": 0.35,
            }),
            user_context=dict(data.get("user_context", {}) or {
                "local_time_bucket": "",
                "likely_busy": 0.0,
                "sleep_window": False,
                "recent_topics": [],
            }),
            companion_affect=dict(data.get("companion_affect", {}) or {
                "concern": 0.2,
                "warmth": 0.65,
                "longing": 0.0,
                "protectiveness": 0.15,
                "playfulness": 0.2,
            }),
            interaction_rhythm=dict(data.get("interaction_rhythm", {}) or {
                "last_idle_hours": 0.0,
                "conversation_frequency": 0.0,
                "reply_latency_avg_minutes": None,
            }),
            conversation_mode=str(data.get("conversation_mode", "casual")),
            open_loops=list(data.get("open_loops", []) or []),
            timeline=list(data.get("timeline", []) or []),
            proactive_readiness=dict(data.get("proactive_readiness", {}) or {
                "longing_score": 0.0,
                "contact_allowed": True,
                "best_signal_type": "",
                "last_reason": "",
            }),
            relationship_arc=_relationship_arc_from_dict(data.get("relationship_arc")),
            attachment=_attachment_from_dict(data.get("attachment")),
            drives=_drives_from_dict(data.get("drives")),
        )

    def snapshot(self) -> dict[str, Any]:
        return self.to_dict()

    def prompt_block(self) -> str:
        lines = [
            f"伴侣状态：",
            f"- mood: {self.mood}",
            f"- energy: {self.energy:.2f}",
            f"- support_need: {self.support_need:.2f}",
            f"- risk_level: {self.risk_level}",
            f"- conversation_count: {self.conversation_count}",
            f"- relationship.trust: {self.relationship.trust:.2f}",
            f"- relationship.intimacy: {self.relationship.intimacy:.2f}",
            f"- relationship.boundaries: {self.relationship.boundaries:.2f}",
            f"- relationship.familiarity: {self.relationship.familiarity:.2f}",
            f"- relationship.rupture: {self.relationship.rupture:.2f}",
            f"- relationship.repair_progress: {self.relationship.repair_progress:.2f}",
            f"- conversation_mode: {self.conversation_mode}",
        ]
        if self.user_affect:
            lines.append(
                "- user_affect: "
                f"stress={float(self.user_affect.get('stress', 0.0)):.2f}, "
                f"loneliness={float(self.user_affect.get('loneliness', 0.0)):.2f}, "
                f"fatigue={float(self.user_affect.get('fatigue', 0.0)):.2f}, "
                f"valence={float(self.user_affect.get('valence', 0.0)):.2f}"
            )
        if self.companion_affect:
            lines.append(
                "- companion_affect: "
                f"concern={float(self.companion_affect.get('concern', 0.0)):.2f}, "
                f"longing={float(self.companion_affect.get('longing', 0.0)):.2f}, "
                f"warmth={float(self.companion_affect.get('warmth', 0.0)):.2f}"
            )
        if self.relationship_arc:
            lines.append(
                "- relationship_arc: "
                f"stage={self.relationship_arc.get('stage', 'first_contact')}, "
                f"direction={self.relationship_arc.get('direction', 'stable')}, "
                f"depth={float(self.relationship_arc.get('depth', 0.0)):.2f}, "
                f"stability={float(self.relationship_arc.get('stability', 0.0)):.2f}"
            )
        if self.attachment:
            lines.append(
                "- attachment: "
                f"user_reliance={float(self.attachment.get('user_reliance', 0.0)):.2f}, "
                f"companion_pull={float(self.attachment.get('companion_pull', 0.0)):.2f}, "
                f"reassurance_need={float(self.attachment.get('reassurance_need', 0.0)):.2f}, "
                f"autonomy_support={float(self.attachment.get('autonomy_support', 0.0)):.2f}"
            )
        if self.drives:
            lines.append(
                "- drives: "
                f"care={float(self.drives.get('care', 0.0)):.2f}, "
                f"curiosity={float(self.drives.get('curiosity', 0.0)):.2f}, "
                f"protectiveness={float(self.drives.get('protectiveness', 0.0)):.2f}, "
                f"restraint={float(self.drives.get('restraint', 0.0)):.2f}, "
                f"initiative={float(self.drives.get('initiative', 0.0)):.2f}"
            )
        if self.open_loops:
            labels = [str(loop.get("summary", "")) for loop in self.open_loops[:3] if isinstance(loop, dict)]
            if labels:
                lines.append(f"- open_loops: {'; '.join(labels)}")
        if self.recent_topics:
            lines.append(f"- recent_topics: {', '.join(self.recent_topics[:5])}")
        if self.flags:
            lines.append(f"- flags: {', '.join(self.flags[:5])}")
        return "\n".join(lines)

    def apply_turn(
        self,
        user_text: str,
        assistant_text: str,
        memory_kinds: list[str] | None = None,
        now: datetime | None = None,
        risk_flags: list[str] | None = None,
    ) -> None:
        memory_kinds = memory_kinds or []
        risk_flags = risk_flags or []
        now_iso = utc_now_iso(now)
        self.conversation_count += 1
        self.last_user_at = now_iso
        self.last_assistant_at = now_iso
        self.relationship.last_update_at = now_iso
        self._update_user_name(user_text)
        self._update_recent_topics(user_text)
        self._update_mood(user_text, assistant_text, risk_flags)
        self._update_energy(user_text, assistant_text, memory_kinds, risk_flags)
        self._update_relationship(user_text, assistant_text, memory_kinds, risk_flags)
        self._update_flags(user_text, assistant_text, risk_flags)

    def mark_proactive_contact(self, now: datetime | None = None) -> None:
        self.last_proactive_at = utc_now_iso(now)

    def is_dnd(self, now: datetime | None = None) -> bool:
        limit = parse_iso_datetime(self.dnd_until)
        if not limit:
            return False
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current.astimezone(timezone.utc) < limit

    def _update_user_name(self, user_text: str) -> None:
        if self.user_name:
            return
        marker = "我叫"
        if marker in user_text:
            tail = user_text.split(marker, 1)[1].strip("：: ，,。.!?！？\n\t ")
            if tail:
                self.user_name = tail[:12]

    def _update_recent_topics(self, user_text: str) -> None:
        for topic in _topic_keywords(user_text):
            if topic not in self.recent_topics:
                self.recent_topics.insert(0, topic)
        del self.recent_topics[10:]

    def _update_mood(self, user_text: str, assistant_text: str, risk_flags: list[str]) -> None:
        if risk_flags:
            self.mood = "protective"
            return
        if any(word in user_text for word in ("开心", "高兴", "终于", "成功", "喜欢")):
            self.mood = "warm"
        elif any(word in user_text for word in ("累", "疲惫", "撑不住", "焦虑", "难过", "孤独")):
            self.mood = "concerned"
        elif any(word in user_text for word in ("谢谢", "抱抱", "想你")):
            self.mood = "soft"
        elif assistant_text.strip():
            self.mood = "steady"

    def _update_energy(self, user_text: str, assistant_text: str, memory_kinds: list[str], risk_flags: list[str]) -> None:
        delta = 0.0
        if any(word in user_text for word in ("累", "疲惫", "撑不住", "焦虑", "难过", "孤独")):
            delta -= 0.08
            self.support_need = clamp(self.support_need + 0.12)
        if any(word in user_text for word in ("开心", "高兴", "喜欢", "谢谢", "抱抱")):
            delta += 0.05
            self.support_need = clamp(self.support_need - 0.05)
        if "emotion" in memory_kinds or "risk" in memory_kinds:
            delta -= 0.03
        if risk_flags:
            delta -= 0.1
            self.support_need = clamp(self.support_need + 0.2)
            self.risk_level = "elevated"
        self.energy = clamp(self.energy + delta)
        if self.energy < 0.35:
            self.flags.append("low_energy")

    def _update_relationship(self, user_text: str, assistant_text: str, memory_kinds: list[str], risk_flags: list[str]) -> None:
        trust_delta = 0.0
        intimacy_delta = 0.0
        familiarity_delta = 0.0
        boundaries_delta = 0.0

        if any(word in user_text for word in ("谢谢", "喜欢", "信任", "抱抱", "靠近")):
            trust_delta += 0.02
            intimacy_delta += 0.03
        if any(word in user_text for word in ("我今天", "我最近", "我其实", "我有点", "我很")):
            intimacy_delta += 0.02
            familiarity_delta += 0.03
        if any(word in user_text for word in ("界限", "边界", "别催", "不用回")):
            boundaries_delta += 0.04
        if memory_kinds:
            familiarity_delta += 0.02
        if risk_flags:
            boundaries_delta += 0.05
            trust_delta -= 0.01
            self.relationship.rupture = clamp(self.relationship.rupture + 0.03)
        if any(word in user_text for word in ("对不起", "没关系", "重新来", "刚才")):
            self.relationship.repair_progress = clamp(self.relationship.repair_progress + 0.04)
            self.relationship.rupture = clamp(self.relationship.rupture - 0.03)

        self.relationship.trust = clamp(self.relationship.trust + trust_delta)
        self.relationship.intimacy = clamp(self.relationship.intimacy + intimacy_delta)
        self.relationship.familiarity = clamp(self.relationship.familiarity + familiarity_delta)
        self.relationship.boundaries = clamp(self.relationship.boundaries + boundaries_delta)

    def _update_flags(self, user_text: str, assistant_text: str, risk_flags: list[str]) -> None:
        if risk_flags:
            self.flags = list(dict.fromkeys(self.flags + risk_flags))
        if "high_risk" in risk_flags or any(word in user_text for word in ("自杀", "自伤", "伤害自己", "不想活", "想死")):
            self.risk_level = "high"
            if "high_risk" not in self.flags:
                self.flags.append("high_risk")
        elif risk_flags or any(word in user_text for word in ("害怕", "恐惧", "焦虑", "崩溃", "孤独", "撑不住", "绝望", "无助")):
            self.risk_level = "elevated"
        elif self.risk_level != "high":
            self.risk_level = "low"


def _topic_keywords(text: str) -> list[str]:
    keywords = [
        ("工作", ("工作", "上班", "项目", "加班")),
        ("学习", ("学习", "考试", "作业", "论文")),
        ("关系", ("朋友", "家人", "伴侣", "关系")),
        ("睡眠", ("睡不着", "失眠", "睡觉", "困")),
        ("情绪", ("累", "疲惫", "焦虑", "难过", "孤独", "开心")),
        ("健康", ("身体", "生病", "心率", "健康")),
        ("日常", ("今天", "明天", "最近", "刚才")),
    ]
    hits: list[str] = []
    for label, patterns in keywords:
        if any(pattern in text for pattern in patterns):
            hits.append(label)
    return hits


def _relationship_arc_from_dict(data: dict[str, Any] | None) -> dict[str, Any]:
    default = {
        "stage": "first_contact",
        "direction": "stable",
        "depth": 0.2,
        "stability": 0.72,
        "care_balance": 0.5,
        "last_shift_reason": "",
        "milestones": [],
    }
    if data:
        default.update(data)
    return _relationship_arc_snapshot(default)


def _relationship_arc_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": str(data.get("stage", "first_contact")),
        "direction": str(data.get("direction", "stable")),
        "depth": round(float(data.get("depth", 0.2)), 3),
        "stability": round(float(data.get("stability", 0.72)), 3),
        "care_balance": round(float(data.get("care_balance", 0.5)), 3),
        "last_shift_reason": str(data.get("last_shift_reason", "")),
        "milestones": list(data.get("milestones", []) or [])[:12],
    }


def _attachment_from_dict(data: dict[str, Any] | None) -> dict[str, Any]:
    default = {
        "user_reliance": 0.0,
        "companion_pull": 0.18,
        "reassurance_need": 0.0,
        "separation_sensitivity": 0.0,
        "autonomy_support": 0.72,
        "last_signal": "",
    }
    if data:
        default.update(data)
    return _attachment_snapshot(default)


def _attachment_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_reliance": round(float(data.get("user_reliance", 0.0)), 3),
        "companion_pull": round(float(data.get("companion_pull", 0.18)), 3),
        "reassurance_need": round(float(data.get("reassurance_need", 0.0)), 3),
        "separation_sensitivity": round(float(data.get("separation_sensitivity", 0.0)), 3),
        "autonomy_support": round(float(data.get("autonomy_support", 0.72)), 3),
        "last_signal": str(data.get("last_signal", "")),
    }


def _drives_from_dict(data: dict[str, Any] | None) -> dict[str, float]:
    default = {
        "care": 0.62,
        "curiosity": 0.45,
        "play": 0.24,
        "protectiveness": 0.16,
        "restraint": 0.68,
        "initiative": 0.18,
    }
    if data:
        default.update(data)
    return {key: round(float(value), 3) for key, value in default.items()}


def _rounded_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    rounded: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, float):
            rounded[key] = round(value, 3)
        else:
            rounded[key] = value
    return rounded
