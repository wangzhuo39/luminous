import asyncio
import json
import pickle
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, patch

from livekit import api
from livekit.agents import llm

from luminous.runtime.config import BackendConfig
from luminous.runtime.application.service import CompanionService
from luminous.runtime.infrastructure.http import make_handler
from luminous.runtime.application.livekit_service import LiveKitService
from luminous.runtime.infrastructure.livekit_agent import CompanionLLM, build_server, voice_session


class LiveKitVoiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.frontend = Path(__file__).resolve().parents[2] / "apps/companion-web/companion-ui"

    def tearDown(self):
        self.temp_dir.cleanup()

    def config(self, **updates):
        values = {
            "project_root": self.root,
            "env_path": self.root / ".env",
            "frontend_dir": self.frontend,
            "data_dir": self.root / "runtime",
            "mock": True,
            "livekit_url": "wss://livekit.example",
            "livekit_api_key": "test-key",
            "livekit_api_secret": "test-secret-with-at-least-thirty-two-bytes",
            "livekit_agent_name": "luminous-voice-agent",
            "livekit_public_url": "wss://livekit-public.example",
            "stt_api_key": "stored-stt-key",
            "stt_stream_api_key": "deployment-stt-key",
            "tts_api_key": "stored-tts-key",
            "tts_stream_api_key": "deployment-tts-key",
        }
        values.update(updates)
        return BackendConfig(**values)

    def test_session_endpoint_signs_room_scoped_token_and_dispatches_agent(self):
        config = self.config()
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/voice/livekit/session",
                data=json.dumps({"client": "android"}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                self.assertEqual(response.status, 201)
                payload = json.loads(response.read())
            claims = api.TokenVerifier(config.livekit_api_key, config.livekit_api_secret).verify(
                payload["participantToken"]
            )
            self.assertEqual(payload["serverUrl"], config.livekit_public_url)
            self.assertTrue(payload["callSessionId"].startswith("voice_"))
            self.assertEqual(claims.video.room, payload["roomName"])
            self.assertTrue(claims.video.room_join)
            self.assertEqual(claims.video.can_publish_sources, ["microphone"])
            self.assertNotIn(config.livekit_api_secret, json.dumps(payload))

            session_url = (
                f"http://127.0.0.1:{server.server_port}/api/voice/livekit/session/"
                f"{payload['callSessionId']}"
            )
            with urllib.request.urlopen(session_url, timeout=10) as response:
                session = json.loads(response.read())
            self.assertEqual(session["status"], "created")
            self.assertEqual(session["roomName"], payload["roomName"])

            connected_request = urllib.request.Request(
                f"{session_url}/metrics",
                data=json.dumps({"status": "connected", "metrics": {}}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(connected_request, timeout=10) as response:
                connected = json.loads(response.read())
            self.assertEqual(connected["status"], "connected")

            stale_request = urllib.request.Request(
                f"{session_url}/metrics",
                data=json.dumps({"status": "connecting", "metrics": {}}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(stale_request, timeout=10) as response:
                still_connected = json.loads(response.read())
            self.assertEqual(still_connected["status"], "connected")

            metrics_request = urllib.request.Request(
                f"{session_url}/metrics",
                data=json.dumps({
                    "status": "ended",
                    "metrics": {"reconnect_count": 1, "duration_ms": 1234},
                }).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(metrics_request, timeout=10) as response:
                updated = json.loads(response.read())
            self.assertEqual(updated["status"], "ended")
            self.assertEqual(updated["metrics"]["reconnect_count"], 1)

            end_request = urllib.request.Request(session_url, method="DELETE")
            with patch.object(LiveKitService, "_delete_room", new=AsyncMock()) as delete_room:
                with urllib.request.urlopen(end_request, timeout=10) as response:
                    ended = json.loads(response.read())
                delete_room.assert_awaited_once_with(payload["roomName"])
            self.assertEqual(ended["status"], "ended")
            self.assertTrue(ended["metrics"]["room_deleted"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_companion_llm_adapter_uses_luminous_service(self):
        class Service:
            def __init__(self):
                self.messages = []
                self.histories = []

            def recent_chat_context(self, limit):
                self.asserted_limit = limit
                return [{"role": "assistant", "content": "我在听。"}]

            def chat(self, text, history):
                self.messages.append(text)
                self.histories.append(history)
                return {"reply": f"叶筝：{text}"}

        async def run():
            service = Service()
            context = llm.ChatContext()
            context.add_message(role="user", content="今天有点累")
            replies = []
            async for chunk in CompanionLLM(service).chat(chat_ctx=context):
                if chunk.delta and chunk.delta.content:
                    replies.append(chunk.delta.content)
            self.assertEqual(service.messages, ["今天有点累"])
            self.assertEqual(service.histories, [[{"role": "assistant", "content": "我在听。"}]])
            self.assertEqual(service.asserted_limit, 12)
            self.assertEqual(replies, ["叶筝：今天有点累"])

        asyncio.run(run())

    def test_voice_session_entrypoint_is_process_picklable(self):
        self.assertTrue(pickle.dumps(voice_session))
        server = build_server(self.config())
        self.assertIs(server._entrypoint_fnc, voice_session)

    def test_companion_settings_do_not_replace_deployment_stream_keys(self):
        config = self.config()
        CompanionService(config)
        self.assertEqual(config.stt_stream_api_key, "deployment-stt-key")
        self.assertEqual(config.tts_stream_api_key, "deployment-tts-key")


if __name__ == "__main__":
    unittest.main()
