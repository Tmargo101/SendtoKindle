from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from send_to_kindle.dependencies import get_job_store, get_settings, get_user_registry


class ApiAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base_path = Path(self.temp_dir.name)
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
        os.environ["STK_BASE_DIR"] = str(base_path)
        os.environ["STK_USERS_CONFIG_PATH"] = str(users_path)
        os.environ["STK_DATA_DIR"] = str(base_path / "data")
        os.environ["STK_ARTIFACTS_DIR"] = str(base_path / "artifacts")
        os.environ["STK_DATABASE_PATH"] = str(base_path / "data" / "test.db")

        get_settings.cache_clear()
        get_user_registry.cache_clear()
        get_job_store.cache_clear()

        from send_to_kindle.api.app import app

        self.client = TestClient(app)

    def tearDown(self) -> None:
        get_settings.cache_clear()
        get_user_registry.cache_clear()
        get_job_store.cache_clear()
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
