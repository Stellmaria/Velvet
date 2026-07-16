from __future__ import annotations

from typing import Any

from velvet_bot.database import Database, SaveMediaResult
from velvet_bot.media import MediaDescriptor

_INSTALLED = False
_ORIGINAL_SAVE = Database.save_character_media


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


async def _save_with_preview(
    self: Database,
    character,
    media: MediaDescriptor,
    **kwargs: Any,
) -> SaveMediaResult:
    result = await _ORIGINAL_SAVE(self, character, media, **kwargs)
    if media.preview_file_id:
        await set_media_preview(
            self,
            media_id=result.media_id,
            file_id=media.preview_file_id,
            file_unique_id=media.preview_file_unique_id,
            width=media.preview_width,
            height=media.preview_height,
            source=media.preview_source or "source_thumbnail",
        )
    return result


def install_media_preview_persistence() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    Database.save_character_media = _save_with_preview  # type: ignore[method-assign]
    _INSTALLED = True
