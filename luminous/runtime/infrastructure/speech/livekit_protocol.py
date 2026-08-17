from __future__ import annotations

import asyncio
import json
import logging
import time
from uuid import uuid4

from livekit import agents, rtc
from livekit.agents import stt, tts, vad
from websockets.asyncio.client import connect


PROTOCOL_VERSION = "2"
STT_SAMPLE_RATE = 16_000
TTS_SAMPLE_RATE = 24_000
LOGGER = logging.getLogger("luminous.livekit_voice_protocol")


class _PhraseBuffer:
    """Turn token deltas into natural TTS-sized phrases without waiting for EOF."""

    _STRONG_ENDINGS = frozenset("。！？!?\n")
    _SOFT_ENDINGS = frozenset("，,；;：:、")

    def __init__(self, *, min_chars: int = 6, soft_chars: int = 18, max_chars: int = 36) -> None:
        self._text = ""
        self._min_chars = min_chars
        self._soft_chars = soft_chars
        self._max_chars = max_chars

    def feed(self, text: str, *, final: bool = False) -> list[str]:
        self._text += text
        phrases: list[str] = []
        while True:
            boundary = self._next_boundary()
            if boundary is None:
                break
            phrase = self._text[:boundary].strip()
            self._text = self._text[boundary:]
            if phrase:
                phrases.append(phrase)
        if final:
            phrase = self._text.strip()
            self._text = ""
            if phrase:
                phrases.append(phrase)
        return phrases

    def _next_boundary(self) -> int | None:
        for index, char in enumerate(self._text):
            prefix = self._text[: index + 1].strip()
            strong_ellipsis = char == "…" and index > 0 and self._text[index - 1] == "…"
            if (char in self._STRONG_ENDINGS or strong_ellipsis) and len(prefix) >= self._min_chars:
                if index + 1 <= self._max_chars:
                    return index + 1
                break

        for index, char in enumerate(self._text[: self._max_chars]):
            if char in self._SOFT_ENDINGS and len(self._text[: index + 1].strip()) >= self._soft_chars:
                return index + 1

        if len(self._text.strip()) < self._max_chars:
            return None

        hard_limit = min(len(self._text), self._max_chars)
        for index in range(hard_limit - 1, self._min_chars - 1, -1):
            if self._text[index] in self._SOFT_ENDINGS or self._text[index].isspace():
                return index + 1
        return hard_limit


def _json_message(message: str | bytes) -> dict[str, object]:
    if not isinstance(message, str):
        raise agents.APIConnectionError("voice service sent binary data where JSON was expected")
    try:
        payload = json.loads(message)
    except json.JSONDecodeError as exc:
        raise agents.APIConnectionError("voice service sent invalid JSON") from exc
    if not isinstance(payload, dict):
        raise agents.APIConnectionError("voice service JSON frame must be an object")
    if payload.get("type") == "error":
        raise agents.APIStatusError(
            str(payload.get("message", "voice service error")),
            body=payload,
            retryable=bool(payload.get("retryable", False)),
        )
    return payload


def _frame_bytes(frame: rtc.AudioFrame) -> bytes:
    if frame.num_channels != 1:
        raise agents.APIStatusError(
            "Luminous STT requires mono audio",
            status_code=400,
            retryable=False,
        )
    return frame.data.tobytes()


