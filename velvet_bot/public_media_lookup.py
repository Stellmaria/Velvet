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
    include_oversized: bool | None = None,
) -> int | None:
    """Return the newest-first offset of one visible character-media link."""
    visibility_filter = (
        "AND ("
        + public_media_visibility_sql(
            link_alias="character_media",
            file_alias="mf",
            include_adult_restricted=include_restricted,
            include_oversized_images=(
                include_restricted
                if include_oversized is None
                else bool(include_oversized)
            ),
        )
        + ")"
        if public_only
        else ""
    )
    safe_workspace_id = int(workspace_id)
    async with database.acquire() as connection:
        value = await connection.fetchval(
            f"""
            WITH ordered_media AS (
                SELECT
                    character_media.media_id,
                    ROW_NUMBER() OVER (
                        ORDER BY created_at DESC, media_id DESC
                    ) - 1 AS media_offset
                FROM character_media
                JOIN media_files AS mf ON mf.id = character_media.media_id
                WHERE character_id = $1::BIGINT
                  AND EXISTS (
                        SELECT 1
                        FROM characters AS character
                        WHERE character.id = character_media.character_id
                          AND character.workspace_id = {safe_workspace_id}
                      )
                  {visibility_filter}
            )
            SELECT media_offset
            FROM ordered_media
            WHERE media_id = $2::BIGINT
            """,
            int(character_id),
            int(media_id),
        )
    return int(value) if value is not None else None
