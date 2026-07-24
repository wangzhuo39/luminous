from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from luminous.training.pipeline.jsonl import read_jsonl, write_jsonl
from luminous.training.pipeline.models import PromptRequest, RunSummary
from luminous.training.pipeline.profile import load_profile_brief
from luminous.training.pipeline.prompts import render_prompt
from luminous.training.pipeline.qa import check_sft_message
from luminous.training.pipeline.role_setup import FIXED_BACKGROUND, FIXED_PROFILE


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def prepare_speaker_attribution_prompt_requests(
    candidates_path: Path,
    output_dir: Path,
    language: str,
    max_candidates_per_request: int = 4,
) -> RunSummary:
    rows = []
    candidates_by_chapter: dict[str, list[dict[str, object]]] = defaultdict(list)
    titles: dict[str, str] = {}
    for candidate in read_jsonl(candidates_path):
        chapter_id = str(candidate.get("chapter_id", ""))
        candidates_by_chapter[chapter_id].append(candidate)
        titles[chapter_id] = str(candidate.get("chapter_title", ""))

    for chapter_id in sorted(candidates_by_chapter):
        chapter_candidates = sorted(candidates_by_chapter[chapter_id], key=_candidate_sort_key)
        groups = _speaker_candidate_groups(chapter_candidates, max_candidates_per_request)
        for batch_index, candidates in enumerate(groups, start=1):
            candidate_ids = [str(candidate.get("candidate_id", "")) for candidate in candidates]
            group_id = _candidate_group_id(candidates)
            request_id = (
                f"{chapter_id}_speaker_attribution"
                if len(groups) == 1
                else f"{group_id or f'{chapter_id}_a{batch_index:03d}'}_speaker_attribution"
            )
            prompt = render_prompt(
                "speaker_attribution",
                language,
                {
                    "character_name": "叶筝",
                    "candidate": _json_text(_speaker_group_payload(candidates)),
                },
            )
            rows.append(
                PromptRequest(
                    request_id=request_id,
                    stage="speaker_attribution",
                    language=language,
                    prompt=prompt,
                    metadata={
                        "chapter_id": chapter_id,
                        "chapter_title": titles.get(chapter_id, ""),
                        "candidate_ids": candidate_ids,
                        "batch_index": batch_index,
                    },
                ).to_json()
            )

    path = output_dir / "prompt_requests" / "02_speaker_attribution.jsonl"
    count = write_jsonl(path, rows)
    return RunSummary(output_dir=output_dir, files_written=[path], counts={"speaker_attribution_requests": count})


def _candidate_sort_key(candidate: dict[str, object]) -> tuple[int, str]:
    value = candidate.get("source_start_char", 0)
    try:
        start = int(value)
    except (TypeError, ValueError):
        start = 0
    return start, str(candidate.get("candidate_id", ""))


