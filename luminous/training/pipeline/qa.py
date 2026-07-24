from __future__ import annotations

import re
from typing import Any


REQUIRED_TAGS = [
    "<system_thinking>",
    "</system_thinking>",
    "<role_thinking>",
    "</role_thinking>",
]


TAG_PAIRS = {
    "system_thinking": ("<system_thinking>", "</system_thinking>"),
    "role_thinking": ("<role_thinking>", "</role_thinking>"),
    "role_action": ("<role_action>", "</role_action>"),
}

UNSUPPORTED_ACTION_MARKERS = [
    "微笑",
    "笑",
    "歪头",
    "偏头",
    "抬头",
    "低头",
    "抬眸",
    "垂眸",
    "垂眼",
    "眨眼",
    "眼神",
    "目光",
    "眸",
    "皱眉",
    "挑眉",
    "点头",
    "摇头",
    "颔首",
    "叹气",
    "抬手",
    "握住",
    "转身",
    "靠近",
    "杀意",
    "冷意",
    "冰冷",
    "无辜",
]

PRIVATE_MIND_MARKERS = [
    "心中",
    "内心",
    "心里",
    "暗自",
    "默默",
    "想起",
    "想到",
    "怀念",
    "觉得",
    "认为",
    "意识到",
    "疑惑",
    "困惑",
    "打算",
    "决定",
    "计划",
    "希望",
    "害怕",
    "担心",
    "后悔",
]

PROFILE_ECHO_MARKERS = [
    "宏大理想",
    "宏大而残酷",
    "旧秩序",
    "底层救赎",
    "神性悲悯",
    "反叛者",
    "双S级",
    "创生异能",
    "觉醒观测者",
    "规则重构者",
    "实用主义",
    "博弈棋盘",
    "降维打击",
    "棋手视角",
    "系统性漏洞",
    "资源重组",
    "信息差",
]

KNOWN_ENTITY_TARGETS = {
    "叶筝",
    "裴西",
    "塞克斯",
    "赛拉",
    "玛希",
    "秦路",
    "白木清",
    "武姝",
    "周芸",
    "舒婉",
    "玛格丽特",
    "温简",
    "文德",
    "叶笛",
    "希斯",
    "基兰",
    "卓雅",
    "文森特阿斯顿",
}

MODULAR_META_PROMPT_PATTERNS = [
    r"\bprompt\b",
    r"\bsystem prompt\b",
    r"\btarget_speech\b",
    r"\brequest_id\b",
    r"\bmetadata\b",
    r"\bmessages\b",
    r"训练样本",
    r"用户要求",
]

SHORT_TARGET_ACTION_MARKERS = {
    "杀",
    "刺杀",
}

ANALYST_VOICE_MARKERS = [
    "这句回应",
    "此回应",
    "当前触发",
    "外部触发",
    "维持人设",
    "符合设定",
    "符合她",
    "语气应",
    "需要表现",
    "此刻需要",
    "回应功能",
]


def _message(messages: list[dict[str, Any]], role: str) -> str:
    for message in messages:
        if message.get("role") == role:
            return str(message.get("content", ""))
    return ""


def _message_roles_valid(messages: list[dict[str, Any]]) -> bool:
    return [message.get("role") for message in messages] == ["system", "user", "assistant"]


def _tag_order_valid(content: str) -> bool:
    cursor = -1
    for tag in REQUIRED_TAGS:
        next_pos = content.find(tag)
        if next_pos <= cursor:
            return False
        cursor = next_pos
    role_action_start = content.find("<role_action>")
    role_action_end = content.find("</role_action>")
    if role_action_start < 0 and role_action_end < 0:
        return True
    if role_action_start < 0 or role_action_end < 0 or role_action_end <= role_action_start:
        return False
    return role_action_start > content.find("</role_thinking>")


def _tag_block(content: str, name: str) -> str:
    start_tag, end_tag = TAG_PAIRS[name]
    start = content.find(start_tag)
    end = content.find(end_tag)
    if start < 0 or end < 0 or end <= start:
        return ""
    return content[start + len(start_tag) : end].strip()


def _annotation(row: dict[str, object]) -> dict[str, Any]:
    annotation = row.get("annotation", {})
    return annotation if isinstance(annotation, dict) else {}


