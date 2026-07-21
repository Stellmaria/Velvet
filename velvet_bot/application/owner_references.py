from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.app.references import build_reference_service
from velvet_bot.character_resolution import resolve_character
from velvet_bot.database import Character, Database
from velvet_bot.domains.references import CharacterReference, ReferencePage
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.reference_uploads import ReferenceUploadSession, ReferenceUploadSessions


@dataclass(frozen=True, slots=True)
class ReferenceDeleteResult:
    character: Character
    index: int
    reference: CharacterReference | None
    remaining: int


async def start_reference_upload(
    database: Database,
    sessions: ReferenceUploadSessions,
    *,
    user_id: int,
    character_name: str,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> ReferenceUploadSession:
    character = await resolve_character(
        database,
        character_name,
        workspace_id=workspace_id,
    )
    if character is None:
        raise ValueError("Такой персонаж или быстрый тег не найден.")
    return sessions.start(
        user_id,
        character_id=character.id,
        character_name=character.name,
        workspace_id=workspace_id,
    )


def finish_reference_upload(
    sessions: ReferenceUploadSessions,
    *,
    user_id: int,
) -> ReferenceUploadSession | None:
    return sessions.stop(user_id)


async def get_reference_page_by_name(
    database: Database,
    character_name: str,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> ReferencePage | None:
    character = await resolve_character(
        database,
        character_name,
        workspace_id=workspace_id,
    )
    if character is None:
        return None
    return await build_reference_service(database).get_page(
        character.id,
        0,
        workspace_id=workspace_id,
    )


async def delete_reference_by_index(
    database: Database,
    raw_value: str,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> ReferenceDeleteResult:
    character_name, index = parse_reference_index(raw_value)
    character = await resolve_character(
        database,
        character_name,
        workspace_id=workspace_id,
    )
    if character is None:
        raise ValueError("Такой персонаж или быстрый тег не найден.")
    service = build_reference_service(database)
    page = await service.get_page(
        character.id,
        index - 1,
        workspace_id=workspace_id,
    )
    if page is None or page.reference is None or index > page.total:
        raise ValueError("Референс с таким номером не найден.")
    result = await service.delete(
        character_id=character.id,
        reference_id=page.reference.id,
        workspace_id=workspace_id,
    )
    return ReferenceDeleteResult(
        character=character,
        index=index,
        reference=result.reference,
        remaining=result.total,
    )


def parse_reference_index(raw_value: str) -> tuple[str, int]:
    cleaned = " ".join(raw_value.split())
    parts = cleaned.rsplit(maxsplit=1)
    if len(parts) != 2:
        raise ValueError("Укажите персонажа и номер референса.")
    character_name, raw_index = parts
    if raw_index.startswith("#"):
        raw_index = raw_index[1:]
    try:
        index = int(raw_index)
    except ValueError as error:
        raise ValueError("Номер референса должен быть целым числом.") from error
    if index < 1:
        raise ValueError("Номер референса должен быть больше нуля.")
    return character_name, index


__all__ = (
    "ReferenceDeleteResult",
    "delete_reference_by_index",
    "finish_reference_upload",
    "get_reference_page_by_name",
    "parse_reference_index",
    "start_reference_upload",
)
