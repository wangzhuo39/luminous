from __future__ import annotations

import io
import math
import struct
import wave

from luminous.runtime.config import BackendConfig
from luminous.runtime.domain.voice import (
    SpeechAudio,
    SpeechToTextProvider,
    TextToSpeechProvider,
    TranscriptionResult,
    VoiceProviderError,
)
from luminous.runtime.infrastructure.speech import OpenAICompatibleSpeechProvider, QwenVoiceProvider


MAX_AUDIO_BYTES = 15 * 1024 * 1024
MIN_DURATION_MS = 500
MAX_DURATION_MS = 60_000
ALLOWED_AUDIO_TYPES = frozenset({"audio/webm", "audio/mp4", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/ogg"})


class VoiceService:
    def __init__(
        self,
        config: BackendConfig,
        *,
        stt: SpeechToTextProvider | None = None,
        tts: TextToSpeechProvider | None = None,
    ) -> None:
        self.config = config
        self.stt = stt or self._provider(stt=True)
        self.tts = tts or self._provider(stt=False)
        self._managed_stt = stt is None
        self._managed_tts = tts is None
        self._stt_signature = self._provider_signature(stt=True)
        self._tts_signature = self._provider_signature(stt=False)

    def provider_summary(self) -> dict[str, object]:
        return {
            "stt": {"provider": self.config.stt_provider or "openai-compatible", "configured": self.config.stt_configured},
            "tts": {"provider": self.config.tts_provider or "openai-compatible", "configured": self.config.tts_configured},
        }

    def transcribe(self, audio: bytes, *, content_type: str, duration_ms: int, filename: str = "recording") -> dict[str, object]:
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type not in ALLOWED_AUDIO_TYPES:
            raise VoiceProviderError("unsupported_audio", "此录音格式暂不支持，请换一个浏览器重试。", retryable=False)
        if not MIN_DURATION_MS <= duration_ms <= MAX_DURATION_MS:
            code = "recording_too_short" if duration_ms < MIN_DURATION_MS else "recording_too_long"
            message = "录音太短，请再说一次。" if duration_ms < MIN_DURATION_MS else "单条语音最长 60 秒。"
            raise VoiceProviderError(code, message, retryable=True)
        if not audio:
            raise VoiceProviderError("empty_audio", "没有收到录音内容，请重试。")
        if len(audio) > MAX_AUDIO_BYTES:
            raise VoiceProviderError("audio_too_large", "录音文件超过 15 MiB，请缩短后重试。", retryable=True)
        if self.config.mock:
            result = TranscriptionResult("这是一条语音消息。", "zh")
        else:
            self._refresh_stt_provider()
            if self.stt is None:
                raise VoiceProviderError("stt_not_configured", "语音消息暂时不可用，请稍后再试。", retryable=False)
            result = self.stt.transcribe(audio, content_type=media_type, filename=filename)
        return {"text": result.text, "language": result.language, "duration_ms": duration_ms}

    def synthesize(self, text: str, *, voice_id: str, speaking_rate: float) -> SpeechAudio:
        clean = text.strip()
        if not clean or len(clean) > 4_000:
            raise ValueError("text must be between 1 and 4000 characters")
        if not voice_id or len(voice_id) > 128:
            raise ValueError("voice_id must be between 1 and 128 characters")
        if not math.isfinite(speaking_rate) or not 0.5 <= speaking_rate <= 2.0:
            raise ValueError("speaking_rate must be between 0.5 and 2")
        if self.config.mock:
            return SpeechAudio(_mock_wav(), "audio/wav")
        self._refresh_tts_provider()
        if self.tts is None:
            raise VoiceProviderError("tts_not_configured", "语音合成服务尚未配置。", retryable=False)
        return self.tts.synthesize(clean, voice_id=voice_id, speaking_rate=speaking_rate)

    def _refresh_tts_provider(self) -> None:
        if not self._managed_tts:
            return
        signature = self._provider_signature(stt=False)
        if signature == self._tts_signature:
            return
        self.tts = self._provider(stt=False)
        self._tts_signature = signature

    def _refresh_stt_provider(self) -> None:
        if not self._managed_stt:
            return
        signature = self._provider_signature(stt=True)
        if signature == self._stt_signature:
            return
        self.stt = self._provider(stt=True)
        self._stt_signature = signature

    def _provider_signature(self, *, stt: bool) -> tuple[str, str, str, str, int]:
        return (
            self.config.stt_provider if stt else self.config.tts_provider,
            self.config.stt_base_url if stt else self.config.tts_base_url,
            self.config.stt_api_key if stt else self.config.tts_api_key,
            self.config.stt_model if stt else self.config.tts_model,
            self.config.voice_timeout_seconds,
        )

    def _provider(self, *, stt: bool):
        base_url = self.config.stt_base_url if stt else self.config.tts_base_url
        api_key = self.config.stt_api_key if stt else self.config.tts_api_key
        model = self.config.stt_model if stt else self.config.tts_model
        provider_name = (self.config.stt_provider if stt else self.config.tts_provider).strip().lower()
        if provider_name in {"qwen-voice", "qwen3", "cosyvoice3"} or "havilume.me" in base_url:
            if stt and (not base_url or not api_key or not model):
                return None
            if not stt and not base_url:
                return None
            return QwenVoiceProvider(
                stt_base_url=base_url if stt else "",
                stt_api_key=api_key if stt else "",
                stt_model=model if stt else "qwen3-asr",
                tts_base_url="" if stt else base_url,
                tts_voice=self.config.tts_voice,
                tts_instruct_text=self.config.tts_instruct_text,
                timeout_seconds=self.config.voice_timeout_seconds,
            )
        if not base_url or not api_key or not model:
            return None
        return OpenAICompatibleSpeechProvider(
            base_url=base_url, api_key=api_key,
            stt_model=model if stt else "", tts_model="" if stt else model,
            timeout_seconds=self.config.voice_timeout_seconds,
        )


def _mock_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setparams((1, 2, 16_000, 0, "NONE", "not compressed"))
        samples = [int(1200 * math.sin(2 * math.pi * 440 * index / 16_000)) for index in range(2_400)]
        output.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return buffer.getvalue()
