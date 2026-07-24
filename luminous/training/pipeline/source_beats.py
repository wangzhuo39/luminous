from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from luminous.training.pipeline.jsonl import read_jsonl, write_jsonl
from luminous.training.pipeline.models import RunSummary


@dataclass(frozen=True)
class SpeechGroup:
    candidates: list[dict[str, Any]]
    start: int
    end: int


def build_source_anchored_beats(
    candidates_path: Path,
    attributions_path: Path,
    stage1_requests_path: Path,
    coarse_output_path: Path,
    turns_output_path: Path,
    merge_gap_chars: int = 400,
    silent_gap_chars: int = 1800,
) -> RunSummary:
    chapter_texts, chapter_titles = _chapter_texts_from_stage1_requests(stage1_requests_path)
    candidates = [_normalize_candidate(row) for row in read_jsonl(candidates_path)]
    candidates = [candidate for candidate in candidates if _has_location(candidate)]
    attributions_by_candidate = {
        str(row.get("candidate_id", "")): row
        for row in read_jsonl(attributions_path)
        if str(row.get("candidate_id", ""))
    }

    coarse_rows: list[dict[str, object]] = []
    turn_rows: list[dict[str, object]] = []
    chapters = sorted({str(candidate.get("chapter_id", "")) for candidate in candidates if candidate.get("chapter_id")})

    for chapter_id in chapters:
        chapter_text = chapter_texts.get(chapter_id, "")
        if not chapter_text:
            continue
        chapter_candidates = sorted(
            [candidate for candidate in candidates if candidate.get("chapter_id") == chapter_id],
            key=lambda candidate: int(candidate["source_start_char"]),
        )
        title = chapter_titles.get(chapter_id, str(chapter_candidates[0].get("chapter_title", "")))
        speech_groups = _merge_yezhen_speech_groups(
            chapter_text,
            chapter_candidates,
            attributions_by_candidate,
            merge_gap_chars=merge_gap_chars,
        )
        covered_spans: list[tuple[int, int]] = []
        chapter_coarse_count = 0
        chapter_turn_count = 0
        previous_group_end: int | None = None

        for group in speech_groups:
            chapter_coarse_count += 1
            chapter_turn_count += 1
            beat_id = f"{chapter_id}_b{chapter_coarse_count:03d}"
            turn_id = f"{chapter_id}_t{chapter_turn_count:03d}"
            beat_start = (
                0
                if previous_group_end is None
                else _next_content_start(chapter_text, previous_group_end)
            )
            beat_end = _line_end(chapter_text, group.end)
            candidate_ids = _candidate_ids_in_span(chapter_candidates, beat_start, beat_end)
            source_segments = [
                _speech_segment(candidate, attributions_by_candidate.get(str(candidate.get("candidate_id", "")), {}))
                for candidate in group.candidates
            ]
            target_speech = "".join(str(segment["text"]) for segment in source_segments)
            speaker_confidence = _combined_confidence(source_segments)
            coarse_rows.append(
                {
                    "beat_id": beat_id,
                    "beat_type": "dialogue_anchored_beat",
                    "chapter_id": chapter_id,
                    "chapter_title": title,
                    "candidate_ids": candidate_ids,
                    "source_text": chapter_text[beat_start:beat_end].strip(),
                    "source_start_char": beat_start,
                    "source_end_char": beat_end,
                    "line_hint": _line_hint(chapter_text, beat_start),
                    "sft_turn_ids": [turn_id],
                    "trace": {"stage": "source_anchored_beats", "strategy": "yezhen_speech_anchor"},
                }
            )
            turn_rows.append(
                {
                    "turn_id": turn_id,
                    "beat_id": beat_id,
                    "chapter_id": chapter_id,
                    "chapter_title": title,
                    "target_speech": target_speech,
                    "source_speech_segments": source_segments,
                    "speaker_confidence": speaker_confidence,
                    "attribution_ids": [str(segment["attribution_id"]) for segment in source_segments],
                    "trace": {"stage": "source_anchored_beats", "strategy": "yezhen_speech_anchor"},
                }
            )
            covered_spans.append((beat_start, beat_end))
            previous_group_end = beat_end

        for silent_span in _silent_spans(chapter_text, covered_spans, silent_gap_chars):
            chapter_coarse_count += 1
            beat_start, beat_end = silent_span
            coarse_rows.append(
                {
                    "beat_id": f"{chapter_id}_b{chapter_coarse_count:03d}",
                    "beat_type": _silent_beat_type(chapter_text[beat_start:beat_end]),
                    "chapter_id": chapter_id,
                    "chapter_title": title,
                    "candidate_ids": _candidate_ids_in_span(chapter_candidates, beat_start, beat_end),
                    "source_text": chapter_text[beat_start:beat_end].strip(),
                    "source_start_char": beat_start,
                    "source_end_char": beat_end,
                    "line_hint": _line_hint(chapter_text, beat_start),
                    "sft_turn_ids": [],
                    "trace": {"stage": "source_anchored_beats", "strategy": "silent_span"},
                }
            )

    coarse_rows.sort(key=lambda row: (str(row.get("chapter_id", "")), int(row.get("source_start_char", 0))))
    _renumber_beats_and_turns(coarse_rows, turn_rows)
    write_jsonl(coarse_output_path, coarse_rows)
    write_jsonl(turns_output_path, turn_rows)
    return RunSummary(
        output_dir=coarse_output_path.parent,
        files_written=[coarse_output_path, turns_output_path],
        counts={"coarse_beats": len(coarse_rows), "sft_turns": len(turn_rows)},
    )


