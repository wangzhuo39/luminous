from __future__ import annotations

import base64
import hashlib
import json
import logging
import select
import socket
import threading
import time
from typing import Any

from luminous.runtime.infrastructure.realtime import _FrameReader, _send_close, _send_frame, _send_json, _validate_handshake


LOGGER = logging.getLogger(__name__)
_WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def serve_voice_realtime_websocket(handler: Any, service: Any, config: Any) -> None:
    """Bridge a browser call to private ASR/TTS credentials held by Luminous."""
    config.stt_stream_url = config.stt_stream_url or _asr_stream_url(config.stt_base_url)
    config.tts_stream_url = config.tts_stream_url or _tts_stream_url(config.tts_base_url)
    if not config.stt_stream_url or not config.tts_stream_url or not config.stt_api_key or not config.tts_api_key:
        raise ValueError("realtime voice is not configured")
    key, _ = _validate_handshake(handler.headers)
    accept = base64.b64encode(hashlib.sha1(f"{key}{_WEBSOCKET_GUID}".encode("ascii")).digest()).decode("ascii")
    handler.send_response(101, "Switching Protocols")
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", accept)
    handler.end_headers()
    handler.wfile.flush()
    handler.close_connection = True

    bridge = _VoiceBridge(service, config, handler.connection)
    _send_json(handler.connection, {"type": "call.ready", "asr_sample_rate": 16_000, "tts_sample_rate": 24_000})
    reader = _FrameReader()
    connection: socket.socket = handler.connection
    # Keep writes blocking: this socket is also written by the ASR/TTS worker
    # thread, and a recv timeout would otherwise make a slow mobile client look
    # like a failed call while an audio frame is being sent.
    connection.setblocking(True)
    next_ping = time.monotonic() + 25
    try:
        while True:
            if time.monotonic() >= next_ping:
                bridge.send_ping()
                next_ping = time.monotonic() + 25
            readable, _, _ = select.select([connection], [], [], 1.0)
            if not readable:
                continue
            chunk = connection.recv(8_192)
            if not chunk:
                return
            for opcode, payload in reader.feed(chunk):
                if opcode == 0x8:
                    _send_frame(connection, 0x8, payload[:125])
                    return
                if opcode == 0x9:
                    bridge.send_pong(payload[:125])
                    continue
                if opcode == 0xA:
                    continue
                if opcode == 0x2:
                    bridge.send_audio(payload)
                    continue
                if opcode != 0x1:
                    _send_close(connection, 1003, "unsupported frame")
                    return
                bridge.handle_control(payload)
    except (BrokenPipeError, ConnectionResetError, OSError):
        return
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("voice realtime websocket closed after %s: %s", type(exc).__name__, exc)
        try:
            _send_json(connection, {"type": "error", "code": "voice_realtime_failed", "message": "实时语音连接中断。", "retryable": True})
            _send_close(connection, 1011, "voice realtime failed")
        except OSError:
            pass
    finally:
        bridge.close()


