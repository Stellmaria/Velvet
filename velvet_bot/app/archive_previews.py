from __future__ import annotations

from aiogram import Bot

from velvet_bot.database import Database
from velvet_bot.domains.archive.preview_repository import ArchivePreviewRepository
from velvet_bot.infrastructure.telegram.archive_previews import (
    TelegramArchivePreviewResolver,
)


def build_archive_preview_resolver(
    bot: Bot,
    database: Database,
) -> TelegramArchivePreviewResolver:
    return TelegramArchivePreviewResolver(
        bot=bot,
        repository=ArchivePreviewRepository(database),
    )


__all__ = ("build_archive_preview_resolver",)
