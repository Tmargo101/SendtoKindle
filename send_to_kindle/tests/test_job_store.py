from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from send_to_kindle.db import init_db
from send_to_kindle.repository import JobStore


class JobStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "jobs.db"
        init_db(self.database_path)
        self.store = JobStore(self.database_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_claim_and_retry_flow(self) -> None:
        job = self.store.enqueue_job("tester", "https://example.com/a")
        claimed = self.store.claim_next_job()
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.job_id, job.job_id)

        self.store.mark_failed(job.job_id, "temporary", transient=True, max_retries=3, backoff_seconds=1)
        retried = self.store.get_job(job.job_id)
        self.assertEqual(retried.status, "queued")
        self.assertEqual(retried.retry_count, 1)

    def test_artifact_cleanup_detaches_old_files(self) -> None:
        job = self.store.enqueue_job("tester", "https://example.com/a")
        self.store.mark_sent(job.job_id, "Title", "/tmp/test.epub")
        old_cutoff = datetime.now(timezone.utc) + timedelta(hours=1)
        artifacts = self.store.delete_expired_artifacts(old_cutoff)
        self.assertEqual(artifacts, ["/tmp/test.epub"])
        refreshed = self.store.get_job(job.job_id)
        self.assertIsNone(refreshed.artifact_path)
