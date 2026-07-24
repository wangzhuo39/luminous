from __future__ import annotations

import shutil
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_EXCEPTION
from pathlib import Path

from tqdm import tqdm

from luminous.training.pipeline.jsonl import read_jsonl, write_jsonl
from luminous.training.pipeline.llm import call_prompt_requests
from luminous.training.pipeline.models import RunSummary
from luminous.training.pipeline.profile import apply_profile_revision, load_profile_brief
from luminous.training.pipeline.requests import (
    build_annotation_prompt_request,
    build_annotation_contextual_beat,
    build_profile_revision_prompt_request,
    prepare_assistant_response_prompt_requests,
    prepare_speaker_attribution_prompt_requests,
    prepare_system_context_prompt_requests,
    prepare_user_context_prompt_requests,
)
from luminous.training.pipeline.responses import (
    assemble_modular_sft_messages,
    audit_path_for_annotations,
    extract_annotations,
    extract_assistant_responses,
    extract_profile_revisions,
    extract_speaker_attributions,
    extract_system_contexts,
    extract_user_contexts,
    qa_sft_file,
)
from luminous.training.pipeline.quote_candidates import build_quote_candidates
from luminous.training.pipeline.source_beats import build_source_anchored_beats


LlmCaller = Callable[[Path, Path], int]
DEFAULT_PROFILE_PATH = Path(__file__).resolve().parents[3] / "docs/superpowers/profiles/yezhen-profile-v0001.md"


def run_staged_pipeline(
    input_path: Path,
    output_dir: Path,
    chapter_limit: int | None,
    language: str,
    llm_caller: LlmCaller = call_prompt_requests,
    profile_path: Path | None = None,
    concurrency: int = 4,
    continue_on_failure: bool = True,
) -> RunSummary:
    prompt_dir = output_dir / "prompt_requests"
    response_dir = output_dir / "llm_responses"
    response_dir.mkdir(parents=True, exist_ok=True)
    parallel_llm_caller = (
        _parallel_progress_llm_caller(concurrency) if llm_caller is call_prompt_requests else llm_caller
    )
    build_quote_candidates(input_path, output_dir, chapter_limit, language)
    stage1_requests = prompt_dir / "01_beat_candidates.jsonl"
    beat_candidates_path = output_dir / "beat_candidates.jsonl"

    prepare_speaker_attribution_prompt_requests(beat_candidates_path, output_dir, language)
    stage2_requests = prompt_dir / "02_speaker_attribution.jsonl"
    stage2_responses = response_dir / "02_speaker_attribution.jsonl"

    if llm_caller is call_prompt_requests:
        _speaker_attribution_llm_caller(
            stage2_requests,
            stage2_responses,
            output_dir / "failed_requests.jsonl",
            concurrency,
            continue_on_failure,
        )
    else:
        llm_caller(stage2_requests, stage2_responses)

    speaker_attribution_path = output_dir / "speaker_attribution.jsonl"
    extract_speaker_attributions(stage2_responses, speaker_attribution_path)

    coarse_beats_path = output_dir / "coarse_beats.jsonl"
    sft_turns_path = output_dir / "sft_turns.jsonl"
    build_source_anchored_beats(
        beat_candidates_path,
        speaker_attribution_path,
        stage1_requests,
        coarse_beats_path,
        sft_turns_path,
    )

    prepare_system_context_prompt_requests(sft_turns_path, coarse_beats_path, output_dir, language)
    stage4_requests = prompt_dir / "04_system_contexts.jsonl"
    stage4_responses = response_dir / "04_system_contexts.jsonl"
    system_contexts_path = output_dir / "system_contexts.jsonl"

    prepare_user_context_prompt_requests(
        sft_turns_path,
        coarse_beats_path,
        system_contexts_path,
        output_dir,
        language,
    )
    stage5_requests = prompt_dir / "05_user_contexts.jsonl"
    stage5_responses = response_dir / "05_user_contexts.jsonl"
    user_contexts_path = output_dir / "user_contexts.jsonl"

    prepare_assistant_response_prompt_requests(
        sft_turns_path,
        coarse_beats_path,
        system_contexts_path,
        user_contexts_path,
        output_dir,
        language,
    )
    stage6_requests = prompt_dir / "06_assistant_responses.jsonl"
    stage6_responses = response_dir / "06_assistant_responses.jsonl"
    assistant_responses_path = output_dir / "assistant_responses.jsonl"

    _run_modular_context_llm_stages(
        parallel_llm_caller,
        stage4_requests,
        stage4_responses,
        stage5_requests,
        stage5_responses,
        stage6_requests,
        stage6_responses,
    )
    extract_system_contexts(stage4_responses, system_contexts_path)
    extract_user_contexts(stage5_responses, user_contexts_path)
    extract_assistant_responses(stage6_responses, assistant_responses_path)

    sft_draft_path = output_dir / "sft_messages_draft.jsonl"
    assemble_modular_sft_messages(
        system_contexts_path,
        user_contexts_path,
        assistant_responses_path,
        sft_turns_path,
        sft_draft_path,
    )
    sft_qa_input_path = sft_draft_path
    sft_audit_path = output_dir / "sft_messages_audit.jsonl"
    shutil.copyfile(sft_qa_input_path, sft_audit_path)

    qa_summary = qa_sft_file(sft_qa_input_path, output_dir)
    return RunSummary(
        output_dir=output_dir,
        files_written=[
            beat_candidates_path,
            speaker_attribution_path,
            output_dir / "failed_requests.jsonl",
            coarse_beats_path,
            sft_turns_path,
            system_contexts_path,
            user_contexts_path,
            assistant_responses_path,
            sft_draft_path,
            sft_audit_path,
            output_dir / "sft_messages_trainable.jsonl",
            output_dir / "sft_messages_her.jsonl",
            output_dir / "review_queue.jsonl",
        ],
        counts=qa_summary.counts,
    )