class LuminousSTT(stt.STT):
    """LiveKit STT adapter for the Luminous multi-utterance WebSocket protocol."""

    def __init__(
        self,
        *,
        stream_url: str,
        api_key: str,
        vad_model: vad.VAD,
        model: str = "qwen3-asr",
        language: str = "Chinese",
        context: str = "",
        chunk_size_sec: float = 0.5,
        timeout: float = 60,
    ) -> None:
        if not stream_url or not api_key:
            raise ValueError("Luminous streaming STT URL and API key are required")
        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=True,
                interim_results=True,
                offline_recognize=True,
            )
        )
        self._stream_url = stream_url
        self._api_key = api_key
        self._vad = vad_model
        self._model = model
        self._language = language
        self._context = context
        self._chunk_size_sec = chunk_size_sec
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "luminous"

    async def _recognize_impl(self, buffer, *, language=agents.NOT_GIVEN, conn_options):
        frame = rtc.combine_audio_frames(buffer)
        frames = [frame]
        if frame.sample_rate != STT_SAMPLE_RATE:
            resampler = rtc.AudioResampler(
                frame.sample_rate,
                STT_SAMPLE_RATE,
                num_channels=frame.num_channels,
            )
            frames = [*resampler.push(frame), *resampler.flush()]
        utterance_id = f"utt_{uuid4().hex}"
        try:
            async with asyncio.timeout(self._timeout):
                async with connect(
                    self._stream_url,
                    additional_headers={"Authorization": f"Bearer {self._api_key}"},
                    open_timeout=self._timeout,
                    max_size=None,
                ) as websocket:
                    await websocket.send(json.dumps(self._start_payload(language)))
                    ready = _json_message(await websocket.recv())
                    if ready.get("type") != "ready":
                        raise agents.APIConnectionError("STT did not send ready")
                    await websocket.send(json.dumps({
                        "type": "utterance_start",
                        "utterance_id": utterance_id,
                    }))
                    for audio_frame in frames:
                        await websocket.send(_frame_bytes(audio_frame))
                    await websocket.send(json.dumps({
                        "type": "utterance_end",
                        "utterance_id": utterance_id,
                    }))
                    while True:
                        payload = _json_message(await websocket.recv())
                        if payload.get("type") != "final":
                            continue
                        return stt.SpeechEvent(
                            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                            request_id=utterance_id,
                            alternatives=[stt.SpeechData(
                                language=str(payload.get("language", self._language)),
                                text=str(payload.get("text", "")).strip(),
                            )],
                        )
        except TimeoutError as exc:
            raise agents.APITimeoutError("Luminous STT timed out") from exc
        except agents.APIError:
            raise
        except Exception as exc:
            raise agents.APIConnectionError(f"Luminous STT connection failed: {exc}") from exc

    def _start_payload(self, language=agents.NOT_GIVEN) -> dict[str, object]:
        selected_language = self._language
        if isinstance(language, str) and language:
            selected_language = language
        return {
            "type": "start",
            "protocol_version": PROTOCOL_VERSION,
            "language": selected_language,
            "context": self._context,
            "chunk_size_sec": self._chunk_size_sec,
            "sample_rate": STT_SAMPLE_RATE,
            "channels": 1,
            "format": "s16le",
        }

    def stream(self, *, language=agents.NOT_GIVEN, conn_options=agents.DEFAULT_API_CONNECT_OPTIONS):
        return _LuminousRecognizeStream(
            self,
            language=language,
            conn_options=conn_options,
        )


