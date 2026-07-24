from __future__ import annotations

import re
from dataclasses import dataclass


TAG_RE = re.compile(r"<(system_thinking|role_thinking|role_action)[^>]*>(.*?)</\1>", re.DOTALL | re.IGNORECASE)
NATIVE_THINK_RE = re.compile(r"<think[^>]*>.*?</think>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ParsedCompanionOutput:
    role_thinking: str
    role_action: str
    reply: str


def parse_model_output(raw: str) -> ParsedCompanionOutput:
    text = NATIVE_THINK_RE.sub("", raw or "").strip()
    text = _remove_system_thinking(text)
    role_thinking, text = _extract_visible_tag(text, "role_thinking")
    role_action, text = _extract_visible_tag(text, "role_action")
    text = TAG_RE.sub("", text)
    reply = _clean_reply(text)
    return ParsedCompanionOutput(
        role_thinking=_compact(role_thinking),
        role_action=_compact(role_action),
        reply=reply,
    )


def _remove_system_thinking(text: str) -> str:
    text = re.sub(
        r"<system_thinking[^>]*>[\s\S]*?</system_thinking>",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    boundary = text.lower().find("</system_thinking>")
    if boundary >= 0:
        return text[boundary + len("</system_thinking>") :]
    return text


def _extract_visible_tag(text: str, tag: str) -> tuple[str, str]:
    pattern = re.compile(rf"<{tag}[^>]*>([\s\S]*?)</{tag}>", re.IGNORECASE)
    match = pattern.search(text)
    if match:
        content = match.group(1).strip()
        return content, text[: match.start()] + text[match.end() :]

    boundary = text.lower().find(f"</{tag}>")
    if boundary >= 0:
        content = re.sub(rf"^<{tag}[^>]*>", "", text[:boundary], flags=re.IGNORECASE).strip()
        return content, text[boundary + len(f"</{tag}>") :]
    return "", text


def _clean_reply(text: str) -> str:
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    return cleaned or "我在。刚才那句话我听见了，我们可以慢一点。"


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
