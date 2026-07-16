from __future__ import annotations

from aiogram.types import PhotoSize

from velvet_bot.app.references import build_reference_service
from velvet_bot.database import Character, Database
from velvet_bot.domains.references import (
    AddReferenceResult,
    CharacterReference,
    DeleteReferenceResult,
    ReferencePage,
)
from velvet_bot.infrastructure.telegram import reference_payload_from_photo


async def add_character_reference(
    database: Database,
    character: Character,
    photo: PhotoSize,
    *,
    added_by: int | None,
) -> AddReferenceResult:
    return await build_reference_service(database).add(
        character_id=character.id,
        media=reference_payload_from_photo(photo),
        added_by=added_by,
    )


async def delete_character_reference(
    database: Database,
    character_id: int,
    reference_id: int,
) -> DeleteReferenceResult:
    return await build_reference_service(database).delete(
        character_id=character_id,
        reference_id=reference_id,
    )


async def count_character_references(database: Database, character_id: int) -> int:
    return await build_reference_service(database).count(character_id)


async def list_character_references(
    database: Database,
    character_id: int,
    *,
    limit: int = 50,
) -> list[CharacterReference]:
    return await build_reference_service(database).list(
        character_id,
        limit=limit,
    )


async def get_reference_page(
    database: Database,
    character_id: int,
    offset: int,
) -> ReferencePage | None:
    return await build_reference_service(database).get_page(character_id, offset)


__all__ = (
    "AddReferenceResult",
    "CharacterReference",
    "DeleteReferenceResult",
    "ReferencePage",
    "add_character_reference",
    "count_character_references",
    "delete_character_reference",
    "get_reference_page",
    "list_character_references",
)
