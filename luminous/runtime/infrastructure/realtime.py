from __future__ import annotations

import base64
import hashlib
import json
import logging
import socket
import struct
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from luminous.runtime.domain.time import parse_iso_datetime, utc_now_iso


LOGGER = logging.getLogger(__name__)

_WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_PROTOCOL = "luminous.realtime.v1"
_MAX_FRAME_BYTES = 64 * 1024
_NOTIFIABLE_STATUSES = {"drafted", "queued", "retrying", "delivering", "sent", "delivered"}
_RECEIPT_TYPES = {
    "notification_displayed",
    "notification_opened",
    "notification_dismissed",
}


def websocket_upgrade_requested(headers: Any) -> bool:
    upgrade = str(headers.get("Upgrade", "")).strip().lower()
    connection = {item.strip().lower() for item in str(headers.get("Connection", "")).split(",")}
    return upgrade == "websocket" and "upgrade" in connection


def serve_outbox_websocket(
    handler: Any,
    service: Any,
    *,
    since_ms: int = 0,
    poll_interval: float = 1.0,
) -> None:
    key, protocol = _validate_handshake(handler.headers)
    accept = base64.b64encode(hashlib.sha1(f"{key}{_WEBSOCKET_GUID}".encode("ascii")).digest()).decode("ascii")
    handler.send_response(101, "Switching Protocols")
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", accept)
    if protocol:
        handler.send_header("Sec-WebSocket-Protocol", protocol)
    handler.end_headers()
    handler.wfile.flush()
    handler.close_connection = True

    connection: socket.socket = handler.connection
    connection.settimeout(0.5)
    reader = _FrameReader()
    sent_ids: set[str] = set()
    next_poll = 0.0
    next_ping = time.monotonic() + 25.0
    _send_json(connection, {
        "type": "ready",
        "protocol": _PROTOCOL,
        "server_time": utc_now_iso(),
        "poll_interval_ms": int(max(0.25, poll_interval) * 1000),
    })

    try:
        while True:
            now = time.monotonic()
            if now >= next_poll:
                _send_new_outbox_items(connection, service, sent_ids, since_ms=since_ms)
                next_poll = now + max(0.25, poll_interval)
            if now >= next_ping:
                _send_frame(connection, 0x9, b"luminous")
                next_ping = now + 25.0
            try:
                chunk = connection.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                return
            for opcode, payload in reader.feed(chunk):
                if opcode == 0x8:
                    _send_frame(connection, 0x8, payload[:125])
                    return
                if opcode == 0x9:
                    _send_frame(connection, 0xA, payload[:125])
                    continue
                if opcode == 0xA:
                    continue
                if opcode != 0x1:
                    _send_close(connection, 1003, "text frames only")
                    return
                _handle_client_message(connection, service, payload)
    except (BrokenPipeError, ConnectionResetError, OSError):
        return
    except Exception as exc:  # noqa: BLE001 - the connection must not crash the HTTP server.
        LOGGER.warning("realtime websocket closed after %s", type(exc).__name__)
        try:
            _send_close(connection, 1011, "server error")
        except OSError:
            pass


