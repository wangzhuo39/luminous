from __future__ import annotations

import hashlib
import hmac
from collections import deque
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from secrets import token_urlsafe
from threading import Lock

from luminous.runtime.config import BackendConfig
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore


COOKIE_NAME = "__Host-luminous_session"
_COOKIE_EXPIRES = "Thu, 01 Jan 1970 00:00:00 GMT"
_FAILURE_WINDOW = timedelta(minutes=5)
_LOCKOUT_DURATION = timedelta(minutes=15)
_MAX_FAILURES = 5


class LoginRateLimited(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("login is temporarily rate limited")
        self.retry_after_seconds = max(1, retry_after_seconds)


class SessionAuth:
    """Single-tester, database-backed browser sessions.

    The browser only receives a random opaque token. The database stores a
    keyed digest, so a database copy cannot be used directly as a session.
    """

    def __init__(
        self,
        config: BackendConfig,
        store: CompanionRuntimeStore,
        *,
        clock: callable | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._failed_logins: deque[datetime] = deque()
        self._blocked_until: datetime | None = None
        self._login_lock = Lock()

    @property
    def enabled(self) -> bool:
        return self.config.cookie_auth_configured

    def authenticate(self, cookie_header: str) -> bool:
        token = self._read_cookie(cookie_header)
        if not token or not self.enabled:
            return False
        digest = self._digest(token)
        session = self.store.read_auth_session(digest)
        if session is None or session.get("revoked_at"):
            return False
        now = self.clock()
        if _parse_time(str(session.get("expires_at", ""))) <= now:
            self.store.revoke_auth_session(digest, _iso(now))
            return False
        last_seen = _parse_time(str(session.get("last_seen_at", "")))
        if last_seen + timedelta(seconds=max(60, self.config.session_idle_seconds)) <= now:
            self.store.revoke_auth_session(digest, _iso(now))
            return False
        if (now - last_seen).total_seconds() >= 300:
            self.store.touch_auth_session(digest, _iso(now))
        return True

    def login(self, access_code: str) -> str | None:
        if not self.enabled:
            return None
        now = self.clock()
        with self._login_lock:
            if self._blocked_until and self._blocked_until > now:
                raise LoginRateLimited(int((self._blocked_until - now).total_seconds()))
            self._blocked_until = None
            cutoff = now - _FAILURE_WINDOW
            while self._failed_logins and self._failed_logins[0] < cutoff:
                self._failed_logins.popleft()
            expected = self.config.tester_access_code
            if not hmac.compare_digest(str(access_code).strip(), expected):
                self._failed_logins.append(now)
                if len(self._failed_logins) >= _MAX_FAILURES:
                    self._blocked_until = now + _LOCKOUT_DURATION
                return None
            self._failed_logins.clear()
        token = token_urlsafe(32)
        self.store.purge_auth_sessions(_iso(now))
        self.store.create_auth_session(
            self._digest(token),
            _iso(now),
            _iso(now + timedelta(seconds=max(300, self.config.session_ttl_seconds))),
        )
        return token

    def logout(self, cookie_header: str) -> None:
        token = self._read_cookie(cookie_header)
        if token:
            self.store.revoke_auth_session(self._digest(token), _iso(self.clock()))

    @staticmethod
    def cookie_header(token: str, *, clear: bool = False) -> str:
        if clear:
            return f"{COOKIE_NAME}=; Path=/; Max-Age=0; Expires={_COOKIE_EXPIRES}; HttpOnly; Secure; SameSite=Lax"
        return f"{COOKIE_NAME}={token}; Path=/; HttpOnly; Secure; SameSite=Lax"

    @staticmethod
    def _read_cookie(header: str) -> str:
        if not header:
            return ""
        cookie = SimpleCookie()
        try:
            cookie.load(header)
        except Exception:  # pragma: no cover - SimpleCookie is deliberately defensive.
            return ""
        morsel = cookie.get(COOKIE_NAME)
        return morsel.value.strip() if morsel else ""

    def _digest(self, token: str) -> str:
        secret = self.config.session_secret.encode("utf-8")
        return hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