def _serial_progress_llm_caller(input_path: Path, output_path: Path) -> int:
    return call_prompt_requests(input_path, output_path, show_progress=True)


def _parallel_progress_llm_caller(concurrency: int) -> LlmCaller:
    def caller(input_path: Path, output_path: Path) -> int:
        return call_prompt_requests(input_path, output_path, show_progress=True, concurrency=concurrency)

    return caller


def _run_modular_context_llm_stages(
    llm_caller: LlmCaller,
    system_requests: Path,
    system_responses: Path,
    user_requests: Path,
    user_responses: Path,
    assistant_requests: Path,
    assistant_responses: Path,
) -> None:
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(llm_caller, system_requests, system_responses),
            executor.submit(llm_caller, user_requests, user_responses),
            executor.submit(llm_caller, assistant_requests, assistant_responses),
        ]
        done, pending = wait(futures, return_when=FIRST_EXCEPTION)
        for future in done:
            future.result()
        for future in pending:
            future.result()


def _run_independent_context_stages(
    llm_caller: LlmCaller,
    speaker_requests: Path,
    speaker_responses: Path,
    system_requests: Path,
    system_responses: Path,
    failed_output_path: Path,
    concurrency: int,
    continue_on_failure: bool = True,
) -> None:
    if llm_caller is not call_prompt_requests:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(llm_caller, speaker_requests, speaker_responses),
                executor.submit(llm_caller, system_requests, system_responses),
            ]
            done, pending = wait(futures, return_when=FIRST_EXCEPTION)
            for future in done:
                future.result()
            for future in pending:
                future.result()
        return

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _speaker_attribution_llm_caller,
                speaker_requests,
                speaker_responses,
                failed_output_path,
                concurrency,
                continue_on_failure,
            ),
            executor.submit(
                _system_context_llm_caller,
                system_requests,
                system_responses,
                concurrency,
            ),
        ]
        done, pending = wait(futures, return_when=FIRST_EXCEPTION)
        for future in done:
            future.result()
        for future in pending:
            future.result()


def _system_context_llm_caller(
    input_path: Path,
    output_path: Path,
    concurrency: int,
) -> int:
    return call_prompt_requests(
        input_path,
        output_path,
        show_progress=True,
        concurrency=concurrency,
    )


def _speaker_attribution_llm_caller(
    input_path: Path,
    output_path: Path,
    failed_output_path: Path,
    concurrency: int,
    continue_on_failure: bool = True,
) -> int:
    return call_prompt_requests(
        input_path,
        output_path,
        show_progress=True,
        continue_on_failure=continue_on_failure,
        failed_output_path=failed_output_path,
        concurrency=concurrency,
    )


