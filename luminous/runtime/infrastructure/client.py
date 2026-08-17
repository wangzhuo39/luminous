from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from typing import Any
from urllib.parse import urlparse

from luminous.runtime.config import BackendConfig


Message = dict[str, str]
Transport = Callable[[BackendConfig, Sequence[Message]], str]
StreamTransport = Callable[[BackendConfig, Sequence[Message]], Iterator[str]]


class ModelClientError(RuntimeError):
    """Raised when the configured model endpoint cannot produce a response."""


class ModelClient:
    def __init__(
        self,
        config: BackendConfig,
        transport: Transport | None = None,
        stream_transport: StreamTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or openai_compatible_chat_completion
        self.stream_transport = (
            stream_transport
            if stream_transport is not None
            else openai_compatible_chat_completion_stream if transport is None else None
        )

    def complete(self, messages: Sequence[Message]) -> str:
        if not self.config.llm_configured:
            raise ModelClientError("LLM is not configured; add an API connection in companion settings or server environment")
        try:
            return self.transport(self.config, messages)
        except ModelClientError:
            raise
        except Exception as exc:  # noqa: BLE001 - present a compact API error to callers.
            raise ModelClientError(str(exc)) from exc

    def stream(self, messages: Sequence[Message]) -> Iterator[str]:
        if not self.config.llm_configured:
            raise ModelClientError("LLM is not configured; add an API connection in companion settings or server environment")
        if self.stream_transport is None:
            yield self.complete(messages)
            return
        try:
            yield from self.stream_transport(self.config, messages)
        except ModelClientError:
            raise
        except Exception as exc:  # noqa: BLE001 - present a compact API error to callers.
            raise ModelClientError(str(exc)) from exc


def openai_compatible_chat_completion(config: BackendConfig, messages: Sequence[Message]) -> str:
    url = _chat_url(config.base_url)
    payload = {
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "messages": list(messages),
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

    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(800).decode("utf-8", errors="replace")
        raise ModelClientError(f"model endpoint returned HTTP {exc.code}: {detail}") from exc

    return _response_content(body)


def openai_compatible_chat_completion_stream(
    config: BackendConfig,
    messages: Sequence[Message],
) -> Iterator[str]:
    """Yield OpenAI-compatible SSE content deltas as soon as they arrive."""
    url = _chat_url(config.base_url)
    payload = {
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "messages": list(messages),
        "stream": True,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/event-stream" not in content_type:
                body = json.loads(response.read().decode("utf-8"))
                yield _response_content(body)
                return

            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                if not data:
                    continue
                try:
                    body = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise ModelClientError("model stream returned invalid JSON") from exc
                delta = _response_delta(body)
                if delta:
                    yield delta
    except urllib.error.HTTPError as exc:
        detail = exc.read(800).decode("utf-8", errors="replace")
        raise ModelClientError(f"model endpoint returned HTTP {exc.code}: {detail}") from exc


def _chat_url(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    if urlparse(clean).path in {"", "/"}:
        clean = f"{clean}/v1"
    return f"{clean}/chat/completions"


def _response_content(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ModelClientError("model response did not include choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ModelClientError("model response choice is not an object")
    message = first.get("message")
    if isinstance(message, dict) and message.get("content") is not None:
        return str(message["content"])
    if first.get("text") is not None:
        return str(first["text"])
    raise ModelClientError("model response did not include message.content")


def _response_delta(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    delta = first.get("delta")
    if isinstance(delta, dict) and delta.get("content") is not None:
        return str(delta["content"])
    if first.get("text") is not None:
        return str(first["text"])
    return ""
