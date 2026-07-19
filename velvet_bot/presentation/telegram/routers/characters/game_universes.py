from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.access import AccessPolicy
from velvet_bot.archive_catalog import ArchivePage, get_archive_page
from velvet_bot.character_directory import (
    GAME_UNIVERSE_ORDER,
    UNIVERSE_EMOJI,
    UNIVERSE_LABELS,
    UniverseSummary,
    get_character_directory_item,
    set_character_universe,
)
from velvet_bot.database import Database
from velvet_bot.presentation.telegram.routers.characters.directory import (
    AdminDirectoryCallback,
)
from velvet_bot.presentation.telegram.routers.characters.uncategorized import (
    _render_profile,
    _render_uncategorized_page,
)
from velvet_bot.public_archive_display import refresh_viewer_archive_caption
from velvet_bot.public_catalog import list_public_characters
from velvet_bot.public_manager_access import has_public_manager_access
from velvet_bot.public_ui import PublicArchiveCallback

router = Router(name=__name__)


def _admin_game_keyboard(
    callback_data: AdminDirectoryCallback,
) -> InlineKeyboardMarkup:
    return_category = (
        callback_data.return_category
        or callback_data.category
        or "uncategorized"
    )
    rows = [
        [
            InlineKeyboardButton(
                text=f"{UNIVERSE_EMOJI[key]} {UNIVERSE_LABELS[key]}",
                callback_data=AdminDirectoryCallback(
                    action="setgame",
                    universe=key,
                    page=callback_data.page,
                    character_id=callback_data.character_id,
                    return_category=return_category,
                ).pack(),
            )
            for key in GAME_UNIVERSE_ORDER
        ],
        [
            InlineKeyboardButton(
                text="↩️ Вселенные",
                callback_data=AdminDirectoryCallback(
                    action="pickuni",
                    category=return_category,
                    page=callback_data.page,
                    character_id=callback_data.character_id,
                ).pack(),
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _manager_game_keyboard(page: ArchivePage) -> InlineKeyboardMarkup:
    if page.media is None:
        return InlineKeyboardMarkup(inline_keyboard=[])
    common = {
        "character_id": page.character.id,
        "offset": page.offset,
        "media_id": page.media.id,
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{UNIVERSE_EMOJI[key]} {UNIVERSE_LABELS[key]}",
                    callback_data=PublicArchiveCallback(
                        action="pgame",
                        universe=key,
                        **common,
                    ).pack(),
                )
                for key in GAME_UNIVERSE_ORDER
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Вселенные",
                    callback_data=PublicArchiveCallback(
                        action="punis",
                        **common,
                    ).pack(),
                )
            ],
        ]
    )


def _public_game_keyboard(
    category: str,
    summaries: list[UniverseSummary],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{item.emoji} {item.label} · {item.character_count}",
                callback_data=PublicArchiveCallback(
                    action="menu",
                    category=category,
                    universe=item.key,
                ).pack(),
            )
            for item in summaries
        ],
        [
            InlineKeyboardButton(
                text="↩️ Вселенные",
                callback_data=PublicArchiveCallback(
                    action="universes",
                    category=category,
                ).pack(),
            ),
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=PublicArchiveCallback(
                    action="menu",
                    category=category,
                    universe="games",
                ).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text="✖ Закрыть",
                callback_data=PublicArchiveCallback(action="close").pack(),
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _public_game_summaries(
    database: Database,
    *,
    category: str,
) -> list[UniverseSummary]:
    summaries: list[UniverseSummary] = []
    for universe in GAME_UNIVERSE_ORDER:
        page = await list_public_characters(
            database,
            category=category,
            universe=universe,
            page=0,
            page_size=1,
        )
        summaries.append(
            UniverseSummary(
                key=universe,
                label=UNIVERSE_LABELS[universe],
                emoji=UNIVERSE_EMOJI[universe],
                character_count=page.total_characters,
            )
        )
    return summaries


async def handle_admin_game_group(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    await callback.message.edit_text(
        "<b>🎮 Игры</b>\n\n"
        f"Персонаж: <b>{escape(item.character.name)}</b>\n"
        "Выберите игровую вселенную.",
        reply_markup=_admin_game_keyboard(callback_data),
    )
    await callback.answer()


async def handle_admin_game_assignment(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    await set_character_universe(
        database,
        character_id=item.character.id,
        universe=callback_data.universe,
    )
    item = await get_character_directory_item(database, item.character.id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    return_category = (
        callback_data.return_category
        or callback_data.category
        or item.category
        or "uncategorized"
    )
    if return_category == "uncategorized":
        await _render_uncategorized_page(
            callback,
            database,
            page_number=callback_data.page,
        )
        return
    await _render_profile(
        callback,
        item,
        return_category=return_category,
        page=callback_data.page,
    )
    await callback.answer(
        f"{item.character.name}: {UNIVERSE_LABELS[callback_data.universe]}",
        show_alert=True,
    )


async def handle_manager_game_group(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    access_policy: AccessPolicy,
) -> None:
    if not has_public_manager_access(callback.from_user, access_policy):
        await callback.answer("Управление архивом для вас закрыто.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return
    await callback.message.edit_caption(
        caption=(
            "<b>🎮 Игры</b>\n\n"
            f"Персонаж: <b>{escape(page.character.name)}</b>\n"
            "Выберите игровую вселенную."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=_manager_game_keyboard(page),
    )
    await callback.answer()


async def handle_manager_game_assignment(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    access_policy: AccessPolicy,
) -> None:
    if not has_public_manager_access(callback.from_user, access_policy):
        await callback.answer("Управление архивом для вас закрыто.", show_alert=True)
        return
    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return
    await set_character_universe(
        database,
        character_id=page.character.id,
        universe=callback_data.universe,
    )
    await refresh_viewer_archive_caption(
        callback=callback,
        database=database,
        page=page,
        viewer_user_id=callback.from_user.id,
        manager_access=True,
    )
    await callback.answer(
        f"Вселенная: {UNIVERSE_LABELS[callback_data.universe]}",
        show_alert=True,
    )


async def handle_public_game_group(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
) -> None:
    if not callback_data.category:
        await callback.answer("Сначала выберите пол или состав.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    summaries = await _public_game_summaries(
        database,
        category=callback_data.category,
    )
    total = sum(item.character_count for item in summaries)
    try:
        await callback.message.edit_text(
            "<b>🎮 Игры</b>\n\n"
            "Выберите игровую вселенную.\n\n"
            f"Персонажей с материалами: <b>{total}</b>",
            reply_markup=_public_game_keyboard(callback_data.category, summaries),
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
    await callback.answer()


router.callback_query.register(
    handle_admin_game_group,
    AdminDirectoryCallback.filter(
        (F.action == "setuni") & (F.universe == "games")
    ),
)
router.callback_query.register(
    handle_admin_game_assignment,
    AdminDirectoryCallback.filter(
        F.action.in_({"setgame", "setuni"})
        & F.universe.in_(GAME_UNIVERSE_ORDER)
    ),
)
router.callback_query.register(
    handle_manager_game_group,
    PublicArchiveCallback.filter(
        (F.action == "puni") & (F.universe == "games")
    ),
)
router.callback_query.register(
    handle_manager_game_assignment,
    PublicArchiveCallback.filter(
        F.action.in_({"pgame", "puni"})
        & F.universe.in_(GAME_UNIVERSE_ORDER)
    ),
)
router.callback_query.register(
    handle_public_game_group,
    PublicArchiveCallback.filter(
        (F.action == "menu") & (F.universe == "games")
    ),
)

__all__ = ("router",)
