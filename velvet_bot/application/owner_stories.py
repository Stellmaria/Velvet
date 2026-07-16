from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.application.owner_parsing import require_character, split_tail
from velvet_bot.character_directory import get_character_directory_item, normalize_universe
from velvet_bot.database import Character, Database
from velvet_bot.story_catalog import (
    CharacterStory,
    create_story,
    find_story,
    list_stories,
    set_character_story,
)


@dataclass(frozen=True, slots=True)
class StoryAssignmentResult:
    character: Character
    story: CharacterStory | None
    removed: bool


@dataclass(frozen=True, slots=True)
class StoryListResult:
    universe: str
    stories: tuple[CharacterStory, ...]


async def set_story_from_text(
    database: Database,
    raw_value: str,
) -> StoryAssignmentResult:
    character_name, raw_story = split_tail(raw_value, "сокращение истории")
    character = await require_character(database, character_name)
    item = await get_character_directory_item(database, character.id)
    if item is None or not item.universe:
        raise ValueError("Сначала назначьте персонажу вселенную.")
    if raw_story.casefold() in {"без", "нет", "off", "удалить", "-"}:
        await set_character_story(
            database,
            character_id=character.id,
            story_id=None,
        )
        return StoryAssignmentResult(character=character, story=None, removed=True)
    story = await find_story(
        database,
        universe=item.universe,
        value=raw_story,
    )
    if story is None:
        raise ValueError("История не найдена в этой вселенной.")
    await set_character_story(
        database,
        character_id=character.id,
        story_id=story.id,
    )
    return StoryAssignmentResult(character=character, story=story, removed=False)


async def add_story_from_text(
    database: Database,
    raw_value: str,
) -> CharacterStory:
    parts = raw_value.split(maxsplit=2)
    if len(parts) != 3:
        raise ValueError("Укажите вселенную, сокращение и полное название истории.")
    raw_universe, short_label, title = parts
    universe = normalize_universe(raw_universe)
    return await create_story(
        database,
        universe=universe,
        short_label=short_label,
        title=title,
    )


async def list_stories_from_text(
    database: Database,
    raw_value: str,
) -> StoryListResult:
    universe = normalize_universe(raw_value)
    stories = await list_stories(database, universe=universe)
    return StoryListResult(universe=universe, stories=tuple(stories))


__all__ = (
    "StoryAssignmentResult",
    "StoryListResult",
    "add_story_from_text",
    "list_stories_from_text",
    "set_story_from_text",
)
