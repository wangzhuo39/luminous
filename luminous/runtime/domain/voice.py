from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str = ""


@dataclass(frozen=True)
class SpeechAudio:
    data: bytes
    content_type: str


class VoiceProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class SpeechToTextProvider(Protocol):
    def transcribe(self, audio: bytes, *, content_type: str, filename: str) -> TranscriptionResult: ...


class TextToSpeechProvider(Protocol):
    def synthesize(self, text: str, *, voice_id: str, speaking_rate: float) -> SpeechAudio: ...
