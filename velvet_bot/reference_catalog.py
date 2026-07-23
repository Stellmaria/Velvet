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
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.infrastructure.telegram import reference_payload_from_photo


async def add_character_reference(
    database: Database,
    character: Character,
    photo: PhotoSize,
    *,
    added_by: int | None,
    workspace_id: int | None = None,
) -> AddReferenceResult:
    target_workspace_id = (
        int(workspace_id)
        if workspace_id is not None
        else int(getattr(character, "workspace_id", DEFAULT_WORKSPACE_ID))
    )
    return await build_reference_service(database).add(
        character_id=character.id,
        media=reference_payload_from_photo(photo),
        added_by=added_by,
        workspace_id=target_workspace_id,
    )


async def replace_character_reference(
    database: Database,
    character: Character,
    reference_id: int,
    photo: PhotoSize,
    *,
    added_by: int | None,
    workspace_id: int | None = None,
) -> CharacterReference:
    target_workspace_id = (
        int(workspace_id)
        if workspace_id is not None
        else int(getattr(character, "workspace_id", DEFAULT_WORKSPACE_ID))
    )
    return await build_reference_service(database).replace(
        character_id=character.id,
        reference_id=int(reference_id),
        media=reference_payload_from_photo(photo),
        added_by=added_by,
        workspace_id=target_workspace_id,
    )


async def delete_character_reference(
    database: Database,
    character_id: int,
    reference_id: int,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> DeleteReferenceResult:
    return await build_reference_service(database).delete(
        character_id=character_id,
        reference_id=reference_id,
        workspace_id=workspace_id,
    )


async def count_character_references(
    database: Database,
    character_id: int,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> int:
    return await build_reference_service(database).count(
        character_id,
        workspace_id=workspace_id,
    )


async def list_character_references(
    database: Database,
    character_id: int,
    *,
    limit: int = 50,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> list[CharacterReference]:
    return await build_reference_service(database).list(
        character_id,
        limit=limit,
        workspace_id=workspace_id,
    )


async def get_reference_page(
    database: Database,
    character_id: int,
    offset: int,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> ReferencePage | None:
    return await build_reference_service(database).get_page(
        character_id,
        offset,
        workspace_id=workspace_id,
    )


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
    "replace_character_reference",
)
