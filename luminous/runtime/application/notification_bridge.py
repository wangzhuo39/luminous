from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from luminous.runtime.config import BackendConfig
from luminous.runtime.domain.events import ProactiveSignal
from luminous.runtime.domain.time import utc_now_iso


@dataclass(frozen=True)
class NotificationDelivery:
    channel: str
    status: str
    attempted: bool
    ok: bool
    receipt_type: str
    detail: str = ""
    status_code: int = 0
    occurred_at: str = ""
    provider: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "status": self.status,
            "attempted": self.attempted,
            "ok": self.ok,
            "receipt_type": self.receipt_type,
            "detail": self.detail,
            "status_code": self.status_code,
            "occurred_at": self.occurred_at,
            "provider": self.provider,
            "metadata": self.metadata,
        }

    def to_receipt(self, message_id: str) -> dict[str, Any]:
        return {
            "message_id": message_id,
            "receipt_type": self.receipt_type,
            "channel": self.channel,
            "status": self.status,
            "ok": self.ok,
            "occurred_at": self.occurred_at,
            "detail": self.detail,
            "status_code": self.status_code,
            "provider": self.provider,
            "metadata": self.metadata,
        }


class NotificationBridge:
    """Deliver proactive messages to optional real-world notification channels.

    The runtime still writes every proactive message to the internal outbox.
    This bridge adds external delivery when configured, and returns a compact
    receipt that can be stored without leaking provider secrets.
    """

    def __init__(self, config: BackendConfig) -> None:
        self.config = config

    def deliver(
        self,
        *,
        message: str,
        signal: ProactiveSignal,
        trace_id: str,
        now: datetime | None = None,
        title: str = "叶筝",
    ) -> NotificationDelivery:
        now = now or datetime.now(timezone.utc)
        occurred_at = utc_now_iso(now)
        channel = self._select_channel()
        if not self.config.notify_enabled:
            return _skipped(channel="internal", detail="notification_disabled", occurred_at=occurred_at)
        if channel == "internal":
            return _skipped(channel="internal", detail="no_external_channel_configured", occurred_at=occurred_at)

        payload = {
            "title": title,
            "body": message,
            "message": message,
            "trace_id": trace_id,
            "source": "role-play",
            "signal": signal.to_dict(),
        }
        try:
            if channel == "telegram":
                status_code, body = self._deliver_telegram(title, message)
                provider = "telegram"
            elif channel == "bark":
                status_code, body = self._deliver_bark(title, message, payload)
                provider = "bark"
            else:
                status_code, body = self._deliver_webhook(payload)
                provider = "webhook"
        except urllib.error.HTTPError as exc:
            return _failed(
                channel=channel,
                provider=channel,
                detail=_clip(f"HTTPError:{exc.code}:{_safe_read_error(exc)}", 240),
                occurred_at=occurred_at,
                status_code=int(exc.code),
            )
        except Exception as exc:  # noqa: BLE001 - delivery failure should not crash proactive runtime.
            return _failed(
                channel=channel,
                provider=channel,
                detail=_clip(type(exc).__name__ + ": " + str(exc), 240),
                occurred_at=occurred_at,
            )

        ok = 200 <= int(status_code) < 300
        if not ok:
            return _failed(
                channel=channel,
                provider=provider,
                detail=_clip(body, 240),
                occurred_at=occurred_at,
                status_code=int(status_code),
            )
        return NotificationDelivery(
            channel=channel,
            provider=provider,
            status="delivered",
            attempted=True,
            ok=True,
            receipt_type="notification_delivered",
            detail=_clip(body, 240),
            status_code=int(status_code),
            occurred_at=occurred_at,
        )

    def _select_channel(self) -> str:
        explicit = self.config.notify_channel.strip().lower()
        if explicit in {"webhook", "telegram", "bark"}:
            return explicit
        if self.config.notify_webhook_url:
            return "webhook"
        if self.config.notify_telegram_bot_token and self.config.notify_telegram_chat_id:
            return "telegram"
        if self.config.notify_bark_url:
            return "bark"
        return "internal"

    def _deliver_webhook(self, payload: dict[str, Any]) -> tuple[int, str]:
        if not self.config.notify_webhook_url:
            raise ValueError("notify_webhook_url is required")
        return _post_json(self.config.notify_webhook_url, payload, timeout=self.config.notify_timeout_seconds)

    def _deliver_telegram(self, title: str, message: str) -> tuple[int, str]:
        if not self.config.notify_telegram_bot_token or not self.config.notify_telegram_chat_id:
            raise ValueError("telegram bot token and chat id are required")
        url = f"https://api.telegram.org/bot{self.config.notify_telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.config.notify_telegram_chat_id,
            "text": f"{title}\n\n{message}",
            "disable_web_page_preview": True,
        }
        return _post_json(url, payload, timeout=self.config.notify_timeout_seconds)

    def _deliver_bark(self, title: str, message: str, payload: dict[str, Any]) -> tuple[int, str]:
        if not self.config.notify_bark_url:
            raise ValueError("notify_bark_url is required")
        url = self.config.notify_bark_url
        if "{title}" in url or "{body}" in url or "{message}" in url:
            rendered = (
                url.replace("{title}", urllib.parse.quote(title, safe=""))
                .replace("{body}", urllib.parse.quote(message, safe=""))
                .replace("{message}", urllib.parse.quote(message, safe=""))
            )
            return _get(rendered, timeout=self.config.notify_timeout_seconds)
        rendered = f"{url.rstrip('/')}/{urllib.parse.quote(title, safe='')}/{urllib.parse.quote(message, safe='')}"
        try:
            return _get(rendered, timeout=self.config.notify_timeout_seconds)
        except urllib.error.HTTPError:
            return _post_json(url, payload, timeout=self.config.notify_timeout_seconds)


def _post_json(url: str, payload: dict[str, Any], *, timeout: int) -> tuple[int, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "role-play-companion/0.1"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=max(1, int(timeout))) as response:  # noqa: S310 - URL is user-configured.
        body = response.read(2048).decode("utf-8", errors="replace")
        return int(getattr(response, "status", 200)), body


def _get(url: str, *, timeout: int) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "role-play-companion/0.1"}, method="GET")
    with urllib.request.urlopen(request, timeout=max(1, int(timeout))) as response:  # noqa: S310 - URL is user-configured.
        body = response.read(2048).decode("utf-8", errors="replace")
        return int(getattr(response, "status", 200)), body


def _skipped(*, channel: str, detail: str, occurred_at: str) -> NotificationDelivery:
    return NotificationDelivery(
        channel=channel,
        provider=channel,
        status="skipped",
        attempted=False,
        ok=False,
        receipt_type="notification_skipped",
        detail=detail,
        occurred_at=occurred_at,
    )


def _failed(
    *,
    channel: str,
    provider: str,
    detail: str,
    occurred_at: str,
    status_code: int = 0,
) -> NotificationDelivery:
    return NotificationDelivery(
        channel=channel,
        provider=provider,
        status="failed",
        attempted=True,
        ok=False,
        receipt_type="notification_failed",
        detail=detail,
        status_code=status_code,
        occurred_at=occurred_at,
    )


def _safe_read_error(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read(2048).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _clip(text: str, limit: int) -> str:
    compact = " ".join(str(text).split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"
