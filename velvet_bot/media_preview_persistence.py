from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.archive.preview_models import PreviewPayload
from velvet_bot.domains.archive.preview_repository import ArchivePreviewRepository


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
    await ArchivePreviewRepository(database).save(
        media_id=media_id,
        preview=PreviewPayload(
            file_id=file_id,
            file_unique_id=file_unique_id,
            width=width,
            height=height,
            source=source,
        ),
    )


__all__ = ("set_media_preview",)
