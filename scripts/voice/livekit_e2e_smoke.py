#!/usr/bin/env python3
"""Exercise the deployed voice path with a synthetic LiveKit microphone."""

from __future__ import annotations

import argparse
import asyncio
from array import array
import json
import math
import urllib.request
from uuid import uuid4

from livekit import rtc
from websockets.asyncio.client import connect

from luminous.runtime.application.service import CompanionService
from luminous.runtime.config import load_backend_config


API_BASE = "http://127.0.0.1:8000"


def _request(config, path: str, *, method: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {config.auth_token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


async def _synthesize_question(config, text: str) -> bytes:
    pcm = bytearray()
    async with connect(
        config.tts_stream_url,
        additional_headers={"Authorization": f"Bearer {config.tts_stream_api_key}"},
        open_timeout=30,
        max_size=None,
    ) as websocket:
        await websocket.send(json.dumps({
            "type": "start",
            "protocol_version": "2",
            "voice_id": config.tts_voice or "default",
            "instruct_text": config.tts_instruct_text,
        }, ensure_ascii=False))
        ready = json.loads(await websocket.recv())
        if ready.get("type") != "ready":
            raise RuntimeError(
                f"TTS did not become ready: {ready.get('code', ready.get('type'))}"
            )
        request_id = f"smoke_{uuid4().hex}"
        await websocket.send(json.dumps({
            "type": "synthesize",
            "request_id": request_id,
            "text": text,
        }, ensure_ascii=False))
        while True:
            message = await websocket.recv()
            if isinstance(message, bytes):
                pcm.extend(message)
                continue
            payload = json.loads(message)
            if payload.get("type") == "audio_end" and payload.get("request_id") == request_id:
                break
        await websocket.send(json.dumps({"type": "session_end"}))
    return bytes(pcm)


def _rms(raw: bytes) -> float:
    samples = array("h")
    samples.frombytes(raw)
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


async def run_smoke(question: str, timeout: float, server_url: str = "") -> dict:
    config = load_backend_config()
    service = CompanionService(config)
    context_before = service.recent_chat_context(24)
    question_pcm = await _synthesize_question(config, question)
    control = await asyncio.to_thread(
        _request,
        config,
        "/api/voice/livekit/session",
        method="POST",
        body={"client": "android"},
    )
    room = rtc.Room()
    agent_seen = asyncio.Event()
    response_audio_seen = asyncio.Event()
    consumers: list[asyncio.Task] = []
    evidence = {
        "remote_audio_frames": 0,
        "remote_speech_frames": 0,
        "remote_audio_ms": 0,
        "transcripts": [],
        "input_ended_at": None,
        "first_remote_speech_at": None,
        "first_final_transcript_at": None,
    }

    async def consume_audio(track: rtc.RemoteAudioTrack) -> None:
        stream = rtc.AudioStream(track, sample_rate=48_000, num_channels=1)
        try:
            async for event in stream:
                frame = event.frame
                evidence["remote_audio_frames"] += 1
                evidence["remote_audio_ms"] += round(
                    1_000 * frame.samples_per_channel / frame.sample_rate
                )
                if _rms(frame.data.tobytes()) >= 100:
                    evidence["remote_speech_frames"] += 1
                    if evidence["first_remote_speech_at"] is None:
                        evidence["first_remote_speech_at"] = asyncio.get_running_loop().time()
                if evidence["remote_speech_frames"] >= 10:
                    response_audio_seen.set()
        finally:
            await stream.aclose()

    @room.on("participant_connected")
    def on_participant_connected(participant) -> None:
        if participant.identity != room.local_participant.identity:
            agent_seen.set()

    @room.on("track_subscribed")
    def on_track_subscribed(track, publication, participant) -> None:
        if isinstance(track, rtc.RemoteAudioTrack):
            consumers.append(asyncio.create_task(consume_audio(track)))

    @room.on("transcription_received")
    def on_transcription(segments, participant, publication) -> None:
        for segment in segments:
            text = getattr(segment, "text", "").strip()
            if text:
                is_final = bool(getattr(segment, "final", False))
                if is_final and evidence["first_final_transcript_at"] is None:
                    evidence["first_final_transcript_at"] = asyncio.get_running_loop().time()
                evidence["transcripts"].append({
                    "text": text,
                    "final": is_final,
                })

    try:
        await room.connect(server_url or control["serverUrl"], control["participantToken"])
        try:
            await asyncio.wait_for(agent_seen.wait(), timeout=20)
        except asyncio.TimeoutError:
            pass
        source = rtc.AudioSource(48_000, 1, queue_size_ms=2_000)
        track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
        options = rtc.TrackPublishOptions()
        options.source = rtc.TrackSource.Value("SOURCE_MICROPHONE")
        await room.local_participant.publish_track(track, options)
        await asyncio.sleep(1)

        input_frame = rtc.AudioFrame(
            data=question_pcm,
            sample_rate=24_000,
            num_channels=1,
            samples_per_channel=len(question_pcm) // 2,
        )
        resampler = rtc.AudioResampler(24_000, 48_000, num_channels=1)
        output_pcm = b"".join(
            frame.data.tobytes()
            for frame in [*resampler.push(input_frame), *resampler.flush()]
        )
        bytes_per_frame = 960 * 2
        for offset in range(0, len(output_pcm), bytes_per_frame):
            chunk = output_pcm[offset:offset + bytes_per_frame].ljust(bytes_per_frame, b"\0")
            await source.capture_frame(rtc.AudioFrame(
                data=chunk,
                sample_rate=48_000,
                num_channels=1,
                samples_per_channel=960,
            ))
            await asyncio.sleep(0.02)
        evidence["input_ended_at"] = asyncio.get_running_loop().time()
        silence = b"\0" * bytes_per_frame
        for _ in range(75):
            await source.capture_frame(rtc.AudioFrame(
                data=silence,
                sample_rate=48_000,
                num_channels=1,
                samples_per_channel=960,
            ))
            await asyncio.sleep(0.02)

        await asyncio.wait_for(response_audio_seen.wait(), timeout=timeout)
        deadline = asyncio.get_running_loop().time() + 10
        context_after = context_before
        while context_after == context_before and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.25)
            context_after = service.recent_chat_context(24)
        latest_user = next(
            (item["content"] for item in reversed(context_after) if item["role"] == "user"),
            "",
        )
        latest_assistant = next(
            (item["content"] for item in reversed(context_after) if item["role"] == "assistant"),
            "",
        )
        if context_after == context_before or not latest_user or not latest_assistant:
            raise RuntimeError("voice response was not persisted through CompanionService.chat")
        return {
            "result": "LIVEKIT_VOICE_E2E_OK",
            "input_pcm_bytes": len(question_pcm),
            "remote_audio_frames": evidence["remote_audio_frames"],
            "remote_speech_frames": evidence["remote_speech_frames"],
            "remote_audio_ms": evidence["remote_audio_ms"],
            "endpoint_to_final_transcript_ms": _elapsed_ms(
                evidence["input_ended_at"], evidence["first_final_transcript_at"]
            ),
            "endpoint_to_first_remote_speech_ms": _elapsed_ms(
                evidence["input_ended_at"], evidence["first_remote_speech_at"]
            ),
            "latest_user": latest_user,
            "latest_assistant": latest_assistant,
            "final_transcripts": [
                item["text"] for item in evidence["transcripts"] if item["final"]
            ],
        }
    finally:
        await room.disconnect()
        for task in consumers:
            task.cancel()
        if consumers:
            await asyncio.gather(*consumers, return_exceptions=True)
        ended = await asyncio.to_thread(
            _request,
            config,
            f"/api/voice/livekit/session/{control['callSessionId']}",
            method="DELETE",
        )
        if ended.get("status") != "ended":
            raise RuntimeError("voice session did not end cleanly")


def _elapsed_ms(start: float | None, end: float | None) -> int | None:
    if start is None or end is None:
        return None
    return round((end - start) * 1000)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default="你好，请告诉我现在的语音通话是否清楚。")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument(
        "--server-url",
        default="",
        help="Override the client-facing URL, for example ws://127.0.0.1:7880 in WSL smoke tests.",
    )
    args = parser.parse_args()
    print(json.dumps(
        asyncio.run(run_smoke(args.question, args.timeout, args.server_url)),
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
