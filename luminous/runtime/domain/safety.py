from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SafetyPolicy:
    """Versioned, deterministic guard for all outbound companion actions."""

    version: str = "2026-07-23"
    blocked_risk_levels: frozenset[str] = frozenset({"high", "critical"})
    allowed_kinds_at_risk: frozenset[str] = frozenset({"repair"})
    crisis_message: str = "我很在意你现在的安全。请优先联系你身边可信任的人或当地紧急支持。"
    metadata: dict[str, Any] = field(default_factory=dict)

    def permits(self, *, risk_level: str, proactive_kind: str) -> tuple[bool, str]:
        normalized = risk_level.strip().lower()
        if normalized in self.blocked_risk_levels and proactive_kind not in self.allowed_kinds_at_risk:
            return False, f"safety_policy:{self.version}:risk_{normalized}"
        return True, ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "blocked_risk_levels": sorted(self.blocked_risk_levels),
            "allowed_kinds_at_risk": sorted(self.allowed_kinds_at_risk),
            "crisis_message": self.crisis_message,
            "metadata": self.metadata,
        }