def _annotation_source_text(annotation: dict[str, Any], row: dict[str, object] | None = None) -> str:
    if row is not None:
        row_source = row.get("source", {})
        if isinstance(row_source, dict):
            source_text = row_source.get("source_text", "")
            if source_text:
                return str(source_text)
        audit = row.get("annotation_audit", {})
        if isinstance(audit, dict):
            source = audit.get("source", {})
            if isinstance(source, dict):
                annotation_source_text = source.get("annotation_source_text", "")
                if annotation_source_text:
                    return str(annotation_source_text)
                source_text = source.get("source_text", "")
                if source_text:
                    return str(source_text)
    source = annotation.get("source", {})
    if isinstance(source, dict) and source.get("source_text", ""):
        return str(source.get("source_text", ""))
    return str(annotation.get("source_text", ""))


def _current_source_text(annotation: dict[str, Any], row: dict[str, object] | None = None) -> str:
    if row is not None:
        row_source = row.get("source", {})
        if isinstance(row_source, dict):
            source_text = row_source.get("source_text", "")
            if source_text:
                return str(source_text)
        audit = row.get("annotation_audit", {})
        if isinstance(audit, dict):
            source = audit.get("source", {})
            if isinstance(source, dict) and source.get("source_text", ""):
                return str(source.get("source_text", ""))
    source = annotation.get("source", {})
    if isinstance(source, dict) and source.get("source_text", ""):
        return str(source.get("source_text", ""))
    return str(annotation.get("source_text", ""))


def _speech_segments(row: dict[str, object], annotation: dict[str, Any], turn: dict[str, Any]) -> list[dict[str, Any]]:
    segments = turn.get("source_speech_segments")
    audit = row.get("annotation_audit", {})
    literal = {}
    if isinstance(audit, dict):
        literal = audit.get("literal_extraction", {})
    if not literal:
        literal = annotation.get("literal_extraction", {})
    if not isinstance(segments, list) and isinstance(literal, dict):
        segments = literal.get("yezhen_speech_segments")
    if not isinstance(segments, list):
        segments = annotation.get("source_speech_segments")
    if not isinstance(segments, list):
        return []
    return [segment for segment in segments if isinstance(segment, dict)]


def _joined_segment_text(segments: list[dict[str, Any]]) -> str:
    return "".join(str(segment.get("text", "")) for segment in segments)


def _contains_meta_prompt_language(content: str) -> bool:
    patterns = [
        r"用户",
        r"用户要求",
        r"用户希望",
        r"任务要求",
        r"prompt",
        r"Prompt",
        r"system prompt",
        r"模型",
        r"扮演叶筝",
        r"角色扮演",
        r"训练样本",
        r"标注",
        r"sft_turn",
        r"target_speech",
        r"\bmessages\b",
    ]
    return any(re.search(pattern, content) for pattern in patterns)


def _contains_audit_language(content: str) -> bool:
    patterns = [
        r"\bevidence\b",
        r"\bsource_text\b",
        r"\bannotation\b",
        r"\bdebug\b",
        r"\breview\b",
        r"证据字段",
        r"审计",
        r"复核",
    ]
    return any(re.search(pattern, content) for pattern in patterns)


def _future_leakage_risk(annotation: dict[str, Any], row: dict[str, object] | None = None) -> bool:
    if row is not None:
        audit = row.get("annotation_audit", {})
        if isinstance(audit, dict):
            quality = audit.get("quality", {})
            if isinstance(quality, dict) and "future_leakage_risk" in quality:
                return bool(quality.get("future_leakage_risk"))
    quality = annotation.get("quality", {})
    if isinstance(quality, dict) and "future_leakage_risk" in quality:
        return bool(quality.get("future_leakage_risk"))
    return bool(annotation.get("future_leakage_risk", False))


def _contains_second_person_instruction(content: str) -> bool:
    patterns = [
        r"你\s*(需要|应该|必须|要|可以|不能|不要|得|会)",
        r"你\s*是",
        r"\byou\s+(need|should|must|have to|can|cannot|can't|will|are)\b",
    ]
    return any(re.search(pattern, content, flags=re.IGNORECASE) for pattern in patterns)


def _contains_private_mind_language(content: str) -> bool:
    return any(marker in content for marker in PRIVATE_MIND_MARKERS)


def _role_thinking_is_first_person(content: str) -> bool:
    return bool(re.search(r"我|我的|I\b|I'm\b|I’m\b|\bmy\b", content, flags=re.IGNORECASE))


def _contains_analyst_voice(content: object) -> bool:
    return any(marker in str(content or "") for marker in ANALYST_VOICE_MARKERS)


