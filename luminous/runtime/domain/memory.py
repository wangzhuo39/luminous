from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from luminous.runtime.domain.time import clamp, parse_iso_datetime, utc_now_iso


@dataclass
class MemoryRecord:
    memory_id: str
    kind: str
    text: str
    source_event_id: str
    layer: str = "L1"
    status: str = "active"
    source_role: str = "user"
    source_excerpt: str = ""
    evidence_quote: str = ""
    evidence_event_id: str = ""
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5
    confidence: float = 0.6
    created_at: str = ""
    observed_at: str = ""
    last_accessed_at: str = ""
    access_count: int = 0
    superseded_by: str = ""
    supersedes: list[str] = field(default_factory=list)
    expires_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "kind": self.kind,
            "text": self.text,
            "source_event_id": self.source_event_id,
            "layer": self.layer,
            "status": self.status,
            "source_role": self.source_role,
            "source_excerpt": self.source_excerpt,
            "evidence_quote": self.evidence_quote,
            "evidence_event_id": self.evidence_event_id or self.source_event_id,
            "tags": self.tags,
            "importance": round(self.importance, 3),
            "confidence": round(self.confidence, 3),
            "created_at": self.created_at,
            "observed_at": self.observed_at,
            "last_accessed_at": self.last_accessed_at,
            "access_count": self.access_count,
            "superseded_by": self.superseded_by,
            "supersedes": self.supersedes,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryRecord":
        return cls(
            memory_id=str(data.get("memory_id", "")),
            kind=str(data.get("kind", "fact")),
            text=str(data.get("text", "")),
            source_event_id=str(data.get("source_event_id", "")),
            layer=str(data.get("layer", "L1")),
            status=str(data.get("status", "active")),
            source_role=str(data.get("source_role", "user")),
            source_excerpt=str(data.get("source_excerpt", "")),
            evidence_quote=str(data.get("evidence_quote", "")),
            evidence_event_id=str(data.get("evidence_event_id", data.get("source_event_id", ""))),
            tags=list(data.get("tags", []) or []),
            importance=float(data.get("importance", 0.5)),
            confidence=float(data.get("confidence", 0.6)),
            created_at=str(data.get("created_at", "")),
            observed_at=str(data.get("observed_at", "")),
            last_accessed_at=str(data.get("last_accessed_at", "")),
            access_count=int(data.get("access_count", 0)),
            superseded_by=str(data.get("superseded_by", "")),
            supersedes=list(data.get("supersedes", []) or []),
            expires_at=str(data.get("expires_at", "")),
            metadata=dict(data.get("metadata", {}) or {}),
            schema_version=int(data.get("schema_version", 1)),
        )


@dataclass(frozen=True)
class MemoryHit:
    record: MemoryRecord
    score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        payload = self.record.to_dict()
        payload.update({"score": round(self.score, 3), "reason": self.reason})
        return payload


@dataclass(frozen=True)
class MemoryQuery:
    text: str
    limit: int = 5
    kinds: tuple[str, ...] | None = None


def build_memory_records(
    user_text: str,
    assistant_text: str,
    source_event_id: str,
    now: datetime | None = None,
) -> list[MemoryRecord]:
    now_iso = utc_now_iso(now)
    records: list[MemoryRecord] = []
    for kind, text, tags, importance in _extract_memory_candidates(user_text, assistant_text):
        quote = _evidence_quote(user_text, text)
        records.append(
            MemoryRecord(
                memory_id=f"mem_{len(records) + 1:03d}_{source_event_id[-8:]}",
                kind=kind,
                text=text,
                source_event_id=source_event_id,
                source_role="user",
                source_excerpt=_excerpt(user_text),
                evidence_quote=quote,
                evidence_event_id=source_event_id,
                tags=tags,
                importance=importance,
                confidence=0.62 if kind == "fact" else 0.72,
                created_at=now_iso,
                observed_at=now_iso,
                last_accessed_at=now_iso,
                metadata={"extractor": "heuristic_fallback"},
            )
        )
    return records


