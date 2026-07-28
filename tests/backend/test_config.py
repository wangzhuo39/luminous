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

    def test_public_cookie_auth_and_external_data_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "durable-data"
            config = load_backend_config(
                project_root=root,
                env_path=root / ".env",
                environ={
                    "LUMINOUS_DEPLOYMENT_MODE": "public",
                    "LUMINOUS_CORS_ORIGINS": "https://test.example",
                    "LUMINOUS_TESTER_ACCESS_CODE": "invite-code",
                    "LUMINOUS_SESSION_SECRET": "test-session-secret",
                    "LUMINOUS_DATA_DIR": str(data_dir),
                },
            )

            config.validate_server_boundary()
            self.assertTrue(config.cookie_auth_configured)
            self.assertEqual(config.runtime_data_dir, data_dir.resolve())

    def test_tester_access_code_requires_session_secret(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaisesRegex(ValueError, "session secret"):
                load_backend_config(
                    project_root=root,
                    env_path=root / ".env",
                    environ={"LUMINOUS_TESTER_ACCESS_CODE": "invite-code"},
                )


if __name__ == "__main__":
    unittest.main()
