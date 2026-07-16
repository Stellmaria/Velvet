from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.application.owner_parsing import require_character, split_tail
from velvet_bot.character_aliases import (
    CharacterAlias,
    add_character_alias,
    delete_character_alias,
    ensure_name_aliases,
    list_character_aliases,
    rebuild_hashtag_character_links,
)
from velvet_bot.database import Character, Database


@dataclass(frozen=True, slots=True)
class AliasDeleteResult:
    character: Character
    alias: str
    deleted: bool


@dataclass(frozen=True, slots=True)
class AliasIndexResult:
    created_name_aliases: int
    matched_links: int
    total_hashtags: int


async def add_alias_from_text(
    database: Database,
    raw_value: str,
    *,
    actor_id: int | None,
) -> CharacterAlias:
    character_name, alias = split_tail(raw_value, "алиас")
    character = await require_character(database, character_name)
    return await add_character_alias(
        database,
        character_id=character.id,
        alias=alias,
        created_by=actor_id,
    )


async def list_aliases_from_text(
    database: Database,
    raw_value: str,
) -> tuple[Character, tuple[CharacterAlias, ...]]:
    character = await require_character(database, raw_value)
    aliases = await list_character_aliases(database, character_id=character.id)
    return character, tuple(aliases)


async def delete_alias_from_text(
    database: Database,
    raw_value: str,
) -> AliasDeleteResult:
    character_name, alias = split_tail(raw_value, "алиас")
    character = await require_character(database, character_name)
    deleted = await delete_character_alias(
        database,
        character_id=character.id,
        alias=alias,
    )
    return AliasDeleteResult(character=character, alias=alias, deleted=deleted)


async def rebuild_alias_index(database: Database) -> AliasIndexResult:
    created = await ensure_name_aliases(database)
    matched, total = await rebuild_hashtag_character_links(database)
    return AliasIndexResult(
        created_name_aliases=created,
        matched_links=matched,
        total_hashtags=total,
    )


__all__ = (
    "AliasDeleteResult",
    "AliasIndexResult",
    "add_alias_from_text",
    "delete_alias_from_text",
    "list_aliases_from_text",
    "rebuild_alias_index",
)