def _compact_for_overlap(text: object) -> str:
    compacted = re.sub(r"[\s“”\"'：:，。！？、；;,.!?…—\-·]+", "", str(text or ""))
    return re.sub(r"皇太子|殿下|教皇|圣女|冕下|大人", "", compacted)


def _target_overlap_is_high_confidence(target_speech: object, content: object) -> bool:
    target = _compact_for_overlap(target_speech)
    if target in KNOWN_ENTITY_TARGETS:
        return False
    if len(target) < 6 and not any(marker in target for marker in SHORT_TARGET_ACTION_MARKERS):
        return False
    return target in _compact_for_overlap(content)


def _contains_modular_meta_prompt_artifact(content: object) -> bool:
    text = str(content or "")
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in MODULAR_META_PROMPT_PATTERNS)


def _response_request_id(response: dict[str, object]) -> str:
    return str(response.get("request_id", ""))


def _response_metadata(response: dict[str, object]) -> dict[str, object]:
    metadata = response.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _response_json(response: dict[str, object]) -> dict[str, object]:
    value = response.get("response_json", {})
    return value if isinstance(value, dict) else {}


def check_system_context_response(response: dict[str, object]) -> dict[str, object]:
    response_json = _response_json(response)
    metadata = _response_metadata(response)
    target_speech = metadata.get("target_speech", "")
    current_scenario = str(response_json.get("current_scenario", "")).strip()
    other_characters = str(response_json.get("other_characters", "")).strip()
    checks = {
        "required_fields_present": bool(current_scenario and other_characters),
        "no_high_confidence_target_leakage": not _target_overlap_is_high_confidence(
            target_speech,
            f"{current_scenario}\n{other_characters}",
        ),
        "no_meta_prompt_artifacts": not _contains_modular_meta_prompt_artifact(
            f"{current_scenario}\n{other_characters}"
        ),
    }
    review_reasons = [
        reason
        for reason, passed in {
            "missing_required_system_context_field": checks["required_fields_present"],
            "meta_prompt_artifact_in_system_context": checks["no_meta_prompt_artifacts"],
        }.items()
        if not passed
    ]
    warning_reasons = []
    if not checks["no_high_confidence_target_leakage"]:
        warning_reasons.append("target_leakage_in_system_context")
    return {
        "request_id": _response_request_id(response),
        "stage": response.get("stage", "system_context"),
        "checks": checks,
        "needs_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "warning_reasons": warning_reasons,
    }


def check_assistant_response(response: dict[str, object]) -> dict[str, object]:
    response_json = _response_json(response)
    metadata = _response_metadata(response)
    target_speech = metadata.get("target_speech", "")
    system_thinking = str(response_json.get("system_thinking", "")).strip()
    role_thinking = str(response_json.get("role_thinking", "")).strip()
    role_action = str(response_json.get("role_action", "")).strip()
    thinking_and_action = "\n".join(part for part in [system_thinking, role_thinking, role_action] if part)
    support_text = "\n".join(
        str(metadata.get(key, ""))
        for key in ("source_text", "source_before_target", "source_after_target_for_attribution")
        if metadata.get(key, "")
    )
    unsupported_action_markers = [
        marker
        for marker in UNSUPPORTED_ACTION_MARKERS
        if role_action and marker in role_action and marker not in support_text
    ]
    checks = {
        "required_thinking_fields_present": bool(system_thinking and role_thinking),
        "no_high_confidence_target_leakage": not _target_overlap_is_high_confidence(
            target_speech,
            thinking_and_action,
        ),
        "no_meta_prompt_artifacts": not _contains_modular_meta_prompt_artifact(thinking_and_action),
        "role_thinking_first_person": not role_thinking or _role_thinking_is_first_person(role_thinking),
        "role_thinking_no_analyst_voice": not _contains_analyst_voice(role_thinking),
        "role_action_grounded": not unsupported_action_markers,
    }
    review_reasons = [
        reason
        for reason, passed in {
            "missing_required_assistant_thinking_field": checks["required_thinking_fields_present"],
            "meta_prompt_artifact_in_assistant_response": checks["no_meta_prompt_artifacts"],
        }.items()
        if not passed
    ]
    warning_reasons = []
    if not checks["no_high_confidence_target_leakage"]:
        warning_reasons.append("target_leakage_in_assistant_thinking")
    if not checks["role_thinking_first_person"]:
        warning_reasons.append("role_thinking_not_first_person")
    if not checks["role_thinking_no_analyst_voice"]:
        warning_reasons.append("role_thinking_analyst_voice")
    if not checks["role_action_grounded"]:
        warning_reasons.append("unsupported_role_action_detail")
    return {
        "request_id": _response_request_id(response),
        "stage": response.get("stage", "assistant_response"),
        "checks": checks,
        "needs_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "warning_reasons": warning_reasons,
        "unsupported_action_markers": unsupported_action_markers,
    }


