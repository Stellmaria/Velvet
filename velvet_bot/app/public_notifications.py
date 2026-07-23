from __future__ import annotations

from dataclasses import replace

from aiogram import Bot

from velvet_bot.app.public_archive import build_public_archive_service
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.presentation.telegram.public_notifications import (
    TelegramPublicNotificationDispatcher,
)


class WorkspacePublicNotificationDispatcher:
    """Process pending notifications across every currently public workspace."""

    def __init__(self, *, bot: Bot, database: Database) -> None:
        self._bot = bot
        self._database = database

    async def _workspace_ids(self) -> tuple[int, ...]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT workspace.id
                FROM workspaces AS workspace
                JOIN workspace_settings AS settings
                  ON settings.workspace_id = workspace.id
                WHERE workspace.id = $1::BIGINT
                   OR settings.public_archive_enabled
                ORDER BY workspace.is_system DESC, workspace.id
                """,
                DEFAULT_WORKSPACE_ID,
            )
        return tuple(dict.fromkeys(int(row["id"]) for row in rows))

    async def process_once(self, *, limit: int = 100) -> int:
        remaining = max(1, min(int(limit), 500))
        delivered = 0
        for workspace_id in await self._workspace_ids():
            if remaining <= 0:
                break
            service = build_public_archive_service(
                self._database,
                workspace_id=workspace_id,
            )
            pending = await service.list_pending_notifications(limit=remaining)
            if not pending:
                continue
            scoped = tuple(
                replace(notification, workspace_id=workspace_id)
                for notification in pending
            )
            dispatcher = TelegramPublicNotificationDispatcher(
                bot=self._bot,
                service=service,
                workspace_id=workspace_id,
            )
            delivered += await dispatcher.deliver(scoped)
            remaining -= len(scoped)
        return delivered


def build_public_notification_dispatcher(
    bot: Bot,
    database: Database,
) -> WorkspacePublicNotificationDispatcher:
    return WorkspacePublicNotificationDispatcher(bot=bot, database=database)


__all__ = (
    "WorkspacePublicNotificationDispatcher",
    "build_public_notification_dispatcher",
)
