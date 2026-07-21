from __future__ import annotations

from velvet_bot.app.public_archive import build_public_archive_service
from velvet_bot.database import Database
from velvet_bot.domains.characters import (
    GAME_UNIVERSE_ORDER,
    CategorySummary,
    CharacterDirectoryItem,
    CharacterDirectoryPage,
    UniverseSummary,
)
from velvet_bot.domains.public_archive import PublicDownloadSource, PublicMediaState
from velvet_bot.domains.stories import StorySummary
from velvet_bot.domains.workspaces.character_directory import (
    list_workspace_category_summaries,
    list_workspace_character_directory,
    list_workspace_story_summaries,
    list_workspace_universe_summaries,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.public_directory import (
    list_visible_categories,
    list_visible_characters,
    list_visible_stories,
    list_visible_universes,
)

PublicCharacterItem = CharacterDirectoryItem
PublicCharacterPage = CharacterDirectoryPage


async def _selected_workspace_id(
    database: Database,
    *,
    user_id: int,
    workspace_id: int | None,
) -> int:
    if workspace_id is not None:
        return int(workspace_id)
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT preference.workspace_id
            FROM user_public_workspace_preferences AS preference
            JOIN workspace_settings AS settings
              ON settings.workspace_id = preference.workspace_id
             AND settings.public_archive_enabled
            WHERE preference.user_id = $1::BIGINT
            """,
            int(user_id),
        )
    return int(value) if value is not None else DEFAULT_WORKSPACE_ID


async def list_public_categories(
    database: Database,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    include_restricted: bool = False,
) -> list[CategorySummary]:
    if int(workspace_id) != DEFAULT_WORKSPACE_ID:
        return await list_workspace_category_summaries(
            database,
            workspace_id=int(workspace_id),
            public_only=True,
            include_restricted=include_restricted,
        )
    return await list_visible_categories(
        database,
        workspace_id=workspace_id,
        include_restricted=include_restricted,
    )


async def list_public_universes(
    database: Database,
    *,
    category: str,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    include_restricted: bool = False,
) -> list[UniverseSummary]:
    if int(workspace_id) != DEFAULT_WORKSPACE_ID:
        return await list_workspace_universe_summaries(
            database,
            workspace_id=int(workspace_id),
            category=category,
            public_only=True,
            include_restricted=include_restricted,
        )
    summaries = await list_visible_universes(
        database,
        category=category,
        workspace_id=workspace_id,
        include_restricted=include_restricted,
    )
    game_count = 0
    for universe in GAME_UNIVERSE_ORDER:
        page = await list_visible_characters(
            database,
            category=category,
            universe=universe,
            page=0,
            page_size=1,
            workspace_id=workspace_id,
            include_restricted=include_restricted,
        )
        game_count += page.total_characters
    return [
        UniverseSummary(
            key=item.key,
            label=item.label,
            emoji=item.emoji,
            character_count=game_count,
        )
        if item.key == "games"
        else item
        for item in summaries
    ]


async def list_public_stories(
    database: Database,
    *,
    category: str,
    universe: str,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    include_restricted: bool = False,
) -> list[StorySummary]:
    if int(workspace_id) != DEFAULT_WORKSPACE_ID:
        return await list_workspace_story_summaries(
            database,
            workspace_id=int(workspace_id),
            category=category,
            universe=universe,
            public_only=True,
            include_restricted=include_restricted,
        )
    return await list_visible_stories(
        database,
        category=category,
        universe=universe,
        workspace_id=workspace_id,
        include_restricted=include_restricted,
    )


async def list_public_characters(
    database: Database,
    *,
    category: str,
    universe: str | None = None,
    story_id: int | None = None,
    page: int = 0,
    page_size: int = 6,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    include_restricted: bool = False,
) -> PublicCharacterPage:
    if int(workspace_id) != DEFAULT_WORKSPACE_ID:
        return await list_workspace_character_directory(
            database,
            workspace_id=int(workspace_id),
            category=category,
            universe=universe,
            story_id=story_id,
            page=page,
            page_size=page_size,
            public_only=True,
            include_restricted=include_restricted,
        )
    return await list_visible_characters(
        database,
        category=category,
        universe=universe,
        story_id=story_id,
        page=page,
        page_size=page_size,
        workspace_id=workspace_id,
        include_restricted=include_restricted,
    )


async def get_public_media_state(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    user_id: int,
    workspace_id: int | None = None,
) -> PublicMediaState:
    selected = await _selected_workspace_id(
        database,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    return await build_public_archive_service(
        database,
        workspace_id=selected,
    ).get_media_state(
        character_id=character_id,
        media_id=media_id,
        user_id=user_id,
    )


async def record_public_media_view(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    user_id: int,
    workspace_id: int | None = None,
) -> None:
    selected = await _selected_workspace_id(
        database,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    await build_public_archive_service(
        database,
        workspace_id=selected,
    ).record_view(
        character_id=character_id,
        media_id=media_id,
        user_id=user_id,
    )


async def resolve_public_download_source(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    member_access: bool,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> PublicDownloadSource | None:
    return await build_public_archive_service(
        database,
        workspace_id=workspace_id,
    ).resolve_download_source(
        character_id=character_id,
        media_id=media_id,
        member_access=member_access,
    )


async def record_public_media_download(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    user_id: int,
    variant: str,
    workspace_id: int | None = None,
) -> None:
    selected = await _selected_workspace_id(
        database,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    await build_public_archive_service(
        database,
        workspace_id=selected,
    ).record_download(
        character_id=character_id,
        media_id=media_id,
        user_id=user_id,
        variant=variant,
    )


async def toggle_public_like(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    user_id: int,
    workspace_id: int | None = None,
) -> tuple[bool, int]:
    selected = await _selected_workspace_id(
        database,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    result = await build_public_archive_service(
        database,
        workspace_id=selected,
    ).toggle_like(
        character_id=character_id,
        media_id=media_id,
        user_id=user_id,
    )
    return result.liked, result.like_count


async def toggle_character_subscription(
    database: Database,
    *,
    character_id: int,
    user_id: int,
    workspace_id: int | None = None,
) -> bool:
    selected = await _selected_workspace_id(
        database,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    return await build_public_archive_service(
        database,
        workspace_id=selected,
    ).toggle_subscription(
        character_id=character_id,
        user_id=user_id,
    )


async def list_character_subscriber_ids(
    database: Database,
    character_id: int,
    *,
    exclude_user_id: int | None = None,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> list[int]:
    return await build_public_archive_service(
        database,
        workspace_id=workspace_id,
    ).list_subscriber_ids(
        character_id,
        exclude_user_id=exclude_user_id,
    )


async def remove_character_subscription(
    database: Database,
    *,
    character_id: int,
    user_id: int,
    workspace_id: int | None = None,
) -> None:
    selected = await _selected_workspace_id(
        database,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    await build_public_archive_service(
        database,
        workspace_id=selected,
    ).remove_subscription(
        character_id=character_id,
        user_id=user_id,
    )


__all__ = (
    "PublicCharacterItem",
    "PublicCharacterPage",
    "PublicDownloadSource",
    "PublicMediaState",
    "get_public_media_state",
    "list_character_subscriber_ids",
    "list_public_categories",
    "list_public_characters",
    "list_public_stories",
    "list_public_universes",
    "record_public_media_download",
    "record_public_media_view",
    "remove_character_subscription",
    "resolve_public_download_source",
    "toggle_character_subscription",
    "toggle_public_like",
)
