from __future__ import annotations

from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.archive_ui import ArchiveMediaCallback
from velvet_bot.character_directory import (
    CharacterDirectoryItem,
    category_label,
    story_label,
    universe_label,
)
from velvet_bot.presentation.telegram.routers.characters.aliases import CharacterTagCallback
from velvet_bot.presentation.telegram.routers.characters.contracts import directory_callback
from velvet_bot.story_catalog import universe_requires_story


def format_character_profile(item: CharacterDirectoryItem) -> str:
    prompt_line = (
        f'<a href="{escape(item.prompt_post_url, quote=True)}">Пост с промтом</a>'
        if item.prompt_post_url
        else "Промт персонажа: <b>не привязан</b>"
    )
    story_is_required = universe_requires_story(item.universe)
    public_ready = bool(
        item.category
        and item.universe
        and (not story_is_required or item.story_id is not None)
    )
    public_state = (
        "доступен после добавления материалов"
        if public_ready
        else "скрыт, пока не заполнены обязательные категории"
    )
    return (
        "<b>Карточка персонажа</b>\n\n"
        f"Имя: <b>{escape(item.character.name)}</b>\n"
        f"Пол / состав: <b>{escape(category_label(item.category))}</b>\n"
        f"Вселенная: <b>{escape(universe_label(item.universe))}</b>\n"
        f"История: <b>{escape(story_label(item.story_short_label, item.story_title))}</b>\n"
        f"Материалов: <b>{item.media_count}</b>\n"
        f"Публичный архив: <b>{public_state}</b>\n"
        f"{prompt_line}"
    )


def build_character_profile_keyboard(
    item: CharacterDirectoryItem,
    *,
    category: str,
    page: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="👥 Изменить пол / состав",
                callback_data=directory_callback(
                    "pickcat",
                    category=category,
                    page=page,
                    character_id=item.character.id,
                ),
            ),
            InlineKeyboardButton(
                text="🎭 Изменить вселенную",
                callback_data=directory_callback(
                    "pickuni",
                    category=category,
                    page=page,
                    character_id=item.character.id,
                ),
            ),
        ]
    ]
    if universe_requires_story(item.universe):
        rows.append(
            [
                InlineKeyboardButton(
                    text="📖 Изменить историю",
                    callback_data=directory_callback(
                        "pickstory",
                        category=category,
                        universe=item.universe or "",
                        page=page,
                        character_id=item.character.id,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🏷 Быстрые теги",
                callback_data=CharacterTagCallback(
                    action="menu",
                    character_id=item.character.id,
                    category=category,
                    page=page,
                ).pack(),
            )
        ]
    )
    if item.media_count:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🖼 Открыть архив · {item.media_count}",
                    callback_data=ArchiveMediaCallback(
                        action="open",
                        character_id=item.character.id,
                        offset=0,
                    ).pack(),
                )
            ]
        )
    if item.prompt_post_url:
        rows.append(
            [InlineKeyboardButton(text="📝 Открыть промт", url=item.prompt_post_url)]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К списку",
                callback_data=directory_callback(
                    "menu",
                    category=category,
                    page=page,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


__all__ = ("build_character_profile_keyboard", "format_character_profile")
