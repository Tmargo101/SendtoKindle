from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, detect_types=sqlite3.PARSE_DECLTYPES, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA foreign_keys=ON;")
    return connection


def init_db(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                source_url TEXT NOT NULL,
                status TEXT NOT NULL,
                normalized_title TEXT,
                failure_reason TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                sent_at TEXT,
                artifact_path TEXT,
                next_attempt_at TEXT NOT NULL,
                last_error_is_transient INTEGER NOT NULL DEFAULT 0,
                processing_started_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_ready
            ON jobs(status, next_attempt_at, created_at);
            """
        )
        connection.commit()


@contextmanager
def transaction(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