class _LuminousRecognizeStream(stt.RecognizeStream):
    def __init__(self, luminous_stt: LuminousSTT, *, language, conn_options) -> None:
        super().__init__(
            stt=luminous_stt,
            conn_options=conn_options,
            sample_rate=STT_SAMPLE_RATE,
        )
        self._luminous_stt = luminous_stt
        self._language = language
        self._utterance_started_at: dict[str, float] = {}
        self._utterance_ended_at: dict[str, float] = {}

    async def _run(self) -> None:
        try:
            async with connect(
                self._luminous_stt._stream_url,
                additional_headers={
                    "Authorization": f"Bearer {self._luminous_stt._api_key}",
                },
                open_timeout=self._luminous_stt._timeout,
                max_size=None,
            ) as websocket:
                await websocket.send(json.dumps(
                    self._luminous_stt._start_payload(self._language)
                ))
                ready = _json_message(
                    await asyncio.wait_for(websocket.recv(), self._luminous_stt._timeout)
                )
                if ready.get("type") != "ready" or not ready.get("multi_utterance"):
                    raise agents.APIConnectionError("STT does not support protocol v2")

                send_task = asyncio.create_task(
                    self._send_audio(websocket),
                    name="luminous-stt-send",
                )
                receive_task = asyncio.create_task(
                    self._receive_transcripts(websocket),
                    name="luminous-stt-receive",
                )
                try:
                    await asyncio.gather(send_task, receive_task)
                finally:
                    for task in (send_task, receive_task):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(send_task, receive_task, return_exceptions=True)
        except TimeoutError as exc:
            raise agents.APITimeoutError("Luminous streaming STT timed out") from exc
        except agents.APIError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise agents.APIConnectionError(f"Luminous streaming STT failed: {exc}") from exc

    async def _send_audio(self, websocket) -> None:
        vad_stream = self._luminous_stt._vad.stream()
        active_utterance_id = ""

        async def forward_input() -> None:
            async for item in self._input_ch:
                if isinstance(item, self._FlushSentinel):
                    vad_stream.flush()
                else:
                    vad_stream.push_frame(item)
            vad_stream.end_input()

        async def forward_vad() -> None:
            nonlocal active_utterance_id
            async for event in vad_stream:
                if event.type == vad.VADEventType.START_OF_SPEECH:
                    active_utterance_id = f"utt_{uuid4().hex}"
                    self._utterance_started_at[active_utterance_id] = time.perf_counter()
                    await websocket.send(json.dumps({
                        "type": "utterance_start",
                        "utterance_id": active_utterance_id,
                    }))
                    self._event_ch.send_nowait(stt.SpeechEvent(
                        type=stt.SpeechEventType.START_OF_SPEECH,
                        request_id=active_utterance_id,
                    ))
                    for frame in event.frames:
                        await websocket.send(_frame_bytes(frame))
                elif event.type == vad.VADEventType.INFERENCE_DONE and active_utterance_id:
                    for frame in event.frames:
                        await websocket.send(_frame_bytes(frame))
                elif event.type == vad.VADEventType.END_OF_SPEECH and active_utterance_id:
                    ending_id = active_utterance_id
                    self._utterance_ended_at[ending_id] = time.perf_counter()
                    await websocket.send(json.dumps({
                        "type": "utterance_end",
                        "utterance_id": ending_id,
                    }))
                    self._event_ch.send_nowait(stt.SpeechEvent(
                        type=stt.SpeechEventType.END_OF_SPEECH,
                        request_id=ending_id,
                    ))
                    active_utterance_id = ""

        try:
            await asyncio.gather(forward_input(), forward_vad())
            if active_utterance_id:
                await websocket.send(json.dumps({
                    "type": "utterance_end",
                    "utterance_id": active_utterance_id,
                }))
            await websocket.send(json.dumps({"type": "session_end"}))
        finally:
            await vad_stream.aclose()

    async def _receive_transcripts(self, websocket) -> None:
        async for message in websocket:
            payload = _json_message(message)
            message_type = payload.get("type")
            if message_type in {"utterance_ready", "pong"}:
                continue
            if message_type == "session_ended":
                return
            if message_type not in {"partial", "final"}:
                continue
            text = str(payload.get("text", "")).strip()
            if not text:
                continue
            event_type = (
                stt.SpeechEventType.INTERIM_TRANSCRIPT
                if message_type == "partial"
                else stt.SpeechEventType.FINAL_TRANSCRIPT
            )
            utterance_id = str(payload.get("utterance_id", ""))
            if message_type == "final":
                now = time.perf_counter()
                started_at = self._utterance_started_at.pop(utterance_id, now)
                ended_at = self._utterance_ended_at.pop(utterance_id, now)
                LOGGER.info(
                    "voice_stt_final speech_to_final_ms=%d endpoint_to_final_ms=%d "
                    "audio_duration_ms=%s inference_duration_ms=%s text_chars=%d",
                    round((now - started_at) * 1000),
                    round((now - ended_at) * 1000),
                    payload.get("audio_duration_ms", 0),
                    payload.get("inference_duration_ms", 0),
                    len(text),
                )
            self._event_ch.send_nowait(stt.SpeechEvent(
                type=event_type,
                request_id=utterance_id,
                alternatives=[stt.SpeechData(
                    language=str(payload.get("language", self._luminous_stt._language)),
                    text=text,
                    metadata={
                        "revision": payload.get("revision", 0),
                        "audio_duration_ms": payload.get("audio_duration_ms", 0),
                        "inference_duration_ms": payload.get("inference_duration_ms", 0),
                    },
                )],
            ))
        raise agents.APIConnectionError("STT connection closed before session_ended")


