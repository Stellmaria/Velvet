from __future__ import annotations

from velvet_bot.domains.references.models import (
    AddReferenceResult,
    CharacterReference,
    DeleteReferenceResult,
    ReferenceMediaPayload,
    ReferencePage,
)
from velvet_bot.domains.references.repository import ReferenceRepository


class ReferenceService:
    """Coordinate reference catalog operations using neutral media payloads."""

    def __init__(self, repository: ReferenceRepository) -> None:
        self._repository = repository

    async def add(
        self,
        *,
        character_id: int,
        media: ReferenceMediaPayload,
        added_by: int | None,
    ) -> AddReferenceResult:
        if not media.telegram_file_id or not media.telegram_file_unique_id:
            raise ValueError("Референс не содержит Telegram file_id.")
        return await self._repository.add(
            character_id=character_id,
            media=media,
            added_by=added_by,
        )

    async def delete(
        self,
        *,
        character_id: int,
        reference_id: int,
    ) -> DeleteReferenceResult:
        return await self._repository.delete(
            character_id=character_id,
            reference_id=reference_id,
        )

    async def count(self, character_id: int) -> int:
        return await self._repository.count(character_id)

    async def list(
        self,
        character_id: int,
        *,
        limit: int = 50,
    ) -> list[CharacterReference]:
        return await self._repository.list(character_id, limit=limit)

    async def get_page(
        self,
        character_id: int,
        offset: int,
    ) -> ReferencePage | None:
        return await self._repository.get_page(character_id, offset)


__all__ = ("ReferenceService",)
