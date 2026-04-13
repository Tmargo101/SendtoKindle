from __future__ import annotations

from functools import lru_cache

from send_to_kindle.auth import UserRegistry
from send_to_kindle.config import ensure_directories, load_settings, load_users
from send_to_kindle.db import init_db
from send_to_kindle.repository import JobStore


@lru_cache(maxsize=1)
def get_settings():
    settings = load_settings()
    ensure_directories(settings)
    return settings


@lru_cache(maxsize=1)
def get_user_registry() -> UserRegistry:
    settings = get_settings()
    return UserRegistry(load_users(settings.users_config_path))


@lru_cache(maxsize=1)
def get_job_store() -> JobStore:
    settings = get_settings()
    init_db(settings.database_path)
    return JobStore(settings.database_path)
