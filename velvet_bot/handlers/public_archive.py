from __future__ import annotations

import io
import logging

from aiogram import Bot, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, InputMediaPhoto, Message

from velvet_bot.archive_catalog import ArchivePage, ArchivedMedia, get_archive_page
from velvet_bot.archive_ui import build_input_media
from velvet_bot.database import Database
from velvet_bot.public_catalog import (
    get_public_media_state,
    list_public_categories,
    list_public_characters,
    list_public_universes,
    toggle_character_subscription,
    toggle_public_like,
)
from velvet_bot.public_ui import (
    PUBLIC_DOWNLOAD_USER_ID,
    PublicArchiveCallback,
    build_public_archive_keyboard,
    build_public_category_menu,
    build_public_character_menu,
    build_public_universe_menu,
    format_public_archive_caption,
    format_public_categories,
    format_public_menu,
    format_public_universes,
)

router = Router(name=__name__)
logger = logging.getLogger(__name__)


async def _download_image_for_preview(bot: Bot, media: ArchivedMedia) -> BufferedInputFile:
    destination = io.BytesIO()
    await bot.download(media.telegram_file_id, destination=destination, seek=True)
    return BufferedInputFile(destination.getvalue(), filename=media.display_file_name)


async def _load_state(database: Database, page: ArchivePage, user_id: int):
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")
    return await get_public_media_state(
        database,
        character_id=page.character.id,
        media_id=page.media.id,
        user_id=user_id,
    )


async def _build_public_input_media(bot: Bot, page: ArchivePage, state):
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")
    caption = format_public_archive_caption(page, state)
    if page.media.is_image_document:
        try:
            upload = await _download_image_for_preview(bot, page.media)
            return InputMediaPhoto(media=upload, caption=caption, parse_mode=ParseMode.HTML)
        except Exception:
            logger.exception("Failed to build public image-document preview")
    return build_input_media(page.media, caption)


async def _send_public_archive_page(
    *,
    bot: Bot,
    database: Database,
    chat_id: int,
    page: ArchivePage,
    viewer_user_id: int,
    menu_page: int,
    category: str = "",
    universe: str = "",
) -> Message:
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")

    state = await _load_state(database, page, viewer_user_id)
    caption = format_public_archive_caption(page, state)
    keyboard = build_public_archive_keyboard(
        page,
        state,
        viewer_user_id=viewer_user_id,
        menu_page=menu_page,
        category=category,
        universe=universe,
    )
    common = {"chat_id": chat_id, "caption": caption, "reply_markup": keyboard}

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
            logger.info("Public image preview fallback to document: %s", error)
        except Exception:
            logger.exception("Public image preview download failed")
    return await bot.send_document(document=page.media.telegram_file_id, **common)


async def _replace_public_archive_page(
    *,
    callback: CallbackQuery,
    bot: Bot,
    database: Database,
    page: ArchivePage,
    menu_page: int,
    category: str,
    universe: str,
) -> None:
    if page.media is None or not isinstance(callback.message, Message):
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return

    state = await _load_state(database, page, callback.from_user.id)
    media = await _build_public_input_media(bot, page, state)
    keyboard = build_public_archive_keyboard(
        page,
        state,
        viewer_user_id=callback.from_user.id,
        menu_page=menu_page,
        category=category,
        universe=universe,
    )
    try:
        await callback.message.edit_media(media=media, reply_markup=keyboard)
    except TelegramBadRequest as error:
        logger.info("Public archive edit fallback: %s", error)
        await _send_public_archive_page(
            bot=bot,
            database=database,
            chat_id=callback.message.chat.id,
            page=page,
            viewer_user_id=callback.from_user.id,
            menu_page=menu_page,
            category=category,
            universe=universe,
        )
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
    await callback.answer()


async def _send_category_menu(*, bot: Bot, database: Database, chat_id: int) -> Message:
    summaries = await list_public_categories(database)
    return await bot.send_message(
        chat_id=chat_id,
        text=format_public_categories(summaries),
        reply_markup=build_public_category_menu(summaries),
    )


