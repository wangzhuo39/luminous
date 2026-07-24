from __future__ import annotations
from pathlib import Path

from luminous.training.pipeline.jsonl import read_jsonl, write_jsonl
from luminous.training.pipeline.models import RunSummary
from luminous.training.pipeline.profile import apply_profile_revision, load_profile_brief, profile_revision_applies
from luminous.training.pipeline.role_setup import build_system_content
from luminous.training.pipeline.qa import check_assistant_response, check_sft_message, check_system_context_response


def audit_path_for_annotations(output_path: Path) -> Path:
    if output_path.name == "annotations.jsonl":
        return output_path.with_name("annotation_audit.jsonl")
    return output_path.with_name(f"{output_path.stem}_audit.jsonl")


def qa_sft_file(input_path: Path, output_dir: Path) -> RunSummary:
    rows = read_jsonl(input_path)
    trainable_rows: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    her_rows: list[dict[str, object]] = []

    for row in rows:
        report = check_sft_message(row)
        enriched = {**row, "qa": report}
        if report["trainable"] and not report["needs_human_review"]:
            trainable_rows.append(enriched)
            messages = row.get("messages", [])
            if isinstance(messages, list):
                her_rows.append({"messages": messages})
        else:
            review_rows.append(enriched)

    trainable_path = output_dir / "sft_messages_trainable.jsonl"
    review_path = output_dir / "review_queue.jsonl"
    her_path = output_dir / "sft_messages_her.jsonl"
    write_jsonl(trainable_path, trainable_rows)
    write_jsonl(review_path, review_rows)
    write_jsonl(her_path, her_rows)
    return RunSummary(
        output_dir=output_dir,
        files_written=[trainable_path, review_path, her_path],
        counts={"trainable": len(trainable_rows), "review": len(review_rows), "her": len(her_rows)},
    )


def _trace(response: dict[str, object]) -> dict[str, object]:
    request_id = str(response.get("request_id", ""))
    return {
        "prompt_request_id": request_id,
        "llm_response_id": request_id,
        "stage": response.get("stage", ""),
    }


def _metadata(response: dict[str, object]) -> dict[str, object]:
    metadata = response.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _is_successful_llm_response(response: dict[str, object]) -> bool:
    return (
        isinstance(response.get("response_json"), dict)
        and not response.get("error_type")
        and not response.get("error")
        and not response.get("parse_error")
    )


def qa_modular_response_file(response_path: Path, output_path: Path) -> RunSummary:
    rows: list[dict[str, object]] = []
    for response in read_jsonl(response_path):
        if not _is_successful_llm_response(response):
            continue
        stage = str(response.get("stage", ""))
        if stage == "system_context":
            report = check_system_context_response(response)
        elif stage == "assistant_response":
            report = check_assistant_response(response)
        else:
            continue
        row = {
            "request_id": report["request_id"],
            "stage": report["stage"],
            "needs_review": report["needs_review"],
            "review_reasons": report["review_reasons"],
            "warning_reasons": report.get("warning_reasons", []),
            "checks": report["checks"],
        }
        if report.get("unsupported_action_markers"):
            row["unsupported_action_markers"] = report["unsupported_action_markers"]
        rows.append(row)
    count = write_jsonl(output_path, rows)
    return RunSummary(
        output_dir=output_path.parent,
        files_written=[output_path],
        counts={
            "qa_rows": count,
            "review": sum(1 for row in rows if row.get("needs_review")),
            "warning": sum(1 for row in rows if row.get("warning_reasons")),
        },
    )


