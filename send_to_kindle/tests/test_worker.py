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
from send_to_kindle.services.extractor import ExtractionError
from send_to_kindle.services.fetcher import FetchError, FetchedPage
from send_to_kindle.worker import ProcessingFailure, Worker


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
            browser_fetch_enabled=True,
            browser_fetch_timeout_seconds=30,
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
        fetched_page = FetchedPage(
            url=job.source_url,
            html="<html><body><article><h1>Example Article</h1><p>Body</p></article></body></html>",
            content_type="text/html; charset=utf-8",
        )
        epub_path = self.settings.artifacts_dir / "article.epub"
        epub_path.write_bytes(b"epub")

        with patch("send_to_kindle.worker.fetch_url", new=AsyncMock(return_value=fetched_page)), \
             patch("send_to_kindle.worker.extract_article", return_value=article), \
             patch("send_to_kindle.worker.generate_epub", return_value=epub_path), \
             patch("send_to_kindle.worker.send_epub", new=AsyncMock()):
            asyncio.run(self.worker.run_once())

        refreshed = self.store.get_job(job.job_id)
        self.assertEqual(refreshed.status, "sent")
        self.assertEqual(refreshed.normalized_title, "Example Article")

    def test_generic_site_job_runs_through_fetch_pipeline(self) -> None:
        job = self.store.enqueue_job("tester", "https://example.com/feature")
        article = ArticleContent(
            source_url=job.source_url,
            title="Feature Example",
            author=None,
            site_name="Example",
            published_at=None,
            content_html="<p>Body</p>",
            lead_image_url=None,
        )
        fetched_page = FetchedPage(
            url=job.source_url,
            html="<html><body><article><h1>Feature Example</h1><p>Body</p></article></body></html>",
            content_type="text/html; charset=utf-8",
        )
        epub_path = self.settings.artifacts_dir / "feature.epub"
        epub_path.write_bytes(b"epub")

        with patch("send_to_kindle.worker.fetch_url", new=AsyncMock(return_value=fetched_page)) as fetch_mock, \
             patch("send_to_kindle.worker.extract_article", return_value=article), \
             patch("send_to_kindle.worker.generate_epub", return_value=epub_path), \
             patch("send_to_kindle.worker.send_epub", new=AsyncMock()):
            asyncio.run(self.worker.run_once())

        fetch_mock.assert_awaited_once_with(job.source_url, self.settings)
        refreshed = self.store.get_job(job.job_id)
        self.assertEqual(refreshed.status, "sent")
        self.assertEqual(refreshed.normalized_title, "Feature Example")

    def test_extraction_failure_retries_once_in_browser(self) -> None:
        article = ArticleContent(
            source_url="https://example.com/feature",
            title="Rendered Example",
            author=None,
            site_name="Example",
            published_at=None,
            content_html="<p>Body</p>",
            lead_image_url=None,
        )
        http_page = FetchedPage(
            url=article.source_url,
            html="<html><body><div id='app'></div></body></html>",
            content_type="text/html; charset=utf-8",
        )
        browser_page = FetchedPage(
            url=article.source_url,
            html="<html><body><article><h1>Rendered Example</h1><p>Body</p></article></body></html>",
            content_type="text/html; charset=utf-8",
        )
        epub_path = self.settings.artifacts_dir / "rendered.epub"
        epub_path.write_bytes(b"epub")

        with patch("send_to_kindle.worker.fetch_url", new=AsyncMock(return_value=http_page)) as fetch_mock, \
             patch("send_to_kindle.worker.fetch_url_in_browser", new=AsyncMock(return_value=browser_page)) as browser_mock, \
             patch("send_to_kindle.worker.extract_article", side_effect=[ExtractionError("no article"), article]), \
             patch("send_to_kindle.worker.generate_epub", return_value=epub_path):
            resolved_article, resolved_path = asyncio.run(self.worker.create_epub(article.source_url))

        fetch_mock.assert_awaited_once_with(article.source_url, self.settings)
        browser_mock.assert_awaited_once_with(article.source_url, self.settings)
        self.assertEqual(resolved_article.title, "Rendered Example")
        self.assertEqual(resolved_path, epub_path)

    def test_browser_failure_after_extraction_failure_is_transient(self) -> None:
        http_page = FetchedPage(
            url="https://example.com/feature",
            html="<html><body><div id='app'></div></body></html>",
            content_type="text/html; charset=utf-8",
        )

        with patch("send_to_kindle.worker.fetch_url", new=AsyncMock(return_value=http_page)), \
             patch("send_to_kindle.worker.fetch_url_in_browser", new=AsyncMock(side_effect=FetchError("Browser fallback failed", transient=True))), \
             patch("send_to_kindle.worker.extract_article", side_effect=ExtractionError("no article")):
            with self.assertRaises(ProcessingFailure) as context:
                asyncio.run(self.worker.create_epub("https://example.com/feature"))

        self.assertEqual(str(context.exception), "Browser fallback failed")
        self.assertTrue(context.exception.transient)

    def test_unreadable_http_and_browser_content_returns_non_transient_failure(self) -> None:
        http_page = FetchedPage(
            url="https://example.com/feature",
            html="<html><body><div id='app'></div></body></html>",
            content_type="text/html; charset=utf-8",
        )
        browser_page = FetchedPage(
            url="https://example.com/feature",
            html="<html><body><div id='app'>still unreadable</div></body></html>",
            content_type="text/html; charset=utf-8",
        )

        with patch("send_to_kindle.worker.fetch_url", new=AsyncMock(return_value=http_page)), \
             patch("send_to_kindle.worker.fetch_url_in_browser", new=AsyncMock(return_value=browser_page)), \
             patch("send_to_kindle.worker.extract_article", side_effect=[ExtractionError("no article"), ExtractionError("still no article")]):
            with self.assertRaises(ProcessingFailure) as context:
                asyncio.run(self.worker.create_epub("https://example.com/feature"))

        self.assertEqual(str(context.exception), "still no article")
        self.assertFalse(context.exception.transient)

    def test_run_forever_stops_when_stop_event_is_set(self) -> None:
        stop_event = asyncio.Event()

        async def run_worker() -> None:
            task = asyncio.create_task(self.worker.run_forever(stop_event))
            await asyncio.sleep(0.02)
            stop_event.set()
            await asyncio.wait_for(task, timeout=1)

        asyncio.run(run_worker())
