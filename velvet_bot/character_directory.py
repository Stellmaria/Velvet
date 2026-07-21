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
from velvet_bot.domains.workspaces.character_directory import (
    get_workspace_character_directory_item,
    list_workspace_category_summaries,
    list_workspace_character_directory,
    list_workspace_universe_summaries,
)
from velvet_bot.domains.workspaces.character_management import (
    set_workspace_character_category,
    set_workspace_character_prompt_url,
    set_workspace_character_universe,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


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
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> None:
    if int(workspace_id) != DEFAULT_WORKSPACE_ID:
        await set_workspace_character_category(
            database,
            workspace_id=int(workspace_id),
            character_id=character_id,
            category_key=category,
        )
        return
    await _service(database).set_category(
        character_id=character_id,
        category=category,
    )


async def set_character_universe(
    database: Database,
    *,
    character_id: int,
    universe: str | None,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> None:
    if int(workspace_id) != DEFAULT_WORKSPACE_ID:
        await set_workspace_character_universe(
            database,
            workspace_id=int(workspace_id),
            character_id=character_id,
            universe_key=universe,
        )
        return
    await _service(database).set_universe(
        character_id=character_id,
        universe=universe,
    )


async def set_character_prompt_url(
    database: Database,
    *,
    character_id: int,
    prompt_post_url: str | None,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> None:
    if int(workspace_id) != DEFAULT_WORKSPACE_ID:
        await set_workspace_character_prompt_url(
            database,
            workspace_id=int(workspace_id),
            character_id=character_id,
            prompt_post_url=prompt_post_url,
        )
        return
    await _service(database).set_prompt_url(
        character_id=character_id,
        prompt_post_url=prompt_post_url,
    )


async def get_character_directory_item(
    database: Database,
    character_id: int,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    public_only: bool = False,
    include_restricted: bool = True,
) -> CharacterDirectoryItem | None:
    if int(workspace_id) != DEFAULT_WORKSPACE_ID:
        return await get_workspace_character_directory_item(
            database,
            workspace_id=int(workspace_id),
            character_id=character_id,
            public_only=public_only,
            include_restricted=include_restricted,
        )
    return await _service(database).get_item(character_id)


async def list_category_summaries(
    database: Database,
    *,
    public_only: bool,
    include_uncategorized: bool = False,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    include_restricted: bool = True,
) -> list[CategorySummary]:
    if int(workspace_id) != DEFAULT_WORKSPACE_ID:
        return await list_workspace_category_summaries(
            database,
            workspace_id=int(workspace_id),
            public_only=public_only,
            include_uncategorized=include_uncategorized,
            include_restricted=include_restricted,
        )
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
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    include_restricted: bool = True,
) -> list[UniverseSummary]:
    if int(workspace_id) != DEFAULT_WORKSPACE_ID:
        return await list_workspace_universe_summaries(
            database,
            workspace_id=int(workspace_id),
            category=category,
            public_only=public_only,
            include_unassigned=include_unassigned,
            include_restricted=include_restricted,
        )
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
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    include_restricted: bool = True,
) -> CharacterDirectoryPage:
    if int(workspace_id) != DEFAULT_WORKSPACE_ID:
        return await list_workspace_character_directory(
            database,
            workspace_id=int(workspace_id),
            category=category,
            page=page,
            page_size=page_size,
            public_only=public_only,
            universe=universe,
            story_id=story_id,
            include_restricted=include_restricted,
        )
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
