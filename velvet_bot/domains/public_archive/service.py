from __future__ import annotations

from typing import Protocol

from velvet_bot.domains.characters import (
    CategorySummary,
    CharacterDirectoryPage,
    CharacterDirectoryService,
    UniverseSummary,
)
from velvet_bot.domains.public_archive.models import (
    LikeToggleResult,
    PendingPublicNotification,
    PublicDownloadSource,
    PublicMediaState,
)
from velvet_bot.domains.public_archive.repository import PublicArchiveRepository
from velvet_bot.domains.stories import StorySummary


class StorySummaryProvider(Protocol):
    async def list_summaries(
        self,
        *,
        category: str,
        universe: str,
        public_only: bool,
    ) -> list[StorySummary]: ...


class PublicArchiveService:
    """Coordinate public filters, likes, subscriptions and media activity."""

    def __init__(
        self,
        *,
        repository: PublicArchiveRepository,
        characters: CharacterDirectoryService,
        stories: StorySummaryProvider,
    ) -> None:
        self._repository = repository
        self._characters = characters
        self._stories = stories

    async def list_categories(self) -> list[CategorySummary]:
        return list(
            await self._characters.list_category_summaries(public_only=True)
        )

    async def list_universes(self, *, category: str) -> list[UniverseSummary]:
        return list(
            await self._characters.list_universe_summaries(
                category=category,
                public_only=True,
            )
        )

    async def list_stories(
        self,
        *,
        category: str,
        universe: str,
    ) -> list[StorySummary]:
        return await self._stories.list_summaries(
            category=category,
            universe=universe,
            public_only=True,
        )

    async def list_characters(
        self,
        *,
        category: str,
        universe: str | None = None,
        story_id: int | None = None,
        page: int = 0,
        page_size: int = 6,
    ) -> CharacterDirectoryPage:
        return await self._characters.list_directory(
            category=category,
            universe=universe,
            story_id=story_id,
            page=page,
            page_size=page_size,
            public_only=True,
        )

    async def get_media_state(
        self,
        *,
        character_id: int,
        media_id: int,
        user_id: int,
    ) -> PublicMediaState:
        return await self._repository.get_media_state(
            character_id=character_id,
            media_id=media_id,
            user_id=user_id,
        )

    async def record_view(
        self,
        *,
        character_id: int,
        media_id: int,
        user_id: int,
    ) -> None:
        await self._repository.record_view(
            character_id=character_id,
            media_id=media_id,
            user_id=user_id,
        )

    async def resolve_download_source(
        self,
        *,
        character_id: int,
        media_id: int,
        member_access: bool,
        download_access: bool | None = None,
    ) -> PublicDownloadSource | None:
        return await self._repository.resolve_download_source(
            character_id=character_id,
            media_id=media_id,
            member_access=member_access,
            download_access=download_access,
        )

    async def record_download(
        self,
        *,
        character_id: int,
        media_id: int,
        user_id: int,
        variant: str,
    ) -> None:
        await self._repository.record_download(
            character_id=character_id,
            media_id=media_id,
            user_id=user_id,
            variant=variant,
        )

    async def toggle_like(
        self,
        *,
        character_id: int,
        media_id: int,
        user_id: int,
    ) -> LikeToggleResult:
        return await self._repository.toggle_like(
            character_id=character_id,
            media_id=media_id,
            user_id=user_id,
        )

    async def toggle_subscription(
        self,
        *,
        character_id: int,
        user_id: int,
    ) -> bool:
        return await self._repository.toggle_subscription(
            character_id=character_id,
            user_id=user_id,
        )

    async def list_subscriber_ids(
        self,
        character_id: int,
        *,
        exclude_user_id: int | None = None,
    ) -> list[int]:
        return await self._repository.list_subscriber_ids(
            character_id,
            exclude_user_id=exclude_user_id,
        )

    async def remove_subscription(
        self,
        *,
        character_id: int,
        user_id: int,
    ) -> None:
        await self._repository.remove_subscription(
            character_id=character_id,
            user_id=user_id,
        )

    async def list_pending_notifications(
        self,
        *,
        limit: int = 100,
    ) -> list[PendingPublicNotification]:
        return await self._repository.list_pending_notifications(limit=limit)

    async def mark_notification_delivered(
        self,
        notification: PendingPublicNotification,
    ) -> bool:
        return await self._repository.mark_notification_delivered(notification)


__all__ = ("PublicArchiveService", "StorySummaryProvider")