class LuminousTTS(tts.TTS):
    """LiveKit TTS adapter for Luminous 24 kHz PCM streaming and cancellation."""

    def __init__(
        self,
        *,
        stream_url: str,
        api_key: str,
        voice: str = "default",
        instruct_text: str = "请用自然、温和的语气说话。",
        model: str = "cosyvoice3",
        timeout: float = 60,
    ) -> None:
        if not stream_url or not api_key:
            raise ValueError("Luminous streaming TTS URL and API key are required")
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=True),
            sample_rate=TTS_SAMPLE_RATE,
            num_channels=1,
        )
        self._stream_url = stream_url
        self._api_key = api_key
        self._voice = voice
        self._instruct_text = instruct_text
        self._model = model
        self._timeout = timeout
        self._connection_lock = asyncio.Lock()
        self._websocket = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "luminous"

    def synthesize(self, text: str, *, conn_options=agents.DEFAULT_API_CONNECT_OPTIONS):
        return self._synthesize_with_stream(text, conn_options=conn_options)

    def stream(self, *, conn_options=agents.DEFAULT_API_CONNECT_OPTIONS):
        return _LuminousSynthesizeStream(self, conn_options=conn_options)

    async def aprewarm(self) -> None:
        """Open and authenticate the session socket before the first spoken reply."""
        started_at = time.perf_counter()
        websocket = None
        try:
            websocket, reused = await self._acquire_websocket()
            LOGGER.info(
                "voice_tts_prewarmed elapsed_ms=%d reused=%s",
                round((time.perf_counter() - started_at) * 1000),
                reused,
            )
        finally:
            if websocket is not None:
                await self._release_websocket()

    async def _acquire_websocket(self):
        await self._connection_lock.acquire()
        try:
            reused = self._websocket is not None and self._websocket.close_code is None
            if not reused:
                self._websocket = await connect(
                    self._stream_url,
                    additional_headers={"Authorization": f"Bearer {self._api_key}"},
                    open_timeout=self._timeout,
                    max_size=None,
                )
                await self._websocket.send(json.dumps({
                    "type": "start",
                    "protocol_version": PROTOCOL_VERSION,
                    "voice_id": self._voice,
                    "instruct_text": self._instruct_text,
                }, ensure_ascii=False))
                ready = _json_message(await self._websocket.recv())
                if ready.get("type") != "ready" or not ready.get("cancellation"):
                    raise agents.APIConnectionError("TTS does not support protocol v2")
            return self._websocket, reused
        except BaseException:
            websocket = self._websocket
            self._websocket = None
            if websocket is not None:
                await websocket.close()
            if self._connection_lock.locked():
                self._connection_lock.release()
            raise

    async def _release_websocket(self, *, broken: bool = False) -> None:
        try:
            if broken and self._websocket is not None:
                await self._websocket.close()
                self._websocket = None
        finally:
            if self._connection_lock.locked():
                self._connection_lock.release()

    async def aclose(self) -> None:
        await self._connection_lock.acquire()
        try:
            if self._websocket is None:
                return
            websocket = self._websocket
            self._websocket = None
            try:
                await websocket.send(json.dumps({"type": "session_end"}))
                async with asyncio.timeout(min(self._timeout, 2.0)):
                    while True:
                        message = await websocket.recv()
                        if isinstance(message, str) and _json_message(message).get("type") == "session_ended":
                            break
            except Exception:
                pass
            finally:
                await websocket.close()
        finally:
            self._connection_lock.release()


