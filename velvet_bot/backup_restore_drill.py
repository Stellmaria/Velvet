from __future__ import annotations

import asyncio
import os
import re
import secrets
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import asyncpg

from velvet_bot.database import Database

_DATABASE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


@dataclass(frozen=True, slots=True)
class RestoreSnapshot:
    migration_count: int
    character_count: int
    table_count: int


def database_name_from_dsn(dsn: str) -> str:
    parsed = urlsplit(dsn)
    name = unquote(parsed.path.lstrip("/"))
    if not name:
        raise ValueError("В PostgreSQL URL не указано имя базы данных.")
    return name


def replace_database_name(dsn: str, database_name: str) -> str:
    validate_database_name(database_name)
    parsed = urlsplit(dsn)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            "/" + quote(database_name, safe=""),
            parsed.query,
            parsed.fragment,
        )
    )


def validate_database_name(value: str) -> str:
    if not _DATABASE_NAME_RE.fullmatch(value):
        raise ValueError(
            "Имя временной базы должно начинаться с буквы или подчёркивания "
            "и содержать только латинские буквы, цифры и подчёркивания."
        )
    return value


def _run_command(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode == 0:
        return
    diagnostic = (completed.stderr or completed.stdout or "unknown error").strip()
    raise RuntimeError(
        f"Команда {Path(command[0]).name} завершилась с кодом "
        f"{completed.returncode}: {diagnostic[-2000:]}"
    )


async def _snapshot(database_url: str) -> RestoreSnapshot:
    connection = await asyncpg.connect(database_url, timeout=15)
    try:
        migration_count = await connection.fetchval(
            "SELECT COUNT(*) FROM schema_migrations"
        )
        character_count = await connection.fetchval("SELECT COUNT(*) FROM characters")
        table_count = await connection.fetchval(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            """
        )
    finally:
        await connection.close()
    return RestoreSnapshot(
        migration_count=int(migration_count or 0),
        character_count=int(character_count or 0),
        table_count=int(table_count or 0),
    )


async def _create_database(admin_url: str, database_name: str) -> None:
    validate_database_name(database_name)
    connection = await asyncpg.connect(admin_url, timeout=15)
    try:
        await connection.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await connection.close()


async def _drop_database(admin_url: str, database_name: str) -> None:
    validate_database_name(database_name)
    connection = await asyncpg.connect(admin_url, timeout=15)
    try:
        await connection.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1
              AND pid <> pg_backend_pid()
            """,
            database_name,
        )
        await connection.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
    finally:
        await connection.close()


async def run_restore_drill(
    source_url: str,
    *,
    pg_dump_path: str = "pg_dump",
    pg_restore_path: str = "pg_restore",
    target_database: str | None = None,
    keep_database: bool = False,
) -> RestoreSnapshot:
    source_url = source_url.strip()
    if not source_url:
        raise ValueError("Не указан URL исходной PostgreSQL-базы.")

    source_database = database_name_from_dsn(source_url)
    target_database = validate_database_name(
        target_database
        or f"velvet_restore_{os.getpid()}_{secrets.token_hex(4)}"
    )
    if target_database == source_database:
        raise ValueError("Временная база восстановления не может совпадать с исходной.")

    admin_url = replace_database_name(source_url, "postgres")
    target_url = replace_database_name(source_url, target_database)
    sentinel_name = f"Restore Drill {secrets.token_hex(8)}"

    source_database_client = Database(source_url)
    await source_database_client.initialize()
    try:
        await source_database_client.create_character(
            sentinel_name,
            created_by=None,
            created_in_chat=None,
        )
    finally:
        await source_database_client.close()

    source_snapshot = await _snapshot(source_url)
    created = False
    try:
        await _create_database(admin_url, target_database)
        created = True
        with tempfile.TemporaryDirectory(prefix="velvet-restore-") as temporary_dir:
            dump_path = Path(temporary_dir) / "velvet.dump"
            _run_command(
                [
                    pg_dump_path,
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--file",
                    str(dump_path),
                    source_url,
                ]
            )
            if not dump_path.is_file() or dump_path.stat().st_size <= 0:
                raise RuntimeError("pg_dump не создал непустой архив.")
            _run_command(
                [
                    pg_restore_path,
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    "--dbname",
                    target_url,
                    str(dump_path),
                ]
            )

        restored_database = Database(target_url)
        await restored_database.initialize()
        try:
            restored_character = await restored_database.get_character(sentinel_name)
            if restored_character is None:
                raise RuntimeError(
                    "Контрольная запись отсутствует после восстановления backup."
                )
        finally:
            await restored_database.close()

        restored_snapshot = await _snapshot(target_url)
        if restored_snapshot != source_snapshot:
            raise RuntimeError(
                "Снимок восстановленной базы не совпадает с исходной: "
                f"source={source_snapshot}, restored={restored_snapshot}."
            )
        return restored_snapshot
    finally:
        if created and not keep_database:
            await _drop_database(admin_url, target_database)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Создать PostgreSQL dump Velvet и проверить реальное восстановление."
    )
    parser.add_argument(
        "--source-dsn",
        default=os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or "",
    )
    parser.add_argument(
        "--target-database",
        default=None,
        help="Необязательное имя временной базы. По умолчанию генерируется безопасно.",
    )
    parser.add_argument(
        "--pg-dump",
        default=os.getenv("PG_DUMP_PATH", "pg_dump"),
    )
    parser.add_argument(
        "--pg-restore",
        default=os.getenv("PG_RESTORE_PATH", "pg_restore"),
    )
    parser.add_argument("--keep-database", action="store_true")
    arguments = parser.parse_args()

    snapshot = asyncio.run(
        run_restore_drill(
            arguments.source_dsn,
            pg_dump_path=arguments.pg_dump,
            pg_restore_path=arguments.pg_restore,
            target_database=arguments.target_database,
            keep_database=arguments.keep_database,
        )
    )
    print(
        "Restore drill completed: "
        f"migrations={snapshot.migration_count}, "
        f"characters={snapshot.character_count}, tables={snapshot.table_count}"
    )
    return 0


__all__ = (
    "RestoreSnapshot",
    "database_name_from_dsn",
    "main",
    "replace_database_name",
    "run_restore_drill",
    "validate_database_name",
)
