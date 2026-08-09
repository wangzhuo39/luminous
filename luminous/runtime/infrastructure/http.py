from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import mimetypes
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from luminous.runtime.config import PROJECT_ROOT, BackendConfig, load_backend_config
from luminous.runtime.application.service import CompanionService
from luminous.runtime.domain.voice import VoiceProviderError
from luminous.runtime.domain.time import parse_iso_datetime
from luminous.runtime.infrastructure.client import ModelClientError
from luminous.runtime.infrastructure.auth import LoginRateLimited, SessionAuth
from luminous.runtime.infrastructure.realtime import serve_outbox_websocket, websocket_upgrade_requested


LOGGER = logging.getLogger(__name__)

APP_LANDING_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>Havilume Android App</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; background: #090b12; color: #eef1ff; }
    body { min-height: 100vh; margin: 0; display: grid; place-items: center; }
    main { width: min(34rem, calc(100% - 3rem)); padding: 2.5rem; border: 1px solid #29304a; border-radius: 1.5rem; background: #111522; }
    h1 { margin: 0 0 1rem; font-size: 1.65rem; }
    p { color: #b7bfd9; line-height: 1.7; }
    a { display: inline-block; margin-top: 1rem; padding: .8rem 1.15rem; border-radius: 999px; background: #dbe2ff; color: #101526; font-weight: 700; text-decoration: none; }
  </style>
</head>
<body><main>
  <h1>Havilume 已迁移至 Android App</h1>
  <p>浏览器客户端已经停止使用。请安装 Android 内测版继续体验；聊天、状态、提醒与主动联系均在 App 内运行。</p>
  <a href="/downloads/luminous-android-debug.apk?v=20260805-realtime" download>下载 Android 内测版</a>
</main></body>
</html>
""".encode("utf-8")
INTERNAL_HTTP_ENDPOINTS = {
    "/api/ledger",
    "/api/trace",
    "/api/jobs",
    "/api/export",
    "/api/proactive/tick",
    "/api/worker/tick",
    "/api/memory/threads",
    "/api/memory/links",
    "/api/memory/evidence",
}


class CompanionRequestHandler(BaseHTTPRequestHandler):
    service: CompanionService
    config: BackendConfig
    auth: SessionAuth

    server_version = "RolePlayCompanion/0.1"

    def do_OPTIONS(self) -> None:
        if not self._origin_allowed():
            self._send_error(HTTPStatus.FORBIDDEN, "origin_not_allowed", "origin is not allowed")
            return
        self._send_empty(HTTPStatus.NO_CONTENT)

    def do_HEAD(self) -> None:
        path = urlparse(self.path).path
        if not self._authorize(path):
            return
        if path.startswith("/downloads/"):
            self._serve_static(path, head_only=True)
            return
        self._send_error(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", "HEAD is not supported for this resource")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._authorize(path):
            return
        try:
            if path == "/api/auth/session":
                authenticated = (
                    not self.config.public_deployment
                    or self.auth.authenticate(self.headers.get("Cookie", ""))
                )
                if not authenticated:
                    self._send_error(HTTPStatus.UNAUTHORIZED, "authentication_required", "authentication required")
                    return
                self._send_json(HTTPStatus.OK, {"authenticated": True, "mode": self.config.deployment_mode})
                return
            if path == "/api/health":
                self._send_json(HTTPStatus.OK, {"ok": True, "status": "ready" if self.config.mock or self.config.llm_configured else "degraded"})
                return
            if path == "/api/health/deep":
                self._send_json(HTTPStatus.OK, self._deep_health())
                return
            if path == "/api/realtime/outbox":
                if not websocket_upgrade_requested(self.headers):
                    self._send_error(HTTPStatus.UPGRADE_REQUIRED, "websocket_upgrade_required", "websocket upgrade is required")
                    return
                params = self._query_params(parsed.query)
                try:
                    since_ms = max(0, int(params.get("since", ["0"])[0] or "0"))
                except ValueError as exc:
                    raise ValueError("since must be an epoch millisecond value") from exc
                serve_outbox_websocket(self, self.service, since_ms=since_ms)
                return
            if path in INTERNAL_HTTP_ENDPOINTS:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "not found")
                return
            if path.startswith("/api/voice/livekit/session/"):
                session_id, action = self._resource_action(path, "/api/voice/livekit/session/")
                if action:
                    self._send_error(HTTPStatus.NOT_FOUND, "not_found", "not found")
                    return
                session = self.service.read_livekit_voice_session(
                    session_id,
                    session_digest=self.auth.session_digest(self.headers.get("Cookie", "")),
                )
                if session is None:
                    self._send_error(HTTPStatus.NOT_FOUND, "voice_session_not_found", "voice session not found")
                    return
                self._send_json(HTTPStatus.OK, session)
                return
            if path == "/api/state":
                params = self._query_params(parsed.query)
                include_history = params.get("include", [""])[0] == "history"
                self._send_json(HTTPStatus.OK, self.service.get_state(include_history=include_history))
                return
            if path == "/api/chat/history":
                params = self._query_params(parsed.query)
                limit = self._query_limit(params, default=10, maximum=50)
                self._send_json(HTTPStatus.OK, self.service.read_chat_history(limit=limit))
                return
            if path == "/api/memory":
                params = self._query_params(parsed.query)
                query = params.get("q", [""])[0]
                limit = self._query_limit(params, default=5, maximum=50)
                self._send_json(HTTPStatus.OK, self.service.query_memory(query, limit=limit))
                return
            if path == "/api/ledger":
                params = self._query_params(parsed.query)
                limit = self._query_limit(params, default=50, maximum=100)
                trace_id = params.get("trace_id", [""])[0] or None
                self._send_json(HTTPStatus.OK, self.service.read_ledger(limit=limit, trace_id=trace_id))
                return
            if path == "/api/trace":
                params = self._query_params(parsed.query)
                trace_id = params.get("trace_id", [""])[0]
                if not trace_id:
                    raise ValueError("trace_id is required")
                limit = self._query_limit(params, default=50, maximum=100)
                self._send_json(HTTPStatus.OK, self.service.read_trace(trace_id, limit=limit))
                return
            if path == "/api/outbox":
                params = self._query_params(parsed.query)
                limit = self._query_limit(params, default=50, maximum=100)
                status = params.get("status", [""])[0] or None
                self._send_json(HTTPStatus.OK, self.service.read_outbox(limit=limit, status=status))
                return
            if path == "/api/reminders":
                params = self._query_params(parsed.query)
                limit = self._query_limit(params, default=100, maximum=100)
                status = params.get("status", [""])[0] or None
                self._send_json(HTTPStatus.OK, self.service.read_reminders(status=status, limit=limit))
                return
            if path == "/api/calendar-events":
                params = self._query_params(parsed.query)
                limit = self._query_limit(params, default=100, maximum=100)
                self._send_json(HTTPStatus.OK, self.service.read_calendar_events(limit=limit))
                return
            if path == "/api/settings/notifications":
                self._send_json(HTTPStatus.OK, self.service.notification_preferences())
                return
            if path == "/api/settings/companion":
                self._send_json(HTTPStatus.OK, self.service.companion_settings())
                return
            if path == "/api/today":
                params = self._query_params(parsed.query)
                self._send_json(HTTPStatus.OK, self.service.today(date=params.get("date", [""])[0]))
                return
            if path == "/api/timeline":
                params = self._query_params(parsed.query)
                self._send_json(
                    HTTPStatus.OK,
                    self.service.timeline(
                        from_date=params.get("from", [""])[0], to_date=params.get("to", [""])[0],
                        kind=params.get("kind", [""])[0], limit=self._query_limit(params, default=200, maximum=500),
                    ),
                )
                return
            if path == "/api/tasks":
                params = self._query_params(parsed.query)
                self._send_json(HTTPStatus.OK, self.service.read_tasks(status=params.get("status", [""])[0] or None, limit=self._query_limit(params, default=100, maximum=100)))
                return
            if path == "/api/routines":
                params = self._query_params(parsed.query)
                self._send_json(HTTPStatus.OK, self.service.read_routines(active_only=params.get("active_only", ["false"])[0].lower() == "true", limit=self._query_limit(params, default=100, maximum=100)))
                return
            if path == "/api/activities":
                params = self._query_params(parsed.query)
                self._send_json(HTTPStatus.OK, self.service.read_activities(status=params.get("status", [""])[0] or None, limit=self._query_limit(params, default=100, maximum=100)))
                return
            if path == "/api/diary-entries":
                params = self._query_params(parsed.query)
                self._send_json(HTTPStatus.OK, self.service.read_diary_entries(date=params.get("date", [""])[0], limit=self._query_limit(params, default=100, maximum=100)))
                return
            if path.startswith("/api/tasks/"):
                task_id, action = self._resource_action(path, "/api/tasks/")
                if action:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                self._send_json(HTTPStatus.OK, self.service.get_task(task_id))
                return
            if path.startswith("/api/routines/"):
                routine_id, action = self._resource_action(path, "/api/routines/")
                if action:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                self._send_json(HTTPStatus.OK, self.service.get_routine(routine_id))
                return
            if path.startswith("/api/activities/"):
                activity_id, action = self._resource_action(path, "/api/activities/")
                if action:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                self._send_json(HTTPStatus.OK, self.service.get_activity(activity_id))
                return
            if path.startswith("/api/diary-entries/"):
                entry_id, action = self._resource_action(path, "/api/diary-entries/")
                if action:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                self._send_json(HTTPStatus.OK, self.service.get_diary_entry(entry_id))
                return
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not self._authorize(path):
            return
        if path == "/api/auth/login":
            if not self.auth.enabled:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "authentication is not configured")
                return
            try:
                payload = self._read_json_body(max_bytes=8 * 1024)
                access_code = payload.get("access_code", "")
                if not isinstance(access_code, str) or not access_code.strip():
                    raise ValueError("access_code is required")
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            try:
                token = self.auth.login(access_code)
            except LoginRateLimited as exc:
                self._send_json(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    {"error": {"code": "login_rate_limited", "message": "请稍后再试。", "retryable": True}},
                    response_headers={"Retry-After": str(exc.retry_after_seconds)},
                )
                return
            if token is None:
                self._send_error(HTTPStatus.UNAUTHORIZED, "invalid_access_code", "access code is not valid")
                return
            self._send_json(
                HTTPStatus.OK,
                {"authenticated": True, "mode": self.config.deployment_mode},
                response_headers={"Set-Cookie": self.auth.cookie_header(token)},
            )
            return
        if path == "/api/auth/logout":
            self.auth.logout(self.headers.get("Cookie", ""))
            self._send_json(
                HTTPStatus.OK,
                {"authenticated": False},
                response_headers={"Set-Cookie": self.auth.cookie_header("", clear=True)},
            )
            return
        if path == "/api/voice/livekit/session":
            try:
                payload = self._read_json_body(max_bytes=8 * 1024)
                client = payload.get("client", "android")
                if client != "android":
                    raise ValueError("realtime voice is available only to the Android client")
                connection = self.service.create_livekit_voice_session(
                    session_digest=self.auth.session_digest(self.headers.get("Cookie", "")),
                    client=client,
                )
            except ValueError as exc:
                self._send_error(HTTPStatus.SERVICE_UNAVAILABLE, "livekit_unavailable", str(exc))
                return
            self._send_json(HTTPStatus.CREATED, connection)
            return
        if path.startswith("/api/voice/livekit/session/"):
            session_id, action = self._resource_action(path, "/api/voice/livekit/session/")
            if action != "metrics":
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "not found")
                return
            try:
                payload = self._read_json_body(max_bytes=16 * 1024)
                metrics = payload.get("metrics", {})
                status = payload.get("status")
                last_error = payload.get("last_error")
                if not isinstance(metrics, dict):
                    raise ValueError("metrics must be a JSON object")
                if status is not None and not isinstance(status, str):
                    raise ValueError("status must be a string")
                if last_error is not None and not isinstance(last_error, str):
                    raise ValueError("last_error must be a string")
                session = self.service.update_livekit_voice_session(
                    session_id,
                    session_digest=self.auth.session_digest(self.headers.get("Cookie", "")),
                    status=status,
                    metrics=metrics,
                    last_error=last_error,
                )
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
                return
            if session is None:
                self._send_error(HTTPStatus.NOT_FOUND, "voice_session_not_found", "voice session not found")
                return
            self._send_json(HTTPStatus.OK, session)
            return
        if path != "/api/voice/speech" and not self._begin_idempotency("POST", path):
            return
        if path in INTERNAL_HTTP_ENDPOINTS:
            self._send_error(HTTPStatus.NOT_FOUND, "not_found", "not found")
            return
        if path != "/api/chat":
            if path == "/api/voice/transcriptions":
                try:
                    duration_ms = int(self.headers.get("X-Audio-Duration-Ms", "0"))
                    audio = self._read_binary_body(max_bytes=15 * 1024 * 1024)
                    result = self.service.transcribe_voice(
                        audio,
                        content_type=self.headers.get("Content-Type", ""),
                        duration_ms=duration_ms,
                        filename=self.headers.get("X-Audio-Filename", "recording"),
                    )
                except ValueError as exc:
                    self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
                    return
                except VoiceProviderError as exc:
                    self._send_voice_error(exc)
                    return
                self._send_json(HTTPStatus.OK, result)
                return
            if path == "/api/voice/speech":
                try:
                    payload = self._read_json_body(max_bytes=16 * 1024)
                    text = payload.get("text", "")
                    voice_id = payload.get("voice_id")
                    speaking_rate = payload.get("speaking_rate")
                    if not isinstance(text, str):
                        raise ValueError("text must be a string")
                    if voice_id is not None and not isinstance(voice_id, str):
                        raise ValueError("voice_id must be a string")
                    if speaking_rate is not None:
                        speaking_rate = float(speaking_rate)
                    audio = self.service.synthesize_voice(
                        text, voice_id=voice_id, speaking_rate=speaking_rate,
                    )
                except ValueError as exc:
                    self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
                    return
                except VoiceProviderError as exc:
                    self._send_voice_error(exc)
                    return
                self._send_binary(HTTPStatus.OK, audio.data, audio.content_type)
                return
            if path == "/api/tasks":
                try:
                    self._send_json(HTTPStatus.CREATED, self.service.create_task(self._read_json_body(max_bytes=32 * 1024)))
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path == "/api/routines":
                try:
                    self._send_json(HTTPStatus.CREATED, self.service.create_routine(self._read_json_body(max_bytes=32 * 1024)))
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path == "/api/activities":
                try:
                    self._send_json(HTTPStatus.CREATED, self.service.create_activity(self._read_json_body(max_bytes=32 * 1024)))
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path == "/api/diary-entries":
                try:
                    self._send_json(HTTPStatus.CREATED, self.service.create_diary_entry(self._read_json_body(max_bytes=64 * 1024)))
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path == "/api/diary-entries/draft":
                try:
                    payload = self._read_json_body(max_bytes=16 * 1024, optional=True)
                    self._send_json(HTTPStatus.CREATED, self.service.draft_diary_entry(date=str(payload.get("date", ""))))
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path == "/api/actions/preview":
                try:
                    self._send_json(HTTPStatus.OK, self.service.preview_life_action(self._read_json_body(max_bytes=32 * 1024)))
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path == "/api/actions/confirm":
                try:
                    self._send_json(HTTPStatus.OK, self.service.confirm_life_action(self._read_json_body(max_bytes=32 * 1024)))
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path.startswith("/api/tasks/"):
                task_id, action = self._resource_action(path, "/api/tasks/")
                try:
                    payload = self._read_json_body(max_bytes=32 * 1024, optional=True)
                    if action == "steps":
                        result = self.service.add_task_step(task_id, payload)
                    elif action in {"start", "complete", "block", "cancel"}:
                        result = self.service.transition_task(task_id, action, payload)
                    else:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                        return
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                self._send_json(HTTPStatus.OK, result)
                return
            if path.startswith("/api/routines/"):
                routine_id, action = self._resource_action(path, "/api/routines/")
                if action != "checkins":
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                try:
                    self._send_json(HTTPStatus.OK, self.service.checkin_routine(routine_id, self._read_json_body(max_bytes=16 * 1024, optional=True)))
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path.startswith("/api/activities/"):
                activity_id, action = self._resource_action(path, "/api/activities/")
                if action not in {"start", "pause", "resume", "complete", "cancel"}:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                try:
                    self._send_json(HTTPStatus.OK, self.service.transition_activity(activity_id, action, self._read_json_body(max_bytes=32 * 1024, optional=True)))
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path == "/api/reminders":
                try:
                    self._send_json(HTTPStatus.CREATED, self.service.create_reminder(self._read_json_body(max_bytes=32 * 1024)))
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path == "/api/calendar-events":
                try:
                    self._send_json(HTTPStatus.CREATED, self.service.create_calendar_event(self._read_json_body(max_bytes=32 * 1024)))
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path == "/api/settings/notifications":
                try:
                    self._send_json(HTTPStatus.OK, self.service.update_notification_preferences(self._read_json_body(max_bytes=16 * 1024)))
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path == "/api/notification-devices":
                try:
                    self._send_json(
                        HTTPStatus.CREATED,
                        self.service.register_notification_device(
                            self._read_json_body(max_bytes=8 * 1024),
                            session_digest=self.auth.session_digest(self.headers.get("Cookie", "")),
                        ),
                    )
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path.startswith("/api/reminders/"):
                reminder_id, action = self._resource_action(path, "/api/reminders/")
                try:
                    payload = self._read_json_body(max_bytes=16 * 1024, optional=True)
                    if action == "snooze":
                        due_at = str(payload.get("due_at", ""))
                        result = self.service.snooze_reminder(reminder_id, due_at)
                    elif action == "complete":
                        result = self.service.complete_reminder(reminder_id)
                    elif action == "cancel":
                        result = self.service.cancel_reminder(reminder_id)
                    else:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                        return
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                self._send_json(HTTPStatus.OK, result)
                return
            if path == "/api/proactive/tick":
                try:
                    payload = self._read_json_body(max_bytes=16 * 1024, optional=True)
                    send = bool(payload.get("send", False))
                    result = self.service.proactive_tick(send=send)
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                except Exception as exc:  # noqa: BLE001 - keep the API from crashing the server.
                    LOGGER.exception("proactive tick failed")
                    self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "暂时无法完成这次请求。", retryable=True)
                    return
                self._send_json(HTTPStatus.OK, result)
                return
            if path == "/api/memory/update":
                try:
                    payload = self._read_json_body(max_bytes=32 * 1024)
                    memory_id = str(payload.get("memory_id", ""))
                    updates = payload.get("updates", {})
                    if not memory_id:
                        raise ValueError("memory_id is required")
                    if not isinstance(updates, dict):
                        raise ValueError("updates must be a JSON object")
                    result = self.service.update_memory(memory_id, updates)
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                self._send_json(HTTPStatus.OK, result)
                return
            if path == "/api/memory/forget":
                try:
                    payload = self._read_json_body(max_bytes=16 * 1024)
                    memory_id = str(payload.get("memory_id", ""))
                    hard_delete = bool(payload.get("hard_delete", False))
                    if not memory_id:
                        raise ValueError("memory_id is required")
                    result = self.service.forget_memory(memory_id, hard_delete=hard_delete)
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                self._send_json(HTTPStatus.OK, result)
                return
            if path == "/api/outbox/feedback":
                try:
                    payload = self._read_json_body(max_bytes=16 * 1024)
                    message_id = str(payload.get("message_id", ""))
                    status = str(payload.get("status", "")).strip()
                    feedback_text = str(payload.get("feedback_text", ""))
                    replied_at = payload.get("replied_at")
                    if not message_id:
                        raise ValueError("message_id is required")
                    if not status:
                        raise ValueError("status is required")
                    if replied_at is not None:
                        replied_at = str(replied_at)
                    result = self.service.record_outbox_feedback(
                        message_id,
                        status,
                        feedback_text=feedback_text,
                        replied_at=replied_at,
                    )
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                self._send_json(HTTPStatus.OK, result)
                return
            if path == "/api/outbox/receipt":
                try:
                    payload = self._read_json_body(max_bytes=16 * 1024)
                    message_id = str(payload.get("message_id", ""))
                    receipt_type = str(payload.get("receipt_type", "")).strip()
                    channel = str(payload.get("channel", ""))
                    receipt_payload = payload.get("payload", {})
                    occurred_at = payload.get("occurred_at")
                    if not message_id:
                        raise ValueError("message_id is required")
                    if not receipt_type:
                        raise ValueError("receipt_type is required")
                    if not isinstance(receipt_payload, dict):
                        raise ValueError("payload must be a JSON object")
                    result = self.service.record_outbox_receipt(
                        message_id,
                        receipt_type,
                        channel=channel,
                        payload=receipt_payload,
                        occurred_at=str(occurred_at) if occurred_at is not None else None,
                    )
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                self._send_json(HTTPStatus.OK, result)
                return
            if path == "/api/worker/tick":
                try:
                    result = self.service.tick_worker()
                except Exception as exc:  # noqa: BLE001 - keep the API from crashing the server.
                    LOGGER.exception("worker tick endpoint was called unexpectedly")
                    self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "暂时无法完成这次请求。", retryable=True)
                    return
                self._send_json(HTTPStatus.OK, result)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        try:
            payload = self._read_json_body(max_bytes=64 * 1024)
            message = payload.get("message", "")
            if not isinstance(message, str) or not message.strip() or len(message) > 8_000:
                raise ValueError("message must be a non-empty string up to 8000 characters")
            history = payload.get("history", [])
            if not isinstance(history, list):
                raise ValueError("history must be a JSON array")
            if len(history) > 10:
                raise ValueError("history must contain at most 10 messages")
            for item in history:
                if (
                    not isinstance(item, dict)
                    or item.get("role") not in {"user", "assistant"}
                    or not isinstance(item.get("content"), str)
                    or not item["content"].strip()
                    or len(item["content"]) > 8_000
                ):
                    raise ValueError("history messages must contain a role and content")
            result = self.service.chat(message, history)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except ModelClientError as exc:
            LOGGER.warning("model request unavailable: %s", exc)
            self._send_error(HTTPStatus.SERVICE_UNAVAILABLE, "llm_unavailable", "陪伴服务暂时不可用，请稍后重试。", retryable=True)
            return
        except Exception as exc:  # noqa: BLE001 - keep the API from crashing the server.
            LOGGER.exception("chat request failed")
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "暂时无法完成这次请求。", retryable=True)
            return

        self._send_json(HTTPStatus.OK, result)

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        if not self._authorize(path):
            return
        if not self._begin_idempotency("PATCH", path):
            return
        try:
            payload = self._read_json_body(max_bytes=32 * 1024)
            if path.startswith("/api/tasks/") and "/steps/" in path:
                remainder = path.removeprefix("/api/tasks/")
                task_id, _, step_id = remainder.partition("/steps/")
                if not task_id or not step_id or "/" in step_id:
                    raise ValueError("invalid task step path")
                result = self.service.update_task_step(task_id, step_id, payload)
            elif path.startswith("/api/tasks/"):
                task_id, action = self._resource_action(path, "/api/tasks/")
                if action:
                    raise ValueError("PATCH a task resource, not an action")
                result = self.service.update_task(task_id, payload)
            elif path.startswith("/api/routines/"):
                routine_id, action = self._resource_action(path, "/api/routines/")
                if action:
                    raise ValueError("PATCH a routine resource, not an action")
                result = self.service.update_routine(routine_id, payload)
            elif path.startswith("/api/diary-entries/"):
                entry_id, action = self._resource_action(path, "/api/diary-entries/")
                if action:
                    raise ValueError("PATCH a diary entry resource, not an action")
                result = self.service.update_diary_entry(entry_id, payload)
            elif path.startswith("/api/reminders/"):
                reminder_id, action = self._resource_action(path, "/api/reminders/")
                if action:
                    raise ValueError("PATCH a reminder resource, not an action")
                result = self.service.update_reminder(reminder_id, payload)
            elif path.startswith("/api/calendar-events/"):
                event_id, action = self._resource_action(path, "/api/calendar-events/")
                if action:
                    raise ValueError("PATCH a calendar event resource, not an action")
                result = self.service.update_calendar_event(event_id, payload)
            elif path == "/api/settings/notifications":
                result = self.service.update_notification_preferences(payload)
            elif path == "/api/settings/companion":
                result = self.service.update_companion_settings(payload)
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._send_json(HTTPStatus.OK, result)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if not self._authorize(path):
            return
        if not self._begin_idempotency("DELETE", path):
            return
        if path.startswith("/api/voice/livekit/session/"):
            session_id, action = self._resource_action(path, "/api/voice/livekit/session/")
            if action:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "not found")
                return
            session = self.service.end_livekit_voice_session(
                session_id,
                session_digest=self.auth.session_digest(self.headers.get("Cookie", "")),
            )
            if session is None:
                self._send_error(HTTPStatus.NOT_FOUND, "voice_session_not_found", "voice session not found")
                return
            self._send_json(HTTPStatus.OK, session)
            return
        if path.startswith("/api/notification-devices/"):
            device_id, action = self._resource_action(path, "/api/notification-devices/")
            if action:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                self._send_json(
                    HTTPStatus.OK,
                    self.service.unregister_notification_device(
                        device_id,
                        session_digest=self.auth.session_digest(self.headers.get("Cookie", "")),
                    ),
                )
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if path.startswith("/api/activities/"):
            self._send_error(HTTPStatus.NOT_FOUND, "not_found", "activity deletion is not supported")
            return
        if path.startswith("/api/tasks/"):
            task_id, action = self._resource_action(path, "/api/tasks/")
            if action:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                self._send_json(HTTPStatus.OK, self.service.update_task(task_id, {"status": "archived"}))
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if path.startswith("/api/routines/"):
            routine_id, action = self._resource_action(path, "/api/routines/")
            if action:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                self._send_json(HTTPStatus.OK, self.service.update_routine(routine_id, {"active": False}))
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if path.startswith("/api/diary-entries/"):
            entry_id, action = self._resource_action(path, "/api/diary-entries/")
            if action:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                self._send_json(HTTPStatus.OK, self.service.update_diary_entry(entry_id, {"status": "deleted"}))
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if path.startswith("/api/reminders/"):
            reminder_id, action = self._resource_action(path, "/api/reminders/")
            if action:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            self._send_json(HTTPStatus.OK, self.service.cancel_reminder(reminder_id))
            return
        if path.startswith("/api/calendar-events/"):
            event_id, action = self._resource_action(path, "/api/calendar-events/")
            if action:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            self._send_json(HTTPStatus.OK, self.service.update_calendar_event(event_id, {"status": "deleted"}))
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}", flush=True)

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin", "").strip()
        if not origin:
            return True
        if self.config.cors_origins:
            return origin in self.config.cors_origins
        if self.config.public_deployment:
            return False
        return origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:")

    def _authorize(self, path: str) -> bool:
        if not path.startswith("/api/"):
            return True
        if not self._origin_allowed():
            self._send_error(HTTPStatus.FORBIDDEN, "origin_not_allowed", "origin is not allowed")
            return False
        if path == "/api/health/deep":
            authorization = self.headers.get("Authorization", "")
            expected = f"Bearer {self.config.auth_token}"
            if self.config.auth_token and hmac.compare_digest(authorization, expected):
                return True
            self._send_error(HTTPStatus.UNAUTHORIZED, "admin_authentication_required", "authentication required")
            return False
        if path in {"/api/health", "/api/auth/login", "/api/auth/session"} or not self.config.public_deployment:
            return True
        authorization = self.headers.get("Authorization", "")
        expected = f"Bearer {self.config.auth_token}"
        if self.config.auth_token and hmac.compare_digest(authorization, expected):
            return True
        if self.auth.authenticate(self.headers.get("Cookie", "")):
            return True
        self._send_error(HTTPStatus.UNAUTHORIZED, "authentication_required", "authentication required")
        return False

    def _deep_health(self) -> dict[str, object]:
        checks: dict[str, object] = {}
        try:
            checks["database"] = self.service.runtime.store.database_probe()
        except Exception as exc:
            checks["database"] = {"writable": False, "error": type(exc).__name__}
        worker = self.service.runtime.store.read_runtime_health("worker")
        last_seen = parse_iso_datetime(str((worker or {}).get("last_seen_at", "")))
        age_seconds = None
        if last_seen is not None:
            age_seconds = max(0, int((datetime.now(timezone.utc) - last_seen).total_seconds()))
        worker_ready = bool(
            worker
            and age_seconds is not None
            and age_seconds <= 150
            and int(worker.get("consecutive_failures", 0)) == 0
        )
        checks["worker"] = {
            "ready": worker_ready,
            "age_seconds": age_seconds,
            "consecutive_failures": int((worker or {}).get("consecutive_failures", 0)),
        }
        model_ready = self.config.mock or self.config.llm_configured
        checks["model"] = {"ready": model_ready, "mock": self.config.mock}
        ready = bool(checks["database"].get("writable") and worker_ready and model_ready)
        return {"ok": ready, "status": "ready" if ready else "degraded", "checks": checks}

    def _begin_idempotency(self, method: str, path: str) -> bool:
        key = self.headers.get("Idempotency-Key", "").strip()
        if not key:
            return True
        if len(key) > 128:
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request", "Idempotency-Key is too long")
            return False
        try:
            request_fingerprint = self._request_fingerprint(method, path)
        except ValueError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
            return False
        record = self.service.runtime.store.reserve_api_idempotency(
            key, method, path, request_fingerprint=request_fingerprint,
        )
        state = record.get("state")
        if state == "completed":
            try:
                payload = json.loads(str(record.get("response_json", "{}")))
            except json.JSONDecodeError:
                self._send_error(HTTPStatus.CONFLICT, "idempotency_conflict", "stored response is unavailable")
                return False
            self._send_json(HTTPStatus(int(record["status_code"])), payload)
            return False
        if state == "conflict":
            self._send_error(HTTPStatus.CONFLICT, "idempotency_conflict", "Idempotency-Key was used for another request")
            return False
        if state == "in_flight":
            self._send_error(HTTPStatus.CONFLICT, "request_in_flight", "the same request is already running", retryable=True)
            return False
        self._active_idempotency_key = key
        self._active_idempotency_token = str(record.get("reservation_token", ""))
        return True

    def _request_fingerprint(self, method: str, path: str) -> str:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0:
            raise ValueError("invalid Content-Length")
        maximum = 15 * 1024 * 1024 if path == "/api/voice/transcriptions" else 512 * 1024
        if length > maximum:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length) if length else b""
        if length:
            self._buffered_request_body = raw
        digest = hashlib.sha256()
        digest.update(method.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(raw)
        return digest.hexdigest()

    def _send_error(
        self,
        status: HTTPStatus,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        self._send_json(
            status,
            {"error": {"code": code, "message": message, "retryable": retryable}},
        )

    def _read_json_body(self, max_bytes: int, optional: bool = False) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            if optional:
                return {}
            raise ValueError("request body is required")
        if length > max_bytes:
            raise ValueError("request body is too large")
        buffered = getattr(self, "_buffered_request_body", None)
        if buffered is not None:
            raw = bytes(buffered)
            self._buffered_request_body = None
            if len(raw) != length:
                raise ValueError("request body length does not match Content-Length")
        else:
            raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("request body must be JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _read_binary_body(self, max_bytes: int) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            raise ValueError("request body is required")
        if length > max_bytes:
            raise VoiceProviderError("audio_too_large", "录音文件超过 15 MiB，请缩短后重试。")
        buffered = getattr(self, "_buffered_request_body", None)
        if buffered is not None:
            self._buffered_request_body = None
            raw = bytes(buffered)
        else:
            raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("request body length does not match Content-Length")
        return raw

    def _serve_static(self, request_path: str, *, head_only: bool = False) -> None:
        if self.config.public_deployment:
            if request_path in {"/", "/index.html"}:
                self._serve_app_landing()
                return
            if not request_path.startswith("/downloads/"):
                self._send_error(
                    HTTPStatus.GONE,
                    "web_client_retired",
                    "浏览器客户端已停止使用，请安装 Android App。",
                )
                return
        static_root = self.config.frontend_dir.resolve()
        relative = unquote(request_path.lstrip("/")) or "index.html"
        candidate = (static_root / relative).resolve()
        try:
            candidate.relative_to(static_root)
        except ValueError:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.exists() or not candidate.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        content_type = (
            "application/manifest+json"
            if candidate.suffix == ".webmanifest"
            else mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        )
        file_size = candidate.stat().st_size
        start = 0
        end = max(0, file_size - 1)
        status = HTTPStatus.OK
        range_header = self.headers.get("Range", "").strip()
        if range_header:
            try:
                if not range_header.startswith("bytes=") or "," in range_header:
                    raise ValueError
                range_spec = range_header[6:]
                first, last = range_spec.split("-", 1)
                if not first:
                    suffix_length = int(last)
                    if suffix_length <= 0:
                        raise ValueError
                    start = max(0, file_size - suffix_length)
                else:
                    start = int(first)
                    end = int(last) if last else file_size - 1
                if start < 0 or start >= file_size or end < start:
                    raise ValueError
                end = min(end, file_size - 1)
                status = HTTPStatus.PARTIAL_CONTENT
            except (TypeError, ValueError):
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self._send_common_headers(cache_control="no-cache")
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        content_length = max(0, end - start + 1) if file_size else 0
        self.send_response(status)
        self._send_common_headers(cache_control="no-cache")
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(content_length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()
        if head_only or content_length == 0:
            return
        try:
            with candidate.open("rb") as stream:
                stream.seek(start)
                remaining = content_length
                while remaining:
                    chunk = stream.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _serve_app_landing(self) -> None:
        self.send_response(HTTPStatus.OK)
        self._send_common_headers(cache_control="no-store")
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Clear-Site-Data", '"cache", "storage"')
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Content-Length", str(len(APP_LANDING_HTML)))
        self.end_headers()
        self.wfile.write(APP_LANDING_HTML)

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, object],
        *,
        response_headers: dict[str, str] | None = None,
    ) -> None:
        status = HTTPStatus(status)
        if isinstance(payload.get("error"), str):
            message = str(payload["error"])
            normalized_status = status
            lowered = message.lower()
            if "not found" in lowered:
                normalized_status = HTTPStatus.NOT_FOUND
            elif "cannot transition" in lowered or "already" in lowered:
                normalized_status = HTTPStatus.CONFLICT
            payload = {
                "error": {
                    "code": "not_found" if normalized_status == HTTPStatus.NOT_FOUND else "invalid_request",
                    "message": message,
                    "retryable": normalized_status >= HTTPStatus.INTERNAL_SERVER_ERROR,
                }
            }
            status = normalized_status
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        key = getattr(self, "_active_idempotency_key", "")
        if key:
            reservation_token = getattr(self, "_active_idempotency_token", "")
            completed = self.service.runtime.store.complete_api_idempotency(
                key,
                int(status),
                data.decode("utf-8"),
                reservation_token=reservation_token,
            )
            self._active_idempotency_key = ""
            self._active_idempotency_token = ""
            if not completed:
                status = HTTPStatus.CONFLICT
                payload = {
                    "error": {
                        "code": "idempotency_lease_lost",
                        "message": "request ownership expired before completion",
                        "retryable": True,
                    }
                }
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_common_headers()
        if status == HTTPStatus.UNAUTHORIZED:
            self.send_header("WWW-Authenticate", "Bearer")
        for name, value in (response_headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_binary(self, status: HTTPStatus, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_voice_error(self, error: VoiceProviderError) -> None:
        statuses = {
            "unsupported_audio": HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            "audio_too_large": HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            "recording_too_short": HTTPStatus.UNPROCESSABLE_ENTITY,
            "recording_too_long": HTTPStatus.UNPROCESSABLE_ENTITY,
            "empty_audio": HTTPStatus.BAD_REQUEST,
            "stt_not_configured": HTTPStatus.SERVICE_UNAVAILABLE,
            "tts_not_configured": HTTPStatus.SERVICE_UNAVAILABLE,
        }
        status = statuses.get(error.code, HTTPStatus.BAD_GATEWAY)
        self._send_error(status, error.code, str(error), retryable=error.retryable)

    def _send_empty(self, status: HTTPStatus) -> None:
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_common_headers(self, *, cache_control: str = "no-store") -> None:
        origin = self.headers.get("Origin", "").strip()
        if origin and self._origin_allowed():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, Idempotency-Key, X-Audio-Duration-Ms, X-Audio-Filename",
        )
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), geolocation=(), microphone=(self)")

    def _query_params(self, query: str) -> dict[str, list[str]]:
        return parse_qs(query, keep_blank_values=True)

    @staticmethod
    def _query_limit(params: dict[str, list[str]], *, default: int, maximum: int) -> int:
        raw = params.get("limit", [""])[0]
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError("limit must be an integer") from exc
        if value < 1 or value > maximum:
            raise ValueError(f"limit must be between 1 and {maximum}")
        return value

    def _resource_action(self, path: str, prefix: str) -> tuple[str, str]:
        suffix = path.removeprefix(prefix).strip("/")
        parts = suffix.split("/", 1)
        resource_id = parts[0]
        if not resource_id:
            raise ValueError("resource id is required")
        return resource_id, parts[1] if len(parts) > 1 else ""


def make_handler(config: BackendConfig) -> type[CompanionRequestHandler]:
    service = CompanionService(config)

    class ConfiguredCompanionRequestHandler(CompanionRequestHandler):
        pass

    ConfiguredCompanionRequestHandler.config = config
    ConfiguredCompanionRequestHandler.service = service
    ConfiguredCompanionRequestHandler.auth = SessionAuth(config, service.runtime.store)
    return ConfiguredCompanionRequestHandler


def serve(config: BackendConfig, host: str, port: int) -> None:
    config.validate_server_boundary()
    handler = make_handler(config)
    server = ThreadingHTTPServer((host, port), handler)
    print(
        f"serving companion frontend at http://{host}:{port} "
        f"(mode={config.deployment_mode}, mock={config.mock})",
        flush=True,
    )
    server.serve_forever()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the role-play companion backend and frontend.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--env", type=Path, default=None)
    parser.add_argument("--frontend", type=Path, default=PROJECT_ROOT / "apps" / "companion-web" / "companion-ui")
    parser.add_argument("--mock", action="store_true", help="Use deterministic local replies instead of calling an LLM.")
    parser.add_argument("--deployment-mode", choices=("local", "public"), default="", help="Select the local or authenticated public boundary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_backend_config(
        project_root=args.project_root,
        env_path=args.env or args.project_root / ".env",
        frontend_dir=args.frontend,
    )
    if args.mock:
        config.mock = True
    if args.deployment_mode:
        config.deployment_mode = args.deployment_mode
    serve(config, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
