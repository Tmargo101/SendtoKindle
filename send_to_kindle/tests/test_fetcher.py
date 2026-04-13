from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from send_to_kindle.config import Settings
from send_to_kindle.services.fetcher import FetchedPage, looks_like_blocked_or_interstitial_page, should_retry_in_browser


class FetcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base_path = Path(self.temp_dir.name)
        self.settings = Settings(
            app_name="send-to-kindle",
            base_dir=base_path,
            data_dir=base_path / "data",
            artifacts_dir=base_path / "artifacts",
            database_path=base_path / "data" / "jobs.db",
            users_config_path=base_path / "config" / "users.yaml",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username=None,
            smtp_password=None,
            smtp_sender="sender@example.com",
            smtp_use_tls=False,
            request_timeout_seconds=5,
            max_redirects=5,
            worker_poll_interval_seconds=0.1,
            worker_max_retries=3,
            retry_backoff_seconds=1,
            retention_hours=24,
            user_agent="test-agent",
            browser_fetch_enabled=True,
            browser_fetch_timeout_seconds=30,
            log_level="INFO",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_403_triggers_browser_retry_for_any_host(self) -> None:
        self.assertTrue(should_retry_in_browser(self.settings, status_code=403))

    def test_429_triggers_browser_retry(self) -> None:
        self.assertTrue(should_retry_in_browser(self.settings, status_code=429))

    def test_successful_http_fetch_with_readable_content_does_not_trigger_browser_retry(self) -> None:
        page = FetchedPage(
            url="https://example.com/article",
            html="<html><body><article><h1>Hello</h1><p>Readable content</p></article></body></html>",
            content_type="text/html; charset=utf-8",
        )
        self.assertFalse(should_retry_in_browser(self.settings, page=page))

    def test_interstitial_html_triggers_browser_retry(self) -> None:
        page = FetchedPage(
            url="https://example.com/article",
            html="<html><body>Please enable JavaScript and disable any ad blocker</body></html>",
            content_type="text/html; charset=utf-8",
        )
        self.assertTrue(looks_like_blocked_or_interstitial_page(page.html))
        self.assertTrue(should_retry_in_browser(self.settings, page=page))

    def test_browser_retry_disabled_via_settings(self) -> None:
        self.settings.browser_fetch_enabled = False
        self.assertFalse(should_retry_in_browser(self.settings, status_code=403))
