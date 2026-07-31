from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import asyncpg


CRITICAL_TABLES = (
    "schema_migrations",
    "characters",
    "media_files",
    "media_ai_profiles",
    "ai_runtime_state",
    "ai_usage_events",
    "ai_tasks",
    "ai_task_batches",
    "roleplay_sessions",
)


async def inspect_database(database_url: str) -> dict[str, object]:
    connection = await asyncpg.connect(database_url, timeout=15)
    try:
        database_name = await connection.fetchval("SELECT current_database()")
        migration_count = int(
            await connection.fetchval("SELECT COUNT(*) FROM schema_migrations") or 0
        )
        rows = await connection.fetch(
            """
            SELECT expected.name,
                   to_regclass('public.' || expected.name) IS NOT NULL AS present
            FROM unnest($1::TEXT[]) AS expected(name)
            ORDER BY expected.name
            """,
            list(CRITICAL_TABLES),
        )
        missing_tables = tuple(
            str(row["name"]) for row in rows if not bool(row["present"])
        )
        runtime = await connection.fetchrow(
            """
            SELECT paused,pause_reason
            FROM ai_runtime_state
            WHERE singleton_id=1
            """
        )
        active_tasks = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM ai_tasks WHERE status IN ('queued','running')"
            )
            or 0
        )
        async with connection.transaction():
            await connection.execute(
                "CREATE TEMP TABLE velvet_server_smoke(value INTEGER) ON COMMIT DROP"
            )
            await connection.execute(
                "INSERT INTO velvet_server_smoke(value) VALUES(1)"
            )
            writable = (
                int(
                    await connection.fetchval(
                        "SELECT COUNT(*) FROM velvet_server_smoke"
                    )
                    or 0
                )
                == 1
            )
        return {
            "database": str(database_name),
            "migration_count": migration_count,
            "missing_tables": missing_tables,
            "ai_paused": bool(runtime["paused"]) if runtime is not None else None,
            "pause_reason_present": bool(runtime and runtime["pause_reason"]),
            "active_ai_tasks": active_tasks,
            "writable": writable,
        }
    finally:
        await connection.close()


def check_backup_directory(path: Path) -> None:
    if not path.is_dir():
        raise RuntimeError(f"Backup directory does not exist: {path}")
    with tempfile.NamedTemporaryFile(
        prefix=".velvet-smoke-",
        dir=path,
        delete=True,
    ) as handle:
        handle.write(b"ok")
        handle.flush()


def telegram_get_me(token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/getMe",
        headers={"User-Agent": "VelvetServerSmoke/1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError("Telegram getMe smoke failed.") from error
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError("Telegram getMe returned an unsuccessful response.")
    result = payload.get("result")
    if not isinstance(result, dict) or not result.get("id"):
        raise RuntimeError("Telegram getMe returned no bot identity.")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Velvet post-deploy smoke checks.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--backup-dir", default=os.getenv("BACKUP_DIR", "/app/backups"))
    parser.add_argument("--bot-token", default=os.getenv("BOT_TOKEN", ""))
    parser.add_argument("--skip-telegram", action="store_true")
    return parser


async def async_main(args: argparse.Namespace) -> int:
    if not args.database_url:
        raise RuntimeError("DATABASE_URL is required for server smoke.")
    database = await inspect_database(args.database_url)
    if int(database["migration_count"]) < 1:
        raise RuntimeError("schema_migrations is empty after deployment.")
    missing = tuple(database["missing_tables"])
    if missing:
        raise RuntimeError("Missing critical tables: " + ", ".join(missing))
    if not database["writable"]:
        raise RuntimeError("PostgreSQL smoke transaction was not writable.")

    check_backup_directory(Path(args.backup_dir))
    bot_name = "skipped"
    if not args.skip_telegram:
        if not args.bot_token:
            raise RuntimeError("BOT_TOKEN is required unless --skip-telegram is set.")
        identity = await asyncio.to_thread(telegram_get_me, args.bot_token)
        bot_name = str(identity.get("username") or identity.get("id"))

    print(
        "Server smoke OK: "
        f"database={database['database']} "
        f"migrations={database['migration_count']} "
        f"active_ai_tasks={database['active_ai_tasks']} "
        f"ai_paused={database['ai_paused']} "
        f"telegram={bot_name}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(async_main(args))
    except (RuntimeError, OSError, asyncpg.PostgresError) as error:
        print(f"Server smoke failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
