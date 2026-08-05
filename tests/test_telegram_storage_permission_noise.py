from __future__ import annotations

import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from velvet_bot.domains.telegram_storage.deletion import (
    build_storage_deletion_policy,
    delete_paths,
)
from velvet_bot.domains.telegram_storage.models import MigrationSummary
from velvet_bot.domains.telegram_storage.service import TelegramStorageMigrationService


_LOGGER = "velvet_bot.domains.telegram_storage.deletion"


class TelegramStorageDeletionLoggingTests(unittest.TestCase):
    def _policy(self, base: Path):
        root = base / "staging"
        project = base / "project"
        root.mkdir()
        project.mkdir()
        return root, build_storage_deletion_policy(
            name="test-telegram-storage",
            roots=(root,),
            project_dir=project,
        )

    def test_empty_deletion_result_is_debug_only(self) -> None:
        with TemporaryDirectory() as temporary:
            root, policy = self._policy(Path(temporary))
            with self.assertLogs(_LOGGER, level=logging.DEBUG) as captured:
                result = delete_paths((root / "missing.bin",), policy=policy)

        self.assertTrue(result.complete)
        self.assertEqual(len(result.planned), 0)
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelno, logging.DEBUG)
        self.assertIn("planned=0 deleted=0 issues=0", captured.records[0].getMessage())

    def test_non_empty_deletion_result_remains_info(self) -> None:
        with TemporaryDirectory() as temporary:
            root, policy = self._policy(Path(temporary))
            candidate = root / "candidate.bin"
            candidate.write_bytes(b"payload")
            with self.assertLogs(_LOGGER, level=logging.INFO) as captured:
                result = delete_paths((candidate,), policy=policy, dry_run=True)

        self.assertEqual(len(result.planned), 1)
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelno, logging.INFO)
        self.assertIn("planned=1", captured.records[0].getMessage())


class _BackupRepository:
    def __init__(self, items: list[SimpleNamespace]) -> None:
        self.items = items

    async def list_backup_backfill(self, _backup_dir: Path):
        return self.items


class TelegramStorageBackupIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_permission_error_is_scoped_and_next_backup_is_processed(self) -> None:
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            backup_dir = base / "backups"
            staging_dir = base / "staging"
            backup_dir.mkdir()
            blocked = backup_dir / "blocked.dump"
            next_file = backup_dir / "next.dump"
            blocked.write_bytes(b"blocked")
            next_file.write_bytes(b"next")
            items = [
                SimpleNamespace(
                    run_id=1,
                    file_name=blocked.name,
                    path=blocked,
                    sha256=None,
                    backup_kind="database",
                    schema_version="1",
                    validation={},
                ),
                SimpleNamespace(
                    run_id=2,
                    file_name=next_file.name,
                    path=next_file,
                    sha256=None,
                    backup_kind="database",
                    schema_version="1",
                    validation={},
                ),
            ]
            service = object.__new__(TelegramStorageMigrationService)
            service.settings = SimpleNamespace(
                backup_dir=backup_dir,
                staging_dir=staging_dir,
                encryption_key_id="test-key",
                encryption_keyring={},
            )
            service.repository = _BackupRepository(items)
            service.uploader = None
            summary = MigrationSummary(run_id=10, migration_kind="test")

            def fail_digest(path: Path) -> str:
                if Path(path) == blocked:
                    raise PermissionError(13, "Permission denied", str(path))
                raise RuntimeError("next backup reached")

            with (
                patch(
                    "velvet_bot.domains.telegram_storage.service.sha256_file",
                    side_effect=fail_digest,
                ) as digest,
                patch(
                    "velvet_bot.domains.telegram_storage.service.remove_paths",
                    return_value=(0, 0),
                ),
            ):
                await service._migrate_backups(summary)

        self.assertEqual(digest.call_count, 2)
        self.assertEqual(summary.discovered_files, 2)
        self.assertEqual(summary.failed_files, 2)
        self.assertTrue(any("Permission denied" in item for item in summary.errors))
        self.assertTrue(any("next backup reached" in item for item in summary.errors))


if __name__ == "__main__":
    unittest.main()
