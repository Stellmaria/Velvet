from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class RoleplayCharacterDraft:
    name: str
    adult_confirmed: bool
    age_text: str | None = None
    pronouns: str | None = None
    appearance: JsonObject | None = None
    personality: JsonObject | None = None
    speech: JsonObject | None = None
    biography: JsonObject | None = None
    behavior_rules: JsonObject | None = None
    canonical_facts: tuple[str, ...] = ()
    example_dialogue: tuple[str, ...] = ()
    system_notes: str | None = None


@dataclass(frozen=True, slots=True)
class RoleplayCharacter:
    id: int
    owner_user_id: int
    name: str
    normalized_name: str
    adult_confirmed: bool
    age_text: str | None
    pronouns: str | None
    appearance: JsonObject
    personality: JsonObject
    speech: JsonObject
    biography: JsonObject
    behavior_rules: JsonObject
    canonical_facts: tuple[str, ...]
    example_dialogue: tuple[str, ...]
    system_notes: str | None
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RoleplaySession:
    id: int
    owner_user_id: int
    title: str
    model: str
    status: str
    scenario: str
    world_lore: str
    scene_state: JsonObject
    summary: str
    generation_settings: JsonObject
    next_sequence: int
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None


@dataclass(frozen=True, slots=True)
class RoleplayMessage:
    id: int
    session_id: int
    sequence_no: int
    role: str
    speaker_key: str | None
    content: str
    token_count: int | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RoleplayMemory:
    id: int
    session_id: int
    character_id: int | None
    kind: str
    content: str
    metadata: JsonObject
    importance: int
    pinned: bool
    active: bool
    source_message_id: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RoleplayContext:
    messages: tuple[dict[str, str], ...]
    estimated_input_tokens: int
    trimmed_message_count: int


__all__ = (
    "JsonObject",
    "RoleplayCharacter",
    "RoleplayCharacterDraft",
    "RoleplayContext",
    "RoleplayMemory",
    "RoleplayMessage",
    "RoleplaySession",
)