def _chapter_texts_from_stage1_requests(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    chunks_by_chapter: dict[str, list[tuple[int, str]]] = {}
    titles: dict[str, str] = {}
    for row in read_jsonl(path):
        metadata = row.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        chapter_id = str(metadata.get("chapter_id", ""))
        chunk_text = str(metadata.get("chunk_text", ""))
        if not chapter_id or not chunk_text:
            continue
        chunk_start = int(metadata.get("chunk_start_char", 0) or 0)
        chunks_by_chapter.setdefault(chapter_id, []).append((chunk_start, chunk_text))
        titles[chapter_id] = str(metadata.get("chapter_title", ""))

    texts: dict[str, str] = {}
    for chapter_id, chunks in chunks_by_chapter.items():
        max_end = max(start + len(text) for start, text in chunks)
        buffer = [" "] * max_end
        for start, text in chunks:
            for offset, char in enumerate(text):
                buffer[start + offset] = char
        texts[chapter_id] = "".join(buffer).rstrip()
    return texts, titles


def _normalize_candidate(row: dict[str, Any]) -> dict[str, Any]:
    candidate = dict(row)
    for key in ("source_start_char", "source_end_char"):
        value = candidate.get(key, "")
        if value == "":
            continue
        candidate[key] = int(value)
    return candidate


def _has_location(candidate: dict[str, Any]) -> bool:
    return isinstance(candidate.get("source_start_char"), int) and isinstance(candidate.get("source_end_char"), int)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "是"}
    return False


def _is_yezhen_speech(candidate: dict[str, Any], attribution: dict[str, Any]) -> bool:
    return candidate.get("candidate_type") == "dialogue_line" and _truthy(attribution.get("is_yezhen_speech"))


def _merge_yezhen_speech_groups(
    chapter_text: str,
    candidates: list[dict[str, Any]],
    attributions_by_candidate: dict[str, dict[str, Any]],
    merge_gap_chars: int,
) -> list[SpeechGroup]:
    anchors = [
        candidate
        for candidate in candidates
        if _is_yezhen_speech(candidate, attributions_by_candidate.get(str(candidate.get("candidate_id", "")), {}))
    ]
    groups: list[SpeechGroup] = []
    for anchor in anchors:
        if not groups:
            groups.append(SpeechGroup([anchor], int(anchor["source_start_char"]), int(anchor["source_end_char"])))
            continue
        previous = groups[-1]
        gap_start = previous.end
        gap_end = int(anchor["source_start_char"])
        if _can_merge_speech_group(chapter_text, candidates, gap_start, gap_end, merge_gap_chars, attributions_by_candidate):
            groups[-1] = SpeechGroup(
                [*previous.candidates, anchor],
                previous.start,
                int(anchor["source_end_char"]),
            )
        else:
            groups.append(SpeechGroup([anchor], int(anchor["source_start_char"]), int(anchor["source_end_char"])))
    return groups


