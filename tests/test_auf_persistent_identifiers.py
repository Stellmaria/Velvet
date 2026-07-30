from __future__ import annotations

import os
import unittest
from pathlib import Path

from velvet_bot.database import Database

ROOT = Path(__file__).resolve().parents[1]
OLD_TABLES = (
    "meow_runtime_settings",
    "workspace_meow_settings",
    "meow_economy_settings",
    "meow_wallets",
    "meow_wallet_entries",
    "meow_price_versions",
    "meow_task_charges",
    "meow_purchase_invoices",
    "meow_reconciliation_state",
)
NEW_TABLES = tuple(name.replace("meow", "auf", 1) for name in OLD_TABLES)


class AufPersistentIdentifierContractTests(unittest.TestCase):
    def test_canonical_sources_do_not_query_retired_tables(self) -> None:
        paths = (
            *sorted((ROOT / "velvet_bot/domains/auf_runtime").glob("*.py")),
            *sorted((ROOT / "velvet_bot/domains/auf_wallet").glob("*.py")),
            ROOT / "velvet_bot/app/auf_user_portal_install.py",
        )
        for path in paths:
            source = path.read_text(encoding="utf-8")
            for old_table in OLD_TABLES:
                self.assertNotIn(old_table, source, str(path))

    def test_module_catalog_uses_auf_key(self) -> None:
        source = (ROOT / "velvet_bot/domains/workspaces/product_models.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"auf"', source)
        self.assertNotIn('"meow"', source)

    def test_historical_migrations_are_immutable_and_z024_exists(self) -> None:
        for name in (
            "z020_meow_runtime_module.sql",
            "z021_meow_wallets.sql",
            "z022_meow_task_charging.sql",
            "z023_meow_purchase_invoices.sql",
        ):
            self.assertTrue((ROOT / "migrations" / name).is_file())
        migration = (
            ROOT / "migrations/z024_auf_persistent_identifiers.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("ALTER TABLE meow_wallets RENAME TO auf_wallets", migration)
        self.assertIn("settle_auf_task_charge", migration)
        self.assertIn("array_replace(allowed_modules, 'meow', 'auf')", migration)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLAufPersistentIdentifierTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_only_canonical_tables_and_module_rows_remain(self) -> None:
        async with self.database.acquire() as connection:
            for table in NEW_TABLES:
                self.assertIsNotNone(await connection.fetchval(
                    "SELECT to_regclass($1::TEXT)", table
                ))
            for table in OLD_TABLES:
                self.assertIsNone(await connection.fetchval(
                    "SELECT to_regclass($1::TEXT)", table
                ))
            self.assertEqual(
                0,
                await connection.fetchval(
                    "SELECT COUNT(*) FROM workspace_modules WHERE module_key = 'meow'"
                ),
            )
            self.assertGreater(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM workspace_modules WHERE module_key = 'auf'"
                ),
                0,
            )


if __name__ == "__main__":
    unittest.main()
