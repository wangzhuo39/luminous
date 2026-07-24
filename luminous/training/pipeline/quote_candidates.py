from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from luminous.training.pipeline.chapters import load_chapters
from luminous.training.pipeline.jsonl import write_jsonl
from luminous.training.pipeline.models import RunSummary


@dataclass(frozen=True)
class QuoteSpan:
    text: str
    source_start: int
    source_end: int
    quote_start: int
    quote_end: int


@dataclass(frozen=True)
class QuoteContextGroup:
    start: int
    end: int
    quotes: list[QuoteSpan]


def build_quote_candidates(
    input_path: Path,
    output_dir: Path,
    chapter_limit: int,
    language: str = "zh",
    context_char_limit: int = 700,
) -> RunSummary:
    chapters = load_chapters(input_path, limit=chapter_limit)
    source_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []

    for chapter in chapters:
        source_rows.append(
            {
                "request_id": f"{chapter.chapter_id}_source_text",
                "stage": "source_text",
                "language": language,
                "prompt": "",
                "metadata": {
                    "chapter_id": chapter.chapter_id,
                    "chapter_title": chapter.title,
                    "chunk_id": f"{chapter.chapter_id}_source",
                    "chunk_index": 1,
                    "chunk_text": chapter.text,
                    "chunk_start_char": 0,
                    "chunk_end_char": len(chapter.text),
                    "start_char": chapter.start_char,
                    "end_char": chapter.end_char,
                },
            }
        )
        quote_spans = extract_chinese_quote_spans(chapter.text)
        groups = build_quote_context_groups(chapter.text, quote_spans, context_char_limit)
        quote_index = 0
        for group_index, group in enumerate(groups, start=1):
            group_id = f"{chapter.chapter_id}_g{group_index:03d}"
            source_context = chapter.text[group.start : group.end].strip()
            for quote in group.quotes:
                quote_index += 1
                candidate_rows.append(
                    {
                        "candidate_id": f"{chapter.chapter_id}_c{quote_index:03d}",
                        "chapter_id": chapter.chapter_id,
                        "chapter_title": chapter.title,
                        "candidate_type": "dialogue_line",
                        "source_text": quote.text,
                        "source_context": source_context,
                        "source_start_char": quote.source_start,
                        "source_end_char": quote.source_end,
                        "quote_start_char": quote.quote_start,
                        "quote_end_char": quote.quote_end,
                        "context_start_char": group.start,
                        "context_end_char": group.end,
                        "line_hint": _line_hint(chapter.text, quote.quote_start),
                        "attribution_group_id": group_id,
                        "trace": {"stage": "quote_candidates", "strategy": "deterministic_chinese_quotes"},
                    }
                )

    source_path = output_dir / "prompt_requests" / "01_beat_candidates.jsonl"
    candidates_path = output_dir / "beat_candidates.jsonl"
    source_count = write_jsonl(source_path, source_rows)
    candidate_count = write_jsonl(candidates_path, candidate_rows)
    return RunSummary(
        output_dir=output_dir,
        files_written=[source_path, candidates_path],
        counts={"source_text_chunks": source_count, "beat_candidates": candidate_count},
    )


def extract_chinese_quote_spans(text: str) -> list[QuoteSpan]:
    quotes: list[QuoteSpan] = []
    cursor = 0
    while cursor < len(text):
        quote_start = text.find("“", cursor)
        if quote_start < 0:
            break
        quote_end = text.find("”", quote_start + 1)
        if quote_end < 0:
            break

        source_start = quote_start + 1
        source_end = quote_end
        while source_start < source_end and text[source_start].isspace():
            source_start += 1
        while source_end > source_start and text[source_end - 1].isspace():
            source_end -= 1
        if source_end > source_start:
            quotes.append(
                QuoteSpan(
                    text=text[source_start:source_end],
                    source_start=source_start,
                    source_end=source_end,
                    quote_start=quote_start,
                    quote_end=quote_end + 1,
                )
            )
        cursor = quote_end + 1
    return quotes


def build_quote_context_groups(
    chapter_text: str,
    quotes: list[QuoteSpan],
    context_char_limit: int = 700,
) -> list[QuoteContextGroup]:
    if not quotes:
        return []

    windows = []
    for index, quote in enumerate(quotes):
        start = 0 if index == 0 else _line_start(chapter_text, quotes[index - 1].quote_start)
        end = quotes[index + 1].quote_start if index + 1 < len(quotes) else len(chapter_text)
        windows.append((_next_content_start(chapter_text, start), _previous_content_end(chapter_text, end)))

    groups: list[QuoteContextGroup] = []
    index = 0
    while index < len(quotes):
        group_start, group_end = windows[index]
        group_quotes = [quotes[index]]
        if len(chapter_text[group_start:group_end].strip()) > context_char_limit:
            groups.append(QuoteContextGroup(group_start, group_end, group_quotes))
            index += 1
            continue

        next_index = index + 1
        while next_index < len(quotes):
            next_end = windows[next_index][1]
            merged_text = chapter_text[group_start:next_end].strip()
            if len(merged_text) > context_char_limit:
                break
            group_end = next_end
            group_quotes.append(quotes[next_index])
            next_index += 1

        groups.append(QuoteContextGroup(group_start, group_end, group_quotes))
        index = next_index
    return groups


def _line_hint(text: str, index: int) -> str:
    return f"L{text[:index].count(chr(10)) + 1}"


def _line_start(text: str, index: int) -> int:
    newline = text.rfind("\n", 0, index)
    return 0 if newline < 0 else newline + 1


def _next_content_start(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _previous_content_end(text: str, index: int) -> int:
    index = min(index, len(text))
    while index > 0 and text[index - 1].isspace():
        index -= 1
    return index