def _validate_handshake(headers: Any) -> tuple[str, str]:
    if not websocket_upgrade_requested(headers):
        raise ValueError("websocket upgrade is required")
    if str(headers.get("Sec-WebSocket-Version", "")).strip() != "13":
        raise ValueError("unsupported websocket version")
    key = str(headers.get("Sec-WebSocket-Key", "")).strip()
    try:
        decoded = base64.b64decode(key.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("invalid websocket key") from exc
    if len(decoded) != 16:
        raise ValueError("invalid websocket key")
    offered = [item.strip() for item in str(headers.get("Sec-WebSocket-Protocol", "")).split(",") if item.strip()]
    return key, _PROTOCOL if _PROTOCOL in offered else ""


def _send_new_outbox_items(
    connection: socket.socket,
    service: Any,
    sent_ids: set[str],
    *,
    since_ms: int,
) -> None:
    response = service.read_outbox(limit=100)
    for item in list(response.get("items", []) or []):
        if not isinstance(item, dict):
            continue
        message_id = str(item.get("message_id", "")).strip()
        body = str(item.get("draft_text", "")).strip()
        status = str(item.get("status", "")).strip()
        if not message_id or not body or message_id in sent_ids or status not in _NOTIFIABLE_STATUSES:
            continue
        created_at = str(item.get("created_at", "")).strip()
        parsed_created_at = parse_iso_datetime(created_at)
        created_ms = int(parsed_created_at.timestamp() * 1000) if parsed_created_at else 0
        if since_ms > 0 and created_ms > 0 and created_ms < since_ms - 5 * 60 * 1000:
            sent_ids.add(message_id)
            continue
        _send_json(connection, {
            "type": "proactive_message",
            "message_id": message_id,
            "title": "叶筝的来信",
            "body": body,
            "status": status,
            "signal_type": str(item.get("signal_type", "notification"))[:48],
            "created_at": created_at,
            "deep_link": f"havilume://app?space=outbox&message_id={quote(message_id, safe='')}",
        })
        sent_ids.add(message_id)


def _handle_client_message(connection: socket.socket, service: Any, raw: bytes) -> None:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _send_json(connection, {"type": "error", "code": "invalid_json"})
        return
    if not isinstance(payload, dict):
        _send_json(connection, {"type": "error", "code": "invalid_message"})
        return
    message_type = str(payload.get("type", "")).strip()
    if message_type == "ping":
        _send_json(connection, {"type": "pong", "server_time": utc_now_iso()})
        return
    if message_type != "receipt":
        _send_json(connection, {"type": "error", "code": "unsupported_message"})
        return
    message_id = str(payload.get("message_id", "")).strip()[:120]
    receipt_type = str(payload.get("receipt_type", "")).strip()
    occurred_at = str(payload.get("occurred_at", "")).strip()[:40]
    if not message_id or receipt_type not in _RECEIPT_TYPES:
        _send_json(connection, {"type": "receipt_ack", "ok": False, "message_id": message_id})
        return
    result = service.record_outbox_receipt(
        message_id,
        receipt_type,
        channel="android-realtime",
        occurred_at=occurred_at or datetime.now(timezone.utc).isoformat(),
    )
    _send_json(connection, {
        "type": "receipt_ack",
        "ok": bool(result.get("ok", False)),
        "message_id": message_id,
        "receipt_type": receipt_type,
    })


def _send_json(connection: socket.socket, payload: dict[str, object]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    _send_frame(connection, 0x1, encoded)


def _send_close(connection: socket.socket, code: int, reason: str) -> None:
    payload = struct.pack("!H", code) + reason.encode("utf-8")[:123]
    _send_frame(connection, 0x8, payload)


def _send_frame(connection: socket.socket, opcode: int, payload: bytes) -> None:
    if len(payload) > _MAX_FRAME_BYTES:
        raise ValueError("websocket frame too large")
    first = 0x80 | (opcode & 0x0F)
    length = len(payload)
    if length < 126:
        header = bytes((first, length))
    elif length <= 0xFFFF:
        header = bytes((first, 126)) + struct.pack("!H", length)
    else:
        header = bytes((first, 127)) + struct.pack("!Q", length)
    connection.sendall(header + payload)


class _FrameReader:
    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, chunk: bytes) -> list[tuple[int, bytes]]:
        self.buffer.extend(chunk)
        frames: list[tuple[int, bytes]] = []
        while True:
            parsed = self._next_frame()
            if parsed is None:
                return frames
            frames.append(parsed)

    def _next_frame(self) -> tuple[int, bytes] | None:
        if len(self.buffer) < 2:
            return None
        first, second = self.buffer[0], self.buffer[1]
        if first & 0x70 or not first & 0x80:
            raise ValueError("fragmented websocket frames are unsupported")
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        offset = 2
        if length == 126:
            if len(self.buffer) < offset + 2:
                return None
            length = struct.unpack("!H", self.buffer[offset:offset + 2])[0]
            offset += 2
        elif length == 127:
            if len(self.buffer) < offset + 8:
                return None
            length = struct.unpack("!Q", self.buffer[offset:offset + 8])[0]
            offset += 8
        if length > _MAX_FRAME_BYTES:
            raise ValueError("websocket frame too large")
        if not masked:
            raise ValueError("client websocket frames must be masked")
        if len(self.buffer) < offset + 4 + length:
            return None
        mask = bytes(self.buffer[offset:offset + 4])
        offset += 4
        payload = bytes(self.buffer[offset:offset + length])
        del self.buffer[:offset + length]
        return opcode, bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
