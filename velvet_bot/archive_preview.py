from __future__ import annotations

from aiogram import Bot
from aiogram.types import Message, PhotoSize

from velvet_bot.app.archive_previews import build_archive_preview_resolver
from velvet_bot.database import Database
from velvet_bot.domains.archive import ArchivePage
from velvet_bot.domains.archive.preview_models import PreviewPayload, PreviewRecord
from velvet_bot.domains.archive.preview_repository import ArchivePreviewRepository
from velvet_bot.infrastructure.telegram.archive_previews import (
    DEFAULT_BOT_API_DOWNLOAD_LIMIT,
    FULL_QUALITY_PHOTO_SOURCE,
    PreviewMedia,
    TelegramArchivePreviewResolver,
    is_telegram_thumbnail_source,
    message_thumbnail,
)

_message_thumbnail = message_thumbnail
_is_telegram_thumbnail_source = is_telegram_thumbnail_source


async def _load_preview_record(
    database: Database,
    *,
    character_id: int,
    media_id: int,
) -> PreviewRecord:
    return await ArchivePreviewRepository(database).load(
        character_id=character_id,
        media_id=media_id,
    )


async def _download_thumbnail_as_photo(
    bot: Bot,
    *,
    file_id: str,
):
    resolver = TelegramArchivePreviewResolver(bot=bot, repository=None)  # type: ignore[arg-type]
    return await resolver._download_thumbnail_as_photo(file_id=file_id)


async def _forward_for_thumbnail(
    bot: Bot,
    *,
    cache_chat_id: int,
    from_chat_id: int,
    message_id: int,
) -> PhotoSize | None:
    resolver = TelegramArchivePreviewResolver(bot=bot, repository=None)  # type: ignore[arg-type]
    return await resolver._forward_for_thumbnail(
        cache_chat_id=cache_chat_id,
        from_chat_id=from_chat_id,
        message_id=message_id,
    )


async def _resend_document_for_thumbnail(
    bot: Bot,
    *,
    cache_chat_id: int,
    file_id: str,
) -> PhotoSize | None:
    resolver = TelegramArchivePreviewResolver(bot=bot, repository=None)  # type: ignore[arg-type]
    return await resolver._resend_document_for_thumbnail(
        cache_chat_id=cache_chat_id,
        file_id=file_id,
    )


async def _store_thumbnail(
    database: Database,
    page: ArchivePage,
    thumbnail: PhotoSize,
    *,
    source: str,
) -> str | None:
    if page.media is None:
        return None
    await ArchivePreviewRepository(database).save(
        media_id=page.media.id,
        preview=PreviewPayload(
            file_id=thumbnail.file_id,
            file_unique_id=thumbnail.file_unique_id,
            width=thumbnail.width,
            height=thumbnail.height,
            source=source,
        ),
    )
    return thumbnail.file_id


async def _recover_stored_thumbnail(
    bot: Bot,
    database: Database,
    page: ArchivePage,
    *,
    cache_chat_id: int,
    record: PreviewRecord,
) -> str | None:
    resolver = build_archive_preview_resolver(bot, database)
    return await resolver._recover_stored_thumbnail(
        page,
        cache_chat_id=cache_chat_id,
        record=record,
    )


async def resolve_archive_image_preview(
    bot: Bot,
    database: Database,
    page: ArchivePage,
    *,
    cache_chat_id: int,
) -> PreviewMedia | None:
    return await build_archive_preview_resolver(bot, database).resolve(
        page,
        cache_chat_id=cache_chat_id,
    )


async def persist_preview_from_sent_message(
    database: Database,
    *,
    media_id: int,
    message: Message,
    source: str = FULL_QUALITY_PHOTO_SOURCE,
) -> None:
    preview = message_thumbnail(message)
    if preview is None:
        return
    await ArchivePreviewRepository(database).save(
        media_id=media_id,
        preview=PreviewPayload(
            file_id=preview.file_id,
            file_unique_id=preview.file_unique_id,
            width=preview.width,
            height=preview.height,
            source=source,
        ),
    )


__all__ = (
    "DEFAULT_BOT_API_DOWNLOAD_LIMIT",
    "FULL_QUALITY_PHOTO_SOURCE",
    "PreviewMedia",
    "PreviewRecord",
    "persist_preview_from_sent_message",
    "resolve_archive_image_preview",
)
