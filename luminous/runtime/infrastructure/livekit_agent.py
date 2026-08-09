from __future__ import annotations

import asyncio
import json
import logging
import os
from uuid import uuid4

from livekit import agents
from livekit.agents import llm
from livekit.plugins import silero

from luminous.runtime.application.service import CompanionService
from luminous.runtime.config import load_backend_config
from luminous.runtime.infrastructure.speech.livekit_protocol import LuminousSTT, LuminousTTS


LOGGER = logging.getLogger("luminous.livekit_agent")


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
        history = await asyncio.to_thread(self._llm.service.recent_chat_context, 12)
        result = await asyncio.to_thread(self._llm.service.chat, text, history)
        reply = str(result.get("reply", "")).strip()
        if reply:
            self._event_ch.send_nowait(
                llm.ChatChunk(
                    id=f"luminous-{uuid4().hex}",
                    delta=llm.ChoiceDelta(role="assistant", content=reply),
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
        if voice_session_id:
            await asyncio.to_thread(
                service.update_livekit_voice_session,
                voice_session_id,
                status="connected",
            )
        await session.start(
            agent=agents.Agent(
                instructions="你是叶筝。保持自然、简洁、温和的中文口语回答，不要输出 Markdown。",
            ),
            room=ctx.room,
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
