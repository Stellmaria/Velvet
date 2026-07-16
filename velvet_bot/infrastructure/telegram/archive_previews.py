from __future__ import annotations

import io
import logging
from typing import TypeAlias

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, Message, PhotoSize

from velvet_bot.domains.archive import ArchivePage
from velvet_bot.domains.archive.preview_models import PreviewPayload, PreviewRecord
from velvet_bot.domains.archive.preview_repository import ArchivePreviewRepository
from velvet_bot.image_preview import build_image_document_preview

logger = logging.getLogger(__name__)

DEFAULT_BOT_API_DOWNLOAD_LIMIT = 20 * 1024 * 1024
PreviewMedia: TypeAlias = str | BufferedInputFile


def message_thumbnail(message: Message) -> PhotoSize | None:
    if message.document and message.document.thumbnail:
        return message.document.thumbnail
    if message.video and message.video.thumbnail:
        return message.video.thumbnail
    if message.animation and message.animation.thumbnail:
        return message.animation.thumbnail
    if message.photo:
        return message.photo[-1]
    return None


def is_telegram_thumbnail_source(source: str | None) -> bool:
    return bool(source and "thumbnail" in source.casefold())


class TelegramArchivePreviewResolver:
    """Resolve a photo-compatible archive preview through Telegram infrastructure."""

    def __init__(
        self,
        *,
        bot: Bot,
        repository: ArchivePreviewRepository,
    ) -> None:
        self._bot = bot
        self._repository = repository

    async def resolve(
        self,
        page: ArchivePage,
        *,
        cache_chat_id: int,
    ) -> PreviewMedia | None:
        if page.media is None or not page.media.is_image_document:
            return None

        record = await self._repository.load(
            character_id=page.character.id,
            media_id=page.media.id,
        )
        if record.file_id:
            if is_telegram_thumbnail_source(record.source):
                thumbnail_photo = await self._download_thumbnail_as_photo(
                    file_id=record.file_id,
                )
                if thumbnail_photo is not None:
                    return thumbnail_photo
            else:
                return record.file_id

        file_size = page.media.file_size
        if file_size is None or file_size <= DEFAULT_BOT_API_DOWNLOAD_LIMIT:
            try:
                return await build_image_document_preview(self._bot, page.media)
            except Exception as error:
                logger.info(
                    "Could not generate preview from original media_id=%s: %s",
                    page.media.id,
                    error,
                )

        thumbnail_file_id = await self._recover_stored_thumbnail(
            page,
            cache_chat_id=cache_chat_id,
            record=record,
        )
        if thumbnail_file_id is None:
            return None
        return await self._download_thumbnail_as_photo(file_id=thumbnail_file_id)

    async def persist_from_message(
        self,
        *,
        media_id: int,
        message: Message,
        source: str = "generated_preview",
    ) -> None:
        preview = message_thumbnail(message)
        if preview is None:
            return
        await self._repository.save(
            media_id=media_id,
            preview=PreviewPayload(
                file_id=preview.file_id,
                file_unique_id=preview.file_unique_id,
                width=preview.width,
                height=preview.height,
                source=source,
            ),
        )

    async def _download_thumbnail_as_photo(
        self,
        *,
        file_id: str,
    ) -> BufferedInputFile | None:
        destination = io.BytesIO()
        try:
            await self._bot.download(file_id, destination=destination, seek=True)
        except TelegramAPIError as error:
            logger.info("Could not download stored Telegram thumbnail: %s", error)
            return None
        payload = destination.getvalue()
        if not payload:
            logger.info("Telegram returned an empty stored thumbnail file")
            return None
        return BufferedInputFile(payload, filename="archive_thumbnail.jpg")

    async def _forward_for_thumbnail(
        self,
        *,
        cache_chat_id: int,
        from_chat_id: int,
        message_id: int,
    ) -> PhotoSize | None:
        forwarded: Message | None = None
        try:
            forwarded = await self._bot.forward_message(
                chat_id=cache_chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                disable_notification=True,
            )
            return message_thumbnail(forwarded)
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
                    await self._bot.delete_message(
                        chat_id=cache_chat_id,
                        message_id=forwarded.message_id,
                    )
                except TelegramAPIError:
                    pass

    async def _resend_document_for_thumbnail(
        self,
        *,
        cache_chat_id: int,
        file_id: str,
    ) -> PhotoSize | None:
        temporary: Message | None = None
        try:
            temporary = await self._bot.send_document(
                chat_id=cache_chat_id,
                document=file_id,
                disable_notification=True,
            )
            return message_thumbnail(temporary)
        except TelegramAPIError as error:
            logger.info("Could not recover preview by resending document: %s", error)
            return None
        finally:
            if temporary is not None:
                try:
                    await self._bot.delete_message(
                        chat_id=cache_chat_id,
                        message_id=temporary.message_id,
                    )
                except TelegramAPIError:
                    pass

    async def _store_thumbnail(
        self,
        page: ArchivePage,
        thumbnail: PhotoSize,
        *,
        source: str,
    ) -> str | None:
        if page.media is None:
            return None
        await self._repository.save(
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
        self,
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
                (
                    record.source_chat_id,
                    record.source_message_id,
                    "source_forward_thumbnail",
                )
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
            thumbnail = await self._forward_for_thumbnail(
                cache_chat_id=cache_chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
            )
            if thumbnail is not None:
                return await self._store_thumbnail(
                    page,
                    thumbnail,
                    source=source,
                )

        thumbnail = await self._resend_document_for_thumbnail(
            cache_chat_id=cache_chat_id,
            file_id=page.media.telegram_file_id,
        )
        if thumbnail is not None:
            return await self._store_thumbnail(
                page,
                thumbnail,
                source="document_resend_thumbnail",
            )
        return None


__all__ = (
    "DEFAULT_BOT_API_DOWNLOAD_LIMIT",
    "PreviewMedia",
    "TelegramArchivePreviewResolver",
    "is_telegram_thumbnail_source",
    "message_thumbnail",
)
