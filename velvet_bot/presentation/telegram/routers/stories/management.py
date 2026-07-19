from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.application.owner_profiles import (
    add_story_from_text,
    list_stories_from_text,
    set_story_from_text,
)
from velvet_bot.character_directory import (
    CharacterDirectoryItem,
    get_character_directory_item,
    story_label,
    universe_label,
)
from velvet_bot.database import Database
from velvet_bot.presentation.telegram.routers.characters.contracts import (
    AdminDirectoryCallback,
)
from velvet_bot.presentation.telegram.routers.characters.profile_views import (
    build_character_profile_keyboard,
    format_character_profile,
)
from velvet_bot.story_catalog import (
    CharacterStory,
    StoryPage,
    format_story_release,
    get_story,
    list_story_page,
    set_character_story,
)

router = Router(name=__name__)


class AdminStoryCallback(CallbackData, prefix="astory"):
    action: str
    category: str = ""
    directory_page: int = 0
    story_page: int = 0
    character_id: int = 0
    story_id: int = 0


def _story_cb(
    action: str,
    *,
    category: str,
    directory_page: int,
    story_page: int,
    character_id: int,
    story_id: int = 0,
) -> str:
    return AdminStoryCallback(
        action=action,
        category=category,
        directory_page=directory_page,
        story_page=story_page,
        character_id=character_id,
        story_id=story_id,
    ).pack()


def _profile_cb(*, category: str, page: int, character_id: int) -> str:
    return AdminDirectoryCallback(
        action="profile",
        category=category,
        page=page,
        character_id=character_id,
    ).pack()


def _picker_text(item: CharacterDirectoryItem, story_page: StoryPage) -> str:
    return (
        "<b>Назначить историю</b>\n\n"
        f"Персонаж: <b>{escape(item.character.name)}</b>\n"
        f"Вселенная: <b>{escape(universe_label(item.universe))}</b>\n"
        f"Текущая история: "
        f"<b>{escape(story_label(item.story_short_label, item.story_title))}</b>\n\n"
        "Сортировка: <b>от новых историй к старым</b>.\n"
        f"Страница: <b>{story_page.page + 1}</b> из "
        f"<b>{story_page.total_pages}</b> · "
        f"историй: <b>{story_page.total_stories}</b>"
    )


def _story_button_text(story: CharacterStory) -> str:
    released = format_story_release(story.released_on, story.release_precision)
    if released == "дата не указана":
        return f"📖 {story.short_label} · {story.title}"
    return f"📖 {released} · {story.short_label} · {story.title}"


