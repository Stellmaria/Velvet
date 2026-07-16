from __future__ import annotations

from velvet_bot.domains.archive.models import ArchivePage, DeletedArchiveItem
from velvet_bot.domains.archive.repository import ArchiveRepository
from velvet_bot.domains.characters.catalog import validate_prompt_post_url


class ArchiveService:
    """Coordinate archive browsing and exact character-media mutations."""

    def __init__(self, repository: ArchiveRepository) -> None:
        self._repository = repository

    async def get_page(self, character_id: int, offset: int) -> ArchivePage | None:
        return await self._repository.get_page(
            character_id=character_id,
            offset=offset,
        )

    async def set_prompt(
        self,
        *,
        character_id: int,
        media_id: int,
        prompt_post_url: str | None,
    ) -> bool:
        cleaned = (
            validate_prompt_post_url(prompt_post_url)
            if prompt_post_url is not None
            else None
        )
        return await self._repository.set_prompt(
            character_id=character_id,
            media_id=media_id,
            prompt_post_url=cleaned,
        )

    async def set_spoiler(
        self,
        *,
        character_id: int,
        media_id: int,
        is_spoiler: bool,
    ) -> bool:
        return await self._repository.set_spoiler(
            character_id=character_id,
            media_id=media_id,
            is_spoiler=is_spoiler,
        )

    async def toggle_spoiler(
        self,
        *,
        character_id: int,
        media_id: int,
    ) -> bool | None:
        return await self._repository.toggle_spoiler(
            character_id=character_id,
            media_id=media_id,
        )

    async def delete_item(
        self,
        *,
        character_id: int,
        media_id: int,
    ) -> DeletedArchiveItem | None:
        return await self._repository.delete_item(
            character_id=character_id,
            media_id=media_id,
        )


__all__ = ("ArchiveService",)
