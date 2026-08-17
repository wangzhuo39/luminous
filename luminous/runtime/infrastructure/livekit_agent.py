from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from uuid import uuid4

from livekit import agents
from livekit.agents import llm
from livekit.plugins import silero

from luminous.runtime.application.service import CompanionService
from luminous.runtime.config import load_backend_config
from luminous.runtime.infrastructure.speech.livekit_protocol import LuminousSTT, LuminousTTS


LOGGER = logging.getLogger("luminous.livekit_agent")
AGENT_CONTROL_TOPIC = "luminous.voice.control"
TTS_WARMUP_GREETING = "我在。"
_HIDDEN_SPEECH_TAGS = {"think", "system_thinking", "role_thinking", "role_action"}


class _SpokenTextFilter:
    """Incrementally remove model-only tags before text reaches TTS."""

    def __init__(self) -> None:
        self._mode = "text"
        self._hidden_tag = ""
        self._tag_buffer = ""

    def feed(self, text: str) -> str:
        visible: list[str] = []
        for char in text:
            if self._mode == "text":
                if char == "<":
                    self._mode = "tag"
                    self._tag_buffer = char
                else:
                    visible.append(char)
                continue

            if self._mode == "hidden":
                if char == "<":
                    self._mode = "hidden_tag"
                    self._tag_buffer = char
                continue

            self._tag_buffer += char
            if char != ">":
                if len(self._tag_buffer) > 80:
                    self._tag_buffer = ""
                    self._mode = "hidden" if self._hidden_tag else "text"
                continue

            tag = self._tag_buffer[1:-1].strip().lower().split(maxsplit=1)[0]
            self._tag_buffer = ""
            closing = tag.startswith("/")
            name = tag.lstrip("/")
            if self._mode == "tag" and not closing and name in _HIDDEN_SPEECH_TAGS:
                self._hidden_tag = name
                self._mode = "hidden"
            elif self._mode == "hidden_tag" and closing and name in _HIDDEN_SPEECH_TAGS:
                self._hidden_tag = ""
                self._mode = "text"
            else:
                self._mode = "hidden" if self._hidden_tag else "text"
        return "".join(visible)

    def finish(self) -> str:
        # Incomplete markup or hidden reasoning must never be spoken.
        self._tag_buffer = ""
        self._mode = "text"
        self._hidden_tag = ""
        return ""


class CompanionLLM(llm.LLM):
    """Minimal LiveKit LLM adapter that preserves Luminous memory semantics."""

    def __init__(self, service: CompanionService) -> None:
        super().__init__()
        self.service = service

    def chat(self, *, chat_ctx, tools=None, conn_options=agents.DEFAULT_API_CONNECT_OPTIONS,
             parallel_tool_calls=agents.NOT_GIVEN, tool_choice=agents.NOT_GIVEN,
             extra_kwargs=agents.NOT_GIVEN):
        return CompanionLLMStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class CompanionLLMStream(llm.LLMStream):
    async def _run(self) -> None:
        text = ""
        for item in reversed(self._chat_ctx.items):
            if getattr(item, "role", None) != "user":
                continue
            content = getattr(item, "content", [])
            text = " ".join(str(part) for part in content if isinstance(part, str)).strip()
            if text:
                break
        if not text:
            return
        started_at = time.perf_counter()
        history_started_at = time.perf_counter()
        history = await asyncio.to_thread(self._llm.service.recent_chat_context, 12)
        LOGGER.info(
            "voice_llm_started input_chars=%d history_items=%d history_ms=%d",
            len(text),
            len(history),
            round((time.perf_counter() - history_started_at) * 1000),
        )
        loop = asyncio.get_running_loop()
        events: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        cancelled = threading.Event()
        text_filter = _SpokenTextFilter()
        visible_parts: list[str] = []
        first_delta_logged = False
        completion_id = f"luminous-{uuid4().hex}"

        def enqueue(kind: str, value: object) -> None:
            if cancelled.is_set():
                return
            try:
                loop.call_soon_threadsafe(events.put_nowait, (kind, value))
            except RuntimeError:
                return

        def run_chat() -> None:
            try:
                stream_chat = getattr(self._llm.service, "chat_stream", None)
                if callable(stream_chat):
                    result = stream_chat(
                        text,
                        history,
                        extract_memory=False,
                        on_model_delta=lambda delta: enqueue("delta", delta),
                        cancelled=cancelled.is_set,
                    )
                else:
                    result = self._llm.service.chat(
                        text,
                        history,
                        extract_memory=False,
                    )
                    enqueue("delta", str(result.get("reply", "")))
            except BaseException as exc:  # noqa: BLE001 - forward worker failure to the async stream.
                enqueue("error", exc)
            else:
                enqueue("done", result)

        worker = asyncio.create_task(asyncio.to_thread(run_chat), name="luminous-chat-stream")
        completed = False
        try:
            while True:
                kind, value = await events.get()
                if kind == "delta":
                    visible = text_filter.feed(str(value))
                    if not visible:
                        continue
                    if not first_delta_logged:
                        first_delta_logged = True
                        LOGGER.info(
                            "voice_llm_first_spoken_delta elapsed_ms=%d",
                            round((time.perf_counter() - started_at) * 1000),
                        )
                    visible_parts.append(visible)
                    self._send_text(visible, completion_id)
                    continue
                if kind == "error":
                    raise value
                result = value
                text_filter.finish()
                reply = str(result.get("reply", "")).strip()
                if not "".join(visible_parts).strip() and reply:
                    fallback_filter = _SpokenTextFilter()
                    spoken_reply = fallback_filter.feed(reply) + fallback_filter.finish()
                    if spoken_reply.strip():
                        visible_parts.append(spoken_reply)
                        self._send_text(spoken_reply, completion_id)
                LOGGER.info(
                    "voice_llm_completed elapsed_ms=%d reply_chars=%d streamed_chars=%d",
                    round((time.perf_counter() - started_at) * 1000),
                    len(reply),
                    len("".join(visible_parts)),
                )
                completed = True
                await worker
                return
        finally:
            if not completed:
                cancelled.set()
                worker.cancel()

    def _send_text(self, text: str, completion_id: str) -> None:
        if text:
            self._event_ch.send_nowait(
                llm.ChatChunk(
                    id=completion_id,
                    delta=llm.ChoiceDelta(role="assistant", content=text),
                )
            )


