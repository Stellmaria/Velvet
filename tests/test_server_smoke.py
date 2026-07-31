from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.server_smoke import (
    CRITICAL_TABLES,
    check_backup_directory,
    telegram_get_me,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class ServerSmokeTests(unittest.TestCase):
    def test_critical_tables_cover_ai_batches_and_roleplay(self) -> None:
        self.assertIn("ai_task_batches", CRITICAL_TABLES)
        self.assertIn("ai_tasks", CRITICAL_TABLES)
        self.assertIn("roleplay_sessions", CRITICAL_TABLES)
        self.assertIn("schema_migrations", CRITICAL_TABLES)

    def test_backup_directory_write_probe_leaves_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            check_backup_directory(path)
            self.assertEqual([], list(path.iterdir()))

    def test_backup_directory_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing"
            with self.assertRaisesRegex(RuntimeError, "does not exist"):
                check_backup_directory(path)

    def test_telegram_get_me_returns_identity_without_exposing_token(self) -> None:
        payload = {
            "ok": True,
            "result": {"id": 123, "username": "velvet_test_bot"},
        }
        with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
            result = telegram_get_me("123456:abcdefghijklmnopqrstuvwxyz_ABC123")
        self.assertEqual("velvet_test_bot", result["username"])

    def test_telegram_get_me_rejects_unsuccessful_payload(self) -> None:
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeResponse({"ok": False}),
        ):
            with self.assertRaisesRegex(RuntimeError, "unsuccessful"):
                telegram_get_me("123456:abcdefghijklmnopqrstuvwxyz_ABC123")


if __name__ == "__main__":
    unittest.main()
