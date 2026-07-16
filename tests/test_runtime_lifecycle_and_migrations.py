from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.app.bootstrap import _close_application_resources
from velvet_bot.database import Database, _migration_checksum, _validate_migration_catalog


class DatabaseInitializationLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_migration_closes_new_pool(self) -> None:
        pool = SimpleNamespace(close=AsyncMock())
        database = Database("postgresql://unused")
        database._apply_migrations = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("migration failed")
        )

        with patch(
            "velvet_bot.database.asyncpg.create_pool",
            new=AsyncMock(return_value=pool),
        ):
            with self.assertRaisesRegex(RuntimeError, "migration failed"):
                await database.initialize()

        pool.close.assert_awaited_once()
        self.assertIsNone(database._pool)


class ApplicationCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_continues_after_worker_and_audit_failures(self) -> None:
        worker_manager = SimpleNamespace(
            stop_all=AsyncMock(side_effect=RuntimeError("worker stop failed"))
        )
        audit_logger = SimpleNamespace(
            send=AsyncMock(side_effect=RuntimeError("audit failed"))
        )
        session = SimpleNamespace(close=AsyncMock())
        bot = SimpleNamespace(session=session)
        database = SimpleNamespace(close=AsyncMock())

        await _close_application_resources(
            worker_manager=worker_manager,
            audit_logger=audit_logger,
            bot=bot,
            database=database,  # type: ignore[arg-type]
        )

        worker_manager.stop_all.assert_awaited_once()
        audit_logger.send.assert_awaited_once()
        session.close.assert_awaited_once()
        database.close.assert_awaited_once()

    async def test_cleanup_accepts_partially_constructed_application(self) -> None:
        database = SimpleNamespace(close=AsyncMock())

        await _close_application_resources(
            worker_manager=None,
            audit_logger=None,
            bot=None,
            database=database,  # type: ignore[arg-type]
        )

        database.close.assert_awaited_once()


class MigrationCatalogTests(unittest.TestCase):
    def test_legacy_003_pair_remains_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = [
                root / "003_character_references.sql",
                root / "003_public_archive.sql",
            ]
            for path in files:
                path.write_text("SELECT 1;\n", encoding="utf-8")

            _validate_migration_catalog(files)

    def test_new_duplicate_migration_number_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = [root / "026_alpha.sql", root / "026_beta.sql"]
            for path in files:
                path.write_text("SELECT 1;\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "Номер миграции 026"):
                _validate_migration_catalog(files)

    def test_checksum_changes_when_applied_sql_is_edited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "026_example.sql"
            path.write_text("SELECT 1;\n", encoding="utf-8")
            before = _migration_checksum(path)
            path.write_text("SELECT 2;\n", encoding="utf-8")
            after = _migration_checksum(path)

        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
