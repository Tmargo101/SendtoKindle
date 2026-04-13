from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from send_to_kindle.auth import UserRegistry
from send_to_kindle.config import Settings
from send_to_kindle.db import init_db
from send_to_kindle.models import ArticleContent, UserRecord
from send_to_kindle.repository import JobStore
from send_to_kindle.worker import Worker


class WorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.settings = Settings(
            app_name="send-to-kindle",
            base_dir=self.base_path,
            data_dir=self.base_path,
            artifacts_dir=self.base_path / "artifacts",
            database_path=self.base_path / "jobs.db",
            users_config_path=self.base_path / "users.yaml",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username=None,
            smtp_password=None,
            smtp_sender="sender@example.com",
            smtp_use_tls=True,
            request_timeout_seconds=5,
            max_redirects=5,
            worker_poll_interval_seconds=0.1,
            worker_max_retries=2,
            retry_backoff_seconds=1,
            retention_hours=24,
            user_agent="test-agent",
            log_level="INFO",
        )
        self.settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
        init_db(self.settings.database_path)
        self.store = JobStore(self.settings.database_path)
        self.user = UserRecord(user_id="tester", token_hash="hash", kindle_email="tester@kindle.com")
        self.worker = Worker(self.settings, self.store, UserRegistry({"tester": self.user}))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_success_path_marks_job_sent(self) -> None:
        job = self.store.enqueue_job("tester", "https://example.com/article")
        article = ArticleContent(
            source_url=job.source_url,
            title="Example Article",
            author=None,
            site_name=None,
            published_at=None,
            content_html="<p>Body</p>",
            lead_image_url=None,
        )
        epub_path = self.settings.artifacts_dir / "article.epub"
        epub_path.write_bytes(b"epub")

        with patch("send_to_kindle.worker.fetch_url", new=AsyncMock()), \
             patch("send_to_kindle.worker.extract_article", return_value=article), \
             patch("send_to_kindle.worker.generate_epub", return_value=epub_path), \
             patch("send_to_kindle.worker.send_epub", new=AsyncMock()):
            asyncio.run(self.worker.run_once())

        refreshed = self.store.get_job(job.job_id)
        self.assertEqual(refreshed.status, "sent")
        self.assertEqual(refreshed.normalized_title, "Example Article")

    def test_run_forever_stops_when_stop_event_is_set(self) -> None:
        stop_event = asyncio.Event()

        async def run_worker() -> None:
            task = asyncio.create_task(self.worker.run_forever(stop_event))
            await asyncio.sleep(0.02)
            stop_event.set()
            await asyncio.wait_for(task, timeout=1)

        asyncio.run(run_worker())
