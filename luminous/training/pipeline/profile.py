from __future__ import annotations

import re
from pathlib import Path


BRIEF_RE = re.compile(
    r"## 初始 profile_snapshot\.brief\b.*?```text\s+(.*?)\s+```",
    re.DOTALL,
)


def load_profile_brief(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = BRIEF_RE.search(text)
    if not match:
        raise ValueError(f"{path}: missing 初始 profile_snapshot.brief block")
    return match.group(1).strip()


def profile_revision_applies(revision: dict[str, object]) -> bool:
    return (
        _truthy(revision.get("required", False))
        and _truthy(revision.get("apply_before_next_beat", True))
        and not _truthy(revision.get("rerun_current_beat", False))
    )


def apply_profile_revision(current_brief: str, revision: dict[str, object]) -> str:
    if not profile_revision_applies(revision):
        return current_brief

    snapshot = revision.get("next_profile_snapshot", {})
    if isinstance(snapshot, dict) and str(snapshot.get("brief", "")).strip():
        return str(snapshot.get("brief", "")).strip()

    return current_brief


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "是"}
    return False
