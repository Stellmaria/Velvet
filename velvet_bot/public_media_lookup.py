from __future__ import annotations

from velvet_bot.database import Database


async def get_character_media_offset(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    public_only: bool = False,
) -> int | None:
    """Return the newest-first offset of one visible character-media link."""
    async with database.acquire() as connection:
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
                  AND ($3::BOOLEAN = FALSE OR is_public = TRUE)
            )
            SELECT media_offset
            FROM ordered_media
            WHERE media_id = $2
            """,
            character_id,
            media_id,
            bool(public_only),
        )
    return int(value) if value is not None else None
