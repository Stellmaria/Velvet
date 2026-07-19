from __future__ import annotations

import asyncpg

from velvet_bot.database import (
    Character,
    Database,
    clean_character_name,
    normalize_character_name,
)


async def rename_character(
    database: Database,
    *,
    character_id: int,
    new_name: str,
) -> Character:
    display_name = clean_character_name(new_name)
    normalized_name = normalize_character_name(display_name)
    try:
        async with database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE characters
                SET name = $2::VARCHAR,
                    normalized_name = $3::VARCHAR
                WHERE id = $1::BIGINT
                RETURNING
                    id,
                    name,
                    created_by,
                    created_in_chat,
                    created_at,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url
                """,
                int(character_id),
                display_name,
                normalized_name,
            )
    except asyncpg.UniqueViolationError as error:
        raise ValueError("Персонаж с таким именем уже существует.") from error
    if row is None:
        raise ValueError("Персонаж больше не найден.")
    return Character(
        id=int(row["id"]),
        name=str(row["name"]),
        created_by=row["created_by"],
        created_in_chat=row["created_in_chat"],
        created_at=row["created_at"],
        archive_chat_id=row["archive_chat_id"],
        archive_thread_id=row["archive_thread_id"],
        archive_topic_url=row["archive_topic_url"],
    )


__all__ = ("rename_character",)
