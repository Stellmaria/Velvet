from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.database import Database
from velvet_bot.domains.media_quality import MediaQualityRepository
from velvet_bot.domains.references import ReferenceMediaPayload, ReferenceRepository


ROOT = Path(__file__).resolve().parents[1]


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        self.exited = True
        return False


class DatabaseAcquireBoundaryTests(unittest.TestCase):
    def test_acquire_delegates_to_initialized_pool(self) -> None:
        database = Database("postgresql://unused")
        pool = Mock()
        context = object()
        pool.acquire.return_value = context
        database._pool = pool

        self.assertIs(database.acquire(), context)
        pool.acquire.assert_called_once_with()

    def test_acquire_rejects_uninitialized_database(self) -> None:
        database = Database("postgresql://unused")

        with self.assertRaisesRegex(RuntimeError, "ещё не инициализировано"):
            database.acquire()

    def test_migrated_domain_repositories_use_public_boundary(self) -> None:
        paths = (
            ROOT / "velvet_bot/domains/characters/repository.py",
            ROOT / "velvet_bot/domains/stories/repository.py",
            ROOT / "velvet_bot/domains/archive/repository.py",
            ROOT / "velvet_bot/domains/public_archive/repository.py",
            ROOT / "velvet_bot/domains/references/repository.py",
            ROOT / "velvet_bot/domains/media_quality/repository.py",
        )
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("._require_pool()", source)
                self.assertIn("self._database.acquire()", source)


class ReferenceRepositoryAcquireTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_uses_public_acquire_and_preserves_transaction(self) -> None:
        created_at = datetime(2026, 7, 17, tzinfo=UTC)
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                return_value={
                    "reference_id": 13,
                    "character_id": 7,
                    "telegram_file_id": "file-new",
                    "telegram_file_unique_id": "unique-7",
                    "added_by": 11,
                    "reference_created_at": created_at,
                }
            ),
            fetchval=AsyncMock(return_value=1),
            transaction=Mock(),
        )
        transaction_context = _AsyncContext(None)
        connection.transaction.return_value = transaction_context
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = ReferenceRepository(database)

        result = await repository.add(
            character_id=7,
            media=ReferenceMediaPayload("file-new", "unique-7"),
            added_by=11,
        )

        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertTrue(transaction_context.entered)
        self.assertTrue(transaction_context.exited)
        self.assertTrue(result.created)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.reference.id, 13)
        self.assertEqual(result.reference.telegram_file_id, "file-new")
        self.assertEqual(result.reference.created_at, created_at)


class MediaQualityRepositoryAcquireTests(unittest.IsolatedAsyncioTestCase):
    async def test_claim_uses_public_acquire_and_keeps_locked_transaction(self) -> None:
        rows = [
            {
                "id": 17,
                "scan_file_id": "preview-17",
                "display_name": "image-17.png",
            },
            {
                "id": 19,
                "scan_file_id": "file-19",
                "display_name": "image-19.jpg",
            },
        ]
        connection = SimpleNamespace(
            fetch=AsyncMock(return_value=rows),
            execute=AsyncMock(return_value="UPDATE 2"),
            transaction=Mock(),
        )
        transaction_context = _AsyncContext(None)
        connection.transaction.return_value = transaction_context
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = MediaQualityRepository(database)

        targets = await repository.claim_pending_images(limit=99)

        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertTrue(transaction_context.entered)
        self.assertTrue(transaction_context.exited)
        select_sql = connection.fetch.await_args.args[0]
        self.assertIn("FOR UPDATE SKIP LOCKED", select_sql)
        self.assertEqual(connection.fetch.await_args.args[1], 5)
        connection.execute.assert_awaited_once()
        self.assertEqual(connection.execute.await_args.args[1], [17, 19])
        self.assertEqual([target.media_id for target in targets], [17, 19])
        self.assertEqual(targets[0].telegram_file_id, "preview-17")
        self.assertEqual(targets[1].display_name, "image-19.jpg")


if __name__ == "__main__":
    unittest.main()