def _run_incremental_annotation_profile_stages(
    coarse_beats_path: Path,
    sft_turns_path: Path,
    output_dir: Path,
    language: str,
    llm_caller: LlmCaller,
    annotations_path: Path,
    annotation_audit_path: Path,
    profile_revisions_path: Path,
    profile_snapshots_path: Path,
    profile_path: Path = DEFAULT_PROFILE_PATH,
) -> None:
    prompt_dir = output_dir / "prompt_requests"
    response_dir = output_dir / "llm_responses"
    stage4_requests_path = prompt_dir / "04_annotations.jsonl"
    stage4_responses_path = response_dir / "04_annotations.jsonl"
    stage5_requests_path = prompt_dir / "05_profile_revisions.jsonl"
    stage5_responses_path = response_dir / "05_profile_revisions.jsonl"
    part_prompt_dir = prompt_dir / "incremental_parts"
    part_response_dir = response_dir / "incremental_parts"

    turns_by_beat = {str(turn.get("beat_id", "")): turn for turn in read_jsonl(sft_turns_path)}
    beats = sorted(
        read_jsonl(coarse_beats_path),
        key=lambda row: (str(row.get("chapter_id", "")), int(row.get("source_start_char", 0) or 0)),
    )

    current_brief = load_profile_brief(profile_path)
    current_revision_id = ""
    version_index = 1
    annotation_requests: list[dict[str, object]] = []
    annotation_responses: list[dict[str, object]] = []
    annotation_rows: list[dict[str, object]] = []
    annotation_audit_rows: list[dict[str, object]] = []
    revision_requests: list[dict[str, object]] = []
    revision_responses: list[dict[str, object]] = []
    revision_rows: list[dict[str, object]] = []
    snapshot_rows: list[dict[str, object]] = []

    previous_dialogue_beats: dict[str, list[dict[str, object]]] = {}

    for beat in tqdm(beats, desc="annotation/profile", unit="beat", dynamic_ncols=True):
        beat_id = str(beat.get("beat_id", ""))
        safe_beat_id = beat_id.replace("/", "_")
        profile_snapshot = {
            "beat_id": beat_id,
            "chapter_id": beat.get("chapter_id", ""),
            "chapter_title": beat.get("chapter_title", ""),
            "profile_version": f"v{version_index:04d}",
            "brief": current_brief,
            "source_revision_id": current_revision_id,
        }
        snapshot_rows.append(profile_snapshot)
        write_jsonl(profile_snapshots_path, snapshot_rows)

        turn = turns_by_beat.get(beat_id, {})
        chapter_id = str(beat.get("chapter_id", ""))
        contextual_beat = build_annotation_contextual_beat(beat, turn, previous_dialogue_beats.get(chapter_id, []))
        annotation_request = build_annotation_prompt_request(contextual_beat, turn, profile_snapshot, language)
        annotation_requests.append(annotation_request)
        write_jsonl(stage4_requests_path, annotation_requests)
        single_annotation_request = part_prompt_dir / f"04_{safe_beat_id}_annotation.jsonl"
        single_annotation_response = part_response_dir / f"04_{safe_beat_id}_annotation.jsonl"
        single_annotation_extract = part_response_dir / f"04_{safe_beat_id}_annotation_extracted.jsonl"
        write_jsonl(single_annotation_request, [annotation_request])
        if not _has_successful_response(single_annotation_response, str(annotation_request["request_id"])):
            llm_caller(single_annotation_request, single_annotation_response)
        annotation_responses.extend(read_jsonl(single_annotation_response))
        write_jsonl(stage4_responses_path, annotation_responses)
        extract_annotations(single_annotation_response, single_annotation_extract)
        extracted_annotations = read_jsonl(single_annotation_extract)
        extracted_annotation_audit = read_jsonl(audit_path_for_annotations(single_annotation_extract))
        annotation_rows.extend(extracted_annotations)
        annotation_audit_rows.extend(extracted_annotation_audit)
        write_jsonl(annotations_path, annotation_rows)
        write_jsonl(annotation_audit_path, annotation_audit_rows)
        if turn.get("target_speech"):
            previous_dialogue_beats.setdefault(chapter_id, []).append(beat)
        if not extracted_annotations:
            continue

        annotation = extracted_annotations[0]
        revision_request = build_profile_revision_prompt_request(beat, annotation, profile_snapshot, language)
        revision_requests.append(revision_request)
        write_jsonl(stage5_requests_path, revision_requests)
        single_revision_request = part_prompt_dir / f"05_{safe_beat_id}_profile_revision.jsonl"
        single_revision_response = part_response_dir / f"05_{safe_beat_id}_profile_revision.jsonl"
        single_revision_extract = part_response_dir / f"05_{safe_beat_id}_profile_revision_extracted.jsonl"
        write_jsonl(single_revision_request, [revision_request])
        if not _has_successful_response(single_revision_response, str(revision_request["request_id"])):
            llm_caller(single_revision_request, single_revision_response)
        revision_responses.extend(read_jsonl(single_revision_response))
        write_jsonl(stage5_responses_path, revision_responses)
        extract_profile_revisions(single_revision_response, single_revision_extract)
        extracted_revisions = read_jsonl(single_revision_extract)
        revision_rows.extend(extracted_revisions)
        write_jsonl(profile_revisions_path, revision_rows)
        if not extracted_revisions:
            continue

        next_brief = apply_profile_revision(current_brief, extracted_revisions[0])
        if next_brief != current_brief:
            version_index += 1
            current_brief = next_brief
            current_revision_id = str(extracted_revisions[0].get("revision_id", ""))


def _has_successful_response(path: Path, request_id: str) -> bool:
    if not path.exists():
        return False
    for row in read_jsonl(path):
        if str(row.get("request_id", "")) != request_id:
            continue
        if isinstance(row.get("response_json"), dict) and not row.get("error_type") and not row.get("error"):
            return not row.get("parse_error") and not row.get("failed")
    return False
