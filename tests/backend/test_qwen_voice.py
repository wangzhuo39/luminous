import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from luminous.runtime.infrastructure.speech.qwen_voice import QwenVoiceProvider


class VoiceProtocolHandler(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.__class__.calls.append((self.path, self.headers, body))
        if self.path.endswith("/audio/transcriptions"):
            payload = json.dumps({"text": "language Chinese<asr_text>你好，协议适配成功。"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        else:
            payload = b"\x00\x00" * 240
            self.send_response(200)
            self.send_header("Content-Type", "audio/pcm")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


class QwenVoiceProviderTest(unittest.TestCase):
    def test_protocol_paths_prefix_parsing_and_pcm_wav_wrapping(self):
        VoiceProtocolHandler.calls = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), VoiceProtocolHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = QwenVoiceProvider(
                stt_base_url=f"http://127.0.0.1:{server.server_port}",
                stt_api_key="secret",
                stt_model="qwen3-asr",
                tts_base_url=f"http://127.0.0.1:{server.server_port}",
                tts_voice="default",
            )
            result = provider.transcribe(b"wav", content_type="audio/wav", filename="input.wav")
            self.assertEqual(result.text, "你好，协议适配成功。")
            audio = provider.synthesize("你好", voice_id="default", speaking_rate=1.0)
            self.assertEqual(audio.content_type, "audio/wav")
            self.assertTrue(audio.data.startswith(b"RIFF"))
            self.assertEqual([path for path, _, _ in VoiceProtocolHandler.calls], [
                "/v1/audio/transcriptions", "/v1/tts",
            ])
            self.assertEqual(VoiceProtocolHandler.calls[0][1].get("Authorization"), "Bearer secret")
            self.assertNotIn(b"\\\\r\\\\n", VoiceProtocolHandler.calls[0][2])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