def build_story_picker(
    item: CharacterDirectoryItem,
    story_page: StoryPage,
    *,
    category: str,
    directory_page: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for story in story_page.items:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_story_button_text(story),
                    callback_data=_story_cb(
                        "set",
                        category=category,
                        directory_page=directory_page,
                        story_page=story_page.page,
                        character_id=item.character.id,
                        story_id=story.id,
                    ),
                )
            ]
        )
    if story_page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️ Новее",
                    callback_data=_story_cb(
                        "page",
                        category=category,
                        directory_page=directory_page,
                        story_page=(story_page.page - 1) % story_page.total_pages,
                        character_id=item.character.id,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{story_page.page + 1} / {story_page.total_pages}",
                    callback_data=_story_cb(
                        "noop",
                        category=category,
                        directory_page=directory_page,
                        story_page=story_page.page,
                        character_id=item.character.id,
                    ),
                ),
                InlineKeyboardButton(
                    text="Старее ▶️",
                    callback_data=_story_cb(
                        "page",
                        category=category,
                        directory_page=directory_page,
                        story_page=(story_page.page + 1) % story_page.total_pages,
                        character_id=item.character.id,
                    ),
                ),
            ]
        )
    if item.story_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Убрать историю",
                    callback_data=_story_cb(
                        "set",
                        category=category,
                        directory_page=directory_page,
                        story_page=story_page.page,
                        character_id=item.character.id,
                        story_id=0,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К карточке",
                callback_data=_profile_cb(
                    category=category,
                    page=directory_page,
                    character_id=item.character.id,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_profile(
    callback: CallbackQuery,
    item: CharacterDirectoryItem,
    *,
    category: str,
    page: int,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await callback.message.edit_text(
        format_character_profile(item),
        reply_markup=build_character_profile_keyboard(item, category=category, page=page),
    )


async def _render_story_picker(
    callback: CallbackQuery,
    database: Database,
    *,
    item: CharacterDirectoryItem,
    category: str,
    directory_page: int,
    story_page_number: int,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    if not item.universe:
        await callback.answer("Сначала назначьте вселенную.", show_alert=True)
        return
    story_page = await list_story_page(
        database,
        universe=item.universe,
        page=story_page_number,
    )
    if not story_page.items:
        await callback.answer(
            "Для этой вселенной пока нет историй. Добавьте через центр управления.",
            show_alert=True,
        )
        return
    await callback.message.edit_text(
        _picker_text(item, story_page),
        reply_markup=build_story_picker(
            item,
            story_page,
            category=category,
            directory_page=directory_page,
        ),
    )


@router.message(Command("story"))
async def handle_set_story(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer(
            "Формат: <code>/story Имя СОКР</code>\n"
            "Снять историю: <code>/story Имя без</code>"
        )
        return
    try:
        result = await set_story_from_text(database, command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    if result.removed:
        await message.answer(f"История у <b>{escape(result.character.name)}</b> удалена.")
        return
    assert result.story is not None
    await message.answer(
        f"История персонажа <b>{escape(result.character.name)}</b>: "
        f"<b>{escape(result.story.short_label)} · {escape(result.story.title)}</b>."
    )


@router.message(Command("storyadd"))
async def handle_add_story(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer(
            "Формат: <code>/storyadd Вселенная СОКР Полное название</code>"
        )
        return
    try:
        story = await add_story_from_text(database, command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(
        f"История добавлена в <b>{escape(universe_label(story.universe))}</b>: "
        f"<b>{escape(story.short_label)} · {escape(story.title)}</b>. "
        "Она поставлена первой как самая новая."
    )


def _story_list_chunks(universe: str, stories: tuple[CharacterStory, ...]) -> list[str]:
    header = (
        f"<b>Истории {escape(universe_label(universe))}</b>\n"
        "Сортировка: <b>от новых к старым</b>.\n\n"
    )
    chunks: list[str] = []
    current = header
    for story in stories:
        released = format_story_release(story.released_on, story.release_precision)
        date_prefix = "" if released == "дата не указана" else f"{released} · "
        line = (
            f"• {date_prefix}<code>{escape(story.short_label)}</code> — "
            f"{escape(story.title)}\n"
        )
        if len(current) + len(line) > 3800:
            chunks.append(current.rstrip())
            current = header + line
        else:
            current += line
    chunks.append(current.rstrip())
    return chunks


@router.message(Command("stories", "storylist"))
async def handle_story_list(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer("Формат: <code>/stories Вселенная</code>")
        return
    try:
        result = await list_stories_from_text(database, command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    if not result.stories:
        await message.answer("Для этой вселенной истории ещё не добавлены.")
        return
    for chunk in _story_list_chunks(result.universe, result.stories):
        await message.answer(chunk)


@router.callback_query(AdminDirectoryCallback.filter(F.action == "pickstory"))
async def handle_story_picker(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    await _render_story_picker(
        callback,
        database,
        item=item,
        category=callback_data.category or item.category or "uncategorized",
        directory_page=callback_data.page,
        story_page_number=0,
    )
    await callback.answer()


@router.callback_query(AdminStoryCallback.filter())
async def handle_story_callback(
    callback: CallbackQuery,
    callback_data: AdminStoryCallback,
    database: Database,
) -> None:
    if callback_data.action == "noop":
        await callback.answer()
        return
    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    if callback_data.action == "page":
        await _render_story_picker(
            callback,
            database,
            item=item,
            category=callback_data.category or item.category or "uncategorized",
            directory_page=callback_data.directory_page,
            story_page_number=callback_data.story_page,
        )
        await callback.answer()
        return
    if callback_data.action != "set":
        await callback.answer("Неизвестное действие.", show_alert=True)
        return
    story = None
    if callback_data.story_id:
        story = await get_story(database, callback_data.story_id)
        if story is None or story.universe != item.universe:
            await callback.answer(
                "История больше недоступна или относится к другой вселенной.",
                show_alert=True,
            )
            return
    await set_character_story(
        database,
        character_id=item.character.id,
        story_id=story.id if story else None,
    )
    item = await get_character_directory_item(database, item.character.id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    category = callback_data.category or item.category or "uncategorized"
    await _render_profile(
        callback,
        item,
        category=category,
        page=callback_data.directory_page,
    )
    await callback.answer(
        (
            f"{item.character.name}: {story.short_label} · {story.title}"
            if story
            else f"{item.character.name}: история удалена"
        ),
        show_alert=True,
    )
