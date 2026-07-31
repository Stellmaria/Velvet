from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from scripts.server_smoke import CRITICAL_TABLES
from velvet_bot.core.config.kie import load_kie_settings
from velvet_bot.database import Database, _migration_checksum


ROOT = Path(__file__).resolve().parents[1]


class ServerArtifactContractTests(unittest.TestCase):
    def test_dockerignore_excludes_runtime_server_data(self) -> None:
        ignored = set(
            (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        )
        self.assertTrue(
            {
                "data/postgres",
                "data/postgres.*",
                "data/backups",
                "data/logs",
                "data/runtime",
                "data/hermes",
                "server-data",
            }.issubset(ignored)
        )

    def test_server_example_uses_postgres_17_and_numeric_disabled_rate(self) -> None:
        example = (ROOT / ".env.server.example").read_text(encoding="utf-8")
        self.assertIn("POSTGRES_IMAGE=postgres:17-alpine", example)
        self.assertIn("KIE_USD_TO_RUB=0", example)

    def test_server_smoke_uses_canonical_roleplay_table(self) -> None:
        self.assertIn("roleplay_sessions", CRITICAL_TABLES)
        self.assertNotIn("rp_sessions", CRITICAL_TABLES)


class KieDisabledConfigurationTests(unittest.TestCase):
    def test_disabled_provider_accepts_blank_numeric_environment_values(self) -> None:
        values = {
            "KIE_ENABLED": "false",
            "KIE_USD_TO_RUB": "",
            "KIE_CREDIT_USD": "",
            "KIE_CREDIT_BYN": "",
            "KIE_SEEDREAM_BASIC_USD": "",
            "GRS_NANO_BANANA_2_USD": "",
        }
        with patch.dict(os.environ, values, clear=True), patch(
            "velvet_bot.core.config.kie.load_dotenv"
        ):
            settings = load_kie_settings()

        self.assertFalse(settings.enabled)
        self.assertEqual(Decimal("0"), settings.usd_to_rub)
        self.assertEqual(Decimal("0.005"), settings.credit_usd)
        self.assertEqual(Decimal("0.019"), settings.credit_byn)

    def test_enabled_provider_still_requires_positive_budget_rate(self) -> None:
        values = {
            "KIE_ENABLED": "true",
            "KIE_API_KEY": "kie-secret",
            "GRS_API_KEY": "grs-secret",
            "KIE_USD_TO_RUB": "",
        }
        with patch.dict(os.environ, values, clear=True), patch(
            "velvet_bot.core.config.kie.load_dotenv"
        ):
            with self.assertRaisesRegex(RuntimeError, "больше нуля"):
                load_kie_settings()


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _FakeMigrationConnection:
    def __init__(self, stored_checksum: str | None) -> None:
        self.stored_checksum = stored_checksum
        self.executed_migration_sql: list[str] = []

    async def fetchrow(self, query: str, *args):
        if "SELECT checksum FROM schema_migrations" in query:
            return {"checksum": self.stored_checksum}
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def execute(self, query: str, *args):
        compact = " ".join(query.split())
        if compact.startswith("UPDATE schema_migrations SET checksum"):
            self.stored_checksum = str(args[1])
        elif query.lstrip().upper().startswith(("CREATE TABLE", "ALTER TABLE")):
            pass
        elif compact.startswith("INSERT INTO schema_migrations"):
            self.stored_checksum = str(args[1])
        else:
            self.executed_migration_sql.append(query)
        return "OK"

    def transaction(self):
        return _AsyncContext(None)


class _FakeMigrationPool:
    def __init__(self, connection: _FakeMigrationConnection) -> None:
        self.connection = connection

    def acquire(self):
        return _AsyncContext(self.connection)


class MigrationChecksumPortabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_crlf_hash_is_accepted_and_rewritten_to_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migration = root / "001_example.sql"
            migration.write_bytes(b"SELECT 1;\n")
            legacy_crlf = hashlib.sha256(b"SELECT 1;\r\n").hexdigest()
            connection = _FakeMigrationConnection(legacy_crlf)
            database = Database("postgresql://unused", migrations_path=root)
            database._pool = _FakeMigrationPool(connection)  # type: ignore[assignment]

            await database._apply_migrations()

            self.assertEqual(_migration_checksum(migration), connection.stored_checksum)
            self.assertEqual([], connection.executed_migration_sql)

    async def test_real_sql_change_is_still_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migration = root / "001_example.sql"
            migration.write_bytes(b"SELECT 2;\n")
            old_checksum = hashlib.sha256(b"SELECT 1;\n").hexdigest()
            connection = _FakeMigrationConnection(old_checksum)
            database = Database("postgresql://unused", migrations_path=root)
            database._pool = _FakeMigrationPool(connection)  # type: ignore[assignment]

            with self.assertRaisesRegex(RuntimeError, "была изменена"):
                await database._apply_migrations()


if __name__ == "__main__":
    unittest.main()
