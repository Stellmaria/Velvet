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
from velvet_bot.public_directory import (
    list_visible_categories,
    list_visible_characters,
    list_visible_stories,
    list_visible_universes,
)

PublicCharacterItem = CharacterDirectoryItem
PublicCharacterPage = CharacterDirectoryPage


async def list_public_categories(
    database: Database,
    *,
    include_restricted: bool = False,
) -> list[CategorySummary]:
    return await list_visible_categories(
        database,
        include_restricted=include_restricted,
    )


async def list_public_universes(
    database: Database,
    *,
    category: str,
    include_restricted: bool = False,
) -> list[UniverseSummary]:
    summaries = await list_visible_universes(
        database,
        category=category,
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
    include_restricted: bool = False,
) -> list[StorySummary]:
    return await list_visible_stories(
        database,
        category=category,
        universe=universe,
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
    include_restricted: bool = False,
) -> PublicCharacterPage:
    return await list_visible_characters(
        database,
        category=category,
        universe=universe,
        story_id=story_id,
        page=page,
        page_size=page_size,
        include_restricted=include_restricted,
    )


async def get_public_media_state(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    user_id: int,
) -> PublicMediaState:
    return await build_public_archive_service(database).get_media_state(
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
) -> None:
    await build_public_archive_service(database).record_view(
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
) -> PublicDownloadSource | None:
    return await build_public_archive_service(database).resolve_download_source(
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
) -> None:
    await build_public_archive_service(database).record_download(
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
) -> tuple[bool, int]:
    result = await build_public_archive_service(database).toggle_like(
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
) -> bool:
    return await build_public_archive_service(database).toggle_subscription(
        character_id=character_id,
        user_id=user_id,
    )


async def list_character_subscriber_ids(
    database: Database,
    character_id: int,
    *,
    exclude_user_id: int | None = None,
) -> list[int]:
    return await build_public_archive_service(database).list_subscriber_ids(
        character_id,
        exclude_user_id=exclude_user_id,
    )


async def remove_character_subscription(
    database: Database,
    *,
    character_id: int,
    user_id: int,
) -> None:
    await build_public_archive_service(database).remove_subscription(
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