class _VoiceBridge:
    def __init__(self, service: Any, config: Any, connection: socket.socket) -> None:
        self.service = service
        self.config = config
        self.connection = connection
        self.asr: Any | None = None
        self.processing_asr: Any | None = None
        self.tts: Any | None = None
        self._state_lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._turn_cancel: threading.Event | None = None

    def handle_control(self, raw: bytes) -> None:
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error("invalid_json", "实时语音控制消息无效。", retryable=False)
            return
        if not isinstance(event, dict):
            self._error("invalid_message", "实时语音控制消息无效。", retryable=False)
            return
        event_type = str(event.get("type", "")).strip()
        if event_type == "turn.start":
            self._start_turn(str(event.get("context", ""))[:1_000])
        elif event_type == "turn.end":
            self._finish_turn_async()
        elif event_type == "response.cancel":
            self._interrupt_response()
        elif event_type == "call.end":
            self.close()
        elif event_type == "ping":
            self._send_json({"type": "pong"})
        else:
            self._error("unsupported_message", "不支持的实时语音控制消息。", retryable=False)

    def send_audio(self, payload: bytes) -> None:
        if not payload:
            return
        with self._state_lock:
            asr = self.asr
        if asr is None:
            return
        try:
            asr.send(payload, opcode=2)
        except Exception:  # noqa: BLE001
            self._error("asr_unreachable", "实时识别服务暂时不可用。")
            self._close_asr()

    def close(self) -> None:
        self._interrupt_response(notify=False)
        self._close_asr()

    def _start_turn(self, context: str) -> None:
        with self._state_lock:
            active_asr = self.asr
        if active_asr is not None:
            self._error("turn_active", "当前语音尚未结束。", retryable=False)
            return
        self._interrupt_response(notify=False)
        try:
            import websocket

            asr = _connect_upstream(websocket, self.config.stt_stream_url, self.config.voice_timeout_seconds)
            asr.send(json.dumps({
                "type": "start", "api_key": self.config.stt_api_key, "language": "Chinese",
                "context": context, "chunk_size_sec": 2.0,
            }, ensure_ascii=False))
            ready = _recv_json(asr)
            if ready.get("type") != "ready":
                raise RuntimeError("ASR did not acknowledge the session")
            with self._state_lock:
                self.asr = asr
            self._send_json({"type": "turn.ready", "sample_rate": 16_000, "format": "s16le"})
        except Exception:  # noqa: BLE001
            self._close_asr()
            self._error("asr_unreachable", "实时识别服务暂时不可用。")

    def _finish_turn_async(self) -> None:
        with self._state_lock:
            asr = self.asr
            self.asr = None
            if asr is None:
                return
            cancelled = threading.Event()
            self._turn_cancel = cancelled
            self.processing_asr = asr
        threading.Thread(target=self._finish_turn, args=(asr, cancelled), daemon=True).start()

    def _finish_turn(self, asr: Any, cancelled: threading.Event) -> None:
        try:
            asr.send(json.dumps({"type": "end"}))
            final_text = ""
            while not cancelled.is_set():
                message = _recv_json(asr)
                kind = str(message.get("type", ""))
                if kind == "partial":
                    self._send_json({"type": "transcript.partial", "text": str(message.get("text", ""))})
                elif kind == "final":
                    final_text = str(message.get("text", "")).strip()
                    self._send_json({"type": "transcript.final", "text": final_text})
                    break
            if cancelled.is_set():
                return
            if not final_text:
                self._error("stt_empty", "没有识别到清晰语音，请再说一次。")
                return
            reply = str(self.service.chat(final_text).get("reply", "")).strip()
            if cancelled.is_set():
                return
            if not reply:
                raise RuntimeError("chat did not return a reply")
            self._send_json({"type": "response.text", "text": reply})
            self._stream_speech(reply, cancelled)
        except Exception as exc:  # noqa: BLE001
            if not cancelled.is_set():
                LOGGER.exception("voice turn failed after ASR final: %s", type(exc).__name__)
                self._error("voice_turn_failed", "这句话暂时没有处理完成，请重试。")
        finally:
            try:
                asr.close()
            except Exception:  # noqa: BLE001
                pass
            with self._state_lock:
                if self.processing_asr is asr:
                    self.processing_asr = None
                if self._turn_cancel is cancelled:
                    self._turn_cancel = None

    def _stream_speech(self, text: str, cancelled: threading.Event) -> None:
        if cancelled.is_set():
            return
        import websocket

        settings = self.service.companion_settings().get("voice", {})
        voice_id = str(settings.get("voice_id", self.config.tts_voice)) or self.config.tts_voice
        upstream = _connect_upstream(websocket, self.config.tts_stream_url, self.config.voice_timeout_seconds)
        try:
            with self._state_lock:
                self.tts = upstream
            upstream.send(json.dumps({
                "type": "start", "api_key": self.config.tts_api_key, "voice_id": voice_id,
                "instruct_text": self.config.tts_instruct_text,
            }, ensure_ascii=False))
            ready = _recv_json(upstream)
            if ready.get("type") != "ready":
                raise RuntimeError("TTS did not acknowledge the session")
            self._send_json({"type": "response.audio.ready", "sample_rate": 24_000, "format": "s16le"})
            upstream.send(json.dumps({"type": "text", "text": text}, ensure_ascii=False))
            while not cancelled.is_set():
                frame = upstream.recv()
                if isinstance(frame, bytes):
                    self._send_audio(frame)
                    continue
                event = json.loads(frame)
                kind = str(event.get("type", ""))
                if kind == "audio_start":
                    self._send_json({"type": "response.audio.start"})
                elif kind == "audio_end":
                    self._send_json({"type": "response.audio.end"})
                    break
            if cancelled.is_set():
                return
            upstream.send(json.dumps({"type": "end"}))
            self._send_json({"type": "response.done"})
        finally:
            with self._state_lock:
                if self.tts is upstream:
                    self.tts = None
            try:
                upstream.close()
            except Exception:  # noqa: BLE001
                pass

    def _close_asr(self) -> None:
        with self._state_lock:
            asr = self.asr
            self.asr = None
        if asr is None:
            return
        try:
            asr.close()
        except Exception:  # noqa: BLE001
            pass

    def _interrupt_response(self, *, notify: bool = True) -> None:
        with self._state_lock:
            cancelled = self._turn_cancel
            processing_asr = self.processing_asr
            tts = self.tts
            self.tts = None
        if cancelled is not None:
            cancelled.set()
        for upstream in (processing_asr, tts):
            if upstream is None:
                continue
            try:
                upstream.close()
            except Exception:  # noqa: BLE001
                pass
        if notify:
            self._send_json({"type": "response.interrupted"})

    def _send_json(self, payload: dict[str, object]) -> None:
        with self._write_lock:
            _send_json(self.connection, payload)

    def _send_audio(self, audio: bytes) -> None:
        with self._write_lock:
            _send_frame(self.connection, 0x2, audio, max_bytes=4 * 1024 * 1024)

    def send_ping(self) -> None:
        with self._write_lock:
            _send_frame(self.connection, 0x9, b"luminous-voice")

    def send_pong(self, payload: bytes) -> None:
        with self._write_lock:
            _send_frame(self.connection, 0xA, payload)

    def _error(self, code: str, message: str, *, retryable: bool = True) -> None:
        self._send_json({"type": "error", "code": code, "message": message, "retryable": retryable})


def _recv_json(upstream: Any) -> dict[str, object]:
    payload = upstream.recv()
    if not isinstance(payload, str):
        raise RuntimeError("expected JSON websocket frame")
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise RuntimeError("expected JSON object")
    return decoded


def _connect_upstream(websocket_module: Any, url: str, timeout: int) -> Any:
    # The deployed voice domains must bypass the workstation's HTTP proxy.
    return websocket_module.create_connection(url, timeout=timeout, http_proxy_host="", http_proxy_port=0)


def _asr_stream_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized == "https://stt.havilume.me":
        return "wss://stt-stream.havilume.me/v1/asr/stream"
    return ""


def _tts_stream_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized == "https://tts.havilume.me":
        return "wss://tts.havilume.me/v1/tts/stream"
    return ""
