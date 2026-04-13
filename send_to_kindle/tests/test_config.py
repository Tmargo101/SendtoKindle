from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from send_to_kindle.config import ensure_directories, load_settings


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_cwd = Path.cwd()
        self.original_env = os.environ.copy()
        os.chdir(self.temp_dir.name)

    def tearDown(self) -> None:
        os.chdir(self.original_cwd)
        os.environ.clear()
        os.environ.update(self.original_env)
        self.temp_dir.cleanup()

    def test_defaults_follow_runtime_working_directory(self) -> None:
        for variable in (
            "STK_BASE_DIR",
            "STK_DATA_DIR",
            "STK_ARTIFACTS_DIR",
            "STK_DATABASE_PATH",
            "STK_USERS_CONFIG_PATH",
        ):
            os.environ.pop(variable, None)

        settings = load_settings()
        expected_root = Path(self.temp_dir.name).resolve()

        self.assertEqual(settings.base_dir, expected_root)
        self.assertEqual(settings.data_dir, expected_root / "data")
        self.assertEqual(settings.artifacts_dir, expected_root / "artifacts")
        self.assertEqual(settings.database_path, expected_root / "data" / "send_to_kindle.db")
        self.assertEqual(settings.users_config_path, expected_root / "config" / "users.yaml")

        ensure_directories(settings)
        self.assertTrue(settings.data_dir.is_dir())
        self.assertTrue(settings.artifacts_dir.is_dir())
        self.assertTrue(settings.users_config_path.parent.is_dir())

    def test_legacy_override_paths_still_work(self) -> None:
        base_dir = Path(self.temp_dir.name).resolve() / "legacy-root"
        os.environ["STK_BASE_DIR"] = str(base_dir)
        os.environ["STK_DATA_DIR"] = str(base_dir / "custom-data")
        os.environ["STK_ARTIFACTS_DIR"] = str(base_dir / "custom-artifacts")
        os.environ["STK_DATABASE_PATH"] = str(base_dir / "db" / "jobs.sqlite")

        settings = load_settings()

        self.assertEqual(settings.base_dir, base_dir)
        self.assertEqual(settings.data_dir, base_dir / "custom-data")
        self.assertEqual(settings.artifacts_dir, base_dir / "custom-artifacts")
        self.assertEqual(settings.database_path, base_dir / "db" / "jobs.sqlite")

    def test_loads_smtp_settings_from_dotenv_in_working_directory(self) -> None:
        env_path = Path(self.temp_dir.name) / ".env"
        env_path.write_text(
            "\n".join(
                [
                    "STK_SMTP_HOST=smtp.gmail.com",
                    "STK_SMTP_PORT=587",
                    "STK_SMTP_USERNAME=tester@example.com",
                    "STK_SMTP_PASSWORD=secret",
                    "STK_SMTP_SENDER=tester@example.com",
                ]
            ),
            encoding="utf-8",
        )

        settings = load_settings()

        self.assertEqual(settings.smtp_host, "smtp.gmail.com")
        self.assertEqual(settings.smtp_port, 587)
        self.assertEqual(settings.smtp_username, "tester@example.com")
        self.assertEqual(settings.smtp_password, "secret")
        self.assertEqual(settings.smtp_sender, "tester@example.com")
        self.assertFalse(settings.smtp_use_tls)

    def test_explicit_tls_env_overrides_port_based_default(self) -> None:
        os.environ["STK_SMTP_PORT"] = "465"
        os.environ["STK_SMTP_USE_TLS"] = "false"

        settings = load_settings()

        self.assertFalse(settings.smtp_use_tls)
