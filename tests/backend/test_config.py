import tempfile
import unittest
from pathlib import Path

from luminous.runtime.config import load_backend_config


class BackendConfigTest(unittest.TestCase):
    def test_duplicate_lowercase_aliases_keep_the_first_chat_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env_path = root / ".env"
            env_path.write_text(
                "\n".join(
                    (
                        "base_url=https://chat.example/v1",
                        "key=chat-key",
                        "model=chat-model",
                        "base_url=https://images.example/v1",
                        "key=image-key",
                        "model=image-model",
                    )
                ),
                encoding="utf-8",
            )

            config = load_backend_config(project_root=root, env_path=env_path, environ={})

            self.assertEqual(config.base_url, "https://chat.example/v1")
            self.assertEqual(config.api_key, "chat-key")
            self.assertEqual(config.model, "chat-model")


if __name__ == "__main__":
    unittest.main()
