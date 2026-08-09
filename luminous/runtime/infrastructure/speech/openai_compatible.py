from __future__ import annotations

import json
import mimetypes
import uuid
import urllib.error
import urllib.request
from urllib.parse import urlparse

from luminous.runtime.domain.voice import SpeechAudio, TranscriptionResult, VoiceProviderError


class OpenAICompatibleSpeechProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        stt_model: str = "",
        tts_model: str = "",
        timeout_seconds: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.stt_model = stt_model
        self.tts_model = tts_model
        self.timeout_seconds = timeout_seconds

    def transcribe(self, audio: bytes, *, content_type: str, filename: str) -> TranscriptionResult:
        boundary = f"luminous-{uuid.uuid4().hex}"
        body = _multipart_body(boundary, self.stt_model, audio, content_type, filename)
        request = urllib.request.Request(
            self._endpoint("audio/transcriptions"), data=body, method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        payload, _ = self._open(request)
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VoiceProviderError("stt_invalid_response", "语音转写服务返回了无效结果。") from exc
        text = str(decoded.get("text", "")).strip() if isinstance(decoded, dict) else ""
        if not text:
            raise VoiceProviderError("stt_empty", "没有识别到清晰语音，请重试。", retryable=True)
        return TranscriptionResult(text=text, language=str(decoded.get("language", "")))

    def synthesize(self, text: str, *, voice_id: str, speaking_rate: float) -> SpeechAudio:
        body = json.dumps({
            "model": self.tts_model,
            "input": text,
            "voice": voice_id,
            "speed": speaking_rate,
            "response_format": "mp3",
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint("audio/speech"), data=body, method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "audio/*",
                "Content-Type": "application/json",
            },
        )
        payload, content_type = self._open(request)
        if not payload:
            raise VoiceProviderError("tts_empty", "语音合成服务没有返回音频。")
        return SpeechAudio(payload, _audio_content_type(payload, content_type))

    def _endpoint(self, path: str) -> str:
        base_url = self.base_url
        if urlparse(base_url).path in {"", "/"}:
            base_url = f"{base_url}/v1"
        return f"{base_url}/{path}"

    def _open(self, request: urllib.request.Request) -> tuple[bytes, str]:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read(), response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            raise VoiceProviderError("voice_provider_error", "语音服务暂时不可用。", retryable=retryable) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise VoiceProviderError("voice_provider_unreachable", "暂时无法连接语音服务。") from exc


def _multipart_body(boundary: str, model: str, audio: bytes, content_type: str, filename: str) -> bytes:
    safe_name = filename.replace('"', "") or f"recording{mimetypes.guess_extension(content_type) or '.webm'}"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model}\r\n".encode(),
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{safe_name}\"\r\n"
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode(),
        audio,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts)


def _audio_content_type(payload: bytes, declared: str) -> str:
    media_type = declared.split(";", 1)[0].strip().lower()
    if media_type.startswith("audio/"):
        return media_type
    signatures = (
        (b"ID3", "audio/mpeg"),
        (b"OggS", "audio/ogg"),
        (b"fLaC", "audio/flac"),
        (b"RIFF", "audio/wav"),
        (b"\x1aE\xdf\xa3", "audio/webm"),
    )
    for signature, content_type in signatures:
        if payload.startswith(signature):
            return content_type
    if len(payload) >= 2 and payload[0] == 0xFF and payload[1] & 0xE0 == 0xE0:
        return "audio/mpeg"
    if len(payload) >= 12 and payload[4:8] == b"ftyp":
        return "audio/mp4"
    raise VoiceProviderError(
        "tts_invalid_response",
        "语音合成服务没有返回可播放的音频。",
        retryable=False,
    )