class _LuminousSynthesizeStream(tts.SynthesizeStream):
    def __init__(self, luminous_tts: LuminousTTS, *, conn_options) -> None:
        super().__init__(tts=luminous_tts, conn_options=conn_options)
        self._luminous_tts = luminous_tts

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        output_emitter.initialize(
            request_id=f"tts_stream_{uuid4().hex}",
            sample_rate=TTS_SAMPLE_RATE,
            num_channels=1,
            mime_type="audio/pcm",
            stream=True,
        )
        websocket = None
        broken = False
        try:
            acquiring_at = time.perf_counter()
            async with asyncio.timeout(self._luminous_tts._timeout):
                websocket, reused = await self._luminous_tts._acquire_websocket()
                LOGGER.info(
                    "voice_tts_connection_ready elapsed_ms=%d reused=%s",
                    round((time.perf_counter() - acquiring_at) * 1000),
                    reused,
                )
                await self._run_connected(websocket, output_emitter)
        except TimeoutError as exc:
            broken = True
            raise agents.APITimeoutError("Luminous TTS timed out") from exc
        except agents.APIError:
            broken = True
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            broken = True
            raise agents.APIConnectionError(f"Luminous TTS connection failed: {exc}") from exc
        finally:
            if websocket is not None:
                cleanup = asyncio.create_task(
                    self._luminous_tts._release_websocket(broken=broken),
                    name="luminous-tts-release",
                )
                await asyncio.shield(cleanup)

    async def _run_connected(self, websocket, output_emitter: tts.AudioEmitter) -> None:
        active_request_id = ""
        phrase_buffer = _PhraseBuffer()
        segment_index = 0
        output_segment_started = False
        try:
            async for item in self._input_ch:
                if isinstance(item, str):
                    phrases = phrase_buffer.feed(item)
                    input_boundary = False
                else:
                    phrases = phrase_buffer.feed("", final=True)
                    input_boundary = True
                for text in phrases:
                    segment_index += 1
                    request_id = f"tts_{uuid4().hex}"
                    active_request_id = request_id
                    request_started_at = time.perf_counter()
                    LOGGER.info(
                        "voice_tts_phrase_started segment=%d text_chars=%d",
                        segment_index,
                        len(text),
                    )
                    if not output_segment_started:
                        self._mark_started()
                        output_emitter.start_segment(segment_id=f"tts_stream_{uuid4().hex}")
                        output_segment_started = True
                    await websocket.send(json.dumps({
                        "type": "synthesize",
                        "request_id": request_id,
                        "text": text,
                    }, ensure_ascii=False))
                    await self._receive_audio(
                        websocket,
                        output_emitter,
                        request_id,
                        request_started_at=request_started_at,
                    )
                    active_request_id = ""
                if input_boundary and output_segment_started:
                    output_emitter.end_segment()
                    output_segment_started = False

        except asyncio.CancelledError:
            if active_request_id:
                cleanup = asyncio.create_task(
                    self._cancel_request(websocket, active_request_id),
                    name="luminous-tts-cancel",
                )
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    await cleanup
            raise

    async def _cancel_request(self, websocket, request_id: str) -> None:
        try:
            await websocket.send(json.dumps({
                "type": "cancel",
                "request_id": request_id,
            }))
            async with asyncio.timeout(min(self._luminous_tts._timeout, 2.0)):
                while True:
                    message = await websocket.recv()
                    if isinstance(message, bytes):
                        continue
                    payload = _json_message(message)
                    if (
                        payload.get("type") in {"cancelled", "audio_end"}
                        and str(payload.get("request_id", "")) == request_id
                    ):
                        return
        except Exception:
            # Cancellation is best-effort cleanup; preserve the original task cancellation.
            return

    async def _receive_audio(
        self,
        websocket,
        output_emitter,
        request_id: str,
        *,
        request_started_at: float,
    ) -> None:
        started = False
        first_audio_logged = False
        pcm_bytes = 0
        pcm_chunks = 0
        previous_chunk_at: float | None = None
        chunk_gaps_ms: list[int] = []
        while True:
            message = await websocket.recv()
            if isinstance(message, bytes):
                if not started:
                    raise agents.APIConnectionError("TTS sent PCM before audio_start")
                pcm_bytes += len(message)
                pcm_chunks += 1
                chunk_at = time.perf_counter()
                if previous_chunk_at is not None:
                    chunk_gaps_ms.append(round((chunk_at - previous_chunk_at) * 1000))
                previous_chunk_at = chunk_at
                if not first_audio_logged:
                    first_audio_logged = True
                    LOGGER.info(
                        "voice_tts_first_audio elapsed_ms=%d",
                        round((time.perf_counter() - request_started_at) * 1000),
                    )
                output_emitter.push(message)
                continue
            payload = _json_message(message)
            message_type = payload.get("type")
            if message_type == "audio_start":
                if str(payload.get("request_id", "")) != request_id:
                    raise agents.APIConnectionError("TTS audio_start request_id mismatch")
                started = True
            elif message_type == "audio_end":
                if str(payload.get("request_id", "")) != request_id:
                    raise agents.APIConnectionError("TTS audio_end request_id mismatch")
                LOGGER.info(
                    "voice_tts_completed elapsed_ms=%d pcm_bytes=%d audio_ms=%d "
                    "pcm_chunks=%d avg_chunk_gap_ms=%d max_chunk_gap_ms=%d",
                    round((time.perf_counter() - request_started_at) * 1000),
                    pcm_bytes,
                    round(pcm_bytes / (TTS_SAMPLE_RATE * 2) * 1000),
                    pcm_chunks,
                    round(sum(chunk_gaps_ms) / len(chunk_gaps_ms)) if chunk_gaps_ms else 0,
                    max(chunk_gaps_ms, default=0),
                )
                return
            elif message_type == "cancelled":
                raise agents.APIStatusError("TTS request was cancelled", status_code=499)
