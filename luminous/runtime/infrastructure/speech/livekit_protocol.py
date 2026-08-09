from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from livekit import agents, rtc
from livekit.agents import stt, tts, vad
from websockets.asyncio.client import connect


PROTOCOL_VERSION = "2"
STT_SAMPLE_RATE = 16_000
TTS_SAMPLE_RATE = 24_000


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
            self._event_ch.send_nowait(stt.SpeechEvent(
                type=event_type,
                request_id=str(payload.get("utterance_id", "")),
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
        try:
            async with asyncio.timeout(self._luminous_tts._timeout):
                async with connect(
                    self._luminous_tts._stream_url,
                    additional_headers={
                        "Authorization": f"Bearer {self._luminous_tts._api_key}",
                    },
                    open_timeout=self._luminous_tts._timeout,
                    max_size=None,
                ) as websocket:
                    await self._run_connected(websocket, output_emitter)
        except TimeoutError as exc:
            raise agents.APITimeoutError("Luminous TTS timed out") from exc
        except agents.APIError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise agents.APIConnectionError(f"Luminous TTS connection failed: {exc}") from exc

    async def _run_connected(self, websocket, output_emitter: tts.AudioEmitter) -> None:
        active_request_id = ""
        try:
            await websocket.send(json.dumps({
                "type": "start",
                "protocol_version": PROTOCOL_VERSION,
                "voice_id": self._luminous_tts._voice,
                "instruct_text": self._luminous_tts._instruct_text,
            }, ensure_ascii=False))
            ready = _json_message(await websocket.recv())
            if ready.get("type") != "ready" or not ready.get("cancellation"):
                raise agents.APIConnectionError("TTS does not support protocol v2")

            text_parts: list[str] = []
            async for item in self._input_ch:
                if isinstance(item, str):
                    text_parts.append(item)
                    continue
                text = "".join(text_parts).strip()
                text_parts.clear()
                if not text:
                    continue
                request_id = f"tts_{uuid4().hex}"
                active_request_id = request_id
                self._mark_started()
                output_emitter.start_segment(segment_id=request_id)
                await websocket.send(json.dumps({
                    "type": "synthesize",
                    "request_id": request_id,
                    "text": text,
                }, ensure_ascii=False))
                await self._receive_audio(websocket, output_emitter, request_id)
                output_emitter.end_segment()
                active_request_id = ""

            await websocket.send(json.dumps({"type": "session_end"}))
            while True:
                payload = _json_message(await websocket.recv())
                if payload.get("type") == "session_ended":
                    return
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

    async def _receive_audio(self, websocket, output_emitter, request_id: str) -> None:
        started = False
        while True:
            message = await websocket.recv()
            if isinstance(message, bytes):
                if not started:
                    raise agents.APIConnectionError("TTS sent PCM before audio_start")
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
                return
            elif message_type == "cancelled":
                raise agents.APIStatusError("TTS request was cancelled", status_code=499)