async def voice_session(ctx: agents.JobContext) -> None:
    """Run one voice call from a module-level, process-picklable entrypoint."""
    config = load_backend_config()
    service = CompanionService(config)
    try:
        metadata = json.loads(getattr(ctx.job, "metadata", "") or "{}")
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    voice_session_id = str(metadata.get("voice_session_id", ""))
    if voice_session_id:
        await asyncio.to_thread(
            service.update_livekit_voice_session,
            voice_session_id,
            status="connecting",
        )

        async def mark_ended(reason: str) -> None:
            await asyncio.to_thread(
                service.update_livekit_voice_session,
                voice_session_id,
                status="ended",
                metrics={"agent_shutdown_reason": reason},
            )

        ctx.add_shutdown_callback(mark_ended)
    vad_model = silero.VAD.load()
    stt_provider = LuminousSTT(
        stream_url=config.stt_stream_url,
        api_key=config.stt_stream_api_key,
        vad_model=vad_model,
        model=config.stt_model or "qwen3-asr",
        language="Chinese",
        chunk_size_sec=0.5,
        timeout=float(config.voice_timeout_seconds),
    )
    tts_provider = LuminousTTS(
        stream_url=config.tts_stream_url,
        api_key=config.tts_stream_api_key,
        model=config.tts_model or "cosyvoice3",
        voice=config.tts_voice or "default",
        instruct_text=config.tts_instruct_text,
        timeout=float(config.voice_timeout_seconds),
    )
    tts_prewarm_task = asyncio.create_task(
        tts_provider.aprewarm(),
        name="luminous-tts-prewarm",
    )

    def log_prewarm_failure(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            LOGGER.warning("voice_tts_prewarm_failed error=%s", error)

    tts_prewarm_task.add_done_callback(log_prewarm_failure)
    session = agents.AgentSession(
        stt=stt_provider,
        vad=vad_model,
        llm=CompanionLLM(service),
        tts=tts_provider,
        allow_interruptions=True,
        min_endpointing_delay=0.35,
        max_endpointing_delay=2.0,
    )
    try:
        await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)
        await session.start(
            agent=agents.Agent(
                instructions="你是叶筝。保持自然、简洁、温和的中文口语回答，不要输出 Markdown。",
            ),
            room=ctx.room,
        )
        warmup_started_at = time.perf_counter()
        warmup_speech = session.say(
            TTS_WARMUP_GREETING,
            allow_interruptions=False,
            add_to_chat_ctx=False,
        )
        await warmup_speech.wait_for_playout()
        warmup_elapsed_ms = round((time.perf_counter() - warmup_started_at) * 1000)
        LOGGER.info("voice_tts_warmup_played elapsed_ms=%d", warmup_elapsed_ms)
        await ctx.room.local_participant.publish_data(
            json.dumps({"type": "agent_ready", "tts_warmup_ms": warmup_elapsed_ms}),
            reliable=True,
            topic=AGENT_CONTROL_TOPIC,
        )
        if voice_session_id:
            await asyncio.to_thread(
                service.update_livekit_voice_session,
                voice_session_id,
                status="connected",
                metrics={"tts_warmup_ms": warmup_elapsed_ms},
            )
    except Exception as exc:
        if voice_session_id:
            await asyncio.to_thread(
                service.update_livekit_voice_session,
                voice_session_id,
                status="failed",
                last_error=str(exc),
            )
        raise


def build_server(config):
    server = agents.AgentServer(
        ws_url=config.livekit_url,
        api_key=config.livekit_api_key,
        api_secret=config.livekit_api_secret,
        host="127.0.0.1",
        port=int(os.getenv("LUMINOUS_LIVEKIT_AGENT_PORT", "8090")),
    )
    server.rtc_session(voice_session, agent_name=config.livekit_agent_name)
    return server


def main() -> None:
    config = load_backend_config()
    if not config.livekit_configured:
        raise SystemExit("LUMINOUS_LIVEKIT_URL/API_KEY/API_SECRET are required")
    if not config.stt_stream_url or not config.stt_stream_api_key:
        raise SystemExit("LUMINOUS_STT_STREAM_URL/STREAM_API_KEY are required")
    if not config.tts_stream_url or not config.tts_stream_api_key:
        raise SystemExit("LUMINOUS_TTS_STREAM_URL/STREAM_API_KEY are required")
    logging.basicConfig(level=logging.INFO)
    agents.cli.run_app(build_server(config))


if __name__ == "__main__":
    main()
