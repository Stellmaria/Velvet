from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.application.owner_parsing import require_character, split_tail
from velvet_bot.character_directory import (
    normalize_category,
    normalize_universe,
    set_character_category,
    set_character_prompt_url,
    set_character_universe,
    validate_prompt_post_url,
)
from velvet_bot.database import Character, Database


@dataclass(frozen=True, slots=True)
class CharacterValueResult:
    character: Character
    value: str | None


async def set_category_from_text(
    database: Database,
    raw_value: str,
) -> CharacterValueResult:
    character_name, raw_category = split_tail(raw_value, "категорию")
    character = await require_character(database, character_name)
    category = normalize_category(raw_category, allow_uncategorized=True)
    stored = None if category == "uncategorized" else category
    await set_character_category(
        database,
        character_id=character.id,
        category=stored,
    )
    return CharacterValueResult(character=character, value=stored)


async def set_universe_from_text(
    database: Database,
    raw_value: str,
) -> CharacterValueResult:
    character_name, raw_universe = split_tail(raw_value, "вселенную")
    character = await require_character(database, character_name)
    universe = normalize_universe(raw_universe, allow_unassigned=True)
    stored = None if universe == "unassigned" else universe
    await set_character_universe(
        database,
        character_id=character.id,
        universe=stored,
    )
    return CharacterValueResult(character=character, value=stored)


async def set_prompt_from_text(
    database: Database,
    raw_value: str,
) -> CharacterValueResult:
    character_name, prompt_value = split_tail(raw_value, "ссылку на промт")
    character = await require_character(database, character_name)
    if prompt_value.casefold() in {"off", "нет", "удалить", "-"}:
        prompt_url = None
    else:
        prompt_url = validate_prompt_post_url(prompt_value)
    await set_character_prompt_url(
        database,
        character_id=character.id,
        prompt_post_url=prompt_url,
    )
    return CharacterValueResult(character=character, value=prompt_url)


__all__ = (
    "CharacterValueResult",
    "set_category_from_text",
    "set_prompt_from_text",
    "set_universe_from_text",
)
