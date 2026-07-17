from __future__ import annotations

from velvet_bot import character_directory, story_catalog
from velvet_bot.database import Database
from velvet_bot.domains.stories import AssignedCharacterStory, StoryRepository


async def list_assigned_character_stories(
    database: Database,
    *,
    character_id: int,
) -> list[AssignedCharacterStory]:
    return await StoryRepository(database).list_assigned_character_stories(
        character_id=character_id
    )


async def toggle_character_story(
    database: Database,
    *,
    character_id: int,
    story_id: int,
    assigned_by: int | None = None,
) -> bool:
    return await StoryRepository(database).toggle_character_story(
        character_id=character_id,
        story_id=story_id,
        assigned_by=assigned_by,
    )


async def clear_character_stories(
    database: Database,
    *,
    character_id: int,
) -> None:
    await StoryRepository(database).clear_character_stories(character_id=character_id)


async def set_character_story(
    database: Database,
    *,
    character_id: int,
    story_id: int | None,
) -> None:
    await story_catalog.set_character_story(
        database, character_id=character_id, story_id=story_id
    )


async def set_character_universe(
    database: Database,
    *,
    character_id: int,
    universe: str | None,
) -> None:
    await character_directory.set_character_universe(
        database, character_id=character_id, universe=universe
    )


async def list_story_summaries(database: Database, **kwargs):
    return await story_catalog.list_story_summaries(database, **kwargs)


async def list_category_summaries(database: Database, **kwargs):
    return await character_directory.list_category_summaries(database, **kwargs)


async def list_universe_summaries(database: Database, **kwargs):
    return await character_directory.list_universe_summaries(database, **kwargs)


async def list_character_directory(database: Database, **kwargs):
    return await character_directory.list_character_directory(database, **kwargs)


def install_multi_story_support() -> None:
    """Compatibility no-op: multi-story behavior is wired into repositories."""


__all__ = (
    "AssignedCharacterStory",
    "clear_character_stories",
    "install_multi_story_support",
    "list_assigned_character_stories",
    "list_category_summaries",
    "list_character_directory",
    "list_story_summaries",
    "list_universe_summaries",
    "set_character_story",
    "set_character_universe",
    "toggle_character_story",
)