def extract_speaker_attributions(response_path: Path, output_path: Path) -> int:
    rows: list[dict[str, object]] = []
    for response in read_jsonl(response_path):
        if not _is_successful_llm_response(response):
            continue
        response_json = response.get("response_json", {})
        if not isinstance(response_json, dict):
            continue
        metadata = _metadata(response)
        attribution_items = response_json.get("attributions", response_json.get("rows", response_json.get("results")))
        if not isinstance(attribution_items, list):
            attribution_items = [response_json]
        for item in attribution_items:
            normalized_item = _normalize_speaker_attribution_item(item)
            if not normalized_item:
                continue
            candidate_id = str(normalized_item.get("candidate_id", metadata.get("candidate_id", "")))
            confidence = str(normalized_item.get("speaker_confidence", normalized_item.get("confidence", "unknown")))
            speaker = str(normalized_item.get("speaker", "unknown"))
            needs_review, review_reasons = _speaker_review_fields(confidence, speaker)
            rows.append(
                {
                    "attribution_id": str(normalized_item.get("attribution_id", f"{candidate_id}_attr")),
                    "candidate_id": candidate_id,
                    "chapter_id": normalized_item.get("chapter_id", metadata.get("chapter_id", "")),
                    "chapter_title": normalized_item.get("chapter_title", metadata.get("chapter_title", "")),
                    "is_yezhen_speech": _bool_value(normalized_item.get("is_yezhen_speech", False)),
                    "speaker": speaker,
                    "speaker_confidence": confidence,
                    "needs_human_review": needs_review,
                    "review_reasons": review_reasons,
                    "trace": _trace(response),
                }
            )
    return write_jsonl(output_path, rows)


def _normalize_speaker_attribution_item(item: object) -> dict[str, object]:
    if isinstance(item, dict):
        return item
    if isinstance(item, (list, tuple)) and len(item) >= 4:
        return {
            "candidate_id": item[0],
            "is_yezhen_speech": item[1],
            "speaker": item[2],
            "confidence": item[3],
        }
    return {}


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "是"}
    return bool(value)


