from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.domains.telegram_storage.models import MigrationSummary
from velvet_bot.domains.telegram_storage.service import TelegramStorageMigrationService


class TelegramStorageBackupPermissionIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_unreadable_backup_does_not_abort_remaining_items(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unreadable = root / "unreadable.dump"
            readable = root / "readable.dump"
            unreadable.write_bytes(b"blocked")
            readable.write_bytes(b"available")

            items = [
                SimpleNamespace(
                    run_id=1,
                    backup_kind="pre_migration",
                    path=unreadable,
                    file_name=unreadable.name,
                    sha256=None,
                    schema_version="z032",
                    validation={},
                ),
                SimpleNamespace(
                    run_id=2,
                    backup_kind="daily",
                    path=readable,
                    file_name=readable.name,
                    sha256=None,
                    schema_version="z032",
                    validation={},
                ),
            ]
            repository = SimpleNamespace(
                list_backup_backfill=AsyncMock(return_value=items),
                get_existing=AsyncMock(return_value=None),
                mark_backup_offloaded=AsyncMock(),
            )
            uploader = SimpleNamespace(
                upload=AsyncMock(
                    return_value=(SimpleNamespace(object_id=88), 0, 0, False)
                )
            )
            service = object.__new__(TelegramStorageMigrationService)
            service.settings = SimpleNamespace(
                backup_dir=root,
                staging_dir=root / "staging",
                encryption_key_id="test-key",
                encryption_keyring=object(),
            )
            service.repository = repository
            service.uploader = uploader
            summary = MigrationSummary(run_id=10, migration_kind="manual")

            def fake_sha256(path: Path) -> str:
                candidate = Path(path)
                if candidate == unreadable:
                    raise PermissionError(13, "Permission denied", str(candidate))
                return "a" * 64

            def fake_build_zip(destination: Path, *, files, text_entries) -> None:
                destination.write_bytes(b"zip")

            def fake_encrypt(source: Path, destination: Path, keyring) -> None:
                destination.write_bytes(b"encrypted")

            def fake_decrypt(source: Path, destination: Path, keyring) -> None:
                destination.write_bytes(b"zip")

            with patch(
                "velvet_bot.domains.telegram_storage.service.sha256_file",
                side_effect=fake_sha256,
            ), patch(
                "velvet_bot.domains.telegram_storage.service.build_zip",
                side_effect=fake_build_zip,
            ), patch(
                "velvet_bot.domains.telegram_storage.service.encrypt_file",
                side_effect=fake_encrypt,
            ), patch(
                "velvet_bot.domains.telegram_storage.service.decrypt_file",
                side_effect=fake_decrypt,
            ):
                await service._migrate_backups(summary)

            self.assertEqual(2, summary.discovered_files)
            self.assertEqual(1, summary.failed_files)
            self.assertEqual(1, summary.stored_files)
            self.assertEqual("partial", summary.status)
            self.assertIn("unreadable.dump", summary.errors[0])
            self.assertIn("Permission denied", summary.errors[0])
            uploader.upload.assert_awaited_once()
            repository.mark_backup_offloaded.assert_awaited_once_with(2, 88)


if __name__ == "__main__":
    unittest.main()
