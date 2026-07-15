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
    media_id: int = 0


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

    media_id = page.media.id if page.media else 0
    counter_button = InlineKeyboardButton(
        text=f"{page.offset + 1} / {page.total}",
        callback_data=ArchiveMediaCallback(
            action="noop",
            character_id=page.character.id,
            offset=page.offset,
            media_id=media_id,
        ).pack(),
    )

    if page.total == 1:
        rows: list[list[InlineKeyboardButton]] = [[counter_button]]
    else:
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
                        media_id=media_id,
                    ).pack(),
                ),
                counter_button,
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=ArchiveMediaCallback(
                        action="show",
                        character_id=page.character.id,
                        offset=next_offset,
                        media_id=media_id,
                    ).pack(),
                ),
            ]
        ]

    spoiler_enabled = bool(page.media and page.media.is_spoiler)
    rows.append(
        [
            InlineKeyboardButton(
                text=(
                    "🔞 Спойлер включён"
                    if spoiler_enabled
                    else "👁 Включить спойлер 18+"
                ),
                callback_data=ArchiveMediaCallback(
                    action="spoiler",
                    character_id=page.character.id,
                    offset=page.offset,
                    media_id=media_id,
                ).pack(),
            )
        ]
    )

    if page.media and page.media.prompt_post_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📝 Открыть промт",
                    url=page.media.prompt_post_url,
                ),
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data=ArchiveMediaCallback(
                        action="prompt",
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="🗑 Убрать",
                    callback_data=ArchiveMediaCallback(
                        action="promptremove",
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
                    ).pack(),
                ),
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📝 Привязать промт",
                    callback_data=ArchiveMediaCallback(
                        action="prompt",
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
                    ).pack(),
                )
            ]
        )

    final_row: list[InlineKeyboardButton] = []
    if page.character.archive_topic_url:
        final_row.append(
            InlineKeyboardButton(
                text="📂 Ветка",
                url=page.character.archive_topic_url,
            )
        )
    final_row.extend(
        [
            InlineKeyboardButton(
                text="🗑 Удалить",
                callback_data=ArchiveMediaCallback(
                    action="del",
                    character_id=page.character.id,
                    offset=page.offset,
                    media_id=media_id,
                ).pack(),
            ),
            InlineKeyboardButton(
                text="✖ Закрыть",
                callback_data=ArchiveMediaCallback(
                    action="close",
                    character_id=page.character.id,
                    offset=page.offset,
                    media_id=media_id,
                ).pack(),
            ),
        ]
    )
    rows.append(final_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_delete_confirmation(page: ArchivePage) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=ArchiveMediaCallback(
                        action="delok",
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=page.media.id if page.media else 0,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=ArchiveMediaCallback(
                        action="delno",
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=page.media.id if page.media else 0,
                    ).pack(),
                ),
            ]
        ]
    )


def format_archive_caption(page: ArchivePage) -> str:
    if page.media is None:
        return f"<b>{escape(page.character.name)}</b>"

    linked_at = page.media.linked_at.astimezone().strftime("%d.%m.%Y %H:%M")
    file_name = escape(page.media.display_file_name)
    prompt_state = "<b>привязан</b>" if page.media.prompt_post_url else "не привязан"
    spoiler_state = "<b>включён</b>" if page.media.is_spoiler else "выключен"
    return (
        f"<b>{escape(page.character.name)}</b>\n"
        f"Медиа: <b>{page.offset + 1}</b> из <b>{page.total}</b>\n"
        f"Файл: <code>{file_name}</code>\n"
        f"Добавлен: <code>{escape(linked_at)}</code>\n"
        f"Спойлер 18+: {spoiler_state}\n"
        f"Промт: {prompt_state}"
    )


def format_delete_caption(page: ArchivePage) -> str:
    if page.media is None:
        return "<b>Архив пуст.</b>"
    return (
        "<b>Удалить медиа из архива?</b>\n\n"
        f"Персонаж: <b>{escape(page.character.name)}</b>\n"
        f"Файл: <code>{escape(page.media.display_file_name)}</code>\n\n"
        "Связь в PostgreSQL будет удалена. Копия в ветке персонажа тоже будет "
        "удалена, если Telegram ещё разрешает удалить это сообщение."
    )


def build_input_media(media: ArchivedMedia, caption: str):
    common = {
        "media": media.telegram_file_id,
        "caption": caption,
        "parse_mode": ParseMode.HTML,
    }

    if media.media_type == "photo":
        return InputMediaPhoto(has_spoiler=media.is_spoiler, **common)
    if media.media_type == "video":
        return InputMediaVideo(has_spoiler=media.is_spoiler, **common)
    if media.media_type == "animation":
        return InputMediaAnimation(has_spoiler=media.is_spoiler, **common)
    return InputMediaDocument(**common)
