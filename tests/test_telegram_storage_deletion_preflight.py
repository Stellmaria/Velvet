from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.telegram_storage_deletion_preflight import main
from velvet_bot.domains.telegram_storage.models import TelegramStorageSettings


class TelegramStorageDeletionPreflightTests(unittest.TestCase):
    @staticmethod
    def _environment(project: Path) -> dict[str, str]:
        return {
            "SUPERVISOR_PROJECT_DIR": str(project),
            "SUPERVISOR_RUNTIME_DIR": str(project / "runtime" / "supervisor"),
            "SUPERVISOR_LOG_DIR": str(project / "logs"),
            "BACKUP_DIR": str(project / "backups"),
            "STORAGE_EXPORT_DIRS": str(project / "exports"),
            "STORAGE_RELEASE_DIRS": str(project / "releases"),
            "STORAGE_STAGING_DIR": str(project / "runtime" / "telegram-storage"),
            "KRITA_BRIDGE_DIR": str(project / "runtime" / "krita"),
            "VELVET_DATA_DIR": str(project / "data"),
            "STORAGE_ENCRYPTION_SECRET": "storage-secret-12345678901234567890",
            "STORAGE_DELETE_AFTER_UPLOAD": "true",
        }

    def test_valid_roots_pass_and_are_printed_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            output = io.StringIO()
            with patch.dict(
                os.environ,
                self._environment(project),
                clear=False,
            ), redirect_stdout(output):
                code = main([])

        text = output.getvalue()
        self.assertEqual(0, code)
        self.assertIn("Telegram Storage deletion preflight: OK", text)
        self.assertIn(str(project / "exports"), text)
        self.assertNotIn("storage-secret", text)

    def test_project_root_cannot_be_configured_as_export_deletion_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            environment = self._environment(project)
            environment["STORAGE_EXPORT_DIRS"] = str(project)
            with patch.dict(os.environ, environment, clear=False):
                with self.assertRaisesRegex(ValueError, "Protected path"):
                    TelegramStorageSettings.from_env()

    def test_empty_allowlist_is_rejected_when_auto_delete_is_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            environment = self._environment(project)
            environment["STORAGE_EXPORT_DIRS"] = ";"
            with patch.dict(os.environ, environment, clear=False):
                with self.assertRaisesRegex(ValueError, "empty allowlist"):
                    TelegramStorageSettings.from_env()

    def test_dry_run_returns_failure_for_path_outside_selected_kind_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            outside = project / "outside.json"
            outside.write_text('{"keep":true}', encoding="utf-8")
            output = io.StringIO()
            with patch.dict(
                os.environ,
                self._environment(project),
                clear=False,
            ), redirect_stdout(output):
                code = main(["--kind", "exports", "--path", str(outside)])

            self.assertEqual(1, code)
            self.assertIn("code=outside_allowlist", output.getvalue())
            self.assertTrue(outside.exists())


if __name__ == "__main__":
    unittest.main()
