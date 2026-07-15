from __future__ import annotations

from html import escape

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.archive_catalog import ArchivePage
from velvet_bot.public_catalog import PublicCharacterPage, PublicMediaState

PUBLIC_DOWNLOAD_USER_ID = 8179531132


class PublicArchiveCallback(CallbackData, prefix="pub"):
    action: str
    character_id: int = 0
    offset: int = 0
    media_id: int = 0
    page: int = 0


def _callback(
    action: str,
    *,
    character_id: int = 0,
    offset: int = 0,
    media_id: int = 0,
    page: int = 0,
) -> str:
    return PublicArchiveCallback(
        action=action,
        character_id=character_id,
        offset=offset,
        media_id=media_id,
        page=page,
    ).pack()


def build_public_entry_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Открыть архив персонажей",
                    callback_data=_callback("menu"),
                )
            ]
        ]
    )


def format_public_menu(page: PublicCharacterPage) -> str:
    if page.total_characters == 0:
        return (
            "<b>Архив персонажей Velvet</b>\n\n"
            "В открытом архиве пока нет материалов."
        )
    return (
        "<b>Архив персонажей Velvet</b>\n\n"
        "Выберите персонажа. Архив открывается только через кнопки: "
        "можно листать материалы, ставить отметки и подписываться на обновления.\n\n"
        f"Персонажей с материалами: <b>{page.total_characters}</b>"
    )


def build_public_character_menu(page: PublicCharacterPage) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in page.items:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{item.character.name} · {item.media_count}",
                    callback_data=_callback(
                        "open",
                        character_id=item.character.id,
                        offset=0,
                        page=page.page,
                    ),
                )
            ]
        )

    if page.total_pages > 1:
        previous_page = (page.page - 1) % page.total_pages
        next_page = (page.page + 1) % page.total_pages
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_callback("menu", page=previous_page),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=_callback("noop", page=page.page),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_callback("menu", page=next_page),
                ),
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=_callback("menu", page=page.page),
            ),
            InlineKeyboardButton(
                text="✖ Закрыть",
                callback_data=_callback("close"),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_public_archive_caption(page: ArchivePage, state: PublicMediaState) -> str:
    if page.media is None:
        return f"<b>{escape(page.character.name)}</b>"
    linked_at = page.media.linked_at.astimezone().strftime("%d.%m.%Y %H:%M")
    return (
        f"<b>{escape(page.character.name)}</b>\n"
        f"Материал: <b>{page.offset + 1}</b> из <b>{page.total}</b>\n"
        f"Добавлен: <code>{escape(linked_at)}</code>\n"
        f"Отметок: <b>{state.like_count}</b>"
    )


def build_public_archive_keyboard(
    page: ArchivePage,
    state: PublicMediaState,
    *,
    viewer_user_id: int,
    menu_page: int = 0,
) -> InlineKeyboardMarkup:
    if page.media is None or page.total <= 0:
        return InlineKeyboardMarkup(inline_keyboard=[])

    media_id = page.media.id
    counter = InlineKeyboardButton(
        text=f"{page.offset + 1} / {page.total}",
        callback_data=_callback(
            "noop",
            character_id=page.character.id,
            offset=page.offset,
            media_id=media_id,
            page=menu_page,
        ),
    )
    if page.total == 1:
        rows: list[list[InlineKeyboardButton]] = [[counter]]
    else:
        rows = [
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_callback(
                        "show",
                        character_id=page.character.id,
                        offset=(page.offset - 1) % page.total,
                        page=menu_page,
                    ),
                ),
                counter,
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_callback(
                        "show",
                        character_id=page.character.id,
                        offset=(page.offset + 1) % page.total,
                        page=menu_page,
                    ),
                ),
            ]
        ]

    rows.append(
        [
            InlineKeyboardButton(
                text=("❤️" if state.liked_by_user else "🤍") + f" {state.like_count}",
                callback_data=_callback(
                    "like",
                    character_id=page.character.id,
                    offset=page.offset,
                    media_id=media_id,
                    page=menu_page,
                ),
            ),
            InlineKeyboardButton(
                text="🔕 Отписаться" if state.subscribed else "🔔 Подписаться",
                callback_data=_callback(
                    "sub",
                    character_id=page.character.id,
                    offset=page.offset,
                    media_id=media_id,
                    page=menu_page,
                ),
            ),
        ]
    )

    if viewer_user_id == PUBLIC_DOWNLOAD_USER_ID:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📥 Скачать файлом",
                    callback_data=_callback(
                        "download",
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
                        page=menu_page,
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К персонажам",
                callback_data=_callback("back", page=menu_page),
            ),
            InlineKeyboardButton(
                text="✖ Закрыть",
                callback_data=_callback("close"),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_public_notification_keyboard(character_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Открыть новый материал",
                    callback_data=_callback(
                        "open",
                        character_id=character_id,
                        offset=0,
                    ),
                )
            ]
        ]
    )
