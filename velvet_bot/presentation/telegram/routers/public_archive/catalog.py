from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from velvet_bot.access import AccessPolicy
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.public_catalog import (
    list_public_categories,
    list_public_characters,
    list_public_stories,
    list_public_universes,
)
from velvet_bot.public_manager_access import has_public_manager_access
from velvet_bot.presentation.telegram.workspace_public_access import has_workspace_adult_access
from velvet_bot.public_ui import (
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
_MENU_ACTIONS = {"noop", "close", "categories", "universes", "stories", "menu", "back"}


async def _include_restricted(
    *,
    bot: Bot,
    user_id: int,
    adult_channel_id: int,
    access_policy: AccessPolicy,
    user,
    workspace_id: int,
    workspace_product_service: WorkspaceProductService,
) -> bool:
    manager_access = has_public_manager_access(user, access_policy)
    return await has_workspace_adult_access(
        bot=bot,
        user_id=user_id,
        workspace_id=workspace_id,
        manager_access=manager_access,
        default_adult_channel_id=adult_channel_id,
        workspace_product_service=workspace_product_service,
    )


async def _send_category_menu(
    *,
    bot: Bot,
    database: Database,
    chat_id: int,
    workspace_id: int,
    include_restricted: bool,
) -> Message:
    summaries = await list_public_categories(
        database,
        workspace_id=workspace_id,
        include_restricted=include_restricted,
    )
    return await bot.send_message(
        chat_id=chat_id,
        text=format_public_categories(summaries),
        reply_markup=build_public_category_menu(summaries),
    )


async def _edit_category_menu(
    callback: CallbackQuery,
    database: Database,
    *,
    workspace_id: int,
    include_restricted: bool,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    summaries = await list_public_categories(
        database,
        workspace_id=workspace_id,
        include_restricted=include_restricted,
    )
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
    workspace_id: int,
    include_restricted: bool,
) -> Message:
    summaries = await list_public_universes(
        database,
        category=category,
        workspace_id=workspace_id,
        include_restricted=include_restricted,
    )
    return await bot.send_message(
        chat_id=chat_id,
        text=format_public_universes(category, summaries),
        reply_markup=build_public_universe_menu(category, summaries),
    )


async def _edit_universe_menu(
    callback: CallbackQuery,
    database: Database,
    category: str,
    *,
    workspace_id: int,
    include_restricted: bool,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    summaries = await list_public_universes(
        database,
        category=category,
        workspace_id=workspace_id,
        include_restricted=include_restricted,
    )
    try:
        await callback.message.edit_text(
            text=format_public_universes(category, summaries),
            reply_markup=build_public_universe_menu(category, summaries),
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
    await callback.answer()


async def _send_story_menu(
    *,
    bot: Bot,
    database: Database,
    chat_id: int,
    category: str,
    universe: str,
    workspace_id: int,
    include_restricted: bool,
) -> Message:
    summaries = await list_public_stories(
        database,
        category=category,
        universe=universe,
        workspace_id=workspace_id,
        include_restricted=include_restricted,
    )
    return await bot.send_message(
        chat_id=chat_id,
        text=format_public_stories(category, universe, summaries),
        reply_markup=build_public_story_menu(category, universe, summaries),
    )


async def _edit_story_menu(
    callback: CallbackQuery,
    database: Database,
    category: str,
    universe: str,
    *,
    workspace_id: int,
    include_restricted: bool,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    summaries = await list_public_stories(
        database,
        category=category,
        universe=universe,
        workspace_id=workspace_id,
        include_restricted=include_restricted,
    )
    try:
        await callback.message.edit_text(
            text=format_public_stories(category, universe, summaries),
            reply_markup=build_public_story_menu(category, universe, summaries),
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
    story_id: int,
    page_number: int,
    workspace_id: int,
    include_restricted: bool,
) -> Message:
    page = await list_public_characters(
        database,
        category=category,
        universe=universe,
        story_id=story_id or None,
        page=page_number,
        workspace_id=workspace_id,
        include_restricted=include_restricted,
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
    story_id: int,
    page_number: int,
    *,
    workspace_id: int,
    include_restricted: bool,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    page = await list_public_characters(
        database,
        category=category,
        universe=universe,
        story_id=story_id or None,
        page=page_number,
        workspace_id=workspace_id,
        include_restricted=include_restricted,
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


@router.message(Command("archive", "gallery"))
async def handle_public_archive_menu(
    message: Message,
    database: Database,
    bot: Bot,
    access_policy: AccessPolicy,
    adult_channel_id: int,
    workspace_product_service: WorkspaceProductService,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    workspace_id = await workspace_product_service.public_workspace_id_for_user(user_id)
    include_restricted = await _include_restricted(
        bot=bot,
        user_id=user_id,
        adult_channel_id=adult_channel_id,
        access_policy=access_policy,
        user=message.from_user,
        workspace_id=workspace_id,
        workspace_product_service=workspace_product_service,
    )
    summaries = await list_public_categories(
        database,
        workspace_id=workspace_id,
        include_restricted=include_restricted,
    )
    await message.answer(
        format_public_categories(summaries),
        reply_markup=build_public_category_menu(summaries),
    )


@router.callback_query(
    PublicArchiveCallback.filter(F.action.in_(_MENU_ACTIONS))
)
async def handle_public_archive_callback(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    access_policy: AccessPolicy,
    adult_channel_id: int,
    workspace_product_service: WorkspaceProductService,
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

    workspace_id = await workspace_product_service.public_workspace_id_for_user(
        callback.from_user.id
    )
    include_restricted = await _include_restricted(
        bot=bot,
        user_id=callback.from_user.id,
        adult_channel_id=adult_channel_id,
        access_policy=access_policy,
        user=callback.from_user,
        workspace_id=workspace_id,
        workspace_product_service=workspace_product_service,
    )

    if action == "categories":
        try:
            await _edit_category_menu(
                callback,
                database,
                workspace_id=workspace_id,
                include_restricted=include_restricted,
            )
        except TelegramBadRequest:
            if isinstance(callback.message, Message):
                await _send_category_menu(
                    bot=bot,
                    database=database,
                    chat_id=callback.message.chat.id,
                    workspace_id=workspace_id,
                    include_restricted=include_restricted,
                )
                await callback.answer()
        return

    if action == "universes":
        if not callback_data.category:
            await callback.answer("Сначала выберите пол или состав.", show_alert=True)
            return
        try:
            await _edit_universe_menu(
                callback,
                database,
                callback_data.category,
                workspace_id=workspace_id,
                include_restricted=include_restricted,
            )
        except TelegramBadRequest:
            if isinstance(callback.message, Message):
                await _send_universe_menu(
                    bot=bot,
                    database=database,
                    chat_id=callback.message.chat.id,
                    category=callback_data.category,
                    workspace_id=workspace_id,
                    include_restricted=include_restricted,
                )
                await callback.answer()
        return

    if action == "stories":
        if not callback_data.category or not callback_data.universe:
            await callback.answer("Сначала выберите вселенную.", show_alert=True)
            return
        try:
            await _edit_story_menu(
                callback,
                database,
                callback_data.category,
                callback_data.universe,
                workspace_id=workspace_id,
                include_restricted=include_restricted,
            )
        except TelegramBadRequest:
            if isinstance(callback.message, Message):
                await _send_story_menu(
                    bot=bot,
                    database=database,
                    chat_id=callback.message.chat.id,
                    category=callback_data.category,
                    universe=callback_data.universe,
                    workspace_id=workspace_id,
                    include_restricted=include_restricted,
                )
                await callback.answer()
        return

    if action == "menu":
        if not callback_data.category or not callback_data.universe:
            await callback.answer("Фильтр архива выбран не полностью.", show_alert=True)
            return
        if universe_requires_story(callback_data.universe) and not callback_data.story_id:
            await callback.answer("Сначала выберите историю.", show_alert=True)
            return
        await _edit_public_menu(
            callback,
            database,
            callback_data.category,
            callback_data.universe,
            callback_data.story_id,
            callback_data.page,
            workspace_id=workspace_id,
            include_restricted=include_restricted,
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
                story_id=callback_data.story_id,
                page_number=callback_data.page,
                workspace_id=workspace_id,
                include_restricted=include_restricted,
            )
        elif callback_data.category:
            await _send_universe_menu(
                bot=bot,
                database=database,
                chat_id=chat_id,
                category=callback_data.category,
                workspace_id=workspace_id,
                include_restricted=include_restricted,
            )
        else:
            await _send_category_menu(
                bot=bot,
                database=database,
                chat_id=chat_id,
                workspace_id=workspace_id,
                include_restricted=include_restricted,
            )
        await callback.answer()


__all__ = ("router",)
