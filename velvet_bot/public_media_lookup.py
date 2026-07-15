from __future__ import annotations

from velvet_bot.database import Database


async def get_character_media_offset(
    database: Database,
    *,
    character_id: int,
    media_id: int,
) -> int | None:
    """Return the current newest-first offset of one character-media link."""
    async with database._require_pool().acquire() as connection:
        value = await connection.fetchval(
            """
            WITH ordered_media AS (
                SELECT
                    media_id,
                    ROW_NUMBER() OVER (
                        ORDER BY created_at DESC, media_id DESC
                    ) - 1 AS media_offset
                FROM character_media
                WHERE character_id = $1
            )
            SELECT media_offset
            FROM ordered_media
            WHERE media_id = $2
            """,
            character_id,
            media_id,
        )
    return int(value) if value is not None else None
