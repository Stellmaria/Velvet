from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from velvet_bot.domains.characters.models import CharacterRecord
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


@dataclass(frozen=True, slots=True)
class ReferenceMediaPayload:
    telegram_file_id: str
    telegram_file_unique_id: str


@dataclass(frozen=True, slots=True)
class CharacterReference:
    id: int
    character_id: int
    telegram_file_id: str
    telegram_file_unique_id: str
    added_by: int | None
    created_at: datetime
    workspace_id: int = DEFAULT_WORKSPACE_ID


@dataclass(frozen=True, slots=True)
class ReferencePage:
    character: CharacterRecord
    reference: CharacterReference | None
    offset: int
    total: int


@dataclass(frozen=True, slots=True)
class AddReferenceResult:
    reference: CharacterReference
    created: bool
    total: int


@dataclass(frozen=True, slots=True)
class DeleteReferenceResult:
    reference: CharacterReference | None
    total: int


__all__ = (
    "AddReferenceResult",
    "CharacterReference",
    "DeleteReferenceResult",
    "ReferenceMediaPayload",
    "ReferencePage",
)
