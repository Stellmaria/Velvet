from __future__ import annotations

from velvet_bot.app.archive import build_archive_service
from velvet_bot.database import Database
from velvet_bot.domains.archive import ArchivePage, ArchivedMedia, DeletedArchiveItem
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


async def get_archive_page(
    database: Database,
    character_id: int,
    offset: int,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    public_only: bool = False,
    include_adult_restricted: bool = False,
    include_oversized_images: bool = False,
) -> ArchivePage | None:
    return await build_archive_service(
        database,
        workspace_id=workspace_id,
    ).get_page(
        character_id,
        offset,
        public_only=public_only,
        include_adult_restricted=include_adult_restricted,
        include_oversized_images=include_oversized_images,
    )


async def set_archive_media_prompt(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    prompt_post_url: str | None,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> bool:
    return await build_archive_service(
        database,
        workspace_id=workspace_id,
    ).set_prompt(
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
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> bool:
    return await build_archive_service(
        database,
        workspace_id=workspace_id,
    ).set_spoiler(
        character_id=character_id,
        media_id=media_id,
        is_spoiler=is_spoiler,
    )


async def toggle_archive_media_spoiler(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> bool | None:
    return await build_archive_service(
        database,
        workspace_id=workspace_id,
    ).toggle_spoiler(
        character_id=character_id,
        media_id=media_id,
    )


async def toggle_archive_media_public_visibility(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> bool | None:
    return await build_archive_service(
        database,
        workspace_id=workspace_id,
    ).toggle_public_visibility(
        character_id=character_id,
        media_id=media_id,
    )


async def toggle_archive_media_adult_requirement(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> bool | None:
    return await build_archive_service(
        database,
        workspace_id=workspace_id,
    ).toggle_adult_requirement(
        character_id=character_id,
        media_id=media_id,
    )


async def delete_archive_item(
    database: Database,
    character_id: int,
    media_id: int,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> DeletedArchiveItem | None:
    return await build_archive_service(
        database,
        workspace_id=workspace_id,
    ).delete_item(
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
