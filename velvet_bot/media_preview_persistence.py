from __future__ import annotations

from velvet_bot.database import Database


async def set_media_preview(
    database: Database,
    *,
    media_id: int,
    file_id: str,
    file_unique_id: str | None,
    width: int | None,
    height: int | None,
    source: str,
) -> None:
    async with database._require_pool().acquire() as connection:
        await connection.execute(
            """
            UPDATE media_files
            SET preview_file_id = $2,
                preview_file_unique_id = COALESCE($3, preview_file_unique_id),
                preview_width = COALESCE($4, preview_width),
                preview_height = COALESCE($5, preview_height),
                preview_source = $6,
                preview_updated_at = NOW()
            WHERE id = $1
            """,
            media_id,
            file_id,
            file_unique_id,
            width,
            height,
            source,
        )
