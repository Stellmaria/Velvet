from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.public_archive import (
    PendingPublicNotification,
    PublicArchiveRepository,
)


class PublicNotificationRepository:
    """Compatibility facade for the public archive notification repository."""

    def __init__(self, database: Database) -> None:
        self._repository = PublicArchiveRepository(database)

    async def list_pending(
        self,
        *,
        limit: int = 100,
    ) -> list[PendingPublicNotification]:
        return await self._repository.list_pending_notifications(limit=limit)

    async def mark_delivered(
        self,
        notification: PendingPublicNotification,
    ) -> bool:
        return await self._repository.mark_notification_delivered(notification)


__all__ = ("PendingPublicNotification", "PublicNotificationRepository")
