from __future__ import annotations

from html import escape

from aiogram.enums import ParseMode
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAnimation,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
)

from velvet_bot.archive_catalog import ArchivePage, ArchivedMedia
from velvet_bot.database import Character


class ArchiveMediaCallback(CallbackData, prefix="arc"):
    action: str
    character_id: int
    offset: int


def build_character_archive_keyboard(
    character: Character,
    media_count: int,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🖼 Открыть архив · {media_count}",
                callback_data=ArchiveMediaCallback(
                    action="open",
                    character_id=character.id,
                    offset=0,
                ).pack(),
            )
        ]
    ]

    if character.archive_topic_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📂 Открыть ветку Telegram",
                    url=character.archive_topic_url,
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_character_list_keyboard(
    characters: list[Character],
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🖼 {character.name}",
                    callback_data=ArchiveMediaCallback(
                        action="open",
                        character_id=character.id,
                        offset=0,
                    ).pack(),
                )
            ]
            for character in characters
        ]
    )


def build_archive_navigation(page: ArchivePage) -> InlineKeyboardMarkup:
    if page.total <= 0:
        return InlineKeyboardMarkup(inline_keyboard=[])

    previous_offset = (page.offset - 1) % page.total
    next_offset = (page.offset + 1) % page.total

    rows = [
        [
            InlineKeyboardButton(
                text="◀️",
                callback_data=ArchiveMediaCallback(
                    action="show",
                    character_id=page.character.id,
                    offset=previous_offset,
                ).pack(),
            ),
            InlineKeyboardButton(
                text=f"{page.offset + 1} / {page.total}",
                callback_data=ArchiveMediaCallback(
                    action="noop",
                    character_id=page.character.id,
                    offset=page.offset,
                ).pack(),
            ),
            InlineKeyboardButton(
                text="▶️",
                callback_data=ArchiveMediaCallback(
                    action="show",
                    character_id=page.character.id,
                    offset=next_offset,
                ).pack(),
            ),
        ]
    ]

    final_row: list[InlineKeyboardButton] = []
    if page.character.archive_topic_url:
        final_row.append(
            InlineKeyboardButton(
                text="📂 Ветка",
                url=page.character.archive_topic_url,
            )
        )
    final_row.append(
        InlineKeyboardButton(
            text="✖ Закрыть",
            callback_data=ArchiveMediaCallback(
                action="close",
                character_id=page.character.id,
                offset=page.offset,
            ).pack(),
        )
    )
    rows.append(final_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_archive_caption(page: ArchivePage) -> str:
    if page.media is None:
        return f"<b>{escape(page.character.name)}</b>"

    linked_at = page.media.linked_at.astimezone().strftime("%d.%m.%Y %H:%M")
    file_name = escape(page.media.display_file_name)
    return (
        f"<b>{escape(page.character.name)}</b>\n"
        f"Медиа: <b>{page.offset + 1}</b> из <b>{page.total}</b>\n"
        f"Файл: <code>{file_name}</code>\n"
        f"Добавлен: <code>{escape(linked_at)}</code>"
    )


def build_input_media(media: ArchivedMedia, caption: str):
    common = {
        "media": media.telegram_file_id,
        "caption": caption,
        "parse_mode": ParseMode.HTML,
    }

    if media.media_type == "photo":
        return InputMediaPhoto(**common)
    if media.media_type == "video":
        return InputMediaVideo(**common)
    if media.media_type == "animation":
        return InputMediaAnimation(**common)
    return InputMediaDocument(**common)
