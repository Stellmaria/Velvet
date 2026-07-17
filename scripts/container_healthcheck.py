from __future__ import annotations

import asyncio
import os
import sys

import asyncpg


async def _check() -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    connection = await asyncpg.connect(database_url, timeout=5)
    try:
        value = await connection.fetchval("SELECT 1")
        if value != 1:
            raise RuntimeError("PostgreSQL health query returned an unexpected result")
        await connection.fetchval(
            "SELECT COUNT(*) FROM schema_migrations"
        )
    finally:
        await connection.close()


def main() -> int:
    try:
        asyncio.run(_check())
    except Exception as error:
        print(f"Velvet healthcheck failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print("Velvet healthcheck: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
