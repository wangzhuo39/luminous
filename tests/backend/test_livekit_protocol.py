import asyncio
import json
import unittest

from livekit import rtc
from livekit.agents import stt
from websockets.asyncio.server import serve

from luminous.runtime.infrastructure.speech.livekit_protocol import LuminousSTT, LuminousTTS


class LiveKitProtocolAdapterTest(unittest.TestCase):
    def test_stt_recognize_uses_v2_protocol_and_returns_final(self):
        async def run():
            controls = []

            async def handler(websocket):
                start = json.loads(await websocket.recv())
                controls.append(start)
                await websocket.send(json.dumps({
                    "type": "ready",
                    "protocol_version": "2",
                    "multi_utterance": True,
                }))
                utterance_start = json.loads(await websocket.recv())
                controls.append(utterance_start)
                self.assertIsInstance(await websocket.recv(), bytes)
                utterance_end = json.loads(await websocket.recv())
                controls.append(utterance_end)
                await websocket.send(json.dumps({
                    "type": "final",
                    "utterance_id": utterance_start["utterance_id"],
                    "language": "Chinese",
                    "text": "今天有点累",
                }, ensure_ascii=False))

            async with serve(handler, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                provider = LuminousSTT(
                    stream_url=f"ws://127.0.0.1:{port}",
                    api_key="test-key",
                    vad_model=object(),
                )
                frame = rtc.AudioFrame(
                    data=b"\x00\x00" * 3200,
                    sample_rate=16000,
                    num_channels=1,
                    samples_per_channel=3200,
                )
                event = await provider.recognize(frame)

            self.assertEqual(event.type, stt.SpeechEventType.FINAL_TRANSCRIPT)
            self.assertEqual(event.alternatives[0].text, "今天有点累")
            self.assertEqual(controls[0]["protocol_version"], "2")
            self.assertEqual(controls[1]["type"], "utterance_start")
            self.assertEqual(controls[2]["utterance_id"], controls[1]["utterance_id"])

        asyncio.run(run())

    def test_tts_synthesize_streams_raw_pcm_with_request_ids(self):
        async def run():
            controls = []
            pcm = b"\x01\x00" * 4800

            async def handler(websocket):
                start = json.loads(await websocket.recv())
                controls.append(start)
                await websocket.send(json.dumps({
                    "type": "ready",
                    "protocol_version": "2",
                    "cancellation": True,
                }))
                synthesize = json.loads(await websocket.recv())
                controls.append(synthesize)
                request_id = synthesize["request_id"]
                await websocket.send(json.dumps({
                    "type": "audio_start",
                    "request_id": request_id,
                    "sample_rate": 24000,
                    "channels": 1,
                    "format": "s16le",
                }))
                await websocket.send(pcm)
                await websocket.send(json.dumps({
                    "type": "audio_end",
                    "request_id": request_id,
                }))
                session_end = json.loads(await websocket.recv())
                controls.append(session_end)
                await websocket.send(json.dumps({"type": "session_ended"}))

            async with serve(handler, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                provider = LuminousTTS(
                    stream_url=f"ws://127.0.0.1:{port}",
                    api_key="test-key",
                    voice="default",
                )
                frames = []
                async for event in provider.synthesize("今晚早点休息。"):
                    frames.append(event.frame)
                await provider.aclose()

            self.assertTrue(frames)
            self.assertGreater(sum(frame.samples_per_channel for frame in frames), 0)
            self.assertEqual(controls[0]["protocol_version"], "2")
            self.assertEqual(controls[1]["type"], "synthesize")
            self.assertEqual(controls[1]["text"], "今晚早点休息。")
            self.assertEqual(controls[2]["type"], "session_end")

        asyncio.run(run())

    def test_tts_stream_sends_cancel_before_closing(self):
        async def run():
            request_received = asyncio.Event()
            cancel_received = asyncio.Event()
            resumed_request_received = asyncio.Event()
            connection_count = 0

            async def handler(websocket):
                nonlocal connection_count
                connection_count += 1
                await websocket.recv()
                await websocket.send(json.dumps({
                    "type": "ready",
                    "protocol_version": "2",
                    "cancellation": True,
                }))
                request = json.loads(await websocket.recv())
                await websocket.send(json.dumps({
                    "type": "audio_start",
                    "request_id": request["request_id"],
                }))
                request_received.set()
                cancel = json.loads(await websocket.recv())
                self.assertEqual(cancel, {
                    "type": "cancel",
                    "request_id": request["request_id"],
                })
                await websocket.send(json.dumps({
                    "type": "cancelled",
                    "request_id": request["request_id"],
                }))
                cancel_received.set()
                resumed = json.loads(await websocket.recv())
                self.assertEqual(resumed["type"], "synthesize")
                self.assertEqual(resumed["text"], "打断后继续说。")
                resumed_request_received.set()
                await websocket.send(json.dumps({
                    "type": "audio_start",
                    "request_id": resumed["request_id"],
                }))
                await websocket.send(b"\x01\x00" * 480)
                await websocket.send(json.dumps({
                    "type": "audio_end",
                    "request_id": resumed["request_id"],
                }))
                session_end = json.loads(await websocket.recv())
                self.assertEqual(session_end["type"], "session_end")
                await websocket.send(json.dumps({"type": "session_ended"}))

            async with serve(handler, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                provider = LuminousTTS(
                    stream_url=f"ws://127.0.0.1:{port}",
                    api_key="test-key",
                )
                stream = provider.stream()
                stream.push_text("这句话会被打断。")
                stream.flush()
                consumer = asyncio.create_task(anext(stream))
                await asyncio.wait_for(request_received.wait(), 2)
                await stream.aclose()
                await asyncio.wait_for(cancel_received.wait(), 2)
                await asyncio.gather(consumer, return_exceptions=True)
                frames = []
                async for event in provider.synthesize("打断后继续说。"):
                    frames.append(event.frame)
                await asyncio.wait_for(resumed_request_received.wait(), 2)
                await provider.aclose()
                self.assertTrue(frames)
                self.assertEqual(connection_count, 1)

        asyncio.run(run())

    def test_tts_reuses_one_websocket_across_turns(self):
        async def run():
            connection_count = 0
            synthesize_texts = []

            async def handler(websocket):
                nonlocal connection_count
                connection_count += 1
                start = json.loads(await websocket.recv())
                self.assertEqual(start["type"], "start")
                await websocket.send(json.dumps({
                    "type": "ready",
                    "protocol_version": "2",
                    "cancellation": True,
                }))
                while True:
                    request = json.loads(await websocket.recv())
                    if request["type"] == "session_end":
                        await websocket.send(json.dumps({"type": "session_ended"}))
                        return
                    synthesize_texts.append(request["text"])
                    request_id = request["request_id"]
                    await websocket.send(json.dumps({
                        "type": "audio_start",
                        "request_id": request_id,
                    }))
                    await websocket.send(b"\x01\x00" * 480)
                    await websocket.send(json.dumps({
                        "type": "audio_end",
                        "request_id": request_id,
                    }))

            async with serve(handler, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                provider = LuminousTTS(
                    stream_url=f"ws://127.0.0.1:{port}",
                    api_key="test-key",
                )
                await provider.prewarm()
                for text in ("第一句。", "第二句。"):
                    async for _ in provider.synthesize(text):
                        pass
                await provider.aclose()

            self.assertEqual(connection_count, 1)
            self.assertEqual(synthesize_texts, ["第一句。", "第二句。"])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
