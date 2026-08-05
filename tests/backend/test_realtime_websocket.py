import base64
import hashlib
import json
import os
import socket
import struct
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from luminous.runtime.config import BackendConfig
from luminous.runtime.infrastructure.http import make_handler


class _SocketReader:
    def __init__(self, connection: socket.socket) -> None:
        self.connection = connection
        self.buffer = bytearray()

    def http_headers(self) -> str:
        marker = b"\r\n\r\n"
        while marker not in self.buffer:
            self.buffer.extend(self.connection.recv(4096))
        end = self.buffer.index(marker) + len(marker)
        headers = bytes(self.buffer[:end]).decode("iso-8859-1")
        del self.buffer[:end]
        return headers

    def frame(self) -> tuple[int, dict[str, object]]:
        self._fill(2)
        first, second = self.buffer[0], self.buffer[1]
        length = second & 0x7F
        offset = 2
        if length == 126:
            self._fill(offset + 2)
            length = struct.unpack("!H", self.buffer[offset:offset + 2])[0]
            offset += 2
        elif length == 127:
            self._fill(offset + 8)
            length = struct.unpack("!Q", self.buffer[offset:offset + 8])[0]
            offset += 8
        self._fill(offset + length)
        payload = bytes(self.buffer[offset:offset + length])
        del self.buffer[:offset + length]
        return first & 0x0F, json.loads(payload.decode("utf-8"))

    def _fill(self, size: int) -> None:
        while len(self.buffer) < size:
            chunk = self.connection.recv(4096)
            if not chunk:
                raise ConnectionError("websocket closed")
            self.buffer.extend(chunk)


def _masked_text(payload: dict[str, object]) -> bytes:
    encoded = json.dumps(payload).encode("utf-8")
    mask = os.urandom(4)
    if len(encoded) < 126:
        header = bytes((0x81, 0x80 | len(encoded)))
    else:
        header = bytes((0x81, 0x80 | 126)) + struct.pack("!H", len(encoded))
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(encoded))
    return header + mask + masked


class RealtimeWebSocketTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        config = BackendConfig(
            project_root=root,
            env_path=root / ".env",
            frontend_dir=Path(__file__).resolve().parents[2] / "apps/companion-web/companion-ui",
            mock=True,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def test_realtime_endpoint_requires_websocket_upgrade(self) -> None:
        url = f"http://127.0.0.1:{self.server.server_port}/api/realtime/outbox"
        with self.assertRaises(urllib.error.HTTPError) as captured:
            urllib.request.urlopen(url, timeout=5)
        self.assertEqual(captured.exception.code, 426)

    def test_realtime_stream_delivers_outbox_and_records_display_receipt(self) -> None:
        store = self.server.RequestHandlerClass.service.runtime.store
        store.append_outbox({
            "message_id": "realtime-message-1",
            "draft_text": "这是一封实时抵达的来信。",
            "status": "queued",
            "signal_type": "checkin",
            "idempotency_key": "realtime-message-once",
        })
        connection = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=5)
        connection.settimeout(5)
        reader = _SocketReader(connection)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET /api/realtime/outbox?since=0 HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.server.server_port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Sec-WebSocket-Protocol: luminous.realtime.v1\r\n\r\n"
        )
        connection.sendall(request.encode("ascii"))
        headers = reader.http_headers()
        expected_accept = base64.b64encode(
            hashlib.sha1(f"{key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11".encode("ascii")).digest()
        ).decode("ascii")
        self.assertIn(" 101 ", headers)
        self.assertIn(f"Sec-WebSocket-Accept: {expected_accept}", headers)
        self.assertIn("Sec-WebSocket-Protocol: luminous.realtime.v1", headers)

        _, ready = reader.frame()
        _, message = reader.frame()
        self.assertEqual(ready["type"], "ready")
        self.assertEqual(message["type"], "proactive_message")
        self.assertEqual(message["message_id"], "realtime-message-1")
        self.assertEqual(message["body"], "这是一封实时抵达的来信。")
        self.assertIn("message_id=realtime-message-1", message["deep_link"])

        connection.sendall(_masked_text({
            "type": "receipt",
            "message_id": "realtime-message-1",
            "receipt_type": "notification_displayed",
        }))
        _, acknowledgement = reader.frame()
        self.assertEqual(acknowledgement, {
            "type": "receipt_ack",
            "ok": True,
            "message_id": "realtime-message-1",
            "receipt_type": "notification_displayed",
        })
        connection.close()

        outbox = store.read_outbox(limit=1)[0]
        receipts = outbox["payload"]["delivery_receipts"]
        self.assertEqual(receipts[-1]["receipt_type"], "notification_displayed")
        self.assertEqual(receipts[-1]["channel"], "android-realtime")


if __name__ == "__main__":
    unittest.main()
