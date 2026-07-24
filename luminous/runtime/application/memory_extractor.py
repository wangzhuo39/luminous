from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from luminous.runtime.config import BackendConfig
from luminous.runtime.domain.events import new_event_id
from luminous.runtime.domain.memory import MemoryRecord, build_memory_records
from luminous.runtime.domain.time import clamp, utc_now_iso
from luminous.runtime.infrastructure.client import Message, ModelClient


MEMORY_EXTRACTOR_SYSTEM_PROMPT = """你是 AI 伴侣运行时的记忆摘录器。

任务：从一轮用户/伴侣对话里抽取值得长期保存的记忆。你不是聊天角色。

只输出 JSON，不要 Markdown，不要解释：
{
  "memories": [
    {
      "kind": "fact | preference | relationship | event | boundary | recurring_topic | open_loop",
      "text": "用第三人称、稳定、简短地写：用户...",
      "quote": "必须逐字摘自原始对话的一小段证据",
      "source_role": "user | assistant",
      "tags": ["短标签"],
      "importance": 0.0,
      "confidence": 0.0,
      "expires_at": ""
    }
  ]
}

规则：
- 没有值得长期保存的信息时返回 {"memories": []}。
- quote 必须来自原始 user 或 assistant 文本，不能改写。
- 不要保存普通寒暄。
- 用户明确的偏好、称呼、边界、近期事件、未完成事项优先。
"""

ALLOWED_MEMORY_KINDS = {
    "fact",
    "preference",
    "relationship",
    "event",
    "boundary",
    "recurring_topic",
    "open_loop",
    "identity",
    "emotion",
    "state",
    "risk",
}


@dataclass(frozen=True)
class MemoryExtractionResult:
    records: list[MemoryRecord]
    mode: str
    rejected: list[dict[str, Any]] = field(default_factory=list)
    raw_response: str = ""

    def to_trace_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "record_count": len(self.records),
            "records": [record.to_dict() for record in self.records],
            "rejected": self.rejected,
            "raw_response_excerpt": self.raw_response[:600],
        }


class MemoryExtractor:
    def __init__(self, config: BackendConfig, client: ModelClient) -> None:
        self.config = config
        self.client = client

    def extract(
        self,
        user_text: str,
        assistant_text: str,
        *,
        source_event_id: str,
        trace_id: str,
        now: datetime | None = None,
    ) -> MemoryExtractionResult:
        if self.config.mock or not self.config.llm_configured:
            return MemoryExtractionResult(
                records=build_memory_records(user_text, assistant_text, source_event_id, now=now),
                mode="heuristic_fallback",
            )

        messages: list[Message] = [
            {"role": "system", "content": MEMORY_EXTRACTOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"trace_id: {trace_id}\n"
                    f"source_event_id: {source_event_id}\n\n"
                    f"<user>{user_text}</user>\n\n"
                    f"<assistant>{assistant_text}</assistant>\n\n"
                    "请抽取最多 5 条长期记忆。"
                ),
            },
        ]
        try:
            raw = self.client.complete(messages)
            records, rejected = self._records_from_json(raw, user_text, assistant_text, source_event_id, now=now)
        except Exception as exc:  # noqa: BLE001 - memory extraction must not break chat.
            fallback = build_memory_records(user_text, assistant_text, source_event_id, now=now)
            return MemoryExtractionResult(
                records=fallback,
                mode="heuristic_after_llm_error",
                rejected=[{"reason": type(exc).__name__, "detail": str(exc)[:240]}],
            )

        if not records:
            fallback = build_memory_records(user_text, assistant_text, source_event_id, now=now)
            if fallback:
                return MemoryExtractionResult(
                    records=fallback,
                    mode="heuristic_after_empty_llm",
                    rejected=rejected,
                    raw_response=raw,
                )
        return MemoryExtractionResult(records=records, mode="llm", rejected=rejected, raw_response=raw)

    def _records_from_json(
        self,
        raw: str,
        user_text: str,
        assistant_text: str,
        source_event_id: str,
        now: datetime | None = None,
    ) -> tuple[list[MemoryRecord], list[dict[str, Any]]]:
        payload = _loads_json_object(raw)
        items = payload.get("memories", [])
        if not isinstance(items, list):
            return [], [{"reason": "memories_not_list"}]

        now_iso = utc_now_iso(now)
        combined_sources = {"user": user_text, "assistant": assistant_text}
        records: list[MemoryRecord] = []
        rejected: list[dict[str, Any]] = []
        for item in items[:5]:
            if not isinstance(item, dict):
                rejected.append({"reason": "item_not_object", "item": repr(item)[:120]})
                continue
            kind = str(item.get("kind", "fact")).strip()
            if kind not in ALLOWED_MEMORY_KINDS:
                rejected.append({"reason": "unsupported_kind", "kind": kind})
                continue
            text = _clean_text(str(item.get("text", "")))
            quote = _clean_text(str(item.get("quote", "")))
            source_role = str(item.get("source_role", "user")).strip()
            if source_role not in combined_sources:
                source_role = "user"
            if not text or not quote:
                rejected.append({"reason": "missing_text_or_quote", "item": item})
                continue
            if quote not in combined_sources[source_role] and quote not in user_text and quote not in assistant_text:
                rejected.append({"reason": "quote_not_found", "quote": quote[:120]})
                continue
            tags = [str(tag).strip()[:32] for tag in (item.get("tags", []) or []) if str(tag).strip()]
            records.append(
                MemoryRecord(
                    memory_id=new_event_id("mem"),
                    kind=kind,
                    text=text[:240],
                    source_event_id=source_event_id,
                    source_role=source_role,
                    source_excerpt=_excerpt(combined_sources[source_role]),
                    evidence_quote=quote[:180],
                    evidence_event_id=source_event_id,
                    tags=tags[:8],
                    importance=clamp(float(item.get("importance", 0.55))),
                    confidence=clamp(float(item.get("confidence", 0.65))),
                    created_at=now_iso,
                    observed_at=now_iso,
                    last_accessed_at=now_iso,
                    expires_at=str(item.get("expires_at", "")),
                    metadata={"extractor": "llm"},
                )
            )
        return records, rejected


def _loads_json_object(raw: str) -> dict[str, Any]:
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("memory extractor response must be a JSON object")
    return parsed


def _clean_text(text: str) -> str:
    return " ".join(text.split()).strip()


def _excerpt(text: str, limit: int = 160) -> str:
    compact = _clean_text(text)
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"