def _can_merge_speech_group(
    chapter_text: str,
    candidates: list[dict[str, Any]],
    gap_start: int,
    gap_end: int,
    merge_gap_chars: int,
    attributions_by_candidate: dict[str, dict[str, Any]],
) -> bool:
    gap_text = chapter_text[gap_start:gap_end]
    if gap_end - gap_start > merge_gap_chars or _has_scene_break(gap_text):
        return False
    for candidate in candidates:
        start = int(candidate["source_start_char"])
        end = int(candidate["source_end_char"])
        if start < gap_start or end > gap_end or candidate.get("candidate_type") != "dialogue_line":
            continue
        attribution = attributions_by_candidate.get(str(candidate.get("candidate_id", "")), {})
        if not _is_yezhen_speech(candidate, attribution):
            return False
    return _is_continuous_speech_bridge(gap_text)


def _is_continuous_speech_bridge(text: str, max_bridge_chars: int = 80) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    core = re.sub(r"[“”\"'‘’\s，,。.!！?？、:：;；—…·\\-]+", "", stripped)
    if not core:
        return True
    if len(stripped) > max_bridge_chars:
        return False
    if "叶筝" not in stripped and "她" not in stripped:
        return False
    return any(
        marker in stripped
        for marker in (
            "说",
            "道",
            "问",
            "答",
            "开口",
            "出声",
            "回应",
            "反问",
            "解释",
            "补充",
            "继续",
            "停顿",
            "顿了顿",
            "沉默",
            "笑了笑",
            "摇头",
            "点头",
            "叹",
        )
    )


def _speech_segment(candidate: dict[str, Any], attribution: dict[str, Any]) -> dict[str, object]:
    candidate_id = str(candidate.get("candidate_id", ""))
    confidence = str(attribution.get("speaker_confidence", attribution.get("confidence", "unknown")))
    return {
        "candidate_id": candidate_id,
        "text": str(candidate.get("source_text", "")),
        "source_start_char": int(candidate["source_start_char"]),
        "source_end_char": int(candidate["source_end_char"]),
        "line_hint": candidate.get("line_hint", ""),
        "speaker_confidence": confidence,
        "attribution_id": str(attribution.get("attribution_id", f"{candidate_id}_attr")),
    }


def _combined_confidence(segments: list[dict[str, object]]) -> str:
    confidences = [str(segment.get("speaker_confidence", "unknown")) for segment in segments]
    if not confidences:
        return "unknown"
    for value in ("unknown", "low", "medium"):
        if value in confidences:
            return value
    return confidences[0]


def _next_content_start(chapter_text: str, index: int) -> int:
    while index < len(chapter_text) and chapter_text[index] in {"\n", " ", "\t", "*"}:
        index += 1
    return index


def _line_start(chapter_text: str, index: int) -> int:
    newline = chapter_text.rfind("\n", 0, index)
    return 0 if newline < 0 else newline + 1


def _line_end(chapter_text: str, index: int) -> int:
    newline = chapter_text.find("\n", index)
    return len(chapter_text) if newline < 0 else newline


def _line_hint(chapter_text: str, index: int) -> str:
    return f"L{chapter_text[:index].count(chr(10)) + 1}"


def _candidate_ids_in_span(candidates: list[dict[str, Any]], start: int, end: int) -> list[str]:
    return [
        str(candidate.get("candidate_id", ""))
        for candidate in candidates
        if int(candidate["source_start_char"]) >= start and int(candidate["source_end_char"]) <= end
    ]