def _assistant_blocks_nonempty(assistant_content: str) -> bool:
    return bool(_tag_block(assistant_content, "system_thinking")) and bool(
        _tag_block(assistant_content, "role_thinking")
    )


def _thinking_blocks_role_separated(assistant_content: str) -> bool:
    system_thinking = _tag_block(assistant_content, "system_thinking")
    role_thinking = _tag_block(assistant_content, "role_thinking")
    if not system_thinking or not role_thinking:
        return False
    if re.search(r"我|我的|I\b|I'm\b|I’m\b|\bmy\b", system_thinking, flags=re.IGNORECASE):
        return False
    if _contains_second_person_instruction(system_thinking) or _contains_second_person_instruction(role_thinking):
        return False
    return _role_thinking_is_first_person(role_thinking)


def _thinking_no_profile_echo(assistant_content: str) -> bool:
    thinking = "\n".join(
        block for block in (_tag_block(assistant_content, "system_thinking"), _tag_block(assistant_content, "role_thinking")) if block
    )
    return not any(marker in thinking for marker in PROFILE_ECHO_MARKERS)


def _annotation_support_text(annotation: dict[str, Any], row: dict[str, object]) -> str:
    parts: list[str] = [_current_source_text(annotation, row)]
    source = row.get("source", {})
    if isinstance(source, dict):
        parts.extend(str(value) for value in source.values() if value)
    system_context = row.get("system_context", {})
    if isinstance(system_context, dict):
        parts.extend(str(value) for value in system_context.values() if isinstance(value, str) and value)
    user_context = row.get("user_context", {})
    if isinstance(user_context, dict):
        user_content = user_context.get("user_content", "")
        if user_content:
            parts.append(str(user_content))
    for key in (
        "scene_summary",
        "relationship_context",
        "trigger",
        "response_strategy",
        "role_action_basis",
    ):
        value = annotation.get(key, "")
        if value:
            parts.append(str(value))
    psychology = annotation.get("yezhen_psychology", {})
    if isinstance(psychology, dict):
        for value in psychology.values():
            if isinstance(value, list):
                parts.extend(str(item) for item in value if item)
            elif value:
                parts.append(str(value))
    return "\n".join(parts)


def _role_action_no_unsupported_visible_detail(assistant_content: str, annotation: dict[str, Any], row: dict[str, object]) -> bool:
    role_action = _tag_block(assistant_content, "role_action")
    if not role_action:
        return True
    support_text = _annotation_support_text(annotation, row)
    return not any(marker in role_action and marker not in support_text for marker in UNSUPPORTED_ACTION_MARKERS)


def _annotation_analysis_sufficient(annotation: dict[str, Any]) -> bool:
    psychology = annotation.get("yezhen_psychology", {})
    if isinstance(psychology, dict):
        psychology_fields = [
            annotation.get("trigger", ""),
            psychology.get("inner_conflict", ""),
            psychology.get("intent", ""),
            annotation.get("response_strategy", ""),
        ]
        if all(str(value).strip() for value in psychology_fields):
            return True

    interpretation = annotation.get("interpretation", {})
    if not isinstance(interpretation, dict):
        return False
    required_keys = [
        "trigger",
        "role_action",
        "role_thinking",
        "response_strategy",
    ]
    for key in required_keys:
        if not str(interpretation.get(key, "")).strip():
            return False
    return True


def _assistant_response_parts(row: dict[str, object]) -> dict[str, Any]:
    assistant_response = row.get("assistant_response", {})
    if not isinstance(assistant_response, dict):
        return {}
    content_parts = assistant_response.get("content_parts", {})
    return content_parts if isinstance(content_parts, dict) else {}


def _analysis_sufficient(annotation: dict[str, Any], row: dict[str, object], assistant_content: str) -> bool:
    if annotation:
        return _annotation_analysis_sufficient(annotation)
    content_parts = _assistant_response_parts(row)
    if content_parts:
        return bool(str(content_parts.get("system_thinking", "")).strip()) and bool(
            str(content_parts.get("role_thinking", "")).strip()
        )
    return _assistant_blocks_nonempty(assistant_content)


