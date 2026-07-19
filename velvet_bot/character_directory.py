from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.characters import (
    CATEGORY_EMOJI,
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    GAME_UNIVERSE_ORDER,
    UNIVERSE_EMOJI,
    UNIVERSE_LABELS,
    UNIVERSE_ORDER,
    UNIVERSE_VALUE_ORDER,
    CategorySummary,
    CharacterDirectoryItem,
    CharacterDirectoryPage,
    CharacterDirectoryRepository,
    CharacterDirectoryService,
    UniverseSummary,
    category_label,
    normalize_category,
    normalize_universe,
    story_label,
    universe_label,
    validate_prompt_post_url,
)


def _service(database: Database) -> CharacterDirectoryService:
    return CharacterDirectoryService(CharacterDirectoryRepository(database))


def _row_to_directory_item(row) -> CharacterDirectoryItem:
    """Compatibility bridge for stale pre-Phase-15 multi-story modules.

    Current code maps rows inside ``CharacterDirectoryRepository``. A partially
    updated deployment can still contain the old ``multi_story_support.py``
    which imports this module-level helper directly. Keep the bridge until all
    production installations have been fully synchronized.
    """
    return CharacterDirectoryRepository._row_to_directory_item(row)


async def set_character_category(
    database: Database,
    *,
    character_id: int,
    category: str | None,
) -> None:
    await _service(database).set_category(
        character_id=character_id,
        category=category,
    )


async def set_character_universe(
    database: Database,
    *,
    character_id: int,
    universe: str | None,
) -> None:
    await _service(database).set_universe(
        character_id=character_id,
        universe=universe,
    )


async def set_character_prompt_url(
    database: Database,
    *,
    character_id: int,
    prompt_post_url: str | None,
) -> None:
    await _service(database).set_prompt_url(
        character_id=character_id,
        prompt_post_url=prompt_post_url,
    )


async def get_character_directory_item(
    database: Database,
    character_id: int,
) -> CharacterDirectoryItem | None:
    return await _service(database).get_item(character_id)


async def list_category_summaries(
    database: Database,
    *,
    public_only: bool,
    include_uncategorized: bool = False,
) -> list[CategorySummary]:
    result = await _service(database).list_category_summaries(
        public_only=public_only,
        include_uncategorized=include_uncategorized,
    )
    return list(result)


async def list_universe_summaries(
    database: Database,
    *,
    category: str,
    public_only: bool,
    include_unassigned: bool = False,
) -> list[UniverseSummary]:
    result = await _service(database).list_universe_summaries(
        category=category,
        public_only=public_only,
        include_unassigned=include_unassigned,
    )
    return list(result)


async def list_character_directory(
    database: Database,
    *,
    category: str,
    page: int = 0,
    page_size: int = 6,
    public_only: bool,
    universe: str | None = None,
    story_id: int | None = None,
) -> CharacterDirectoryPage:
    result = await _service(database).list_directory(
        category=category,
        page=page,
        page_size=page_size,
        public_only=public_only,
        universe=universe,
        story_id=story_id,
    )
    if isinstance(result.items, list):
        return result
    return CharacterDirectoryPage(
        items=list(result.items),
        category=result.category,
        page=result.page,
        page_size=result.page_size,
        total_characters=result.total_characters,
        universe=result.universe,
        story_id=result.story_id,
        story_short_label=result.story_short_label,
        story_title=result.story_title,
    )


__all__ = (
    "CATEGORY_EMOJI",
    "CATEGORY_LABELS",
    "CATEGORY_ORDER",
    "GAME_UNIVERSE_ORDER",
    "UNIVERSE_EMOJI",
    "UNIVERSE_LABELS",
    "UNIVERSE_ORDER",
    "UNIVERSE_VALUE_ORDER",
    "CategorySummary",
    "CharacterDirectoryItem",
    "CharacterDirectoryPage",
    "UniverseSummary",
    "category_label",
    "get_character_directory_item",
    "list_category_summaries",
    "list_character_directory",
    "list_universe_summaries",
    "normalize_category",
    "normalize_universe",
    "set_character_category",
    "set_character_prompt_url",
    "set_character_universe",
    "story_label",
    "universe_label",
    "validate_prompt_post_url",
)
