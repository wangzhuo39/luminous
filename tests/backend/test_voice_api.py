import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from luminous.runtime.application.voice_service import VoiceService
from luminous.runtime.config import BackendConfig
from luminous.runtime.domain.voice import SpeechAudio, TranscriptionResult, VoiceProviderError
from luminous.runtime.infrastructure.http import make_handler


class FakeStt:
    def transcribe(self, audio, *, content_type, filename):
        self.call = (audio, content_type, filename)
        return TranscriptionResult("明天提醒我喝水", "zh")


class FakeTts:
    def synthesize(self, text, *, voice_id, speaking_rate):
        self.call = (text, voice_id, speaking_rate)
        return SpeechAudio(b"ID3test-audio", "audio/mpeg")


class CapturingTtsHandler(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.__class__.calls.append({
            "path": self.path,
            "authorization": self.headers.get("Authorization", ""),
            "payload": json.loads(self.rfile.read(length)),
        })
        body = b"ID3configured-tts-audio"
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class CapturingSttHandler(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.__class__.calls.append({
            "path": self.path,
            "authorization": self.headers.get("Authorization", ""),
            "body": body,
        })
        payload = json.dumps({"text": "动态语音转写已生效", "language": "zh"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


class VoiceApiTest(unittest.TestCase):
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
            "stt_provider": "funasr",
            "stt_base_url": "https://stt.example/v1",
            "stt_api_key": "stt-private-key",
            "stt_model": "SenseVoiceSmall",
            "tts_provider": "cosyvoice",
            "tts_base_url": "https://tts.example/v1",
            "tts_api_key": "tts-private-key",
            "tts_model": "CosyVoice2",
        }
        values.update(updates)
        return BackendConfig(**values)

    def test_provider_contract_validates_audio_without_persisting_it(self):
        stt = FakeStt()
        tts = FakeTts()
        service = VoiceService(self.config(), stt=stt, tts=tts)

        result = service.transcribe(
            b"not-real-audio", content_type="audio/wav", duration_ms=1_250,
        )
        self.assertEqual(result["text"], "明天提醒我喝水")
        self.assertEqual(stt.call[1], "audio/wav")
        self.assertFalse((self.root / "runtime").exists())

        audio = service.synthesize("晚安", voice_id="warm", speaking_rate=0.9)
        self.assertEqual(audio.content_type, "audio/mpeg")
        self.assertEqual(tts.call, ("晚安", "warm", 0.9))

    def test_validation_distinguishes_short_large_and_unsupported_audio(self):
        service = VoiceService(self.config(), stt=FakeStt(), tts=FakeTts())
        cases = [
            ({"audio": b"x", "content_type": "audio/wav", "duration_ms": 100}, "recording_too_short"),
            ({"audio": b"x", "content_type": "video/mp4", "duration_ms": 1000}, "unsupported_audio"),
            ({"audio": b"x" * (15 * 1024 * 1024 + 1), "content_type": "audio/wav", "duration_ms": 1000}, "audio_too_large"),
        ]
        for kwargs, code in cases:
            with self.subTest(code=code), self.assertRaises(VoiceProviderError) as raised:
                service.transcribe(**kwargs)
            self.assertEqual(raised.exception.code, code)

    def test_http_voice_endpoints_and_public_settings_redact_provider_keys(self):
        config = self.config(mock=True)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        try:
            transcription = urllib.request.Request(
                f"{base}/api/voice/transcriptions", data=b"mock-audio", method="POST",
                headers={"Content-Type": "audio/wav", "X-Audio-Duration-Ms": "1200"},
            )
            with urllib.request.urlopen(transcription, timeout=10) as response:
                payload = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertTrue(payload["text"])

            speech = urllib.request.Request(
                f"{base}/api/voice/speech",
                data=json.dumps({"text": "测试声音", "voice_id": "warm", "speaking_rate": 1}).encode(),
                method="POST", headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(speech, timeout=10) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get_content_type(), "audio/wav")
                self.assertGreater(len(response.read()), 100)

            with urllib.request.urlopen(f"{base}/api/chat/history", timeout=10) as response:
                self.assertEqual(json.loads(response.read())["count"], 0)

            with urllib.request.urlopen(f"{base}/api/settings/companion", timeout=10) as response:
                settings = json.loads(response.read())
            serialized = json.dumps(settings)
            self.assertNotIn("stt-private-key", serialized)
            self.assertNotIn("tts-private-key", serialized)
            self.assertEqual(settings["providers"]["stt"]["provider"], "funasr")
            self.assertTrue(settings["providers"]["tts"]["configured"])
            self.assertEqual(settings["voice"]["auto_play"], False)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_http_short_recording_returns_recoverable_error_code(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.config(mock=True)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/voice/transcriptions",
                data=b"x", method="POST",
                headers={"Content-Type": "audio/wav", "X-Audio-Duration-Ms": "100"},
            )
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=10)
            self.assertEqual(raised.exception.code, 422)
            payload = json.loads(raised.exception.read())
            self.assertEqual(payload["error"]["code"], "recording_too_short")
            self.assertTrue(payload["error"]["retryable"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_user_tts_api_settings_take_effect_without_server_restart(self):
        CapturingTtsHandler.calls = []
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), CapturingTtsHandler)
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()
        config = self.config(
            mock=False,
            tts_base_url="",
            tts_api_key="",
            tts_model="",
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        try:
            tts_base_url = f"http://127.0.0.1:{upstream.server_port}/v1"
            settings_request = urllib.request.Request(
                f"{base}/api/settings/companion",
                data=json.dumps({
                    "tts_base_url": tts_base_url,
                    "tts_api_key": "user-tts-secret",
                    "tts_model": "user-tts-model",
                    "voice_id": "warm-user-voice",
                    "speaking_rate": 0.85,
                }).encode(),
                method="PATCH",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(settings_request, timeout=10) as response:
                settings = json.loads(response.read())
            self.assertEqual(settings["tts"]["base_url"], tts_base_url)
            self.assertEqual(settings["tts"]["model"], "user-tts-model")
            self.assertTrue(settings["tts"]["api_key_configured"])
            self.assertNotIn("user-tts-secret", json.dumps(settings))

            speech_request = urllib.request.Request(
                f"{base}/api/voice/speech",
                data=json.dumps({"text": "用户配置已经生效"}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(speech_request, timeout=10) as response:
                self.assertEqual(response.headers.get_content_type(), "audio/mpeg")
                self.assertEqual(response.read(), b"ID3configured-tts-audio")

            self.assertEqual(len(CapturingTtsHandler.calls), 1)
            call = CapturingTtsHandler.calls[0]
            self.assertEqual(call["path"], "/v1/audio/speech")
            self.assertEqual(call["authorization"], "Bearer user-tts-secret")
            self.assertEqual(call["payload"]["model"], "user-tts-model")
            self.assertEqual(call["payload"]["voice"], "warm-user-voice")
            self.assertEqual(call["payload"]["speed"], 0.85)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(timeout=2)

    def test_user_stt_api_settings_take_effect_without_server_restart(self):
        CapturingSttHandler.calls = []
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), CapturingSttHandler)
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()
        config = self.config(mock=False, stt_base_url="", stt_api_key="", stt_model="")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        try:
            stt_base_url = f"http://127.0.0.1:{upstream.server_port}/v1"
            settings_request = urllib.request.Request(
                f"{base}/api/settings/companion",
                data=json.dumps({
                    "stt_base_url": stt_base_url,
                    "stt_api_key": "user-stt-secret",
                    "stt_model": "whisper-1",
                }).encode(),
                method="PATCH",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(settings_request, timeout=10) as response:
                settings = json.loads(response.read())
            self.assertEqual(settings["stt"]["base_url"], stt_base_url)
            self.assertEqual(settings["stt"]["model"], "whisper-1")
            self.assertTrue(settings["stt"]["api_key_configured"])
            self.assertNotIn("user-stt-secret", json.dumps(settings))

            transcription_request = urllib.request.Request(
                f"{base}/api/voice/transcriptions",
                data=b"recorded-audio",
                method="POST",
                headers={"Content-Type": "audio/wav", "X-Audio-Duration-Ms": "1200"},
            )
            with urllib.request.urlopen(transcription_request, timeout=10) as response:
                result = json.loads(response.read())
            self.assertEqual(result["text"], "动态语音转写已生效")

            self.assertEqual(len(CapturingSttHandler.calls), 1)
            call = CapturingSttHandler.calls[0]
            self.assertEqual(call["path"], "/v1/audio/transcriptions")
            self.assertEqual(call["authorization"], "Bearer user-stt-secret")
            self.assertIn(b'name="model"', call["body"])
            self.assertIn(b"whisper-1", call["body"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