def check_sft_message(row: dict[str, object]) -> dict[str, object]:
    messages = row.get("messages", [])
    if not isinstance(messages, list):
        messages = []
    typed_messages = [m for m in messages if isinstance(m, dict)]
    turn = row.get("sft_turn", {})
    if not isinstance(turn, dict):
        turn = {}
    annotation = _annotation(row)

    target_speech = str(turn.get("target_speech", ""))
    speaker_confidence = str(turn.get("speaker_confidence", "unknown"))
    user_content = _message(typed_messages, "user")
    assistant_content = _message(typed_messages, "assistant")
    all_message_content = "\n".join(str(message.get("content", "")) for message in typed_messages)
    source_text = _annotation_source_text(annotation, row)
    source_segments = _speech_segments(row, annotation, turn)
    segment_text = _joined_segment_text(source_segments)
    segment_texts = [str(segment.get("text", "")) for segment in source_segments]

    user_context = row.get("user_context", {})
    user_context = user_context if isinstance(user_context, dict) else {}

    analysis_sufficient = _analysis_sufficient(annotation, row, assistant_content)
    user_context_no_target_speech = not bool(user_context.get("contains_target_speech", False))
    checks = {
        "message_roles_valid": _message_roles_valid(typed_messages),
        "no_target_leakage_in_user": bool(target_speech) and target_speech not in user_content,
        "user_context_no_target_speech": user_context_no_target_speech,
        "user_context_reports_no_target_speech": user_context_no_target_speech,
        "user_context_reports_no_second_person_instruction": not bool(
            user_context.get("uses_second_person_instruction", False)
        ),
        "user_context_no_private_mind_language": not _contains_private_mind_language(user_content),
        "speech_exact_match": bool(target_speech) and assistant_content.rstrip().endswith(target_speech),
        "tag_order_valid": _tag_order_valid(assistant_content),
        "assistant_blocks_nonempty": _assistant_blocks_nonempty(assistant_content),
        "speaker_confidence_ok": speaker_confidence not in {"low", "unknown"},
        "source_speech_segments_present": bool(source_segments),
        "target_equals_source_segments": bool(target_speech) and bool(segment_text) and target_speech == segment_text,
        "source_speech_segments_grounded": bool(source_text)
        and bool(segment_texts)
        and all(text and text in source_text for text in segment_texts),
        "source_speech_segments_have_location": bool(source_segments)
        and all(segment.get("source_start_char", "") != "" for segment in source_segments),
        "no_meta_prompt_pollution": not _contains_meta_prompt_language(assistant_content),
        "no_second_person_instruction": not _contains_second_person_instruction(assistant_content),
        "thinking_blocks_role_separated": _thinking_blocks_role_separated(assistant_content),
        "thinking_no_profile_echo": _thinking_no_profile_echo(assistant_content),
        "role_action_no_unsupported_visible_detail": _role_action_no_unsupported_visible_detail(
            assistant_content, annotation, row
        ),
        "no_audit_content_inside_messages": not _contains_audit_language(all_message_content),
        "analysis_sufficient": analysis_sufficient,
        "annotation_analysis_sufficient": analysis_sufficient,
        "no_future_leakage_risk": not _future_leakage_risk(annotation, row),
    }

    review_reasons: list[str] = []
    if not checks["message_roles_valid"]:
        review_reasons.append("invalid_message_roles")
    if not checks["speech_exact_match"]:
        review_reasons.append("speech_not_exact_match")
    if not checks["tag_order_valid"]:
        review_reasons.append("invalid_tag_order")
    if not checks["assistant_blocks_nonempty"]:
        review_reasons.append("assistant_blocks_empty")
    if not checks["speaker_confidence_ok"]:
        review_reasons.append("speaker_attribution_low_confidence")
    if not checks["source_speech_segments_present"]:
        review_reasons.append("source_speech_segments_missing")
    if not checks["target_equals_source_segments"]:
        review_reasons.append("target_speech_not_built_from_source_segments")
    if not checks["source_speech_segments_grounded"]:
        review_reasons.append("source_speech_segment_not_in_source_text")
    if not checks["source_speech_segments_have_location"]:
        review_reasons.append("source_speech_segment_missing_location")
    if not checks["no_future_leakage_risk"]:
        review_reasons.append("future_leakage_risk")

    trainable = not review_reasons
    needs_human_review = bool(review_reasons)
    return {
        "turn_id": row.get("turn_id", ""),
        "passed": trainable,
        "trainable": trainable,
        "needs_human_review": needs_human_review,
        "review_reasons": review_reasons,
        "checks": checks,
    }
