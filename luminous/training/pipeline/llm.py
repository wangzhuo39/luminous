from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

from tqdm import tqdm

from luminous.training.pipeline.jsonl import read_jsonl, write_jsonl


@dataclass(frozen=True)
class LlmConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2
    timeout_seconds: int = 120
    max_tokens: int = 4096


Transport = Callable[[LlmConfig, str], str]


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_llm_config(
    env_path: Path = Path(".env"),
    environ: Mapping[str, str] | None = None,
) -> LlmConfig:
    env = dict(os.environ if environ is None else environ)
    file_values = _read_env_file(env_path)

    base_url = env.get("OPENAI_BASE_URL") or file_values.get("OPENAI_BASE_URL") or file_values.get("base_url")
    api_key = env.get("OPENAI_API_KEY") or file_values.get("OPENAI_API_KEY") or file_values.get("key")
    model = env.get("OPENAI_MODEL") or file_values.get("OPENAI_MODEL") or file_values.get("model")
    timeout = env.get("OPENAI_TIMEOUT") or file_values.get("OPENAI_TIMEOUT") or file_values.get("timeout")
    max_tokens = env.get("OPENAI_MAX_TOKENS") or file_values.get("OPENAI_MAX_TOKENS") or file_values.get("max_tokens")

    missing = [
        name
        for name, value in {
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"missing LLM config values: {', '.join(missing)}")

    return LlmConfig(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=model,
        timeout_seconds=int(timeout or 120),
        max_tokens=int(max_tokens or 4096),
    )


def openai_compatible_chat_completion(config: LlmConfig, prompt: str) -> str:
    url = f"{config.base_url}/chat/completions"
    payload = {
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    result_queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def _request_body() -> None:
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                result_queue.put(("ok", json.loads(response.read().decode("utf-8"))))
        except BaseException as exc:  # noqa: BLE001 - transported back to caller.
            result_queue.put(("error", exc))

    worker = threading.Thread(target=_request_body, daemon=True)
    worker.start()
    worker.join(config.timeout_seconds)
    if worker.is_alive():
        raise TimeoutError(f"LLM request exceeded {config.timeout_seconds}s")
    status, value = result_queue.get()
    if status == "error":
        raise value
    body = value
    return str(body["choices"][0]["message"]["content"])


def _parse_response_text(text: str) -> tuple[dict[str, Any] | None, str | None]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        extracted = _extract_json_object(stripped)
        if extracted is None:
            return None, str(exc)
        value = extracted
    if not isinstance(value, dict):
        return None, "response JSON is not an object"
    return value, None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def call_prompt_requests(
    input_path: Path,
    output_path: Path,
    config: LlmConfig | None = None,
    transport: Transport = openai_compatible_chat_completion,
    max_attempts: int | None = 10,
    retry_sleep_seconds: float = 0.0,
    show_progress: bool = False,
    continue_on_failure: bool = False,
    failed_output_path: Path | None = None,
    concurrency: int = 1,
) -> int:
    if max_attempts is not None and max_attempts < 1:
        raise ValueError("max_attempts must be positive or None")
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    llm_config = config or load_llm_config()
    request_rows = read_jsonl(input_path)
    current_request_ids = {str(row.get("request_id", "")) for row in request_rows}
    existing_rows = read_jsonl(output_path) if output_path.exists() else []
    existing_by_request_id = {
        str(row.get("request_id", "")): row
        for row in existing_rows
        if str(row.get("request_id", "")) in current_request_ids
    }
    rows = []
    for request_row in request_rows:
        existing_row = existing_by_request_id.get(str(request_row.get("request_id", "")))
        if existing_row and _is_successful_response_row(existing_row):
            rows.append(existing_row)
    completed_request_ids = {str(row.get("request_id", "")) for row in rows}
    progress = tqdm(
        total=len(request_rows),
        desc=input_path.name,
        initial=len(rows),
        disable=not show_progress,
        unit="req",
        dynamic_ncols=True,
    )
    if concurrency > 1:
        return _call_prompt_requests_parallel(
            request_rows,
            output_path,
            llm_config,
            transport,
            max_attempts,
            retry_sleep_seconds,
            continue_on_failure,
            failed_output_path,
            existing_by_request_id,
            rows,
            progress,
            concurrency,
        )
    for request_row in request_rows:
        request_id = str(request_row.get("request_id", ""))
        if request_id in completed_request_ids:
            continue
        prompt = str(request_row.get("prompt", ""))
        output_row: dict[str, Any] = {
            "request_id": request_id,
            "stage": request_row.get("stage", ""),
            "language": request_row.get("language", ""),
            "metadata": request_row.get("metadata", {}),
        }
        existing_row = existing_by_request_id.get(request_id, {})
        existing_attempts = existing_row.get("attempts", []) if isinstance(existing_row, dict) else []
        attempts: list[dict[str, Any]] = list(existing_attempts) if isinstance(existing_attempts, list) else []
        process_attempts = 0
        while max_attempts is None or process_attempts < max_attempts:
            attempt_index = len(attempts) + 1
            process_attempts += 1
            progress.set_postfix_str(
                f"{request_id} attempt {attempt_index}/{_attempt_limit_label(max_attempts)}"
            )
            try:
                raw_text = transport(_stage_config(llm_config, str(request_row.get("stage", ""))), prompt)
            except Exception as exc:  # noqa: BLE001 - batch runner must record provider failures.
                attempt = {
                    "attempt": attempt_index,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                attempts.append(attempt)
                output_row = {**output_row, **attempt}
                output_row["attempts"] = attempts
                write_jsonl(output_path, [*rows, output_row])
                if retry_sleep_seconds > 0:
                    time.sleep(retry_sleep_seconds)
                continue

            parsed, parse_error = _parse_response_text(raw_text)
            attempt = {"attempt": attempt_index, "raw_text": raw_text}
            if parsed is not None:
                output_row["raw_text"] = raw_text
                output_row["response_json"] = parsed
                output_row.pop("error_type", None)
                output_row.pop("error", None)
                output_row.pop("parse_error", None)
                break
            if parse_error:
                attempt["parse_error"] = parse_error
                attempts.append(attempt)
                output_row["raw_text"] = raw_text
                output_row["parse_error"] = parse_error
                output_row["attempts"] = attempts
                write_jsonl(output_path, [*rows, output_row])
                if retry_sleep_seconds > 0:
                    time.sleep(retry_sleep_seconds)
        if attempts:
            output_row["attempts"] = attempts
        if not _is_successful_response_row(output_row):
            progress.set_postfix_str(f"{request_id} failed after {len(attempts)}/{_attempt_limit_label(max_attempts)}")
            output_row["failed"] = True
            rows.append(output_row)
            completed_request_ids.add(request_id)
            write_jsonl(output_path, rows)
            _write_failed_requests(failed_output_path, rows)
            progress.update(1)
            if continue_on_failure:
                continue
            progress.close()
            raise RuntimeError(f"LLM request {request_id} did not complete after {len(attempts)} attempts")
        rows.append(output_row)
        completed_request_ids.add(request_id)
        write_jsonl(output_path, rows)
        progress.set_postfix_str(f"{request_id} done")
        progress.update(1)
    progress.close()
    _write_failed_requests(failed_output_path, rows)
    return write_jsonl(output_path, rows)


def _call_prompt_requests_parallel(
    request_rows: list[dict[str, Any]],
    output_path: Path,
    llm_config: LlmConfig,
    transport: Transport,
    max_attempts: int | None,
    retry_sleep_seconds: float,
    continue_on_failure: bool,
    failed_output_path: Path | None,
    existing_by_request_id: dict[str, dict[str, Any]],
    successful_rows: list[dict[str, Any]],
    progress: tqdm,
    concurrency: int,
) -> int:
    rows_by_request_id = {str(row.get("request_id", "")): row for row in successful_rows}
    completed_request_ids = set(rows_by_request_id)
    pending_request_rows = [
        row for row in request_rows if str(row.get("request_id", "")) not in completed_request_ids
    ]
    executor = ThreadPoolExecutor(max_workers=concurrency)
    futures = {
        executor.submit(
            _call_single_prompt_request,
            request_row,
            existing_by_request_id.get(str(request_row.get("request_id", "")), {}),
            llm_config,
            transport,
            max_attempts,
            retry_sleep_seconds,
        ): str(request_row.get("request_id", ""))
        for request_row in pending_request_rows
    }
    try:
        for future in as_completed(futures):
            request_id = futures[future]
            output_row = future.result()
            rows_by_request_id[request_id] = output_row
            rows = _ordered_response_rows(request_rows, rows_by_request_id)
            write_jsonl(output_path, rows)
            _write_failed_requests(failed_output_path, rows)
            if _is_successful_response_row(output_row):
                progress.set_postfix_str(f"{request_id} done")
            else:
                progress.set_postfix_str(
                    f"{request_id} failed after {len(output_row.get('attempts', []))}/"
                    f"{_attempt_limit_label(max_attempts)}"
                )
            progress.update(1)
            if not _is_successful_response_row(output_row) and not continue_on_failure:
                for pending in futures:
                    pending.cancel()
                raise RuntimeError(
                    f"LLM request {request_id} did not complete after {len(output_row.get('attempts', []))} attempts"
                )
    finally:
        executor.shutdown(cancel_futures=True)
        progress.close()

    rows = _ordered_response_rows(request_rows, rows_by_request_id)
    _write_failed_requests(failed_output_path, rows)
    return write_jsonl(output_path, rows)


def _call_single_prompt_request(
    request_row: dict[str, Any],
    existing_row: dict[str, Any],
    llm_config: LlmConfig,
    transport: Transport,
    max_attempts: int | None,
    retry_sleep_seconds: float,
) -> dict[str, Any]:
    prompt = str(request_row.get("prompt", ""))
    output_row: dict[str, Any] = {
        "request_id": str(request_row.get("request_id", "")),
        "stage": request_row.get("stage", ""),
        "language": request_row.get("language", ""),
        "metadata": request_row.get("metadata", {}),
    }
    existing_attempts = existing_row.get("attempts", []) if isinstance(existing_row, dict) else []
    attempts: list[dict[str, Any]] = list(existing_attempts) if isinstance(existing_attempts, list) else []
    process_attempts = 0
    while max_attempts is None or process_attempts < max_attempts:
        attempt_index = len(attempts) + 1
        process_attempts += 1
        try:
            raw_text = transport(_stage_config(llm_config, str(request_row.get("stage", ""))), prompt)
        except Exception as exc:  # noqa: BLE001 - batch runner must record provider failures.
            attempt = {
                "attempt": attempt_index,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            attempts.append(attempt)
            output_row = {**output_row, **attempt}
            output_row["attempts"] = attempts
            if retry_sleep_seconds > 0:
                time.sleep(retry_sleep_seconds)
            continue

        parsed, parse_error = _parse_response_text(raw_text)
        attempt = {"attempt": attempt_index, "raw_text": raw_text}
        if parsed is not None:
            output_row["raw_text"] = raw_text
            output_row["response_json"] = parsed
            output_row.pop("error_type", None)
            output_row.pop("error", None)
            output_row.pop("parse_error", None)
            break
        if parse_error:
            attempt["parse_error"] = parse_error
            attempts.append(attempt)
            output_row["raw_text"] = raw_text
            output_row["parse_error"] = parse_error
            output_row["attempts"] = attempts
            if retry_sleep_seconds > 0:
                time.sleep(retry_sleep_seconds)
    if attempts:
        output_row["attempts"] = attempts
    if not _is_successful_response_row(output_row):
        output_row["failed"] = True
    return output_row


def _ordered_response_rows(
    request_rows: list[dict[str, Any]],
    rows_by_request_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        rows_by_request_id[request_id]
        for request_id in [str(row.get("request_id", "")) for row in request_rows]
        if request_id in rows_by_request_id
    ]


def _attempt_limit_label(max_attempts: int | None) -> str:
    return "unlimited" if max_attempts is None else str(max_attempts)


def _write_failed_requests(path: Path | None, rows: list[dict[str, Any]]) -> None:
    if path is None:
        return
    failed_rows = [row for row in rows if not _is_successful_response_row(row)]
    write_jsonl(path, failed_rows)


def _is_successful_response_row(row: dict[str, Any]) -> bool:
    return bool(row.get("response_json")) and not row.get("error_type") and not row.get("error") and not row.get("parse_error")


def _stage_config(config: LlmConfig, stage: str) -> LlmConfig:
    stage_max_tokens = {
        "speaker_attribution": 1024,
        "system_context": 768,
        "user_context": 512,
        "assistant_response": 768,
        "user_repair": 512,
    }
    max_tokens = stage_max_tokens.get(stage)
    if max_tokens is None:
        return config
    return replace(config, max_tokens=min(config.max_tokens, max_tokens))
