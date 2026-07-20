from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.domains.telegram_storage.repository import TelegramStorageRepository


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


class TelegramStorageValidationJsonTests(unittest.IsolatedAsyncioTestCase):
    async def test_backup_backfill_decodes_jsonb_string(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            dump_path = Path(temporary_directory) / "velvet.dump"
            dump_path.write_bytes(b"backup")
            connection = SimpleNamespace(
                fetch=AsyncMock(
                    return_value=[
                        {
                            "id": 41,
                            "backup_kind": "pre_migration",
                            "file_path": str(dump_path),
                            "file_name": dump_path.name,
                            "sha256": "a" * 64,
                            "schema_version": "023_discussion_insights_and_backups.sql",
                            "validation": '{"valid": true, "readable": true}',
                        }
                    ]
                )
            )
            database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))
            repository = TelegramStorageRepository(database)

            items = await repository.list_backup_backfill(
                Path(temporary_directory) / "untracked"
            )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].validation, {"valid": True, "readable": True})

    async def test_backup_backfill_uses_empty_object_for_invalid_json(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            dump_path = Path(temporary_directory) / "velvet.dump"
            dump_path.write_bytes(b"backup")
            connection = SimpleNamespace(
                fetch=AsyncMock(
                    return_value=[
                        {
                            "id": 42,
                            "backup_kind": "manual",
                            "file_path": str(dump_path),
                            "file_name": dump_path.name,
                            "sha256": None,
                            "schema_version": None,
                            "validation": "not-json",
                        }
                    ]
                )
            )
            database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))
            repository = TelegramStorageRepository(database)

            items = await repository.list_backup_backfill(
                Path(temporary_directory) / "untracked"
            )

        self.assertEqual(items[0].validation, {})


if __name__ == "__main__":
    unittest.main()
