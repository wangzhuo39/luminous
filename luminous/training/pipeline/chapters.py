from __future__ import annotations

import re
from pathlib import Path

from luminous.training.pipeline.models import Chapter


CHAPTER_RE = re.compile(r"(?m)^(第[一二三四五六七八九十百千万0-9]+章[^\n]*)")


def split_chapters(text: str, limit: int | None = None) -> list[Chapter]:
    matches = list(CHAPTER_RE.finditer(text))
    if not matches:
        return [Chapter("ch001", "chapter", text, 0, len(text))][:limit]

    chapters: list[Chapter] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chapter_no = index + 1
        chapters.append(
            Chapter(
                chapter_id=f"ch{chapter_no:03d}",
                title=match.group(1).strip(),
                text=text[start:end].strip(),
                start_char=start,
                end_char=end,
            )
        )
        if limit is not None and len(chapters) >= limit:
            break
    return chapters


def load_chapters(path: Path, limit: int | None = None) -> list[Chapter]:
    text = path.read_text(encoding="utf-8-sig")
    return split_chapters(text, limit=limit)
