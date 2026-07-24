from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class Chapter:
    chapter_id: str
    title: str
    text: str
    start_char: int
    end_char: int


@dataclass(frozen=True)
class PromptRequest:
    request_id: str
    stage: str
    language: str
    prompt: str
    metadata: JsonDict = field(default_factory=dict)

    def to_json(self) -> JsonDict:
        return {
            "request_id": self.request_id,
            "stage": self.stage,
            "language": self.language,
            "prompt": self.prompt,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class RunSummary:
    output_dir: Path
    files_written: list[Path]
    counts: dict[str, int]
