from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.database import Database


@dataclass(frozen=True, slots=True)
class BackupKeyReference:
    object_id: int
    encryption_version: str | None
    encryption_key_id: str | None


class TelegramStorageKeyRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_backup_key_references(
        self,
        *,
        limit: int = 500,
    ) -> tuple[BackupKeyReference, ...]:
        safe_limit = max(1, min(int(limit), 5000))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT id, encryption_version,
                       manifest ->> 'encryption_key_id' AS encryption_key_id
                FROM telegram_storage_objects
                WHERE storage_kind = 'backups'
                  AND encrypted = TRUE
                ORDER BY id DESC
                LIMIT $1::INTEGER
                """,
                safe_limit,
            )
        return tuple(
            BackupKeyReference(
                object_id=int(row["id"]),
                encryption_version=(
                    str(row["encryption_version"])
                    if row["encryption_version"] is not None
                    else None
                ),
                encryption_key_id=(
                    str(row["encryption_key_id"])
                    if row["encryption_key_id"] is not None
                    else None
                ),
            )
            for row in rows
        )


__all__ = ("BackupKeyReference", "TelegramStorageKeyRepository")
