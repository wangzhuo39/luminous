from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from luminous.runtime.config import PROJECT_ROOT, BackendConfig, load_backend_config
from luminous.runtime.application.service import CompanionService
from luminous.runtime.infrastructure.client import ModelClientError


class CompanionRequestHandler(BaseHTTPRequestHandler):
    service: CompanionService
    config: BackendConfig

    server_version = "RolePlayCompanion/0.1"

    def do_OPTIONS(self) -> None:
        self._send_empty(HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/health":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "model": self.config.model if self.config.llm_configured else "",
                        "llm_configured": self.config.llm_configured,
                        "mock": self.config.mock,
                    },
                )
                return
            if path == "/api/state":
                self._send_json(HTTPStatus.OK, self.service.get_state())
                return
            if path == "/api/memory":
                params = self._query_params(parsed.query)
                query = params.get("q", [""])[0]
                limit = int(params.get("limit", ["5"])[0])
                self._send_json(HTTPStatus.OK, self.service.query_memory(query, limit=limit))
                return
            if path == "/api/ledger":
                params = self._query_params(parsed.query)
                limit = int(params.get("limit", ["50"])[0])
                trace_id = params.get("trace_id", [""])[0] or None
                self._send_json(HTTPStatus.OK, self.service.read_ledger(limit=limit, trace_id=trace_id))
                return
            if path == "/api/trace":
                params = self._query_params(parsed.query)
                trace_id = params.get("trace_id", [""])[0]
                if not trace_id:
                    raise ValueError("trace_id is required")
                limit = int(params.get("limit", ["50"])[0])
                self._send_json(HTTPStatus.OK, self.service.read_trace(trace_id, limit=limit))
                return
            if path == "/api/outbox":
                params = self._query_params(parsed.query)
                limit = int(params.get("limit", ["50"])[0])
                status = params.get("status", [""])[0] or None
                self._send_json(HTTPStatus.OK, self.service.read_outbox(limit=limit, status=status))
                return
            if path == "/api/memory/threads":
                params = self._query_params(parsed.query)
                limit = int(params.get("limit", ["50"])[0])
                self._send_json(HTTPStatus.OK, self.service.read_memory_threads(limit=limit))
                return
            if path == "/api/memory/links":
                params = self._query_params(parsed.query)
                limit = int(params.get("limit", ["100"])[0])
                self._send_json(HTTPStatus.OK, self.service.read_memory_links(limit=limit))
                return
            if path == "/api/memory/evidence":
                params = self._query_params(parsed.query)
                limit = int(params.get("limit", ["100"])[0])
                memory_id = params.get("memory_id", [""])[0] or None
                status = params.get("status", [""])[0] or None
                self._send_json(
                    HTTPStatus.OK,
                    self.service.read_memory_evidence(limit=limit, memory_id=memory_id, status=status),
                )
                return
            if path == "/api/jobs":
                params = self._query_params(parsed.query)
                limit = int(params.get("limit", ["50"])[0])
                status = params.get("status", [""])[0] or None
                self._send_json(HTTPStatus.OK, self.service.read_jobs(limit=limit, status=status))
                return
            if path == "/api/export":
                self._send_json(HTTPStatus.OK, self.service.export_data())
                return
            if path == "/api/reminders":
                params = self._query_params(parsed.query)
                limit = int(params.get("limit", ["100"])[0])
                status = params.get("status", [""])[0] or None
                self._send_json(HTTPStatus.OK, self.service.read_reminders(status=status, limit=limit))
                return
            if path == "/api/calendar-events":
                params = self._query_params(parsed.query)
                limit = int(params.get("limit", ["100"])[0])
                self._send_json(HTTPStatus.OK, self.service.read_calendar_events(limit=limit))
                return
            if path == "/api/settings/notifications":
                self._send_json(HTTPStatus.OK, self.service.notification_preferences())
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
                        kind=params.get("kind", [""])[0], limit=int(params.get("limit", ["200"])[0]),
                    ),
                )
                return
            if path == "/api/tasks":
                params = self._query_params(parsed.query)
                self._send_json(HTTPStatus.OK, self.service.read_tasks(status=params.get("status", [""])[0] or None, limit=int(params.get("limit", ["100"])[0])))
                return
            if path == "/api/routines":
                params = self._query_params(parsed.query)
                self._send_json(HTTPStatus.OK, self.service.read_routines(active_only=params.get("active_only", ["false"])[0].lower() == "true", limit=int(params.get("limit", ["100"])[0])))
                return
            if path == "/api/activities":
                params = self._query_params(parsed.query)
                self._send_json(HTTPStatus.OK, self.service.read_activities(status=params.get("status", [""])[0] or None, limit=int(params.get("limit", ["100"])[0])))
                return
            if path == "/api/diary-entries":
                params = self._query_params(parsed.query)
                self._send_json(HTTPStatus.OK, self.service.read_diary_entries(date=params.get("date", [""])[0], limit=int(params.get("limit", ["100"])[0])))
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
        if path != "/api/chat":
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
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": type(exc).__name__})
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
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": type(exc).__name__})
                    return
                self._send_json(HTTPStatus.OK, result)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        try:
            payload = self._read_json_body(max_bytes=64 * 1024)
            message = str(payload.get("message", ""))
            history = payload.get("history", [])
            if not isinstance(history, list):
                history = []
            result = self.service.chat(message, history)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except ModelClientError as exc:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - keep the API from crashing the server.
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": type(exc).__name__})
            return

        self._send_json(HTTPStatus.OK, result)

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
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
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._send_json(HTTPStatus.OK, result)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
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
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("request body must be JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _serve_static(self, request_path: str) -> None:
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
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        data = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._send_common_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_empty(self, status: HTTPStatus) -> None:
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")

    def _query_params(self, query: str) -> dict[str, list[str]]:
        return parse_qs(query, keep_blank_values=True)

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
    return ConfiguredCompanionRequestHandler


def serve(config: BackendConfig, host: str, port: int) -> None:
    handler = make_handler(config)
    server = ThreadingHTTPServer((host, port), handler)
    print(
        f"serving companion frontend at http://{host}:{port} "
        f"(mock={config.mock}, llm_configured={config.llm_configured})",
        flush=True,
    )
    server.serve_forever()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the role-play companion backend and frontend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--env", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--frontend", type=Path, default=PROJECT_ROOT / "apps" / "companion-web" / "companion-ui")
    parser.add_argument("--mock", action="store_true", help="Use deterministic local replies instead of calling an LLM.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_backend_config(env_path=args.env, frontend_dir=args.frontend)
    if args.mock:
        config.mock = True
    serve(config, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
