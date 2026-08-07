from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.core.config.arthur import ArthurSettings
from velvet_bot.domains.telegram_storage import TelegramStorageMigrationService
from velvet_bot.domains.telegram_storage.models import MigrationSummary
from velvet_bot.domains.telegram_storage.repository import BackupBackfillItem


class StorageTopicIntegrityTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_backup_is_skipped_before_reencryption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "backup.dump"
            source.write_bytes(b"stable-backup")
            item = BackupBackfillItem(
                run_id=42,
                backup_kind="daily",
                path=source,
                file_name=source.name,
                sha256="a" * 64,
                schema_version="z999",
                validation={},
            )
            service = object.__new__(TelegramStorageMigrationService)
            service.settings = SimpleNamespace(
                backup_dir=root,
                staging_dir=root / "staging",
                delete_after_upload=False,
            )
            service.repository = SimpleNamespace(
                list_backup_backfill=AsyncMock(return_value=[item]),
                latest_object_id_by_logical_key=AsyncMock(return_value=3596),
                mark_backup_offloaded=AsyncMock(),
            )
            service.uploader = SimpleNamespace(upload=AsyncMock())
            summary = MigrationSummary(run_id=1, migration_kind="resume")

            await service._migrate_backups(summary)

            self.assertEqual(1, summary.discovered_files)
            self.assertEqual(1, summary.skipped_files)
            self.assertEqual(0, summary.stored_files)
            service.uploader.upload.assert_not_awaited()
            service.repository.latest_object_id_by_logical_key.assert_awaited_once()
            service.repository.mark_backup_offloaded.assert_awaited_once_with(42, 3596)

    async def test_unchanged_rework_snapshot_is_semantically_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = object.__new__(TelegramStorageMigrationService)
            service.settings = SimpleNamespace(staging_dir=root / "staging")
            service.repository = SimpleNamespace(
                rework_snapshot=AsyncMock(return_value=[{"id": 1, "status": "open"}]),
                latest_object_id_by_logical_key=AsyncMock(return_value=3597),
            )
            service._upload_candidate = AsyncMock()
            summary = MigrationSummary(run_id=1, migration_kind="resume")

            await service._snapshot_rework(summary)

            self.assertEqual(1, summary.discovered_files)
            self.assertEqual(1, summary.skipped_files)
            self.assertEqual(0, summary.stored_files)
            service._upload_candidate.assert_not_awaited()
            service.repository.latest_object_id_by_logical_key.assert_awaited_once()
            self.assertFalse((root / "staging" / "rework").exists())


class ArthurReportDestinationTests(unittest.TestCase):
    def _base_env(self) -> dict[str, str]:
        return {
            "ARTHUR_BOT_TOKEN": "123456:arthur-token-value",
            "BOT_TOKEN": "654321:velvet-token-value",
            "DATABASE_URL": "postgresql://velvet@postgres/velvet",
            "ARTHUR_ALLOWED_USER_IDS": "42",
            "ARTHUR_STORAGE_GATEWAY_API_KEY": "a" * 32,
            "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "false",
        }

    def test_blank_arthur_destination_defaults_to_canonical_reports_topic(self) -> None:
        with patch.dict(os.environ, self._base_env(), clear=True):
            settings = ArthurSettings.from_env()
        self.assertEqual(-1004459280894, settings.report_chat_id)
        self.assertEqual(2478, settings.report_thread_id)

    def test_explicit_arthur_destination_overrides_defaults(self) -> None:
        environment = {
            **self._base_env(),
            "ARTHUR_REPORT_CHAT_ID": "-1001234567890",
            "ARTHUR_REPORT_THREAD_ID": "99",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = ArthurSettings.from_env()
        self.assertEqual(-1001234567890, settings.report_chat_id)
        self.assertEqual(99, settings.report_thread_id)


if __name__ == "__main__":
    unittest.main()