def score_memory(query: str, record: MemoryRecord) -> tuple[float, str]:
    if record.status and record.status != "active":
        return 0.0, "inactive"
    query_text = _normalize(query)
    record_text = _normalize(
        " ".join([record.text, record.source_excerpt, record.evidence_quote, " ".join(record.tags)])
    )
    if not query_text or not record_text:
        return 0.0, "empty_query"

    query_ngrams = _ngrams(query_text)
    record_ngrams = _ngrams(record_text)
    if not query_ngrams or not record_ngrams:
        return 0.0, "empty_ngrams"

    overlap = len(query_ngrams & record_ngrams) / max(1, len(query_ngrams))
    keyword_bonus = 0.0
    if record.kind in {"preference", "relationship"} and any(word in query_text for word in ("喜欢", "偏好", "关系", "边界")):
        keyword_bonus += 0.18
    if record.kind in {"emotion", "state"} and any(word in query_text for word in ("累", "难过", "开心", "情绪", "状态")):
        keyword_bonus += 0.18
    if any(tag in query_text for tag in record.tags):
        keyword_bonus += 0.12

    recency_bonus = 0.0
    created_at = parse_iso_datetime(record.created_at)
    if created_at:
        age_hours = max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds() / 3600)
        recency_bonus = clamp(1.0 - age_hours / 720.0) * 0.15

    confidence_bonus = clamp(record.confidence) * 0.08
    importance_bonus = clamp(record.importance) * 0.22
    score = clamp(overlap * 0.55 + keyword_bonus + recency_bonus + importance_bonus + confidence_bonus)
    reason = "keyword" if keyword_bonus else "overlap"
    return score, reason


def _extract_memory_candidates(user_text: str, assistant_text: str) -> list[tuple[str, str, list[str], float]]:
    text = user_text.strip()
    candidates: list[tuple[str, str, list[str], float]] = []

    alias = _extract_alias(text)
    if alias:
        candidates.append(("identity", f"用户自称为{alias}", ["identity", "name"], 0.85))

    preference_phrases = [
        ("preference", "喜欢", ["preference", "likes"], 0.8),
        ("preference", "不喜欢", ["preference", "dislikes"], 0.8),
        ("preference", "讨厌", ["preference", "dislikes"], 0.82),
        ("preference", "想要", ["wish", "preference"], 0.7),
        ("preference", "希望", ["wish"], 0.68),
    ]
    for kind, marker, tags, importance in preference_phrases:
        if marker in text:
            sentence = _sentence_with_marker(text, marker)
            candidates.append((kind, sentence, tags, importance))
            break

    if any(word in text for word in ("今天", "明天", "昨天", "最近", "刚才", "周末", "生日", "纪念日")):
        candidates.append(("event", _sentence_trim(text), ["event", "timeline"], 0.62))

    if any(word in text for word in ("累", "疲惫", "孤独", "难过", "焦虑", "开心", "高兴", "生气")):
        candidates.append(("emotion", _sentence_trim(text), ["emotion", "support"], 0.76))

    if any(word in text for word in ("工作", "上班", "项目", "考试", "学习", "作业", "论文")):
        candidates.append(("state", _sentence_trim(text), ["state", "life"], 0.58))

    if any(word in text for word in ("家人", "朋友", "伴侣", "关系", "边界", "陪伴")):
        candidates.append(("relationship", _sentence_trim(text), ["relationship"], 0.7))

    if any(word in text for word in ("别", "不要", "不许", "不希望你", "别催", "别叫")):
        candidates.append(("boundary", _sentence_trim(text), ["boundary", "relationship"], 0.82))

    if any(word in text for word in ("总是", "每次", "经常", "习惯", "通常")):
        candidates.append(("recurring_topic", _sentence_trim(text), ["recurring_topic"], 0.64))

    if not candidates and len(text) >= 12:
        candidates.append(("fact", _sentence_trim(text), ["conversation"], 0.45))

    if any(word in text for word in ("自杀", "自伤", "伤害自己", "不想活", "想死")):
        candidates.append(("risk", "用户表达了高风险自伤信号，需要优先安抚并联系现实支持。", ["risk", "safety"], 0.95))

    return candidates[:3]


def _extract_alias(text: str) -> str:
    markers = ["我叫", "你可以叫我", "大家都叫我", "叫我"]
    for marker in markers:
        if marker in text:
            tail = text.split(marker, 1)[1].strip("：: ，,。.!?！？\n\t ")
            if tail:
                return tail[:12]
    return ""


def _sentence_with_marker(text: str, marker: str) -> str:
    index = text.find(marker)
    if index < 0:
        return _sentence_trim(text)
    start = max(0, index - 10)
    end = min(len(text), index + 40)
    return _sentence_trim(text[start:end])


def _sentence_trim(text: str) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= 80 else compact[:79].rstrip() + "…"


def _excerpt(text: str) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= 120 else compact[:119].rstrip() + "…"


def _evidence_quote(source_text: str, memory_text: str) -> str:
    compact = " ".join(source_text.split())
    if not compact:
        return _sentence_trim(memory_text)
    if len(compact) <= 80:
        return compact
    return compact[:80].rstrip()


def _normalize(text: str) -> str:
    return "".join(ch.lower() for ch in text if not ch.isspace())


def _ngrams(text: str, size: int = 2) -> set[str]:
    if len(text) <= size:
        return {text} if text else set()
    return {text[index : index + size] for index in range(len(text) - size + 1)}
