from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.character_directory import (
    CharacterDirectoryItem,
    get_character_directory_item,
    normalize_universe,
    story_label,
    universe_label,
)
from velvet_bot.database import Database
from velvet_bot.handlers.admin_directory import (
    AdminDirectoryCallback,
    _profile_keyboard,
    _profile_text,
)
from velvet_bot.story_catalog import (
    CharacterStory,
    create_story,
    find_story,
    get_story,
    list_stories,
    set_character_story,
)

router = Router(name=__name__)


def _cb(
    action: str,
    *,
    category: str = "",
    page: int = 0,
    character_id: int = 0,
    story_id: int = 0,
) -> str:
    return AdminDirectoryCallback(
        action=action,
        category=category,
        page=page,
        character_id=character_id,
        story_id=story_id,
    ).pack()


def _picker_text(item: CharacterDirectoryItem) -> str:
    return (
        "<b>Назначить историю</b>\n\n"
        f"Персонаж: <b>{escape(item.character.name)}</b>\n"
        f"Вселенная: <b>{escape(universe_label(item.universe))}</b>\n"
        f"Текущая история: "
        f"<b>{escape(story_label(item.story_short_label, item.story_title))}</b>\n\n"
        "На кнопках сначала указано сокращение истории."
    )


def build_story_picker(
    item: CharacterDirectoryItem,
    stories: list[CharacterStory],
    *,
    category: str,
    page: int,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"📖 {story.short_label} · {story.title}",
                callback_data=_cb(
                    "setstory",
                    category=category,
                    page=page,
                    character_id=item.character.id,
                    story_id=story.id,
                ),
            )
        ]
        for story in stories
    ]
    if item.story_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Убрать историю",
                    callback_data=_cb(
                        "setstory",
                        category=category,
                        page=page,
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
                callback_data=_cb(
                    "profile",
                    category=category,
                    page=page,
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
        _profile_text(item),
        reply_markup=_profile_keyboard(
            item,
            category=category,
            page=page,
        ),
    )


@router.message(Command("story"))
async def handle_set_story(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args or len(command.args.rsplit(maxsplit=1)) != 2:
        await message.answer(
            "Формат: <code>/story Имя СОКР</code>\n"
            "Например: <code>/story Каин СНР</code>\n"
            "Снять историю: <code>/story Имя без</code>"
        )
        return

    character_name, raw_story = command.args.rsplit(maxsplit=1)
    character = await database.get_character(character_name)
    if character is None:
        await message.answer("Такой персонаж не найден.")
        return
    item = await get_character_directory_item(database, character.id)
    if item is None or not item.universe:
        await message.answer("Сначала назначьте персонажу вселенную.")
        return

    if raw_story.casefold() in {"без", "нет", "off", "удалить", "-"}:
        await set_character_story(
            database,
            character_id=character.id,
            story_id=None,
        )
        await message.answer(
            f"История у <b>{escape(character.name)}</b> удалена."
        )
        return

    story = await find_story(
        database,
        universe=item.universe,
        value=raw_story,
    )
    if story is None:
        await message.answer(
            "История не найдена в этой вселенной. "
            "Посмотреть сокращения: <code>/stories "
            f"{escape(universe_label(item.universe))}</code>"
        )
        return

    await set_character_story(
        database,
        character_id=character.id,
        story_id=story.id,
    )
    await message.answer(
        f"История персонажа <b>{escape(character.name)}</b>: "
        f"<b>{escape(story.short_label)} · {escape(story.title)}</b>."
    )


@router.message(Command("storyadd"))
async def handle_add_story(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args or len(command.args.split(maxsplit=2)) != 3:
        await message.answer(
            "Формат: <code>/storyadd Вселенная СОКР Полное название</code>\n"
            "Например: <code>/storyadd КР СНР Секрет Небес: Реквием</code>"
        )
        return

    raw_universe, short_label, title = command.args.split(maxsplit=2)
    try:
        universe = normalize_universe(raw_universe)
        story = await create_story(
            database,
            universe=universe,
            short_label=short_label,
            title=title,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return

    await message.answer(
        f"История добавлена в <b>{escape(universe_label(universe))}</b>: "
        f"<b>{escape(story.short_label)} · {escape(story.title)}</b>."
    )


@router.message(Command("stories", "storylist"))
async def handle_story_list(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer(
            "Формат: <code>/stories Вселенная</code>\n"
            "Например: <code>/stories КР</code>"
        )
        return
    try:
        universe = normalize_universe(command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return

    stories = await list_stories(database, universe=universe)
    if not stories:
        await message.answer("Для этой вселенной истории ещё не добавлены.")
        return
    lines = [
        f"• <code>{escape(story.short_label)}</code> — {escape(story.title)}"
        for story in stories
    ]
    text = (
        f"<b>Истории {escape(universe_label(universe))}</b>\n\n"
        + "\n".join(lines)
    )
    await message.answer(text)


@router.callback_query(AdminDirectoryCallback.filter(F.action == "pickstory"))
async def handle_story_picker(
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
    if not item.universe:
        await callback.answer("Сначала назначьте вселенную.", show_alert=True)
        return

    stories = await list_stories(database, universe=item.universe)
    if not stories:
        await callback.answer(
            "Для этой вселенной пока нет историй. Добавьте через /storyadd.",
            show_alert=True,
        )
        return
    await callback.message.edit_text(
        _picker_text(item),
        reply_markup=build_story_picker(
            item,
            stories,
            category=callback_data.category or item.category or "uncategorized",
            page=callback_data.page,
        ),
    )
    await callback.answer()


@router.callback_query(AdminDirectoryCallback.filter(F.action == "setstory"))
async def handle_story_assignment(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
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
        page=callback_data.page,
    )
    await callback.answer(
        (
            f"{item.character.name}: {story.short_label} · {story.title}"
            if story
            else f"{item.character.name}: история удалена"
        ),
        show_alert=True,
    )
