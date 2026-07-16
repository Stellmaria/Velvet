from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import TypeAlias

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, Message, PhotoSize

from velvet_bot.archive_catalog import ArchivePage
from velvet_bot.database import Database
from velvet_bot.image_preview import build_image_document_preview
from velvet_bot.media_preview_persistence import set_media_preview

logger = logging.getLogger(__name__)

DEFAULT_BOT_API_DOWNLOAD_LIMIT = 20 * 1024 * 1024
PreviewMedia: TypeAlias = str | BufferedInputFile


@dataclass(frozen=True, slots=True)
class PreviewRecord:
    file_id: str | None
    file_unique_id: str | None
    width: int | None
    height: int | None
    source: str | None
    source_chat_id: int | None
    source_message_id: int | None
    archive_chat_id: int | None
    archive_message_id: int | None


async def _load_preview_record(
    database: Database,
    *,
    character_id: int,
    media_id: int,
) -> PreviewRecord:
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                mf.preview_file_id,
                mf.preview_file_unique_id,
                mf.preview_width,
                mf.preview_height,
                mf.preview_source,
                cm.source_chat_id,
                cm.source_message_id,
                c.archive_chat_id,
                cm.archive_message_id
            FROM media_files AS mf
            JOIN character_media AS cm
              ON cm.media_id = mf.id AND cm.character_id = $1
            JOIN characters AS c ON c.id = cm.character_id
            WHERE mf.id = $2
            """,
            character_id,
            media_id,
        )
    if row is None:
        return PreviewRecord(None, None, None, None, None, None, None, None, None)
    return PreviewRecord(
        file_id=row["preview_file_id"],
        file_unique_id=row["preview_file_unique_id"],
        width=row["preview_width"],
        height=row["preview_height"],
        source=row["preview_source"],
        source_chat_id=row["source_chat_id"],
        source_message_id=row["source_message_id"],
        archive_chat_id=row["archive_chat_id"],
        archive_message_id=row["archive_message_id"],
    )


def _message_thumbnail(message: Message) -> PhotoSize | None:
    if message.document and message.document.thumbnail:
        return message.document.thumbnail
    if message.video and message.video.thumbnail:
        return message.video.thumbnail
    if message.animation and message.animation.thumbnail:
        return message.animation.thumbnail
    if message.photo:
        return message.photo[-1]
    return None


def _is_telegram_thumbnail_source(source: str | None) -> bool:
    return bool(source and "thumbnail" in source.casefold())


async def _download_thumbnail_as_photo(
    bot: Bot,
    *,
    file_id: str,
) -> BufferedInputFile | None:
    """Re-upload a Telegram thumbnail as a real photo-compatible file.

    Telegram thumbnail file IDs cannot be passed directly to sendPhoto. Downloading
    the thumbnail bytes and uploading them again turns it into a normal photo.
    """
    destination = io.BytesIO()
    try:
        await bot.download(file_id, destination=destination, seek=True)
    except TelegramAPIError as error:
        logger.info("Could not download stored Telegram thumbnail: %s", error)
        return None

    payload = destination.getvalue()
    if not payload:
        logger.info("Telegram returned an empty stored thumbnail file")
        return None

    return BufferedInputFile(payload, filename="archive_thumbnail.jpg")


async def _forward_for_thumbnail(
    bot: Bot,
    *,
    cache_chat_id: int,
    from_chat_id: int,
    message_id: int,
) -> PhotoSize | None:
    forwarded: Message | None = None
    try:
        forwarded = await bot.forward_message(
            chat_id=cache_chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            disable_notification=True,
        )
        return _message_thumbnail(forwarded)
    except TelegramAPIError as error:
        logger.info(
            "Could not recover preview from %s/%s: %s",
            from_chat_id,
            message_id,
            error,
        )
        return None
    finally:
        if forwarded is not None:
            try:
                await bot.delete_message(
                    chat_id=cache_chat_id,
                    message_id=forwarded.message_id,
                )
            except TelegramAPIError:
                pass


async def _resend_document_for_thumbnail(
    bot: Bot,
    *,
    cache_chat_id: int,
    file_id: str,
) -> PhotoSize | None:
    """Ask Telegram to expose the document thumbnail without downloading the file."""
    temporary: Message | None = None
    try:
        temporary = await bot.send_document(
            chat_id=cache_chat_id,
            document=file_id,
            disable_notification=True,
        )
        return _message_thumbnail(temporary)
    except TelegramAPIError as error:
        logger.info("Could not recover preview by resending document: %s", error)
        return None
    finally:
        if temporary is not None:
            try:
                await bot.delete_message(
                    chat_id=cache_chat_id,
                    message_id=temporary.message_id,
                )
            except TelegramAPIError:
                pass


async def _store_thumbnail(
    database: Database,
    page: ArchivePage,
    thumbnail: PhotoSize,
    *,
    source: str,
) -> str | None:
    if page.media is None:
        return None
    await set_media_preview(
        database,
        media_id=page.media.id,
        file_id=thumbnail.file_id,
        file_unique_id=thumbnail.file_unique_id,
        width=thumbnail.width,
        height=thumbnail.height,
        source=source,
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
    if page.media is None:
        return None

    sources: list[tuple[int, int, str]] = []
    if record.source_chat_id and record.source_message_id:
        sources.append(
            (record.source_chat_id, record.source_message_id, "source_forward_thumbnail")
        )
    if record.archive_chat_id and record.archive_message_id:
        candidate = (
            record.archive_chat_id,
            record.archive_message_id,
            "archive_forward_thumbnail",
        )
        if candidate[:2] not in [item[:2] for item in sources]:
            sources.append(candidate)

    for from_chat_id, message_id, source in sources:
        thumbnail = await _forward_for_thumbnail(
            bot,
            cache_chat_id=cache_chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
        )
        if thumbnail is not None:
            return await _store_thumbnail(
                database,
                page,
                thumbnail,
                source=source,
            )

    thumbnail = await _resend_document_for_thumbnail(
        bot,
        cache_chat_id=cache_chat_id,
        file_id=page.media.telegram_file_id,
    )
    if thumbnail is not None:
        return await _store_thumbnail(
            database,
            page,
            thumbnail,
            source="document_resend_thumbnail",
        )
    return None


async def resolve_archive_image_preview(
    bot: Bot,
    database: Database,
    page: ArchivePage,
    *,
    cache_chat_id: int,
) -> PreviewMedia | None:
    """Return a photo-compatible preview for an image document.

    Stored photo IDs are reused directly. Telegram document thumbnails are
    downloaded and re-uploaded because their file IDs are not valid for sendPhoto.
    Smaller original files can be converted into a high-resolution JPEG preview.
    """
    if page.media is None or not page.media.is_image_document:
        return None

    record = await _load_preview_record(
        database,
        character_id=page.character.id,
        media_id=page.media.id,
    )
    if record.file_id:
        if _is_telegram_thumbnail_source(record.source):
            thumbnail_photo = await _download_thumbnail_as_photo(
                bot,
                file_id=record.file_id,
            )
            if thumbnail_photo is not None:
                return thumbnail_photo
        else:
            return record.file_id

    file_size = page.media.file_size
    if file_size is None or file_size <= DEFAULT_BOT_API_DOWNLOAD_LIMIT:
        try:
            return await build_image_document_preview(bot, page.media)
        except Exception as error:
            logger.info(
                "Could not generate preview from original media_id=%s: %s",
                page.media.id,
                error,
            )

    thumbnail_file_id = await _recover_stored_thumbnail(
        bot,
        database,
        page,
        cache_chat_id=cache_chat_id,
        record=record,
    )
    if thumbnail_file_id is None:
        return None
    return await _download_thumbnail_as_photo(bot, file_id=thumbnail_file_id)


async def persist_preview_from_sent_message(
    database: Database,
    *,
    media_id: int,
    message: Message,
    source: str = "generated_preview",
) -> None:
    preview = _message_thumbnail(message)
    if preview is None:
        return
    await set_media_preview(
        database,
        media_id=media_id,
        file_id=preview.file_id,
        file_unique_id=preview.file_unique_id,
        width=preview.width,
        height=preview.height,
        source=source,
    )
