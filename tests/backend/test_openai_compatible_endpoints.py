import unittest

from luminous.runtime.domain.voice import VoiceProviderError
from luminous.runtime.infrastructure.client import _chat_url
from luminous.runtime.infrastructure.speech.openai_compatible import OpenAICompatibleSpeechProvider


class OpenAICompatibleEndpointTest(unittest.TestCase):
    def test_root_base_urls_gain_v1_while_explicit_paths_are_preserved(self):
        self.assertEqual(
            _chat_url("https://api.example.test"),
            "https://api.example.test/v1/chat/completions",
        )
        self.assertEqual(
            _chat_url("https://api.example.test/openai"),
            "https://api.example.test/openai/chat/completions",
        )
        self.assertEqual(
            _chat_url("https://api.example.test/v1/chat/completions"),
            "https://api.example.test/v1/chat/completions",
        )

        provider = OpenAICompatibleSpeechProvider(
            base_url="https://api.example.test",
            api_key="secret",
            tts_model="tts-1",
        )
        self.assertEqual(provider._endpoint("audio/speech"), "https://api.example.test/v1/audio/speech")

    def test_tts_rejects_html_that_was_returned_with_http_200(self):
        provider = OpenAICompatibleSpeechProvider(
            base_url="https://api.example.test/v1",
            api_key="secret",
            tts_model="tts-1",
        )
        provider._open = lambda request: (b"<!DOCTYPE html><title>Gateway</title>", "text/html")

        with self.assertRaises(VoiceProviderError) as raised:
            provider.synthesize("测试", voice_id="alloy", speaking_rate=1)

        self.assertEqual(raised.exception.code, "tts_invalid_response")


if __name__ == "__main__":
    unittest.main()
