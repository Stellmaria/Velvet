from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.telegram_storage import TelegramStorageRepository
from velvet_bot.domains.telegram_storage.backup_repository import decode_json_object
from velvet_bot.domains.telegram_storage.service import (
    TelegramStorageRepository as ServiceTelegramStorageRepository,
)


class _Acquire:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class TelegramStorageBackupValidationTests(unittest.IsolatedAsyncioTestCase):
    def test_decoder_accepts_asyncpg_jsonb_runtime_shapes(self) -> None:
        expected = {"verified": True, "tables": 42}

        self.assertEqual(expected, decode_json_object(expected))
        self.assertEqual(
            expected,
            decode_json_object('{"verified":true,"tables":42}'),
        )
        self.assertEqual(
            expected,
            decode_json_object(b'{"verified":true,"tables":42}'),
        )
        self.assertEqual({}, decode_json_object(None))
        self.assertEqual({}, decode_json_object(""))
        self.assertEqual({}, decode_json_object("[]"))
        self.assertEqual({}, decode_json_object("{broken"))

    def test_storage_service_uses_compatible_repository(self) -> None:
        self.assertIs(
            TelegramStorageRepository,
            ServiceTelegramStorageRepository,
        )

    async def test_backfill_decodes_jsonb_string_and_keeps_scan_running(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dump = root / "daily.dump"
            dump.write_bytes(b"backup")
            connection = SimpleNamespace(
                fetch=AsyncMock(
                    return_value=[
                        {
                            "id": 17,
                            "backup_kind": "daily",
                            "file_path": str(dump),
                            "file_name": dump.name,
                            "sha256": "a" * 64,
                            "schema_version": "z003",
                            "validation": (
                                '{"verified":true,"table_count":42}'
                            ),
                        }
                    ]
                )
            )
            database = SimpleNamespace(acquire=lambda: _Acquire(connection))
            repository = TelegramStorageRepository(database)

            items = await repository.list_backup_backfill(root)

        self.assertEqual(1, len(items))
        self.assertEqual(17, items[0].run_id)
        self.assertEqual(
            {"verified": True, "table_count": 42},
            items[0].validation,
        )


if __name__ == "__main__":
    unittest.main()
