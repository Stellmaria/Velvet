from __future__ import annotations

from datetime import date

from velvet_bot.database import Database
from velvet_bot.domains.stories import (
    KNOWN_UNIVERSES,
    STORY_REQUIRED_UNIVERSES,
    CharacterStory,
    StoryPage,
    StoryRepository,
    StoryService,
    StorySummary,
    clean_story_short_label,
    clean_story_title,
    format_story_release,
    make_story_key,
    universe_requires_story,
)


def _service(database: Database) -> StoryService:
    return StoryService(StoryRepository(database))


async def get_story(database: Database, story_id: int) -> CharacterStory | None:
    return await _service(database).get(story_id)


async def list_stories(
    database: Database,
    *,
    universe: str,
) -> list[CharacterStory]:
    return await _service(database).list(universe=universe)


async def list_story_page(
    database: Database,
    *,
    universe: str,
    page: int = 0,
    page_size: int = 7,
) -> StoryPage:
    return await _service(database).list_page(
        universe=universe,
        page=page,
        page_size=page_size,
    )


async def find_story(
    database: Database,
    *,
    universe: str,
    value: str,
) -> CharacterStory | None:
    return await _service(database).find(universe=universe, value=value)


async def create_story(
    database: Database,
    *,
    universe: str,
    short_label: str,
    title: str,
    released_on: date | None = None,
    release_precision: str = "unknown",
) -> CharacterStory:
    return await _service(database).create(
        universe=universe,
        short_label=short_label,
        title=title,
        released_on=released_on,
        release_precision=release_precision,
    )


async def set_character_story(
    database: Database,
    *,
    character_id: int,
    story_id: int | None,
) -> None:
    await _service(database).set_character_story(
        character_id=character_id,
        story_id=story_id,
    )


async def list_story_summaries(
    database: Database,
    *,
    category: str,
    universe: str,
    public_only: bool,
) -> list[StorySummary]:
    return await _service(database).list_summaries(
        category=category,
        universe=universe,
        public_only=public_only,
    )


__all__ = (
    "KNOWN_UNIVERSES",
    "STORY_REQUIRED_UNIVERSES",
    "CharacterStory",
    "StoryPage",
    "StorySummary",
    "clean_story_short_label",
    "clean_story_title",
    "create_story",
    "find_story",
    "format_story_release",
    "get_story",
    "list_stories",
    "list_story_page",
    "list_story_summaries",
    "make_story_key",
    "set_character_story",
    "universe_requires_story",
)
