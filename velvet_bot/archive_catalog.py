from __future__ import annotations

from velvet_bot.app.archive import build_archive_service
from velvet_bot.database import Database
from velvet_bot.domains.archive import ArchivePage, ArchivedMedia, DeletedArchiveItem


async def get_archive_page(
    database: Database,
    character_id: int,
    offset: int,
    *,
    public_only: bool = False,
) -> ArchivePage | None:
    return await build_archive_service(database).get_page(
        character_id,
        offset,
        public_only=public_only,
    )


async def set_archive_media_prompt(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    prompt_post_url: str | None,
) -> bool:
    return await build_archive_service(database).set_prompt(
        character_id=character_id,
        media_id=media_id,
        prompt_post_url=prompt_post_url,
    )


async def set_archive_media_spoiler(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    is_spoiler: bool,
) -> bool:
    return await build_archive_service(database).set_spoiler(
        character_id=character_id,
        media_id=media_id,
        is_spoiler=is_spoiler,
    )


async def toggle_archive_media_spoiler(
    database: Database,
    *,
    character_id: int,
    media_id: int,
) -> bool | None:
    return await build_archive_service(database).toggle_spoiler(
        character_id=character_id,
        media_id=media_id,
    )


async def toggle_archive_media_public_visibility(
    database: Database,
    *,
    character_id: int,
    media_id: int,
) -> bool | None:
    return await build_archive_service(database).toggle_public_visibility(
        character_id=character_id,
        media_id=media_id,
    )


async def toggle_archive_media_adult_requirement(
    database: Database,
    *,
    character_id: int,
    media_id: int,
) -> bool | None:
    return await build_archive_service(database).toggle_adult_requirement(
        character_id=character_id,
        media_id=media_id,
    )


async def delete_archive_item(
    database: Database,
    character_id: int,
    media_id: int,
) -> DeletedArchiveItem | None:
    return await build_archive_service(database).delete_item(
        character_id=character_id,
        media_id=media_id,
    )


__all__ = (
    "ArchivePage",
    "ArchivedMedia",
    "DeletedArchiveItem",
    "delete_archive_item",
    "get_archive_page",
    "set_archive_media_prompt",
    "set_archive_media_spoiler",
    "toggle_archive_media_adult_requirement",
    "toggle_archive_media_public_visibility",
    "toggle_archive_media_spoiler",
)
