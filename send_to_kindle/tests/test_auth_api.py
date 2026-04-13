from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml
from fastapi.testclient import TestClient

from send_to_kindle.dependencies import get_job_store, get_settings, get_user_registry
from send_to_kindle.models import ArticleContent


class ApiAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base_path = Path(self.temp_dir.name)
        self.original_cwd = Path.cwd()
        os.chdir(base_path)
        config_dir = base_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        users_path = config_dir / "users.yaml"
        users_path.write_text(
            yaml.safe_dump(
                {
                    "users": [
                        {
                            "user_id": "tester",
                            "kindle_email": "tester@kindle.com",
                            "token_hash": hashlib.sha256(b"secret-token").hexdigest(),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        os.environ["STK_USERS_CONFIG_PATH"] = str(users_path)

        get_settings.cache_clear()
        get_user_registry.cache_clear()
        get_job_store.cache_clear()

        from send_to_kindle.api.app import app

        self.client = TestClient(app)

    def tearDown(self) -> None:
        get_settings.cache_clear()
        get_user_registry.cache_clear()
        get_job_store.cache_clear()
        os.chdir(self.original_cwd)
        self.temp_dir.cleanup()

    def test_valid_token_enqueues_job(self) -> None:
        response = self.client.post(
            "/v1/articles",
            headers={"Authorization": "Bearer secret-token"},
            json={"url": "https://example.com/article"},
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "queued")

    def test_missing_token_rejected(self) -> None:
        response = self.client.post("/v1/articles", json={"url": "https://example.com/article"})
        self.assertEqual(response.status_code, 401)

    def test_non_http_url_rejected_by_schema(self) -> None:
        response = self.client.post(
            "/v1/articles",
            headers={"Authorization": "Bearer secret-token"},
            json={"url": "ftp://example.com/article"},
        )
        self.assertEqual(response.status_code, 422)

    def test_valid_token_downloads_epub(self) -> None:
        article = ArticleContent(
            source_url="https://example.com/article",
            title="Test Article",
            author=None,
            site_name=None,
            published_at=None,
            content_html="<p>Hello</p>",
            lead_image_url=None,
        )
        epub_path = Path(self.temp_dir.name) / "test-article.epub"
        epub_path.write_bytes(b"epub-bytes")

        with patch(
            "send_to_kindle.api.app.Worker.create_epub",
            new=AsyncMock(return_value=(article, epub_path)),
        ):
            response = self.client.post(
                "/v1/articles/download",
                headers={"Authorization": "Bearer secret-token"},
                json={"url": "https://example.com/article"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/epub+zip")
        self.assertIn('attachment; filename="test-article.epub"', response.headers["content-disposition"])
        self.assertEqual(response.content, b"epub-bytes")
        self.assertFalse(epub_path.exists())

    def test_download_missing_token_rejected(self) -> None:
        response = self.client.post("/v1/articles/download", json={"url": "https://example.com/article"})
        self.assertEqual(response.status_code, 401)
