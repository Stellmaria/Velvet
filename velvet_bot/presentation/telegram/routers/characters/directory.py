from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.application.owner_profiles import (
    set_category_from_text,
    set_prompt_from_text,
    set_universe_from_text,
)
from velvet_bot.character_directory import (
    CATEGORY_EMOJI,
    CATEGORY_LABELS,
    CharacterDirectoryItem,
    CharacterDirectoryPage,
    get_character_directory_item,
    list_category_summaries,
    list_character_directory,
    universe_label,
)
from velvet_bot.database import Database
from velvet_bot.presentation.telegram.routers.characters.contracts import (
    AdminDirectoryCallback,
    directory_callback,
)
from velvet_bot.presentation.telegram.routers.characters.profile_views import (
    build_character_profile_keyboard,
    format_character_profile,
)
from velvet_bot.story_catalog import universe_requires_story

router = Router(name=__name__)


_cb = directory_callback


def _category_text(total: int) -> str:
    return (
        "<b>Управление архивом персонажей</b>\n\n"
        "Персонажу назначаются пол/состав, вселенная и, для визуальных "
        "новелл, история.\n\n"
        f"Всего персонажей: <b>{total}</b>\n\n"
        "Все операции доступны кнопками в центре управления."
    )


def _category_keyboard(summaries) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{item.emoji} {item.label} · {item.character_count}",
            callback_data=_cb("menu", category=item.key),
        )
        for item in summaries
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data=_cb("categories")),
            InlineKeyboardButton(text="✖ Закрыть", callback_data=_cb("close")),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _page_text(page: CharacterDirectoryPage) -> str:
    label = CATEGORY_LABELS.get(page.category, page.category)
    emoji = CATEGORY_EMOJI.get(page.category, "🗂")
    return (
        f"<b>{emoji} {escape(label)}</b>\n\n"
        "Сортировка: <b>по алфавиту</b>\n"
        f"Персонажей: <b>{page.total_characters}</b>\n"
        f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>"
    )


def _page_keyboard(page: CharacterDirectoryPage) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in page.items:
        universe = universe_label(item.universe)
        story = item.story_short_label or "—"
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"👤 {item.character.name} · {universe} · "
                        f"{story} · {item.media_count}"
                    ),
                    callback_data=_cb(
                        "profile",
                        category=page.category,
                        page=page.page,
                        character_id=item.character.id,
                    ),
                )
            ]
        )
    if page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_cb(
                        "menu",
                        category=page.category,
                        page=(page.page - 1) % page.total_pages,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=_cb("noop"),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_cb(
                        "menu",
                        category=page.category,
                        page=(page.page + 1) % page.total_pages,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="↩️ Категории", callback_data=_cb("categories")),
            InlineKeyboardButton(text="✖ Закрыть", callback_data=_cb("close")),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _profile_text(item: CharacterDirectoryItem) -> str:
    """Compatibility wrapper for callers not yet migrated to profile views."""
    return format_character_profile(item)


def _profile_keyboard(
    item: CharacterDirectoryItem,
    *,
    category: str,
    page: int,
) -> InlineKeyboardMarkup:
    """Compatibility wrapper for callers not yet migrated to profile views."""
    return build_character_profile_keyboard(item, category=category, page=page)


async def _render_categories(message: Message, database: Database) -> None:
    summaries = await list_category_summaries(
        database,
        public_only=False,
        include_uncategorized=True,
    )
    await message.answer(
        _category_text(sum(item.character_count for item in summaries)),
        reply_markup=_category_keyboard(summaries),
    )


@router.message(Command("characters"))
async def handle_admin_characters(message: Message, database: Database) -> None:
    await _render_categories(message, database)


@router.message(Command("category", "cat"))
async def handle_set_category(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer(
            "Формат: <code>/category Имя категория</code>\n"
            "Категории: женский, мужской, мж, мжм, мм, жж."
        )
        return
    try:
        result = await set_category_from_text(database, command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(
        f"Пол / состав персонажа <b>{escape(result.character.name)}</b>: "
        f"<b>{escape(category_label(result.value))}</b>."
    )


@router.message(Command("universe", "world", "series"))
async def handle_set_universe(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer(
            "Формат: <code>/universe Имя вселенная</code>\n"
            "Вселенные: SHS, КР, ЛМ, ИДМ, BG3, Лагерта, Original."
        )
        return
    try:
        result = await set_universe_from_text(database, command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    suffix = (
        "\nТеперь назначьте историю: <code>/story Имя СОКР</code>."
        if universe_requires_story(result.value)
        else ""
    )
    await message.answer(
        f"Вселенная персонажа <b>{escape(result.character.name)}</b>: "
        f"<b>{escape(universe_label(result.value))}</b>.{suffix}"
    )


@router.message(Command("prompt", "setprompt"))
async def handle_set_prompt(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer(
            "Формат: <code>/prompt Имя https://t.me/channel/123</code>\n"
            "Удалить ссылку: <code>/prompt Имя off</code>"
        )
        return
    try:
        result = await set_prompt_from_text(database, command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    if result.value:
        await message.answer(
            f"Промт привязан к карточке <b>{escape(result.character.name)}</b>.\n"
            "Кнопка появится в меню и внутри архива."
        )
    else:
        await message.answer(
            f"Ссылка на промт удалена у <b>{escape(result.character.name)}</b>."
        )


@router.callback_query(AdminDirectoryCallback.filter())
async def handle_admin_directory_callback(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
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
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    if callback_data.action == "categories":
        summaries = await list_category_summaries(
            database,
            public_only=False,
            include_uncategorized=True,
        )
        await callback.message.edit_text(
            _category_text(sum(item.character_count for item in summaries)),
            reply_markup=_category_keyboard(summaries),
        )
        await callback.answer()
        return
    if callback_data.action == "menu":
        page = await list_character_directory(
            database,
            category=callback_data.category,
            page=callback_data.page,
            public_only=False,
        )
        await callback.message.edit_text(
            _page_text(page),
            reply_markup=_page_keyboard(page),
        )
        await callback.answer()
        return
    if callback_data.action == "profile":
        item = await get_character_directory_item(database, callback_data.character_id)
        if item is None:
            await callback.answer("Персонаж больше не найден.", show_alert=True)
            return
        await callback.message.edit_text(
            _profile_text(item),
            reply_markup=_profile_keyboard(
                item,
                category=callback_data.category,
                page=callback_data.page,
            ),
        )
        await callback.answer()
        return
    await callback.answer("Неизвестное действие.", show_alert=True)