def _silent_spans(
    chapter_text: str,
    covered_spans: list[tuple[int, int]],
    silent_gap_chars: int,
) -> list[tuple[int, int]]:
    sorted_spans = sorted(covered_spans)
    if not sorted_spans:
        return []
    return _split_silent_region(chapter_text, sorted_spans[-1][1], len(chapter_text), silent_gap_chars)


def _split_silent_region(chapter_text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    start = _next_content_start(chapter_text, start)
    end = _previous_content_end(chapter_text, end)
    if end <= start:
        return []
    text = chapter_text[start:end]
    if not _looks_relevant_silent_text(text):
        return []
    raw_parts: list[tuple[int, int]] = []
    part_start = start
    index = start
    while index < end:
        marker = chapter_text.find("\n*\n", index, end)
        if marker < 0:
            break
        raw_parts.append((part_start, marker))
        part_start = marker + 3
        index = part_start
    raw_parts.append((part_start, end))

    spans: list[tuple[int, int]] = []
    for part_start, part_end in raw_parts:
        part_start = _next_content_start(chapter_text, part_start)
        part_end = _previous_content_end(chapter_text, part_end)
        if part_end <= part_start:
            continue
        cursor = part_start
        while cursor < part_end:
            chunk_end = min(part_end, cursor + max_chars)
            if chunk_end < part_end:
                newline = chapter_text.rfind("\n", cursor, chunk_end)
                if newline > cursor:
                    chunk_end = newline
            chunk_start = _next_content_start(chapter_text, cursor)
            chunk_end = _previous_content_end(chapter_text, chunk_end)
            if chunk_end > chunk_start and _looks_relevant_silent_text(chapter_text[chunk_start:chunk_end]):
                spans.append((chunk_start, chunk_end))
            cursor = max(chunk_end + 1, cursor + 1)
    return spans


def _previous_content_end(chapter_text: str, index: int) -> int:
    index = min(index, len(chapter_text))
    while index > 0 and chapter_text[index - 1] in {"\n", " ", "\t", "*"}:
        index -= 1
    return index


def _looks_relevant_silent_text(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 6:
        return False
    return "叶筝" in stripped or "她" in stripped


def _silent_beat_type(text: str) -> str:
    stripped = text.strip()
    if (stripped.startswith("叶筝") or stripped.startswith("她")) and any(
        keyword in text
        for keyword in ("想", "知道", "发现", "意识", "觉得", "不确定", "推测", "判断", "沉默", "闭上眼", "垂下眼", "独自")
    ):
        return "silent_internal_beat"
    return "external_perception_beat"


def _has_scene_break(text: str) -> bool:
    return "\n*\n" in text or "\n\n" in text


def _renumber_beats_and_turns(coarse_rows: list[dict[str, object]], turn_rows: list[dict[str, object]]) -> None:
    old_to_new: dict[str, str] = {}
    counters: dict[str, int] = {}
    for row in coarse_rows:
        chapter_id = str(row.get("chapter_id", ""))
        counters[chapter_id] = counters.get(chapter_id, 0) + 1
        old_id = str(row.get("beat_id", ""))
        new_id = f"{chapter_id}_b{counters[chapter_id]:03d}"
        old_to_new[old_id] = new_id
        row["beat_id"] = new_id
    turn_counters: dict[str, int] = {}
    for row in turn_rows:
        chapter_id = str(row.get("chapter_id", ""))
        turn_counters[chapter_id] = turn_counters.get(chapter_id, 0) + 1
        row["turn_id"] = f"{chapter_id}_t{turn_counters[chapter_id]:03d}"
        row["beat_id"] = old_to_new.get(str(row.get("beat_id", "")), row.get("beat_id", ""))
    turns_by_beat: dict[str, list[str]] = {}
    for row in turn_rows:
        turns_by_beat.setdefault(str(row.get("beat_id", "")), []).append(str(row.get("turn_id", "")))
    for row in coarse_rows:
        row["sft_turn_ids"] = turns_by_beat.get(str(row.get("beat_id", "")), [])
