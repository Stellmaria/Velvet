from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.public_archive.visibility import public_media_visibility_sql
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


async def get_character_media_offset(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    public_only: bool = False,
    include_restricted: bool = False,
) -> int | None:
    """Return the newest-first offset of one visible character-media link."""
    visibility_filter = (
        "AND ("
        + public_media_visibility_sql(
            link_alias="character_media",
            file_alias="mf",
            include_adult_restricted=include_restricted,
            include_oversized_images=include_restricted,
        )
        + ")"
        if public_only
        else ""
    )
    async with database.acquire() as connection:
        value = await connection.fetchval(
            f"""
            WITH ordered_media AS (
                SELECT
                    character_media.media_id,
                    ROW_NUMBER() OVER (
                        ORDER BY character_media.created_at DESC,
                                 character_media.media_id DESC
                    ) - 1 AS media_offset
                FROM character_media
                JOIN characters AS character
                  ON character.id = character_media.character_id
                JOIN media_files AS mf ON mf.id = character_media.media_id
                WHERE character.workspace_id = $1::BIGINT
                  AND character_media.character_id = $2::BIGINT
                  {visibility_filter}
            )
            SELECT media_offset
            FROM ordered_media
            WHERE media_id = $3::BIGINT
            """,
            int(workspace_id),
            int(character_id),
            int(media_id),
        )
    return int(value) if value is not None else None