async def _edit_category_menu(callback: CallbackQuery, database: Database) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    summaries = await list_public_categories(database)
    try:
        await callback.message.edit_text(
            text=format_public_categories(summaries),
            reply_markup=build_public_category_menu(summaries),
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
    await callback.answer()


async def _send_universe_menu(
    *,
    bot: Bot,
    database: Database,
    chat_id: int,
    category: str,
) -> Message:
    summaries = await list_public_universes(database, category=category)
    return await bot.send_message(
        chat_id=chat_id,
        text=format_public_universes(category, summaries),
        reply_markup=build_public_universe_menu(category, summaries),
    )


async def _edit_universe_menu(
    callback: CallbackQuery,
    database: Database,
    category: str,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    summaries = await list_public_universes(database, category=category)
    try:
        await callback.message.edit_text(
            text=format_public_universes(category, summaries),
            reply_markup=build_public_universe_menu(category, summaries),
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
    await callback.answer()


async def _send_public_menu(
    *,
    bot: Bot,
    database: Database,
    chat_id: int,
    category: str,
    universe: str,
    page_number: int,
) -> Message:
    page = await list_public_characters(
        database,
        category=category,
        universe=universe,
        page=page_number,
    )
    return await bot.send_message(
        chat_id=chat_id,
        text=format_public_menu(page),
        reply_markup=build_public_character_menu(page),
    )


async def _edit_public_menu(
    callback: CallbackQuery,
    database: Database,
    category: str,
    universe: str,
    page_number: int,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    page = await list_public_characters(
        database,
        category=category,
        universe=universe,
        page=page_number,
    )
    try:
        await callback.message.edit_text(
            text=format_public_menu(page),
            reply_markup=build_public_character_menu(page),
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
    await callback.answer()


async def _send_as_document(*, bot: Bot, media: ArchivedMedia, chat_id: int) -> Message:
    if media.media_type == "document":
        return await bot.send_document(
            chat_id=chat_id,
            document=media.telegram_file_id,
            caption="Файл из Velvet Archive",
        )
    destination = io.BytesIO()
    await bot.download(media.telegram_file_id, destination=destination, seek=True)
    payload = destination.getvalue()
    if not payload:
        raise RuntimeError("Telegram вернул пустой файл.")
    return await bot.send_document(
        chat_id=chat_id,
        document=BufferedInputFile(payload, filename=media.display_file_name),
        caption="Файл из Velvet Archive",
    )


def _page_matches_callback(page: ArchivePage, data: PublicArchiveCallback) -> bool:
    return bool(page.media and (data.media_id == 0 or page.media.id == data.media_id))


@router.message(Command("archive", "gallery", "menu"))
async def handle_public_archive_menu(message: Message, database: Database) -> None:
    summaries = await list_public_categories(database)
    await message.answer(
        format_public_categories(summaries),
        reply_markup=build_public_category_menu(summaries),
    )


@router.callback_query(PublicArchiveCallback.filter())
async def handle_public_archive_callback(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
) -> None:
    action = callback_data.action
    if action == "noop":
        await callback.answer()
        return
    if action == "close":
        if isinstance(callback.message, Message):
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
        await callback.answer()
        return
    if action == "categories":
        try:
            await _edit_category_menu(callback, database)
        except TelegramBadRequest:
            if isinstance(callback.message, Message):
                await _send_category_menu(
                    bot=bot, database=database, chat_id=callback.message.chat.id
                )
                await callback.answer()
        return
    if action == "universes":
        if not callback_data.category:
            await callback.answer("Сначала выберите пол или состав.", show_alert=True)
            return
        try:
            await _edit_universe_menu(callback, database, callback_data.category)
        except TelegramBadRequest:
            if isinstance(callback.message, Message):
                await _send_universe_menu(
                    bot=bot,
                    database=database,
                    chat_id=callback.message.chat.id,
                    category=callback_data.category,
                )
                await callback.answer()
        return
    if action == "menu":
        if not callback_data.category or not callback_data.universe:
            await callback.answer("Фильтр архива выбран не полностью.", show_alert=True)
            return
        await _edit_public_menu(
            callback,
            database,
            callback_data.category,
            callback_data.universe,
            callback_data.page,
        )
        return
    if action == "back":
        if not isinstance(callback.message, Message):
            await callback.answer("Сообщение больше недоступно.", show_alert=True)
            return
        chat_id = callback.message.chat.id
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        if callback_data.category and callback_data.universe:
            await _send_public_menu(
                bot=bot,
                database=database,
                chat_id=chat_id,
                category=callback_data.category,
                universe=callback_data.universe,
                page_number=callback_data.page,
            )
        elif callback_data.category:
            await _send_universe_menu(
                bot=bot,
                database=database,
                chat_id=chat_id,
                category=callback_data.category,
            )
        else:
            await _send_category_menu(bot=bot, database=database, chat_id=chat_id)
        await callback.answer()
        return

    page = await get_archive_page(
        database, callback_data.character_id, callback_data.offset
    )
    if page is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    if page.media is None:
        await callback.answer("Архив персонажа пока пуст.", show_alert=True)
        return

    if action == "open":
        if not isinstance(callback.message, Message):
            await callback.answer("Не удалось определить чат.", show_alert=True)
            return
        try:
            await _send_public_archive_page(
                bot=bot,
                database=database,
                chat_id=callback.message.chat.id,
                page=page,
                viewer_user_id=callback.from_user.id,
                menu_page=callback_data.page,
                category=callback_data.category,
                universe=callback_data.universe,
            )
        except TelegramBadRequest:
            logger.exception("Failed to open public archive item")
            await callback.answer(
                "Telegram больше не может открыть этот материал.", show_alert=True
            )
            return
        await callback.answer()
        return

    if action == "show":
        await _replace_public_archive_page(
            callback=callback,
            bot=bot,
            database=database,
            page=page,
            menu_page=callback_data.page,
            category=callback_data.category,
            universe=callback_data.universe,
        )
        return

    if not _page_matches_callback(page, callback_data):
        await callback.answer(
            "Архив изменился. Откройте материал заново.", show_alert=True
        )
        return

    if action == "like":
        try:
            liked, _ = await toggle_public_like(
                database,
                character_id=page.character.id,
                media_id=page.media.id,
                user_id=callback.from_user.id,
            )
            state = await _load_state(database, page, callback.from_user.id)
            keyboard = build_public_archive_keyboard(
                page,
                state,
                viewer_user_id=callback.from_user.id,
                menu_page=callback_data.page,
                category=callback_data.category,
                universe=callback_data.universe,
            )
            if isinstance(callback.message, Message):
                await callback.message.edit_caption(
                    caption=format_public_archive_caption(page, state),
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            await callback.answer("Отметка поставлена." if liked else "Отметка снята.")
        except Exception:
            logger.exception("Failed to toggle public archive like")
            await callback.answer("Не удалось изменить отметку.", show_alert=True)
        return

    if action == "sub":
        try:
            subscribed = await toggle_character_subscription(
                database,
                character_id=page.character.id,
                user_id=callback.from_user.id,
            )
            state = await _load_state(database, page, callback.from_user.id)
            keyboard = build_public_archive_keyboard(
                page,
                state,
                viewer_user_id=callback.from_user.id,
                menu_page=callback_data.page,
                category=callback_data.category,
                universe=callback_data.universe,
            )
            if isinstance(callback.message, Message):
                await callback.message.edit_reply_markup(reply_markup=keyboard)
            await callback.answer(
                "Подписка включена. Новые материалы придут сюда."
                if subscribed
                else "Подписка отключена.",
                show_alert=True,
            )
        except Exception:
            logger.exception("Failed to toggle character subscription")
            await callback.answer("Не удалось изменить подписку.", show_alert=True)
        return

    if action == "download":
        if callback.from_user.id != PUBLIC_DOWNLOAD_USER_ID:
            await callback.answer("Скачивание файлов для вас закрыто.", show_alert=True)
            return
        try:
            await _send_as_document(
                bot=bot, media=page.media, chat_id=PUBLIC_DOWNLOAD_USER_ID
            )
            await callback.answer("Файл отправлен в личный чат.")
        except Exception:
            logger.exception("Failed to send public archive download")
            await callback.answer("Не удалось отправить файл.", show_alert=True)
        return

    await callback.answer("Неизвестное действие.", show_alert=True)
