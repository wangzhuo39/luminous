from __future__ import annotations

import io
import json
import logging
import mimetypes
from pathlib import Path
import re
import uuid
import urllib.error
import urllib.request
import wave

from luminous.runtime.domain.voice import SpeechAudio, TranscriptionResult, VoiceProviderError


LOGGER = logging.getLogger(__name__)


class QwenVoiceProvider:
    """Adapter for the deployed Qwen3 ASR and CosyVoice3 HTTP protocol."""

    def __init__(
        self,
        *,
        stt_base_url: str = "",
        stt_api_key: str = "",
        stt_model: str = "qwen3-asr",
        tts_base_url: str = "",
        tts_voice: str = "default",
        tts_instruct_text: str = "",
        timeout_seconds: int = 60,
    ) -> None:
        self.stt_base_url = stt_base_url.rstrip("/")
        self.stt_api_key = stt_api_key
        self.stt_model = stt_model
        self.tts_base_url = tts_base_url.rstrip("/")
        self.tts_voice = tts_voice
        self.tts_instruct_text = tts_instruct_text
        self.timeout_seconds = timeout_seconds
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def transcribe(self, audio: bytes, *, content_type: str, filename: str) -> TranscriptionResult:
        if not self.stt_base_url or not self.stt_api_key:
            raise VoiceProviderError("stt_not_configured", "语音消息暂时不可用，请稍后再试。", retryable=False)
        media_type = content_type.split(";", 1)[0].strip().lower()
        boundary = f"luminous-{uuid.uuid4().hex}"
        body = _multipart_body(boundary, self.stt_model, audio, media_type, filename)
        request = urllib.request.Request(
            f"{self.stt_base_url}/v1/audio/transcriptions", data=body, method="POST",
            headers={
                "Authorization": f"Bearer {self.stt_api_key}",
                "Accept": "application/json",
                "User-Agent": "luminous-voice/0.1",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        payload, _ = self._open(request)
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VoiceProviderError("stt_invalid_response", "语音转写服务返回了无效结果。") from exc
        raw_text = str(decoded.get("text", "")).strip() if isinstance(decoded, dict) else ""
        text = re.sub(r"^language\s+[^<]*<asr_text>", "", raw_text, flags=re.IGNORECASE).strip()
        if not text:
            raise VoiceProviderError("stt_empty", "没有识别到清晰语音，请重试。", retryable=True)
        return TranscriptionResult(text=text, language="zh")

    def synthesize(self, text: str, *, voice_id: str, speaking_rate: float) -> SpeechAudio:
        if not self.tts_base_url:
            raise VoiceProviderError("tts_not_configured", "语音合成服务尚未配置。", retryable=False)
        # CosyVoice3 owns speed control; the current deployed protocol exposes no speed field.
        body = json.dumps({
            "text": text,
            "voice_id": voice_id or self.tts_voice,
            "instruct_text": self.tts_instruct_text,
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.tts_base_url}/v1/tts", data=body, method="POST",
            headers={
                "Accept": "audio/pcm",
                "Content-Type": "application/json",
                "User-Agent": "luminous-voice/0.1",
            },
        )
        pcm, _ = self._open(request)
        if not pcm or len(pcm) % 2:
            raise VoiceProviderError("tts_invalid_response", "语音合成服务没有返回有效音频。")
        return SpeechAudio(_wav_from_pcm(pcm), "audio/wav")

    def _open(self, request: urllib.request.Request) -> tuple[bytes, str]:
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                return response.read(), response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            detail = exc.read(512).decode("utf-8", errors="replace").replace("\n", " ").strip()
            LOGGER.warning("voice provider HTTP %s at %s: %s", exc.code, request.full_url, detail[:300])
            retryable = exc.code == 429 or exc.code >= 500
            raise VoiceProviderError("voice_provider_error", "语音服务暂时不可用。", retryable=retryable) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise VoiceProviderError("voice_provider_unreachable", "暂时无法连接语音服务。") from exc


def _multipart_body(boundary: str, model: str, audio: bytes, content_type: str, filename: str) -> bytes:
    safe_name = filename.replace('"', "") or f"recording{mimetypes.guess_extension(content_type) or '.webm'}"
    if not Path(safe_name).suffix:
        safe_name = f"{safe_name}{mimetypes.guess_extension(content_type) or '.webm'}"
    return b"".join((
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model}\r\n".encode(),
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{safe_name}\"\r\n"
         f"Content-Type: {content_type}\r\n\r\n").encode(),
        audio,
        f"\r\n--{boundary}--\r\n".encode(),
    ))


def _wav_from_pcm(pcm: bytes, *, sample_rate: int = 24_000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setparams((1, 2, sample_rate, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    return output.getvalue()
