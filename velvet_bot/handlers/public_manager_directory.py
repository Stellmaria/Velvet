from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from velvet_bot.database import Database
from velvet_bot.public_catalog import (
    list_public_categories,
    list_public_characters,
    list_public_stories,
    list_public_universes,
)
from velvet_bot.public_ui import (
    PUBLIC_DOWNLOAD_USER_ID,
    PublicArchiveCallback,
    build_public_category_menu,
    build_public_character_menu,
    build_public_story_menu,
    build_public_universe_menu,
    format_public_categories,
    format_public_menu,
    format_public_stories,
    format_public_universes,
)
from velvet_bot.story_catalog import universe_requires_story

router = Router(name=__name__)
_MANAGER_ACTIONS = {"categories", "universes", "stories", "menu", "back"}


async def _replace_text(
    callback: CallbackQuery,
    bot: Bot,
    *,
    text: str,
    reply_markup,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_text(text=text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).casefold():
            return
        chat_id = callback.message.chat.id
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


async def _show_categories(
    *,
    database: Database,
    bot: Bot,
    callback: CallbackQuery | None = None,
    message: Message | None = None,
) -> None:
    summaries = await list_public_categories(database, manager_mode=True)
    text = format_public_categories(summaries)
    keyboard = build_public_category_menu(summaries)
    if callback is not None:
        await _replace_text(callback, bot, text=text, reply_markup=keyboard)
    elif message is not None:
        await message.answer(text, reply_markup=keyboard)


async def _show_universes(
    *,
    callback: CallbackQuery,
    database: Database,
    bot: Bot,
    category: str,
) -> None:
    summaries = await list_public_universes(
        database,
        category=category,
        manager_mode=True,
    )
    await _replace_text(
        callback,
        bot,
        text=format_public_universes(category, summaries),
        reply_markup=build_public_universe_menu(category, summaries),
    )


async def _show_stories(
    *,
    callback: CallbackQuery,
    database: Database,
    bot: Bot,
    category: str,
    universe: str,
) -> None:
    summaries = await list_public_stories(
        database,
        category=category,
        universe=universe,
        manager_mode=True,
    )
    await _replace_text(
        callback,
        bot,
        text=format_public_stories(category, universe, summaries),
        reply_markup=build_public_story_menu(category, universe, summaries),
    )


async def _show_characters(
    *,
    callback: CallbackQuery,
    database: Database,
    bot: Bot,
    category: str,
    universe: str,
    story_id: int,
    page_number: int,
) -> None:
    page = await list_public_characters(
        database,
        category=category,
        universe=universe,
        story_id=story_id or None,
        page=page_number,
        manager_mode=True,
    )
    await _replace_text(
        callback,
        bot,
        text=format_public_menu(page),
        reply_markup=build_public_character_menu(page),
    )


@router.message(Command("archive", "gallery", "menu"), F.from_user.id == PUBLIC_DOWNLOAD_USER_ID)
async def handle_manager_archive_menu(
    message: Message,
    database: Database,
    bot: Bot,
) -> None:
    await _show_categories(database=database, bot=bot, message=message)


@router.callback_query(
    F.from_user.id == PUBLIC_DOWNLOAD_USER_ID,
    PublicArchiveCallback.filter(F.action.in_(_MANAGER_ACTIONS)),
)
async def handle_manager_directory(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
) -> None:
    action = callback_data.action

    if action == "categories":
        await _show_categories(database=database, bot=bot, callback=callback)
        await callback.answer()
        return

    if action == "universes":
        if not callback_data.category:
            await callback.answer("Сначала выберите пол или состав.", show_alert=True)
            return
        await _show_universes(
            callback=callback,
            database=database,
            bot=bot,
            category=callback_data.category,
        )
        await callback.answer()
        return

    if action == "stories":
        if not callback_data.category or not callback_data.universe:
            await callback.answer("Сначала выберите вселенную.", show_alert=True)
            return
        await _show_stories(
            callback=callback,
            database=database,
            bot=bot,
            category=callback_data.category,
            universe=callback_data.universe,
        )
        await callback.answer()
        return

    if action == "menu":
        if not callback_data.category or not callback_data.universe:
            await callback.answer("Фильтр архива выбран не полностью.", show_alert=True)
            return
        if universe_requires_story(callback_data.universe) and callback_data.story_id == 0:
            await callback.answer("Сначала выберите историю.", show_alert=True)
            return
        await _show_characters(
            callback=callback,
            database=database,
            bot=bot,
            category=callback_data.category,
            universe=callback_data.universe,
            story_id=callback_data.story_id,
            page_number=callback_data.page,
        )
        await callback.answer()
        return

    if action == "back":
        if callback_data.category and callback_data.universe:
            await _show_characters(
                callback=callback,
                database=database,
                bot=bot,
                category=callback_data.category,
                universe=callback_data.universe,
                story_id=callback_data.story_id,
                page_number=callback_data.page,
            )
        elif callback_data.category:
            await _show_universes(
                callback=callback,
                database=database,
                bot=bot,
                category=callback_data.category,
            )
        else:
            await _show_categories(database=database, bot=bot, callback=callback)
        await callback.answer()
