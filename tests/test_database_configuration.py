"""Configuration tests for local SQLite and remote Turso persistence."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config import Settings
from core.database import Database


class DatabaseConfigurationTests(unittest.TestCase):
    def test_turso_environment_is_loaded_as_a_pair(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TURSO_DATABASE_URL": "libsql://rag-example.turso.io",
                "TURSO_AUTH_TOKEN": "test-token",
            },
            clear=False,
        ):
            settings = Settings.from_env()
        self.assertEqual(settings.turso_database_url, "libsql://rag-example.turso.io")
        self.assertEqual(settings.turso_auth_token, "test-token")

    def test_turso_url_and_token_must_be_configured_together(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.db"
            with self.assertRaisesRegex(RuntimeError, "must be configured together"):
                Database(path, turso_url="libsql://rag-example.turso.io")


if __name__ == "__main__":
    unittest.main()