def _speaker_candidate_groups(
    chapter_candidates: list[dict[str, object]],
    max_candidates_per_request: int,
) -> list[list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    legacy_candidates: list[dict[str, object]] = []
    for candidate in chapter_candidates:
        group_id = str(candidate.get("attribution_group_id", ""))
        if group_id:
            grouped[group_id].append(candidate)
        else:
            legacy_candidates.append(candidate)

    groups = [grouped[group_id] for group_id in sorted(grouped, key=_group_sort_key(grouped))]
    groups.extend(_batch_items(legacy_candidates, max_candidates_per_request))
    return groups


def _group_sort_key(grouped: dict[str, list[dict[str, object]]]):
    def sort_key(group_id: str) -> tuple[int, str]:
        candidates = grouped[group_id]
        first = min((_candidate_sort_key(candidate)[0] for candidate in candidates), default=0)
        return first, group_id

    return sort_key


def _candidate_group_id(candidates: list[dict[str, object]]) -> str:
    group_ids = {str(candidate.get("attribution_group_id", "")) for candidate in candidates}
    group_ids.discard("")
    return sorted(group_ids)[0] if len(group_ids) == 1 else ""


def _batch_items(items: list[dict[str, object]], batch_size: int) -> list[list[dict[str, object]]]:
    if batch_size <= 0:
        return [items]
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


def prepare_annotation_prompt_requests(
    coarse_beats_path: Path,
    turns_path: Path,
    output_dir: Path,
    language: str,
    profile_path: Path = Path("docs/superpowers/profiles/yezhen-profile-v0001.md"),
) -> RunSummary:
    profile_brief = load_profile_brief(profile_path)
    turns_by_beat: dict[str, dict[str, object]] = {}
    for turn in read_jsonl(turns_path):
        beat_id = str(turn.get("beat_id", ""))
        if beat_id:
            turns_by_beat[beat_id] = turn
    rows = []
    previous_dialogue_beats: dict[str, list[dict[str, object]]] = defaultdict(list)
    beats = sorted(
        enumerate(read_jsonl(coarse_beats_path)),
        key=lambda item: _beat_sort_key(item[0], item[1]),
    )
    for _, raw_beat in beats:
        beat_id = str(raw_beat.get("beat_id", ""))
        turn = turns_by_beat.get(beat_id, {})
        chapter_id = str(raw_beat.get("chapter_id", ""))
        contextual_beat = build_annotation_contextual_beat(raw_beat, turn, previous_dialogue_beats.get(chapter_id, []))
        rows.append(
            build_annotation_prompt_request(
                contextual_beat,
                turn,
                {"profile_version": "v0001", "brief": profile_brief},
                language,
            )
        )
        if turn.get("target_speech"):
            previous_dialogue_beats[chapter_id].append(raw_beat)

    path = output_dir / "prompt_requests" / "04_annotations.jsonl"
    count = write_jsonl(path, rows)
    return RunSummary(output_dir=output_dir, files_written=[path], counts={"annotation_requests": count})


def build_annotation_prompt_request(
    raw_beat: dict[str, object],
    turn: dict[str, object],
    profile_snapshot: dict[str, object],
    language: str,
) -> dict[str, object]:
    beat_id = str(raw_beat.get("beat_id", ""))
    turn_id = str(turn.get("turn_id", ""))
    profile_version = str(profile_snapshot.get("profile_version", "v0001"))
    prompt = render_prompt(
        "annotation",
        language,
        {
            "profile_snapshot": _json_text(_profile_snapshot_payload(profile_snapshot)),
            "raw_beat": _json_text(_annotation_raw_beat_payload(raw_beat)),
            "sft_turn": _json_text(_annotation_target_speech_payload(turn)),
        },
    )
    return PromptRequest(
        request_id=f"{beat_id}_annotation",
        stage="annotation",
        language=language,
        prompt=prompt,
        metadata={
            "chapter_id": raw_beat.get("chapter_id", turn.get("chapter_id", "")),
            "chapter_title": raw_beat.get("chapter_title", turn.get("chapter_title", "")),
            "beat_id": beat_id,
            "turn_id": turn_id,
            "beat_type": raw_beat.get("beat_type", ""),
            "source_text": raw_beat.get("source_text", ""),
            "annotation_source_text": raw_beat.get("annotation_source_text", raw_beat.get("source_text", "")),
            "source_speech_segments": turn.get("source_speech_segments", []),
            "profile_version": profile_version,
        },
    ).to_json()


def _annotation_raw_beat_payload(raw_beat: dict[str, object]) -> dict[str, object]:
    payload = {
        "chapter_title": raw_beat.get("chapter_title", ""),
        "source_text": raw_beat.get("source_text", ""),
    }
    prior_context_text = str(raw_beat.get("prior_context_text", "")).strip()
    if prior_context_text:
        payload["prior_context_text"] = prior_context_text
    return payload


def build_annotation_contextual_beat(
    raw_beat: dict[str, object],
    turn: dict[str, object],
    previous_dialogue_beats: list[dict[str, object]],
    short_source_threshold: int = 60,
    max_previous_dialogue_beats: int = 2,
    max_context_chars: int = 1400,
) -> dict[str, object]:
    source_text = str(raw_beat.get("source_text", ""))
    target_speech = str(turn.get("target_speech", ""))
    if not target_speech or len(source_text) >= short_source_threshold or not previous_dialogue_beats:
        return raw_beat

    context_parts = [
        str(beat.get("source_text", "")).strip()
        for beat in previous_dialogue_beats[-max_previous_dialogue_beats:]
        if str(beat.get("source_text", "")).strip()
    ]
    prior_context_text = "\n\n".join(part for part in context_parts if part)
    annotation_source_text = "\n\n".join(part for part in [prior_context_text, source_text.strip()] if part)
    if len(annotation_source_text) > max_context_chars:
        annotation_source_text = annotation_source_text[-max_context_chars:].lstrip()
    return {
        **raw_beat,
        "prior_context_text": prior_context_text,
        "annotation_source_text": annotation_source_text,
    }


def _beat_sort_key(index: int, beat: dict[str, object]) -> tuple[str, int, int]:
    value = beat.get("source_start_char", "")
    try:
        start = int(value)
    except (TypeError, ValueError):
        start = 10**12 + index
    return str(beat.get("chapter_id", "")), start, index


def _annotation_target_speech_payload(turn: dict[str, object]) -> dict[str, object] | None:
    target_speech = str(turn.get("target_speech", ""))
    if not target_speech:
        return None
    return {
        "target_speech": target_speech,
    }


def prepare_profile_revision_prompt_requests(
    coarse_beats_path: Path,
    annotations_path: Path,
    output_dir: Path,
    language: str,
    profile_path: Path = Path("docs/superpowers/profiles/yezhen-profile-v0001.md"),
) -> RunSummary:
    profile_brief = load_profile_brief(profile_path)
    beats_by_id = {str(beat.get("beat_id", "")): beat for beat in read_jsonl(coarse_beats_path)}
    annotations = sorted(
        read_jsonl(annotations_path),
        key=lambda annotation: (
            str(annotation.get("chapter_id", "")),
            int(beats_by_id.get(str(annotation.get("beat_id", "")), {}).get("source_start_char", 0) or 0),
        ),
    )
    rows = []
    for annotation in annotations:
        beat_id = str(annotation.get("beat_id", ""))
        raw_beat = beats_by_id.get(beat_id, {})
        rows.append(
            build_profile_revision_prompt_request(
                raw_beat,
                annotation,
                {"profile_version": "v0001", "brief": profile_brief},
                language,
            )
        )

    path = output_dir / "prompt_requests" / "05_profile_revisions.jsonl"
    count = write_jsonl(path, rows)
    return RunSummary(output_dir=output_dir, files_written=[path], counts={"profile_revision_requests": count})


def build_profile_revision_prompt_request(
    raw_beat: dict[str, object],
    annotation: dict[str, object],
    profile_snapshot: dict[str, object],
    language: str,
) -> dict[str, object]:
    beat_id = str(annotation.get("beat_id", raw_beat.get("beat_id", "")))
    profile_version = str(profile_snapshot.get("profile_version", "v0001"))
    prompt = render_prompt(
        "profile_revision",
        language,
        {
            "profile_snapshot": _json_text(_profile_snapshot_payload(profile_snapshot)),
            "raw_beat": _json_text(_annotation_raw_beat_payload(raw_beat)),
            "annotation": _json_text(_profile_revision_annotation_payload(annotation)),
        },
    )
    return PromptRequest(
        request_id=f"{beat_id}_profile_revision",
        stage="profile_revision",
        language=language,
        prompt=prompt,
        metadata={
            "chapter_id": annotation.get("chapter_id", raw_beat.get("chapter_id", "")),
            "chapter_title": annotation.get("chapter_title", raw_beat.get("chapter_title", "")),
            "beat_id": beat_id,
            "annotation_id": annotation.get("annotation_id", ""),
            "profile_version": profile_version,
        },
    ).to_json()


def prepare_sft_message_prompt_requests(
    turns_path: Path,
    annotations_path: Path,
    output_dir: Path,
    language: str,
    profile_path: Path = Path("docs/superpowers/profiles/yezhen-profile-v0001.md"),
    profile_snapshots_path: Path | None = None,
) -> RunSummary:
    profile_brief = load_profile_brief(profile_path)
    annotations_by_beat = {str(annotation.get("beat_id", "")): annotation for annotation in read_jsonl(annotations_path)}
    annotations_by_turn = {str(annotation.get("turn_id", "")): annotation for annotation in read_jsonl(annotations_path)}
    audit_path = annotations_path.with_name("annotation_audit.jsonl")
    annotation_audits = read_jsonl(audit_path) if audit_path.exists() else []
    audits_by_beat = {str(audit.get("beat_id", "")): audit for audit in annotation_audits}
    audits_by_turn = {str(audit.get("turn_id", "")): audit for audit in annotation_audits}
    snapshots_by_beat = {}
    if profile_snapshots_path is not None and profile_snapshots_path.exists():
        snapshots_by_beat = {str(snapshot.get("beat_id", "")): snapshot for snapshot in read_jsonl(profile_snapshots_path)}
    rows = []
    for turn in read_jsonl(turns_path):
        turn_id = str(turn.get("turn_id", ""))
        beat_id = str(turn.get("beat_id", ""))
        annotation = annotations_by_beat.get(beat_id, annotations_by_turn.get(turn_id, {}))
        target_speech = str(turn.get("target_speech", ""))
        if not target_speech or not annotation:
            continue
        profile_snapshot = snapshots_by_beat.get(beat_id, {"profile_version": "v0001", "brief": profile_brief})
        annotation_audit = audits_by_beat.get(beat_id, audits_by_turn.get(turn_id, {}))
        current_scene_text = _sft_current_scene_text(annotation, annotation_audit)
        prompt = render_prompt(
            "sft_messages",
            language,
            {
                "brief": str(profile_snapshot.get("brief", "")) if isinstance(profile_snapshot, dict) else profile_brief,
                "current_scene_text": current_scene_text,
                "yezhen_analysis": _json_text(_sft_yezhen_analysis_payload(annotation)),
                "target_speech": target_speech,
            },
        )
        rows.append(
            PromptRequest(
                request_id=f"{turn_id}_sft_messages",
                stage="sft_messages",
                language=language,
                prompt=prompt,
                metadata={
                    "chapter_id": turn.get("chapter_id", ""),
                    "chapter_title": turn.get("chapter_title", ""),
                    "beat_id": beat_id,
                    "turn_id": turn_id,
                    "annotation_id": annotation.get("annotation_id", ""),
                    "profile_version": profile_snapshot.get("profile_version", "v0001")
                    if isinstance(profile_snapshot, dict)
                    else "v0001",
                },
            ).to_json()
        )

    path = output_dir / "prompt_requests" / "06_sft_messages.jsonl"
    count = write_jsonl(path, rows)
    return RunSummary(output_dir=output_dir, files_written=[path], counts={"sft_message_requests": count})


def prepare_system_context_prompt_requests(
    turns_path: Path,
    coarse_beats_path: Path,
    output_dir: Path,
    language: str,
) -> RunSummary:
    beats_by_id = {str(beat.get("beat_id", "")): beat for beat in read_jsonl(coarse_beats_path)}
    beats_by_chapter = _beats_by_chapter(coarse_beats_path)
    rows = []
    for turn in read_jsonl(turns_path):
        target_speech = str(turn.get("target_speech", ""))
        turn_id = str(turn.get("turn_id", ""))
        beat_id = str(turn.get("beat_id", ""))
        if not target_speech or not turn_id:
            continue
        beat = beats_by_id.get(beat_id, {})
        chapter_id = str(turn.get("chapter_id", beat.get("chapter_id", "")))
        source_parts = _source_parts_for_turn(turn, beat)
        chapter_context_before_target = _chapter_context_before_target(
            beats_by_chapter.get(chapter_id, []),
            beat,
            source_parts["source_before_target"],
        )
        prompt = render_prompt(
            "system_context",
            language,
            {
                "chapter_id": chapter_id,
                "chapter_title": str(turn.get("chapter_title", beat.get("chapter_title", ""))),
                "target_character": "叶筝",
                "fixed_profile": FIXED_PROFILE,
                "fixed_background": FIXED_BACKGROUND,
                "chapter_context_before_target": chapter_context_before_target,
            },
        )
        rows.append(
            PromptRequest(
                request_id=f"{turn_id}_system_context",
                stage="system_context",
                language=language,
                prompt=prompt,
                metadata={
                    "system_id": turn_id,
                    "chapter_id": chapter_id,
                    "chapter_title": turn.get("chapter_title", beat.get("chapter_title", "")),
                    "beat_id": beat_id,
                    "turn_id": turn_id,
                    "target_speech": target_speech,
                    "source_chapter_context_before_target": chapter_context_before_target,
                    **source_parts,
                },
            ).to_json()
        )

    path = output_dir / "prompt_requests" / "04_system_contexts.jsonl"
    count = write_jsonl(path, rows)
    return RunSummary(output_dir=output_dir, files_written=[path], counts={"system_context_requests": count})


def prepare_user_context_prompt_requests(
    turns_path: Path,
    coarse_beats_path: Path,
    system_contexts_path: Path,
    output_dir: Path,
    language: str,
) -> RunSummary:
    _ = system_contexts_path
    beats_by_id = {str(beat.get("beat_id", "")): beat for beat in read_jsonl(coarse_beats_path)}
    beats_by_chapter = _beats_by_chapter(coarse_beats_path)
    rows = []
    for turn in read_jsonl(turns_path):
        target_speech = str(turn.get("target_speech", ""))
        turn_id = str(turn.get("turn_id", ""))
        beat_id = str(turn.get("beat_id", ""))
        if not target_speech or not turn_id:
            continue
        beat = beats_by_id.get(beat_id, {})
        chapter_id = str(turn.get("chapter_id", beat.get("chapter_id", "")))
        source_parts = _source_parts_for_turn(turn, beat)
        prompt = render_prompt(
            "user_context",
            language,
            {
                "prior_visible_context": _prior_visible_context_for_short_source(
                    beats_by_chapter.get(chapter_id, []),
                    beat,
                    source_parts["source_before_target"],
                ),
                "visible_source_before_target": source_parts["source_before_target"],
                "forbidden_target_speech": target_speech,
            },
        )
        rows.append(
            PromptRequest(
                request_id=f"{turn_id}_user_context",
                stage="user_context",
                language=language,
                prompt=prompt,
                metadata={
                    "system_id": turn_id,
                    "chapter_id": chapter_id,
                    "chapter_title": turn.get("chapter_title", beat.get("chapter_title", "")),
                    "beat_id": beat_id,
                    "turn_id": turn_id,
                    "target_speech": target_speech,
                    **source_parts,
                },
            ).to_json()
        )

    path = output_dir / "prompt_requests" / "05_user_contexts.jsonl"
    count = write_jsonl(path, rows)
    return RunSummary(output_dir=output_dir, files_written=[path], counts={"user_context_requests": count})


def _beats_by_chapter(coarse_beats_path: Path) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for beat in read_jsonl(coarse_beats_path):
        grouped[str(beat.get("chapter_id", ""))].append(beat)
    for chapter_id, beats in grouped.items():
        grouped[chapter_id] = sorted(beats, key=lambda beat: int(beat.get("source_start_char", 0) or 0))
    return grouped


def _prior_visible_context_for_short_source(
    chapter_beats: list[dict[str, object]],
    current_beat: dict[str, object],
    source_before_target: str,
    short_source_threshold: int = 60,
    max_previous_beats: int = 2,
    max_context_chars: int = 1000,
) -> str:
    if not current_beat or len(source_before_target.strip()) >= short_source_threshold:
        return ""
    current_start = int(current_beat.get("source_start_char", 0) or 0)
    previous = [
        beat
        for beat in chapter_beats
        if int(beat.get("source_start_char", 0) or 0) < current_start and str(beat.get("source_text", "")).strip()
    ]
    context_parts = [str(beat.get("source_text", "")).strip() for beat in previous[-max_previous_beats:]]
    context = "\n\n".join(part for part in context_parts if part)
    if len(context) <= max_context_chars:
        return context
    return context[-max_context_chars:].lstrip()


def _chapter_context_before_target(
    chapter_beats: list[dict[str, object]],
    current_beat: dict[str, object],
    source_before_target: str,
) -> str:
    if not current_beat:
        return source_before_target.strip()
    current_start = int(current_beat.get("source_start_char", 0) or 0)
    context_parts = [
        str(beat.get("source_text", "")).strip()
        for beat in chapter_beats
        if int(beat.get("source_start_char", 0) or 0) < current_start and str(beat.get("source_text", "")).strip()
    ]
    context_parts.append(source_before_target.strip())
    return "\n\n".join(part for part in context_parts if part)


def prepare_assistant_response_prompt_requests(
    turns_path: Path,
    coarse_beats_path: Path,
    system_contexts_path: Path,
    user_contexts_path: Path,
    output_dir: Path,
    language: str,
) -> RunSummary:
    _ = (system_contexts_path, user_contexts_path)
    beats_by_id = {str(beat.get("beat_id", "")): beat for beat in read_jsonl(coarse_beats_path)}
    beats_by_chapter = _beats_by_chapter(coarse_beats_path)
    rows = []
    for turn in read_jsonl(turns_path):
        target_speech = str(turn.get("target_speech", ""))
        turn_id = str(turn.get("turn_id", ""))
        beat_id = str(turn.get("beat_id", ""))
        if not target_speech or not turn_id:
            continue
        beat = beats_by_id.get(beat_id, {})
        chapter_id = str(turn.get("chapter_id", beat.get("chapter_id", "")))
        source_parts = _source_parts_for_turn(turn, beat)
        prompt = render_prompt(
            "assistant_response",
            language,
            {
                "target_character": "叶筝",
                "fixed_profile": FIXED_PROFILE,
                "prior_visible_context": _prior_visible_context_for_short_source(
                    beats_by_chapter.get(chapter_id, []),
                    beat,
                    source_parts["source_before_target"],
                ),
                "source_before_target": source_parts["source_before_target"],
                "target_speech": target_speech,
                "post_speech_attribution_evidence": source_parts["source_after_target_for_attribution"],
            },
        )
        rows.append(
            PromptRequest(
                request_id=f"{turn_id}_assistant_response",
                stage="assistant_response",
                language=language,
                prompt=prompt,
                metadata={
                    "system_id": turn_id,
                    "chapter_id": chapter_id,
                    "chapter_title": turn.get("chapter_title", beat.get("chapter_title", "")),
                    "beat_id": beat_id,
                    "turn_id": turn_id,
                    "target_speech": target_speech,
                    **source_parts,
                },
            ).to_json()
        )

    path = output_dir / "prompt_requests" / "06_assistant_responses.jsonl"
    count = write_jsonl(path, rows)
    return RunSummary(output_dir=output_dir, files_written=[path], counts={"assistant_response_requests": count})


def prepare_user_repair_prompt_requests(
    draft_messages_path: Path,
    output_dir: Path,
    language: str,
) -> RunSummary:
    rows = []
    for row in read_jsonl(draft_messages_path):
        report = check_sft_message(row)
        if report["checks"].get("no_target_leakage_in_user", True):
            continue
        turn = row.get("sft_turn", {})
        annotation = row.get("annotation", {})
        annotation_audit = row.get("annotation_audit", {})
        if not isinstance(turn, dict) or not isinstance(annotation, dict):
            continue
        target_speech = str(turn.get("target_speech", ""))
        if not target_speech:
            continue
        prompt = render_prompt(
            "user_repair",
            language,
            {
                "current_user_content": _message_content(row, "user"),
                "current_scene_text": _sft_current_scene_text(annotation, annotation_audit),
                "yezhen_analysis": _json_text(_sft_yezhen_analysis_payload(annotation)),
                "target_speech": target_speech,
            },
        )
        turn_id = str(row.get("turn_id", turn.get("turn_id", "")))
        rows.append(
            PromptRequest(
                request_id=f"{turn_id}_user_repair",
                stage="user_repair",
                language=language,
                prompt=prompt,
                metadata={
                    "chapter_id": row.get("chapter_id", turn.get("chapter_id", "")),
                    "chapter_title": row.get("chapter_title", turn.get("chapter_title", "")),
                    "beat_id": row.get("beat_id", turn.get("beat_id", "")),
                    "turn_id": turn_id,
                    "target_speech": target_speech,
                },
            ).to_json()
        )

    path = output_dir / "prompt_requests" / "07_user_repairs.jsonl"
    count = write_jsonl(path, rows)
    return RunSummary(output_dir=output_dir, files_written=[path], counts={"user_repair_requests": count})


def _message_content(row: dict[str, object], role: str) -> str:
    messages = row.get("messages", [])
    if not isinstance(messages, list):
        return ""
    for message in messages:
        if isinstance(message, dict) and message.get("role") == role:
            return str(message.get("content", ""))
    return ""


def _system_context_prompt_payload(system_context: dict[str, object]) -> dict[str, object]:
    return {
        "current_scenario": system_context.get("current_scenario", ""),
        "other_characters": system_context.get("other_characters", ""),
    }


def _source_parts_for_turn(turn: dict[str, object], beat: dict[str, object]) -> dict[str, str]:
    source_text = str(beat.get("source_text", ""))
    target_speech = str(turn.get("target_speech", ""))
    source_segments = [segment for segment in turn.get("source_speech_segments", []) if isinstance(segment, dict)]
    beat_start = int(beat.get("source_start_char", 0) or 0)
    before = ""
    after = ""
    if source_segments:
        first_start = _int_value(source_segments[0].get("source_start_char"), beat_start)
        last_end = _int_value(source_segments[-1].get("source_end_char"), first_start)
        rel_start = max(0, first_start - beat_start)
        rel_end = max(rel_start, last_end - beat_start)
        before = _strip_trailing_open_quote(source_text[:rel_start].strip())
        after = source_text[rel_end:].strip()
    elif target_speech and target_speech in source_text:
        index = source_text.find(target_speech)
        before = _strip_trailing_open_quote(source_text[:index].strip())
        after = source_text[index + len(target_speech) :].strip()
    else:
        before = source_text.strip()
    return {
        "source_text": source_text,
        "source_before_target": before,
        "source_after_target_for_attribution": after[:500],
    }


def _strip_trailing_open_quote(text: str) -> str:
    return text.rstrip().rstrip("“\"'「『《").rstrip()


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _speaker_candidate_payload(candidate: dict[str, object]) -> list[object]:
    return [
        candidate.get("candidate_id", ""),
        candidate.get("source_text", ""),
    ]


def _speaker_group_payload(candidates: list[dict[str, object]]) -> dict[str, object]:
    source_context = ""
    for candidate in candidates:
        source_context = str(candidate.get("source_context", ""))
        if source_context:
            break
    return {
        "source_context": source_context,
        "target_quotes": [_speaker_candidate_payload(candidate) for candidate in candidates],
    }


def _profile_snapshot_payload(profile_snapshot: dict[str, object]) -> dict[str, object]:
    return {
        "brief": profile_snapshot.get("brief", ""),
    }


def _profile_revision_annotation_payload(annotation: dict[str, object]) -> dict[str, object]:
    return {
        "scene_summary": annotation.get("scene_summary", ""),
        "participants": annotation.get("participants", []),
        "relationship_context": annotation.get("relationship_context", ""),
        "trigger": annotation.get("trigger", ""),
        "yezhen_psychology": annotation.get("yezhen_psychology", {}),
        "response_strategy": annotation.get("response_strategy", ""),
        "role_action_basis": annotation.get("role_action_basis", ""),
    }


def _sft_turn_payload(turn: dict[str, object]) -> dict[str, object]:
    return {
        "target_speech": turn.get("target_speech", ""),
    }


def _sft_yezhen_analysis_payload(annotation: dict[str, object]) -> dict[str, object]:
    return {
        "scene_summary": annotation.get("scene_summary", ""),
        "participants": annotation.get("participants", []),
        "relationship_context": annotation.get("relationship_context", ""),
        "trigger": annotation.get("trigger", ""),
        "yezhen_psychology": annotation.get("yezhen_psychology", {}),
        "response_strategy": annotation.get("response_strategy", ""),
        "role_action_basis": annotation.get("role_action_basis", ""),
    }


def _sft_annotation_payload(annotation: dict[str, object]) -> dict[str, object]:
    return _sft_yezhen_analysis_payload(annotation)


def _sft_current_scene_text(annotation: dict[str, object], annotation_audit: dict[str, object]) -> str:
    source = annotation_audit.get("source", {}) if isinstance(annotation_audit, dict) else {}
    if isinstance(source, dict):
        annotation_source_text = str(source.get("annotation_source_text", "")).strip()
        if annotation_source_text:
            return annotation_source_text
        source_text = str(source.get("source_text", "")).strip()
        if source_text:
            return source_text
    annotation_source = annotation.get("source", {})
    if isinstance(annotation_source, dict):
        source_text = str(annotation_source.get("source_text", "")).strip()
        if source_text:
            return source_text
    return str(annotation.get("source_text", "")).strip()
