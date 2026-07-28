from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOWERCASE_LLM_ALIASES = frozenset({"base_url", "key", "model"})


@dataclass
class BackendConfig:
    project_root: Path
    env_path: Path
    frontend_dir: Path
    data_dir: Path | None = None
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7
    timeout_seconds: int = 120
    max_tokens: int = 768
    mock: bool = False
    notify_enabled: bool = True
    notify_channel: str = ""
    notify_webhook_url: str = ""
    notify_telegram_bot_token: str = ""
    notify_telegram_chat_id: str = ""
    notify_bark_url: str = ""
    notify_timeout_seconds: int = 10
    deployment_mode: str = "local"
    auth_token: str = ""
    tester_access_code: str = ""
    session_secret: str = ""
    session_ttl_seconds: int = 7 * 24 * 60 * 60
    session_idle_seconds: int = 24 * 60 * 60
    cors_origins: tuple[str, ...] = ()

    @property
    def llm_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    @property
    def notification_configured(self) -> bool:
        if not self.notify_enabled:
            return False
        channel = self.notify_channel.strip().lower()
        if channel == "telegram":
            return bool(self.notify_telegram_bot_token and self.notify_telegram_chat_id)
        if channel == "bark":
            return bool(self.notify_bark_url)
        if channel == "webhook":
            return bool(self.notify_webhook_url)
        return bool(
            self.notify_webhook_url
            or (self.notify_telegram_bot_token and self.notify_telegram_chat_id)
            or self.notify_bark_url
        )

    @property
    def public_deployment(self) -> bool:
        return self.deployment_mode == "public"

    @property
    def runtime_data_dir(self) -> Path:
        if self.data_dir is not None:
            return self.data_dir.resolve()
        return (self.project_root / "outputs" / "companion_runtime").resolve()

    @property
    def cookie_auth_configured(self) -> bool:
        return bool(self.tester_access_code and self.session_secret)

    def validate_server_boundary(self) -> None:
        if self.deployment_mode not in {"local", "public"}:
            raise ValueError("deployment mode must be local or public")
        if self.tester_access_code and not self.session_secret:
            raise ValueError("tester access code requires a session secret")
        if self.public_deployment and (not self.cors_origins or "*" in self.cors_origins):
            raise ValueError("public deployment requires explicit CORS origins")
        if self.public_deployment and not (self.auth_token or self.cookie_auth_configured):
            raise ValueError("public deployment requires bearer or cookie authentication")


def load_backend_config(
    project_root: Path = PROJECT_ROOT,
    env_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
    frontend_dir: Path | None = None,
) -> BackendConfig:
    root = project_root.resolve()
    env_file = env_path or root / ".env"
    env = dict(os.environ if environ is None else environ)
    file_values = _read_env_file(env_file)

    def value(*keys: str, default: str = "") -> str:
        for key in keys:
            if key in env and env[key] != "":
                return env[key]
        for key in keys:
            if key in file_values and file_values[key] != "":
                return file_values[key]
        return default

    deployment_mode = value(
        "LUMINOUS_DEPLOYMENT_MODE", "ROLE_PLAY_DEPLOYMENT_MODE", default="local"
    ).strip().lower()
    if deployment_mode not in {"local", "public"}:
        raise ValueError("deployment mode must be local or public")
    auth_token = value("LUMINOUS_AUTH_TOKEN", "ROLE_PLAY_AUTH_TOKEN").strip()
    tester_access_code = value("LUMINOUS_TESTER_ACCESS_CODE", "ROLE_PLAY_TESTER_ACCESS_CODE").strip()
    session_secret = value("LUMINOUS_SESSION_SECRET", "ROLE_PLAY_SESSION_SECRET").strip()
    cors_origins = tuple(
        origin.strip()
        for origin in value("LUMINOUS_CORS_ORIGINS", "ROLE_PLAY_CORS_ORIGINS").split(",")
        if origin.strip()
    )
    if tester_access_code and not session_secret:
        raise ValueError("tester access code requires a session secret")
    if deployment_mode == "public" and (not cors_origins or "*" in cors_origins):
        raise ValueError("public deployment requires explicit CORS origins")
    if deployment_mode == "public" and not (auth_token or (tester_access_code and session_secret)):
        raise ValueError("public deployment requires bearer or cookie authentication")

    raw_data_dir = value("LUMINOUS_DATA_DIR", "ROLE_PLAY_DATA_DIR").strip()

    return BackendConfig(
        project_root=root,
        env_path=env_file,
        frontend_dir=(frontend_dir or root / "apps" / "companion-web" / "companion-ui").resolve(),
        data_dir=Path(raw_data_dir).expanduser().resolve() if raw_data_dir else None,
        base_url=value("ROLE_PLAY_BASE_URL", "OPENAI_BASE_URL", "base_url").rstrip("/"),
        api_key=value("ROLE_PLAY_API_KEY", "OPENAI_API_KEY", "key"),
        model=value("ROLE_PLAY_MODEL", "OPENAI_MODEL", "model"),
        temperature=float(value("ROLE_PLAY_TEMPERATURE", "OPENAI_TEMPERATURE", default="0.7")),
        timeout_seconds=int(value("ROLE_PLAY_TIMEOUT", "OPENAI_TIMEOUT", "timeout", default="120")),
        max_tokens=int(value("ROLE_PLAY_MAX_TOKENS", "OPENAI_MAX_TOKENS", "max_tokens", default="768")),
        mock=_truthy(value("ROLE_PLAY_MOCK", default="false")),
        notify_enabled=_truthy(value("ROLE_PLAY_NOTIFY_ENABLED", default="true")),
        notify_channel=value("ROLE_PLAY_NOTIFY_CHANNEL", default="").strip().lower(),
        notify_webhook_url=value("ROLE_PLAY_NOTIFY_WEBHOOK_URL", "ROLE_PLAY_NOTIFY_URL", default="").strip(),
        notify_telegram_bot_token=value("ROLE_PLAY_NOTIFY_TELEGRAM_BOT_TOKEN", default="").strip(),
        notify_telegram_chat_id=value("ROLE_PLAY_NOTIFY_TELEGRAM_CHAT_ID", default="").strip(),
        notify_bark_url=value("ROLE_PLAY_NOTIFY_BARK_URL", default="").strip(),
        notify_timeout_seconds=int(value("ROLE_PLAY_NOTIFY_TIMEOUT", default="10")),
        deployment_mode=deployment_mode,
        auth_token=auth_token,
        tester_access_code=tester_access_code,
        session_secret=session_secret,
        session_ttl_seconds=int(value("LUMINOUS_SESSION_TTL_SECONDS", default=str(7 * 24 * 60 * 60))),
        session_idle_seconds=int(value("LUMINOUS_SESSION_IDLE_SECONDS", default=str(24 * 60 * 60))),
        cors_origins=cors_origins,
    )


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        value = raw_value.strip().strip('"').strip("'")
        if key in LOWERCASE_LLM_ALIASES:
            values.setdefault(key, value)
        else:
            values[key] = value
    return values


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on", "是"}
