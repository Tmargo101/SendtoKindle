from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import yaml

from send_to_kindle.models import UserRecord


@dataclass(slots=True)
class Settings:
    app_name: str
    base_dir: Path
    data_dir: Path
    artifacts_dir: Path
    database_path: Path
    users_config_path: Path
    smtp_host: str
    smtp_port: int
    smtp_username: Optional[str]
    smtp_password: Optional[str]
    smtp_sender: str
    smtp_use_tls: bool
    request_timeout_seconds: float
    max_redirects: int
    worker_poll_interval_seconds: float
    worker_max_retries: int
    retry_backoff_seconds: int
    retention_hours: int
    user_agent: str
    browser_fetch_enabled: bool
    browser_fetch_timeout_seconds: float
    log_level: str


DEFAULT_APP_NAME = "send-to-kindle"


def _load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        value = value.strip()
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    base_dir = Path(os.getenv("STK_BASE_DIR") or Path.cwd()).resolve()
    _load_dotenv_file(base_dir / ".env")
    base_dir = Path(os.getenv("STK_BASE_DIR") or base_dir).resolve()
    data_dir = Path(os.getenv("STK_DATA_DIR") or (base_dir / "data")).resolve()
    artifacts_dir = Path(os.getenv("STK_ARTIFACTS_DIR") or (base_dir / "artifacts")).resolve()
    database_path = Path(os.getenv("STK_DATABASE_PATH") or (data_dir / "send_to_kindle.db")).resolve()
    users_config_path = Path(os.getenv("STK_USERS_CONFIG_PATH") or (base_dir / "config" / "users.yaml")).resolve()
    smtp_port = int(os.getenv("STK_SMTP_PORT", "587"))
    default_smtp_use_tls = smtp_port == 465

    return Settings(
        app_name=os.getenv("STK_APP_NAME", DEFAULT_APP_NAME),
        base_dir=base_dir,
        data_dir=data_dir,
        artifacts_dir=artifacts_dir,
        database_path=database_path,
        users_config_path=users_config_path,
        smtp_host=os.getenv("STK_SMTP_HOST", "localhost"),
        smtp_port=smtp_port,
        smtp_username=os.getenv("STK_SMTP_USERNAME") or None,
        smtp_password=os.getenv("STK_SMTP_PASSWORD") or None,
        smtp_sender=os.getenv("STK_SMTP_SENDER", "send-to-kindle@example.com"),
        smtp_use_tls=_get_bool_env("STK_SMTP_USE_TLS", default_smtp_use_tls),
        request_timeout_seconds=float(os.getenv("STK_REQUEST_TIMEOUT_SECONDS", "20")),
        max_redirects=int(os.getenv("STK_MAX_REDIRECTS", "5")),
        worker_poll_interval_seconds=float(os.getenv("STK_WORKER_POLL_INTERVAL_SECONDS", "2")),
        worker_max_retries=int(os.getenv("STK_WORKER_MAX_RETRIES", "3")),
        retry_backoff_seconds=int(os.getenv("STK_RETRY_BACKOFF_SECONDS", "30")),
        retention_hours=int(os.getenv("STK_RETENTION_HOURS", "24")),
        user_agent=os.getenv(
            "STK_USER_AGENT",
            "Mozilla/5.0 (compatible; send-to-kindle/0.1; +https://example.invalid)",
        ),
        browser_fetch_enabled=_get_bool_env("STK_BROWSER_FETCH_ENABLED", True),
        browser_fetch_timeout_seconds=float(os.getenv("STK_BROWSER_FETCH_TIMEOUT_SECONDS", "30")),
        log_level=os.getenv("STK_LOG_LEVEL", "INFO"),
    )


def ensure_directories(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    settings.users_config_path.parent.mkdir(parents=True, exist_ok=True)


def load_users(path: Path) -> Dict[str, UserRecord]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    users: Dict[str, UserRecord] = {}
    for entry in raw.get("users", []):
        record = UserRecord(
            user_id=str(entry["user_id"]),
            token_hash=str(entry["token_hash"]),
            kindle_email=str(entry["kindle_email"]),
            display_name=entry.get("display_name"),
        )
        users[record.user_id] = record
    return users
