from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.public_archive.visibility import public_media_visibility_sql


async def get_character_media_offset(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    public_only: bool = False,
) -> int | None:
    """Return the newest-first offset of one visible character-media link."""
    visibility_filter = (
        f"AND ({public_media_visibility_sql()})"
        if public_only
        else ""
    )
    async with database.acquire() as connection:
        value = await connection.fetchval(
            f"""
            WITH ordered_media AS (
                SELECT
                    cm.media_id,
                    ROW_NUMBER() OVER (
                        ORDER BY cm.created_at DESC, cm.media_id DESC
                    ) - 1 AS media_offset
                FROM character_media AS cm
                JOIN media_files AS mf ON mf.id = cm.media_id
                WHERE cm.character_id = $1
                  {visibility_filter}
            )
            SELECT media_offset
            FROM ordered_media
            WHERE media_id = $2
            """,
            character_id,
            media_id,
        )
    return int(value) if value is not None else None