def _speaker_review_fields(confidence: str, speaker: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    normalized_confidence = confidence.strip().lower()
    if speaker.strip().lower() in {"", "unknown", "未知"}:
        reasons.append("speaker_unknown")
    if normalized_confidence in {"", "unknown", "low", "低"}:
        reasons.append("speaker_confidence_low")
    else:
        try:
            if float(normalized_confidence) < 0.8:
                reasons.append("speaker_confidence_low")
        except ValueError:
            pass
    return bool(reasons), reasons


def extract_annotations(response_path: Path, output_path: Path) -> int:
    rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    for response in read_jsonl(response_path):
        if not _is_successful_llm_response(response):
            continue
        response_json = response.get("response_json", {})
        if not isinstance(response_json, dict):
            continue
        metadata = _metadata(response)
        beat_id = str(response_json.get("beat_id", metadata.get("beat_id", "")))
        turn_id = str(response_json.get("turn_id", metadata.get("turn_id", "")))
        default_id = f"{beat_id}_ann" if beat_id else f"{turn_id}_ann"
        annotation_id = str(response_json.get("annotation_id", default_id))
        normalized = _normalize_annotation_response(response_json)
        row = {
            **normalized,
            "annotation_id": annotation_id,
            "chapter_id": normalized.get("chapter_id", metadata.get("chapter_id", "")),
            "chapter_title": normalized.get("chapter_title", metadata.get("chapter_title", "")),
            "beat_id": normalized.get("beat_id", beat_id),
            "turn_id": turn_id,
            "beat_type": normalized.get("beat_type", metadata.get("beat_type", "")),
            "profile_version": normalized.get("profile_version", metadata.get("profile_version", "")),
        }
        rows.append(row)
        audit_rows.append(_build_annotation_audit_row(row, metadata, response))
    count = write_jsonl(output_path, rows)
    write_jsonl(audit_path_for_annotations(output_path), audit_rows)
    return count


def _build_annotation_audit_row(
    annotation: dict[str, object],
    metadata: dict[str, object],
    response: dict[str, object],
) -> dict[str, object]:
    response_json = response.get("response_json", {})
    if not isinstance(response_json, dict):
        response_json = {}
    source_text = str(metadata.get("source_text", "")).strip()
    if not source_text:
        source = response_json.get("source")
        if isinstance(source, dict):
            source_text = str(source.get("source_text", "")).strip()
        if not source_text:
            source_text = str(response_json.get("source_text", "")).strip()
    annotation_source_text = str(metadata.get("annotation_source_text", source_text)).strip()

    speech_segments = metadata.get("source_speech_segments", [])
    if not speech_segments:
        speech_segments = response_json.get("source_speech_segments", [])
    if not isinstance(speech_segments, list):
        speech_segments = []
    literal = {
        "yezhen_speech_segments": speech_segments,
        "yezhen_action_segments": [],
        "yezhen_inner_state_segments": [],
        "external_observation_segments": [],
        "other_speech_segments": [],
    }
    has_target_speech = bool(speech_segments)
    return {
        "annotation_id": annotation.get("annotation_id", ""),
        "chapter_id": annotation.get("chapter_id", metadata.get("chapter_id", "")),
        "chapter_title": annotation.get("chapter_title", metadata.get("chapter_title", "")),
        "beat_id": annotation.get("beat_id", metadata.get("beat_id", "")),
        "turn_id": annotation.get("turn_id", metadata.get("turn_id", "")),
        "beat_type": annotation.get("beat_type", metadata.get("beat_type", "")),
        "profile_version": annotation.get("profile_version", metadata.get("profile_version", "")),
        "source": {
            "source_text": source_text,
            "annotation_source_text": annotation_source_text,
        },
        "literal_extraction": literal,
        "training_usage": {
            "eligible_for_sft": has_target_speech,
            "sft_reason": "has target speech" if has_target_speech else "no target speech",
            "eligible_for_profile_update": True,
            "eligible_for_retrieval_memory": True,
        },
        "quality": {
            "future_leakage_risk": False,
            "needs_human_review": False,
        },
        "trace": _trace(response),
    }


def _normalize_annotation_response(response_json: dict[str, object]) -> dict[str, object]:
    psychology = response_json.get("yezhen_psychology", {})
    psychology = psychology if isinstance(psychology, dict) else {}
    normalized_psychology: dict[str, object] = {
        "known_facts": _string_list(psychology.get("known_facts", [])),
        "inner_conflict": _string_value(psychology.get("inner_conflict", "")),
        "hidden_risks": _string_list(psychology.get("hidden_risks", [])),
        "emotional_underlayer": _string_value(psychology.get("emotional_underlayer", "")),
        "intent": _string_value(psychology.get("intent", "")),
    }
    return {
        "scene_summary": _string_value(response_json.get("scene_summary", "")),
        "participants": _string_list(response_json.get("participants", [])),
        "relationship_context": _string_value(response_json.get("relationship_context", "")),
        "trigger": _string_value(response_json.get("trigger", "")),
        "yezhen_psychology": normalized_psychology,
        "response_strategy": _string_value(response_json.get("response_strategy", "")),
        "role_action_basis": _string_value(response_json.get("role_action_basis", "")),
    }


def _string_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "；".join(str(item) for item in value if str(item).strip())
    return str(value)


def _natural_text_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "；".join(part for item in value if (part := _natural_text_value(item).strip()))
    if isinstance(value, dict):
        preferred_keys = (
            "name",
            "姓名",
            "identity",
            "身份",
            "relationship",
            "relation",
            "与叶筝的关系",
            "stance",
            "立场",
            "current_stance",
            "visible_state",
            "state",
            "状态",
        )
        seen: set[str] = set()
        parts: list[str] = []
        for key in preferred_keys:
            if key not in value:
                continue
            seen.add(key)
            part = _natural_text_value(value.get(key, "")).strip()
            if part:
                parts.append(part)
        for key, item in value.items():
            if key in seen:
                continue
            part = _natural_text_value(item).strip()
            if part:
                parts.append(f"{key}：{part}")
        return "，".join(parts)
    return str(value)


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return [str(value)]


def _list_value(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def extract_profile_revisions(response_path: Path, output_path: Path) -> int:
    rows: list[dict[str, object]] = []
    for response in read_jsonl(response_path):
        if not _is_successful_llm_response(response):
            continue
        response_json = response.get("response_json", {})
        if not isinstance(response_json, dict):
            continue
        metadata = _metadata(response)
        beat_id = str(response_json.get("beat_id", metadata.get("beat_id", "")))
        revision_id = str(response_json.get("revision_id", f"{beat_id}_profile_revision"))
        normalized_revision = dict(response_json)
        normalized_revision.pop("evidence", None)
        rows.append(
            {
                **normalized_revision,
                "revision_id": revision_id,
                "beat_id": beat_id,
                "annotation_id": normalized_revision.get("annotation_id", metadata.get("annotation_id", "")),
                "chapter_id": normalized_revision.get("chapter_id", metadata.get("chapter_id", "")),
                "chapter_title": normalized_revision.get("chapter_title", metadata.get("chapter_title", "")),
                "required": _truthy(normalized_revision.get("required", False)),
                "apply_before_next_beat": _truthy(normalized_revision.get("apply_before_next_beat", True)),
                "rerun_current_beat": _truthy(normalized_revision.get("rerun_current_beat", False)),
                "trace": _trace(response),
            }
        )
    return write_jsonl(output_path, rows)


def extract_system_contexts(response_path: Path, output_path: Path) -> int:
    rows: list[dict[str, object]] = []
    for response in read_jsonl(response_path):
        if not _is_successful_llm_response(response):
            continue
        response_json = response.get("response_json", {})
        if not isinstance(response_json, dict):
            continue
        metadata = _metadata(response)
        current_scenario = _natural_text_value(response_json.get("current_scenario", "")).strip()
        other_characters = _natural_text_value(response_json.get("other_characters", "")).strip()
        chapter_id = str(metadata.get("chapter_id", response_json.get("chapter_id", "")))
        system_id = str(response_json.get("system_id", metadata.get("system_id", chapter_id)))
        rows.append(
            {
                "system_id": system_id,
                "chapter_id": chapter_id,
                "chapter_title": response_json.get("chapter_title", metadata.get("chapter_title", "")),
                "beat_id": response_json.get("beat_id", metadata.get("beat_id", "")),
                "turn_id": response_json.get("turn_id", metadata.get("turn_id", "")),
                "scope": response_json.get("scope", "turn"),
                "needs_scene_split": _truthy(response_json.get("needs_scene_split", False)),
                "scene_split_reason": _string_value(response_json.get("scene_split_reason", "")),
                "current_scenario": current_scenario,
                "other_characters": other_characters,
                "system_content": build_system_content(current_scenario, other_characters),
                "source": {
                    "source_text": metadata.get("source_text", ""),
                    "source_before_target": metadata.get("source_before_target", ""),
                    "source_after_target_for_attribution": metadata.get(
                        "source_after_target_for_attribution", ""
                    ),
                },
                "trace": _trace(response),
            }
        )
    return write_jsonl(output_path, rows)


def extract_user_contexts(response_path: Path, output_path: Path) -> int:
    rows: list[dict[str, object]] = []
    for response in read_jsonl(response_path):
        if not _is_successful_llm_response(response):
            continue
        response_json = response.get("response_json", {})
        if not isinstance(response_json, dict):
            continue
        metadata = _metadata(response)
        user_content = _string_value(response_json.get("user_content", "")).strip()
        if not user_content:
            continue
        target_speech = str(metadata.get("target_speech", ""))
        rows.append(
            {
                "turn_id": str(response_json.get("turn_id", metadata.get("turn_id", ""))),
                "beat_id": response_json.get("beat_id", metadata.get("beat_id", "")),
                "chapter_id": response_json.get("chapter_id", metadata.get("chapter_id", "")),
                "chapter_title": response_json.get("chapter_title", metadata.get("chapter_title", "")),
                "system_id": response_json.get("system_id", metadata.get("system_id", "")),
                "user_content": user_content,
                "contains_target_speech": bool(target_speech and target_speech in user_content),
                "uses_second_person_instruction": _truthy(response_json.get("uses_second_person_instruction", False)),
                "source": {
                    "source_text": metadata.get("source_text", ""),
                    "source_before_target": metadata.get("source_before_target", ""),
                    "source_after_target_for_attribution": metadata.get(
                        "source_after_target_for_attribution", ""
                    ),
                },
                "trace": _trace(response),
            }
        )
    return write_jsonl(output_path, rows)


def extract_assistant_responses(response_path: Path, output_path: Path) -> int:
    rows: list[dict[str, object]] = []
    for response in read_jsonl(response_path):
        if not _is_successful_llm_response(response):
            continue
        response_json = response.get("response_json", {})
        if not isinstance(response_json, dict):
            continue
        metadata = _metadata(response)
        target_speech = str(metadata.get("target_speech", ""))
        parts = _assistant_content_parts(response_json, target_speech)
        if not parts["system_thinking"] or not parts["role_thinking"]:
            continue
        rows.append(
            {
                "turn_id": str(response_json.get("turn_id", metadata.get("turn_id", ""))),
                "beat_id": response_json.get("beat_id", metadata.get("beat_id", "")),
                "chapter_id": response_json.get("chapter_id", metadata.get("chapter_id", "")),
                "chapter_title": response_json.get("chapter_title", metadata.get("chapter_title", "")),
                "system_id": response_json.get("system_id", metadata.get("system_id", "")),
                "content_parts": parts,
                "source": {
                    "source_text": metadata.get("source_text", ""),
                    "source_before_target": metadata.get("source_before_target", ""),
                    "source_after_target_for_attribution": metadata.get(
                        "source_after_target_for_attribution", ""
                    ),
                },
                "trace": _trace(response),
            }
        )
    return write_jsonl(output_path, rows)


def assemble_modular_sft_messages(
    system_contexts_path: Path,
    user_contexts_path: Path,
    assistant_responses_path: Path,
    turns_path: Path,
    output_path: Path,
) -> int:
    system_contexts = read_jsonl(system_contexts_path)
    system_by_id = {str(row.get("system_id", "")): row for row in system_contexts}
    system_by_turn = {str(row.get("turn_id", "")): row for row in system_contexts}
    system_by_chapter = {str(row.get("chapter_id", "")): row for row in system_contexts}
    user_by_turn = {str(row.get("turn_id", "")): row for row in read_jsonl(user_contexts_path)}
    assistant_by_turn = {str(row.get("turn_id", "")): row for row in read_jsonl(assistant_responses_path)}
    rows: list[dict[str, object]] = []
    for turn in read_jsonl(turns_path):
        turn_id = str(turn.get("turn_id", ""))
        chapter_id = str(turn.get("chapter_id", ""))
        user_context = user_by_turn.get(turn_id)
        assistant_response = assistant_by_turn.get(turn_id)
        if not isinstance(user_context, dict) or not isinstance(assistant_response, dict):
            continue
        system_id = str(user_context.get("system_id", assistant_response.get("system_id", chapter_id)))
        system_context = system_by_turn.get(turn_id, system_by_id.get(system_id, system_by_chapter.get(chapter_id, {})))
        if not isinstance(system_context, dict) or not system_context:
            continue
        target_speech = str(turn.get("target_speech", ""))
        assistant_parts = assistant_response.get("content_parts", {})
        if not isinstance(assistant_parts, dict):
            continue
        source = assistant_response.get("source") or user_context.get("source") or {}
        source = source if isinstance(source, dict) else {}
        assistant_content = _join_modular_assistant_content(assistant_parts, target_speech)
        rows.append(
            {
                "turn_id": turn_id,
                "chapter_id": turn.get("chapter_id", ""),
                "chapter_title": turn.get("chapter_title", ""),
                "beat_id": turn.get("beat_id", ""),
                "system_id": system_context.get("system_id", system_id),
                "sft_turn": turn,
                "source": source,
                "system_context": _system_context_payload(system_context),
                "user_context": {
                    "user_content": user_context.get("user_content", ""),
                    "contains_target_speech": user_context.get("contains_target_speech", False),
                    "uses_second_person_instruction": user_context.get("uses_second_person_instruction", False),
                },
                "assistant_response": {
                    "content_parts": _assistant_content_parts(assistant_parts, target_speech),
                },
                "messages": [
                    {
                        "role": "system",
                        "content": str(
                            system_context.get(
                                "system_content",
                                build_system_content(
                                    str(system_context.get("current_scenario", "")),
                                    str(system_context.get("other_characters", "")),
                                ),
                            )
                        ),
                    },
                    {"role": "user", "content": str(user_context.get("user_content", ""))},
                    {
                        "role": "assistant",
                        "content": assistant_content,
                        "content_parts": _assistant_content_parts(assistant_parts, target_speech),
                    },
                ],
                "trace": {
                    "prompt_request_id": assistant_response.get("trace", {}).get("prompt_request_id", "")
                    if isinstance(assistant_response.get("trace"), dict)
                    else "",
                    "stage": "modular_assembly",
                    "system_context": system_context.get("trace", {}),
                    "user_context": user_context.get("trace", {}),
                    "assistant_response": assistant_response.get("trace", {}),
                },
            }
        )
    return write_jsonl(output_path, rows)


def build_profile_snapshots(
    coarse_beats_path: Path,
    revisions_path: Path,
    output_path: Path,
    profile_path: Path = Path("docs/superpowers/profiles/yezhen-profile-v0001.md"),
) -> int:
    current_brief = load_profile_brief(profile_path)
    version_index = 1
    current_revision_id = ""
    revisions_by_beat = {str(revision.get("beat_id", "")): revision for revision in read_jsonl(revisions_path)}
    rows: list[dict[str, object]] = []

    for beat in sorted(
        read_jsonl(coarse_beats_path),
        key=lambda row: (str(row.get("chapter_id", "")), int(row.get("source_start_char", 0) or 0)),
    ):
        beat_id = str(beat.get("beat_id", ""))
        rows.append(
            {
                "beat_id": beat_id,
                "chapter_id": beat.get("chapter_id", ""),
                "chapter_title": beat.get("chapter_title", ""),
                "profile_version": f"v{version_index:04d}",
                "brief": current_brief,
                "source_revision_id": current_revision_id,
            }
        )
        revision = revisions_by_beat.get(beat_id, {})
        if profile_revision_applies(revision):
            next_brief = apply_profile_revision(current_brief, revision)
            if next_brief != current_brief:
                version_index += 1
                current_brief = next_brief
                current_revision_id = str(revision.get("revision_id", ""))

    return write_jsonl(output_path, rows)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "是"}
    return False


def extract_sft_messages(
    response_path: Path,
    annotations_path: Path,
    output_path: Path,
    turns_path: Path | None = None,
) -> int:
    annotations = read_jsonl(annotations_path)
    annotations_by_beat = {str(annotation.get("beat_id", "")): annotation for annotation in annotations}
    annotations_by_turn = {str(annotation.get("turn_id", "")): annotation for annotation in annotations}
    audit_path = audit_path_for_annotations(annotations_path)
    annotation_audits = read_jsonl(audit_path) if audit_path.exists() else []
    audits_by_beat = {str(audit.get("beat_id", "")): audit for audit in annotation_audits}
    audits_by_turn = {str(audit.get("turn_id", "")): audit for audit in annotation_audits}
    turns_by_id: dict[str, dict[str, object]] = {}
    if turns_path is not None and turns_path.exists():
        turns_by_id = {str(turn.get("turn_id", "")): turn for turn in read_jsonl(turns_path)}

    rows: list[dict[str, object]] = []
    for response in read_jsonl(response_path):
        if not _is_successful_llm_response(response):
            continue
        response_json = response.get("response_json", {})
        if not isinstance(response_json, dict):
            continue
        metadata = _metadata(response)
        turn_id = str(response_json.get("turn_id", metadata.get("turn_id", "")))
        beat_id = str(response_json.get("beat_id", metadata.get("beat_id", "")))
        annotation = annotations_by_beat.get(beat_id, annotations_by_turn.get(turn_id, {}))
        if not annotation:
            continue
        annotation_audit = audits_by_beat.get(beat_id, audits_by_turn.get(turn_id, {}))
        sft_turn = turns_by_id.get(turn_id)
        if not isinstance(sft_turn, dict):
            continue
        normalized_response_json = _normalize_sft_response_json(response_json, sft_turn)
        if not normalized_response_json:
            continue
        rows.append(
            {
                **normalized_response_json,
                "turn_id": turn_id,
                "chapter_id": normalized_response_json.get("chapter_id", metadata.get("chapter_id", "")),
                "chapter_title": normalized_response_json.get("chapter_title", metadata.get("chapter_title", "")),
                "beat_id": beat_id,
                "annotation_id": normalized_response_json.get("annotation_id", metadata.get("annotation_id", "")),
                "profile_version": normalized_response_json.get("profile_version", metadata.get("profile_version", "")),
                "sft_turn": sft_turn,
                "annotation": annotation,
                "annotation_audit": annotation_audit,
                "trace": _trace(response),
            }
        )
    return write_jsonl(output_path, rows)


def apply_user_repairs(draft_messages_path: Path, repair_response_path: Path, output_path: Path) -> int:
    repairs_by_turn_id: dict[str, dict[str, object]] = {}
    for response in read_jsonl(repair_response_path):
        if not _is_successful_llm_response(response):
            continue
        response_json = response.get("response_json", {})
        if not isinstance(response_json, dict):
            continue
        user_content = _string_value(response_json.get("user_content", "")).strip()
        if not user_content:
            continue
        metadata = _metadata(response)
        turn_id = str(response_json.get("turn_id", metadata.get("turn_id", "")))
        if not turn_id:
            continue
        target_speech = str(metadata.get("target_speech", ""))
        if target_speech and target_speech in user_content:
            continue
        repairs_by_turn_id[turn_id] = {
            "user_content": user_content,
            "trace": _trace(response),
        }

    repaired_rows = []
    for row in read_jsonl(draft_messages_path):
        turn_id = str(row.get("turn_id", ""))
        repair = repairs_by_turn_id.get(turn_id)
        if not repair:
            repaired_rows.append(row)
            continue
        messages = _replace_user_message(row.get("messages", []), str(repair["user_content"]))
        trace = row.get("trace", {})
        trace = trace if isinstance(trace, dict) else {}
        repaired_rows.append(
            {
                **row,
                "messages": messages,
                "trace": {
                    **trace,
                    "user_repair": repair["trace"],
                },
            }
        )
    return write_jsonl(output_path, repaired_rows)


def _replace_user_message(messages: object, user_content: str) -> list[object]:
    if not isinstance(messages, list):
        return []
    repaired_messages = []
    replaced = False
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "user":
            repaired_messages.append({**message, "content": user_content})
            replaced = True
        else:
            repaired_messages.append(message)
    if replaced:
        return repaired_messages
    return repaired_messages


def _normalize_sft_response_json(response_json: dict[str, object], sft_turn: dict[str, object]) -> dict[str, object]:
    normalized = dict(response_json)
    messages = response_json.get("messages", [])
    if not isinstance(messages, list):
        return {}

    target_speech = str(sft_turn.get("target_speech", ""))
    normalized_messages: list[object] = []
    structured_assistant_seen = False
    for message in messages:
        if not isinstance(message, dict):
            return {}
        if message.get("role") != "assistant":
            normalized_messages.append(message)
            continue
        content = message.get("content", "")
        if not isinstance(content, dict):
            return {}
        structured_assistant_seen = True
        message = {
            **message,
            "content": _join_structured_assistant_content(content, target_speech),
            "content_parts": _assistant_content_parts(content, target_speech),
        }
        normalized_messages.append(message)
    if not structured_assistant_seen:
        return {}
    normalized["messages"] = normalized_messages
    return normalized


def _assistant_content_parts(content: dict[str, object], target_speech: str) -> dict[str, str]:
    return {
        "system_thinking": _string_value(content.get("system_thinking", "")),
        "role_thinking": _string_value(content.get("role_thinking", "")),
        "role_action": _string_value(content.get("role_action", "")),
        "target_speech": target_speech or _string_value(content.get("target_speech", "")),
    }


def _join_structured_assistant_content(content: dict[str, object], target_speech: str) -> str:
    parts = _assistant_content_parts(content, target_speech)
    return _join_modular_assistant_content(parts, target_speech)


def _join_modular_assistant_content(content: dict[str, object], target_speech: str) -> str:
    parts = _assistant_content_parts(content, target_speech)
    blocks = [
        f"<system_thinking>{parts['system_thinking']}</system_thinking>",
        f"<role_thinking>{parts['role_thinking']}</role_thinking>",
    ]
    role_action = parts["role_action"].strip()
    if role_action:
        blocks.append(f"<role_action>{role_action}</role_action>")
    blocks.append(parts["target_speech"])
    return "\n".join(blocks)


def _system_context_payload(system_context: dict[str, object]) -> dict[str, object]:
    return {
        "system_id": system_context.get("system_id", ""),
        "chapter_id": system_context.get("chapter_id", ""),
        "beat_id": system_context.get("beat_id", ""),
        "turn_id": system_context.get("turn_id", ""),
        "scope": system_context.get("scope", ""),
        "current_scenario": system_context.get("current_scenario", ""),
        "other_characters": system_context.get("other_characters", ""),
        "needs_scene_split": system_context.get("needs_scene_split", False),
        "scene_split_reason": system_context.get("scene_split_reason", ""),
    }
