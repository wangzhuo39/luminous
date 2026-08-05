import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from luminous.runtime.application.notification_bridge import NotificationBridge
from luminous.runtime.config import BackendConfig
from luminous.runtime.domain.events import ProactiveSignal
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore


class _SuccessfulFcmBridge(NotificationBridge):
    def _deliver_fcm(self, title, message, payload, *, delivered_device_ids=None):
        return 200, "projects/test/messages/1", {"delivered_devices": 1, "failed_devices": 0}


class NotificationBridgeTest(unittest.TestCase):
    def test_fcm_requires_a_registered_device_and_returns_delivery_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = BackendConfig(
                project_root=root,
                env_path=root / ".env",
                frontend_dir=root,
                notify_enabled=True,
                notify_channel="fcm",
                notify_fcm_project_id="test-project",
                notify_fcm_service_account_file=str(root / "service-account.json"),
            )
            store = CompanionRuntimeStore(root / "runtime")
            bridge = _SuccessfulFcmBridge(config, store)
            signal = ProactiveSignal(due=True, score=0.8, reason="test", next_check_minutes=15)

            skipped = bridge.deliver(message="你好", signal=signal, trace_id="trace-1")
            self.assertFalse(skipped.attempted)
            self.assertEqual(skipped.channel, "fcm")
            self.assertEqual(skipped.detail, "no_registered_android_device")

            store.upsert_notification_device(token="token-1")
            delivered = bridge.deliver(message="你好", signal=signal, trace_id="trace-1")
            self.assertTrue(delivered.ok)
            self.assertEqual(delivered.provider, "fcm")
            self.assertEqual(delivered.metadata["delivered_devices"], 1)

    def test_fcm_partial_failure_retries_only_devices_not_already_delivered(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_account_file = root / "service-account.json"
            service_account_file.write_text("{}", encoding="utf-8")
            config = BackendConfig(
                project_root=root,
                env_path=root / ".env",
                frontend_dir=root,
                notify_enabled=True,
                notify_channel="fcm",
                notify_fcm_project_id="test-project",
                notify_fcm_service_account_file=str(service_account_file),
            )
            store = CompanionRuntimeStore(root / "runtime")
            store.upsert_notification_device(token="token-1", installation_id="install-1")
            store.upsert_notification_device(token="token-2", installation_id="install-2")
            bridge = NotificationBridge(config, store)
            signal = ProactiveSignal(due=True, score=0.8, reason="test", next_check_minutes=15)
            credentials = Mock(token="access-token")
            credentials.refresh = Mock()
            response = MagicMock()
            response.status = 200
            response.read.return_value = b'{"name":"projects/test/messages/1"}'
            response.__enter__.return_value = response

            with (
                patch(
                    "google.oauth2.service_account.Credentials.from_service_account_file",
                    return_value=credentials,
                ),
                patch(
                    "urllib.request.urlopen",
                    side_effect=[response, urllib.error.URLError("temporary")],
                ) as first_urlopen,
            ):
                partial = bridge.deliver(message="你好", signal=signal, trace_id="trace-1")
            self.assertFalse(partial.ok)
            self.assertEqual(partial.status_code, 503)
            self.assertEqual(partial.metadata["delivered_devices"], 1)
            self.assertEqual(partial.metadata["retryable_failed_devices"], 1)
            self.assertEqual(len(partial.metadata["delivered_device_ids"]), 1)
            self.assertEqual(first_urlopen.call_count, 2)

            retry_response = MagicMock()
            retry_response.status = 200
            retry_response.read.return_value = b'{"name":"projects/test/messages/2"}'
            retry_response.__enter__.return_value = retry_response
            with (
                patch(
                    "google.oauth2.service_account.Credentials.from_service_account_file",
                    return_value=credentials,
                ),
                patch("urllib.request.urlopen", return_value=retry_response) as retry_urlopen,
            ):
                completed = bridge.deliver(
                    message="你好",
                    signal=signal,
                    trace_id="trace-1",
                    delivery_context=partial.metadata,
                )
            self.assertTrue(completed.ok)
            self.assertEqual(retry_urlopen.call_count, 1)
            self.assertEqual(len(completed.metadata["delivered_device_ids"]), 2)


if __name__ == "__main__":
    unittest.main()
