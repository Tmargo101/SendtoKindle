from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from send_to_kindle.db import connect, transaction
from send_to_kindle.models import JobRecord


class JobStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def enqueue_job(self, user_id: str, source_url: str) -> JobRecord:
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        with transaction(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, user_id, source_url, status, normalized_title, failure_reason,
                    retry_count, created_at, updated_at, sent_at, artifact_path, next_attempt_at,
                    last_error_is_transient, processing_started_at
                ) VALUES (?, ?, ?, 'queued', NULL, NULL, 0, ?, ?, NULL, NULL, ?, 0, NULL)
                """,
                (job_id, user_id, source_url, now.isoformat(), now.isoformat(), now.isoformat()),
            )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with connect(self.database_path) as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._row_to_record(row) if row else None

    def claim_next_job(self, stale_after_seconds: int = 300) -> Optional[JobRecord]:
        now = datetime.now(timezone.utc)
        stale_cutoff = (now - timedelta(seconds=stale_after_seconds)).isoformat()
        with transaction(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM jobs
                WHERE (
                    status = 'queued' AND next_attempt_at <= ?
                ) OR (
                    status = 'processing' AND processing_started_at <= ?
                )
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (now.isoformat(), stale_cutoff),
            ).fetchone()
            if row is None:
                return None

            connection.execute(
                """
                UPDATE jobs
                SET status = 'processing', updated_at = ?, processing_started_at = ?
                WHERE job_id = ?
                """,
                (now.isoformat(), now.isoformat(), row["job_id"]),
            )

        return self.get_job(str(row["job_id"]))

    def mark_sent(self, job_id: str, normalized_title: str, artifact_path: Optional[str]) -> None:
        now = datetime.now(timezone.utc)
        with transaction(self.database_path) as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = 'sent', normalized_title = ?, artifact_path = ?, sent_at = ?, updated_at = ?,
                    failure_reason = NULL, processing_started_at = NULL
                WHERE job_id = ?
                """,
                (normalized_title, artifact_path, now.isoformat(), now.isoformat(), job_id),
            )

    def mark_failed(
        self,
        job_id: str,
        reason: str,
        transient: bool,
        max_retries: int,
        backoff_seconds: int,
        normalized_title: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        with transaction(self.database_path) as connection:
            row = connection.execute("SELECT retry_count FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                return
            retry_count = int(row["retry_count"])
            next_retry_count = retry_count + 1 if transient else retry_count
            should_retry = transient and retry_count < max_retries
            next_status = "queued" if should_retry else "failed"
            next_attempt_at = now + timedelta(seconds=backoff_seconds * max(1, retry_count + 1))
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, normalized_title = COALESCE(?, normalized_title), failure_reason = ?,
                    retry_count = ?, updated_at = ?, next_attempt_at = ?,
                    last_error_is_transient = ?, processing_started_at = NULL
                WHERE job_id = ?
                """,
                (
                    next_status,
                    normalized_title,
                    reason,
                    next_retry_count,
                    now.isoformat(),
                    next_attempt_at.isoformat(),
                    1 if transient else 0,
                    job_id,
                ),
            )

    def delete_expired_artifacts(self, older_than: datetime) -> list[str]:
        with transaction(self.database_path) as connection:
            rows = connection.execute(
                "SELECT job_id, artifact_path FROM jobs WHERE artifact_path IS NOT NULL AND updated_at < ?",
                (older_than.isoformat(),),
            ).fetchall()
            artifact_paths = [str(row["artifact_path"]) for row in rows if row["artifact_path"]]
            connection.execute(
                "UPDATE jobs SET artifact_path = NULL WHERE artifact_path IS NOT NULL AND updated_at < ?",
                (older_than.isoformat(),),
            )
        return artifact_paths

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            job_id=str(row["job_id"]),
            user_id=str(row["user_id"]),
            source_url=str(row["source_url"]),
            status=str(row["status"]),
            normalized_title=row["normalized_title"],
            failure_reason=row["failure_reason"],
            retry_count=int(row["retry_count"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
            sent_at=datetime.fromisoformat(str(row["sent_at"])) if row["sent_at"] else None,
            artifact_path=row["artifact_path"],
            next_attempt_at=datetime.fromisoformat(str(row["next_attempt_at"])),
            last_error_is_transient=bool(row["last_error_is_transient"]),
        )
