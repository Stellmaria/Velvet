from __future__ import annotations

import io
import logging

from aiogram import Bot, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InputMediaPhoto,
    Message,
)

from velvet_bot.archive_catalog import (
    ArchivePage,
    ArchivedMedia,
    delete_archive_item,
    get_archive_page,
)
from velvet_bot.archive_ui import (
    ArchiveMediaCallback,
    build_archive_navigation,
    build_delete_confirmation,
    build_input_media,
    format_archive_caption,
    format_delete_caption,
)
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Database

router = Router(name=__name__)
logger = logging.getLogger(__name__)


async def _download_image_for_preview(
    bot: Bot,
    media: ArchivedMedia,
) -> BufferedInputFile:
    destination = io.BytesIO()
    await bot.download(
        media.telegram_file_id,
        destination=destination,
        seek=True,
    )
    return BufferedInputFile(
        destination.getvalue(),
        filename=media.display_file_name,
    )


async def _build_display_input_media(
    bot: Bot,
    media: ArchivedMedia,
    caption: str,
):
    if media.is_image_document:
        try:
            upload = await _download_image_for_preview(bot, media)
            return InputMediaPhoto(
                media=upload,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.exception("Failed to prepare full-size image preview")

    return build_input_media(media, caption)


async def _send_archive_page(
    bot: Bot,
    chat_id: int,
    page: ArchivePage,
) -> Message:
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")

    caption = format_archive_caption(page)
    keyboard = build_archive_navigation(page)
    common = {
        "chat_id": chat_id,
        "caption": caption,
        "reply_markup": keyboard,
    }

    if page.media.media_type == "photo":
        return await bot.send_photo(photo=page.media.telegram_file_id, **common)
    if page.media.media_type == "video":
        return await bot.send_video(video=page.media.telegram_file_id, **common)
    if page.media.media_type == "animation":
        return await bot.send_animation(animation=page.media.telegram_file_id, **common)
    if page.media.is_image_document:
        try:
            upload = await _download_image_for_preview(bot, page.media)
            return await bot.send_photo(photo=upload, **common)
        except TelegramAPIError as error:
            logger.info("Image preview fallback to document: %s", error)
        except Exception:
            logger.exception("Image preview download failed; using document")
    return await bot.send_document(document=page.media.telegram_file_id, **common)


async def _replace_archive_page(
    callback: CallbackQuery,
    bot: Bot,
    page: ArchivePage,
) -> None:
    if page.media is None:
        await callback.answer("Архив персонажа пуст.", show_alert=True)
        return

    callback_message = callback.message
    if not isinstance(callback_message, Message):
        await callback.answer("Сообщение архива больше недоступно.", show_alert=True)
        return

    input_media = await _build_display_input_media(
        bot,
        page.media,
        format_archive_caption(page),
    )
    keyboard = build_archive_navigation(page)

    try:
        await callback_message.edit_media(
            media=input_media,
            reply_markup=keyboard,
        )
    except TelegramBadRequest as edit_error:
        logger.info("Archive media edit fallback: %s", edit_error)
        try:
            await _send_archive_page(bot, callback_message.chat.id, page)
        except TelegramBadRequest as send_error:
            logger.warning("Archived Telegram file is unavailable: %s", send_error)
            await callback.answer(
                "Telegram больше не может открыть этот файл.",
                show_alert=True,
            )
            return

        try:
            await callback_message.delete()
        except TelegramBadRequest:
            pass

    await callback.answer()


async def _show_delete_confirmation(
    callback: CallbackQuery,
    page: ArchivePage,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение архива больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_caption(
            caption=format_delete_caption(page),
            parse_mode=ParseMode.HTML,
            reply_markup=build_delete_confirmation(page),
        )
    except TelegramBadRequest as error:
        logger.info("Failed to show delete confirmation: %s", error)
        await callback.answer("Не удалось открыть подтверждение.", show_alert=True)
        return
    await callback.answer()


async def _delete_current_item(
    callback: CallbackQuery,
    callback_data: ArchiveMediaCallback,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    page: ArchivePage,
) -> None:
    if page.media is None:
        await callback.answer("Архив уже пуст.", show_alert=True)
        return

    deleted = await delete_archive_item(
        database,
        callback_data.character_id,
        callback_data.media_id or page.media.id,
    )
    if deleted is None:
        await callback.answer("Медиа уже удалено.", show_alert=True)
        return

    topic_deleted = False
    if (
        deleted.media.archive_message_id is not None
        and deleted.character.archive_chat_id is not None
    ):
        try:
            await bot.delete_message(
                chat_id=deleted.character.archive_chat_id,
                message_id=deleted.media.archive_message_id,
            )
            topic_deleted = True
        except TelegramAPIError as error:
            logger.warning("Could not delete archive topic message: %s", error)
            await audit_logger.error(
                "Не удалось удалить медиа из ветки",
                error,
                character=deleted.character.name,
                file=deleted.media.display_file_name,
                archive_chat_id=deleted.character.archive_chat_id,
                archive_message_id=deleted.media.archive_message_id,
            )

    await audit_logger.send(
        "Медиа удалено из архива",
        level="SUCCESS",
        character=deleted.character.name,
        file=deleted.media.display_file_name,
        media_id=deleted.media.id,
        remaining=deleted.remaining_total,
        topic_message_deleted=topic_deleted,
        database_file_pruned=deleted.orphan_media_removed,
        deleted_by=callback.from_user.id,
    )

    if not isinstance(callback.message, Message):
        await callback.answer("Удалено.", show_alert=True)
        return

    if deleted.remaining_total == 0:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.answer("Удалено. Архив персонажа пуст.", show_alert=True)
        return

    next_offset = min(page.offset, deleted.remaining_total - 1)
    next_page = await get_archive_page(
        database,
        callback_data.character_id,
        next_offset,
    )
    if next_page is None or next_page.media is None:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.answer("Удалено.", show_alert=True)
        return

    await _replace_archive_page(callback, bot, next_page)


@router.callback_query(ArchiveMediaCallback.filter())
async def handle_archive_media_callback(
    callback: CallbackQuery,
    callback_data: ArchiveMediaCallback,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger | None = None,
) -> None:
    audit_logger = audit_logger or TelegramAuditLogger(bot, None)

    if callback_data.action == "noop":
        await callback.answer()
        return

    if callback_data.action == "close":
        if isinstance(callback.message, Message):
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
        await callback.answer()
        return

    try:
        page = await get_archive_page(
            database,
            callback_data.character_id,
            callback_data.offset,
        )
    except Exception as error:
        logger.exception("Failed to load character archive page")
        await audit_logger.error(
            "Ошибка загрузки архива",
            error,
            character_id=callback_data.character_id,
            offset=callback_data.offset,
            user_id=callback.from_user.id,
        )
        await callback.answer(
            "Не удалось загрузить архив из базы.",
            show_alert=True,
        )
        return

    if page is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    if page.media is None:
        await callback.answer("Архив персонажа пока пуст.", show_alert=True)
        return

    if callback_data.action == "open":
        if not isinstance(callback.message, Message):
            await callback.answer("Не удалось определить чат.", show_alert=True)
            return
        try:
            await _send_archive_page(bot, callback.message.chat.id, page)
        except TelegramBadRequest as error:
            logger.warning("Failed to send archived media: %s", error)
            await audit_logger.error(
                "Ошибка показа медиа",
                error,
                character=page.character.name,
                file=page.media.display_file_name,
            )
            await callback.answer(
                "Telegram больше не может открыть этот файл.",
                show_alert=True,
            )
            return
        await callback.answer()
        return

    if callback_data.action == "show":
        await _replace_archive_page(callback, bot, page)
        return

    if callback_data.action == "del":
        await _show_delete_confirmation(callback, page)
        return

    if callback_data.action == "delno":
        await _replace_archive_page(callback, bot, page)
        return

    if callback_data.action == "delok":
        try:
            await _delete_current_item(
                callback,
                callback_data,
                database,
                bot,
                audit_logger,
                page,
            )
        except Exception as error:
            logger.exception("Failed to delete archive media")
            await audit_logger.error(
                "Ошибка удаления медиа",
                error,
                character=page.character.name,
                file=page.media.display_file_name,
                user_id=callback.from_user.id,
            )
            await callback.answer("Не удалось удалить медиа.", show_alert=True)
        return

    await callback.answer("Неизвестное действие.", show_alert=True)
