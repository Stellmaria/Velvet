from __future__ import annotations

from html import escape

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.archive_catalog import ArchivePage
from velvet_bot.character_directory import (
    CATEGORY_LABELS,
    UNIVERSE_LABELS,
    CategorySummary,
)
from velvet_bot.public_catalog import PublicCharacterPage, PublicMediaState

PUBLIC_DOWNLOAD_USER_ID = 8179531132
_FILTER_SEPARATOR = "~"


class PublicArchiveCallback(CallbackData, prefix="pub"):
    action: str
    character_id: int = 0
    offset: int = 0
    media_id: int = 0
    page: int = 0
    category: str = ""


def encode_public_filter(category: str = "", universe_category: str = "") -> str:
    category = category.strip()
    universe_category = universe_category.strip()
    if not universe_category:
        return category
    return f"{category}{_FILTER_SEPARATOR}{universe_category}"


def decode_public_filter(value: str) -> tuple[str, str]:
    cleaned = (value or "").strip()
    if not cleaned:
        return "", ""
    if _FILTER_SEPARATOR not in cleaned:
        return cleaned, ""
    category, universe_category = cleaned.split(_FILTER_SEPARATOR, 1)
    return category, universe_category


def _callback(
    action: str,
    *,
    character_id: int = 0,
    offset: int = 0,
    media_id: int = 0,
    page: int = 0,
    category: str = "",
) -> str:
    return PublicArchiveCallback(
        action=action,
        character_id=character_id,
        offset=offset,
        media_id=media_id,
        page=page,
        category=category,
    ).pack()


def build_public_entry_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Открыть архив персонажей",
                    callback_data=_callback("filters"),
                )
            ]
        ]
    )


def _selected_label(
    value: str,
    labels: dict[str, str],
    *,
    empty_label: str,
) -> str:
    return labels.get(value, empty_label) if value else empty_label


def format_public_filters(
    category_summaries: list[CategorySummary],
    universe_summaries: list[CategorySummary],
    *,
    selected_category: str = "",
    selected_universe: str = "",
) -> str:
    total = sum(item.character_count for item in category_summaries)
    type_label = _selected_label(
        selected_category,
        CATEGORY_LABELS,
        empty_label="Все типы",
    )
    universe_label = _selected_label(
        selected_universe,
        UNIVERSE_LABELS,
        empty_label="Все вселенные",
    )
    return (
        "<b>Архив персонажей Velvet</b>\n\n"
        "Настройте два фильтра. Их можно сочетать, например "
        "<b>Мужской + КР</b>.\n\n"
        f"Тип: <b>{escape(type_label)}</b>\n"
        f"Вселенная: <b>{escape(universe_label)}</b>\n\n"
        f"Персонажей с материалами: <b>{total}</b>"
    )


def _filter_button_text(
    *,
    selected: bool,
    emoji: str,
    label: str,
    count: int | None = None,
) -> str:
    marker = "✅" if selected else emoji
    suffix = f" · {count}" if count is not None else ""
    return f"{marker} {label}{suffix}"


def build_public_filter_menu(
    category_summaries: list[CategorySummary],
    universe_summaries: list[CategorySummary],
    *,
    selected_category: str = "",
    selected_universe: str = "",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    rows.append(
        [
            InlineKeyboardButton(
                text=_filter_button_text(
                    selected=not selected_category,
                    emoji="👥",
                    label="Все типы",
                ),
                callback_data=_callback(
                    "filters",
                    category=encode_public_filter("", selected_universe),
                ),
            )
        ]
    )
    category_buttons = [
        InlineKeyboardButton(
            text=_filter_button_text(
                selected=item.key == selected_category,
                emoji=item.emoji,
                label=item.label,
                count=item.character_count,
            ),
            callback_data=_callback(
                "filters",
                category=encode_public_filter(
                    "" if item.key == selected_category else item.key,
                    selected_universe,
                ),
            ),
        )
        for item in category_summaries
    ]
    rows.extend(
        category_buttons[index : index + 2]
        for index in range(0, len(category_buttons), 2)
    )

    rows.append(
        [
            InlineKeyboardButton(
                text=_filter_button_text(
                    selected=not selected_universe,
                    emoji="🌐",
                    label="Все вселенные",
                ),
                callback_data=_callback(
                    "filters",
                    category=encode_public_filter(selected_category, ""),
                ),
            )
        ]
    )
    universe_buttons = [
        InlineKeyboardButton(
            text=_filter_button_text(
                selected=item.key == selected_universe,
                emoji=item.emoji,
                label=item.label,
                count=item.character_count,
            ),
            callback_data=_callback(
                "filters",
                category=encode_public_filter(
                    selected_category,
                    "" if item.key == selected_universe else item.key,
                ),
            ),
        )
        for item in universe_summaries
    ]
    rows.extend(
        universe_buttons[index : index + 2]
        for index in range(0, len(universe_buttons), 2)
    )

    filter_key = encode_public_filter(selected_category, selected_universe)
    rows.append(
        [
            InlineKeyboardButton(
                text="🔎 Показать персонажей",
                callback_data=_callback("menu", category=filter_key),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="♻ Сбросить",
                callback_data=_callback("filters"),
            ),
            InlineKeyboardButton(text="✖ Закрыть", callback_data=_callback("close")),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# Старые функции оставлены для совместимости со старыми сообщениями и тестами.
def format_public_categories(summaries: list[CategorySummary]) -> str:
    total = sum(item.character_count for item in summaries)
    return (
        "<b>Архив персонажей Velvet</b>\n\n"
        "Выберите категорию. Внутри персонажи расположены по алфавиту "
        "и разбиты на страницы.\n\n"
        f"Персонажей с материалами: <b>{total}</b>"
    )


def build_public_category_menu(
    summaries: list[CategorySummary],
) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{item.emoji} {item.label} · {item.character_count}",
            callback_data=_callback("menu", category=item.key),
        )
        for item in summaries
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=_callback("categories"),
            ),
            InlineKeyboardButton(text="✖ Закрыть", callback_data=_callback("close")),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_public_menu(page: PublicCharacterPage) -> str:
    type_label = _selected_label(
        page.category,
        CATEGORY_LABELS,
        empty_label="Все типы",
    )
    universe_label = _selected_label(
        page.universe_category,
        UNIVERSE_LABELS,
        empty_label="Все вселенные",
    )
    heading = f"{escape(type_label)} · {escape(universe_label)}"
    if page.total_characters == 0:
        return (
            f"<b>🔎 {heading}</b>\n\n"
            "По этому сочетанию пока нет персонажей с материалами."
        )
    return (
        f"<b>🔎 {heading}</b>\n\n"
        "Выберите персонажа. Список отсортирован по алфавиту.\n\n"
        f"Персонажей: <b>{page.total_characters}</b> · "
        f"страница <b>{page.page + 1}</b> из <b>{page.total_pages}</b>"
    )


def build_public_character_menu(page: PublicCharacterPage) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    filter_key = encode_public_filter(page.category, page.universe_category)
    for item in page.items:
        world = UNIVERSE_LABELS.get(item.universe_category or "", "")
        world_suffix = f" · {world}" if world else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🖼 {item.character.name}{world_suffix} · {item.media_count}",
                    callback_data=_callback(
                        "open",
                        character_id=item.character.id,
                        offset=0,
                        page=page.page,
                        category=filter_key,
                    ),
                )
            ]
        )

    if page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_callback(
                        "menu",
                        page=(page.page - 1) % page.total_pages,
                        category=filter_key,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=_callback(
                        "noop", page=page.page, category=filter_key
                    ),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_callback(
                        "menu",
                        page=(page.page + 1) % page.total_pages,
                        category=filter_key,
                    ),
                ),
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Фильтры",
                callback_data=_callback("filters", category=filter_key),
            ),
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=_callback(
                    "menu", page=page.page, category=filter_key
                ),
            ),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="✖ Закрыть", callback_data=_callback("close"))]
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
    category: str = "",
    prompt_post_url: str | None = None,
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
            category=category,
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
                        category=category,
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
                        category=category,
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
                    category=category,
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
                    category=category,
                ),
            ),
        ]
    )

    effective_prompt_url = page.media.prompt_post_url
    if effective_prompt_url:
        rows.append(
            [InlineKeyboardButton(text="📝 Открыть промт", url=effective_prompt_url)]
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
                        category=category,
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К персонажам",
                callback_data=_callback(
                    "back", page=menu_page, category=category
                ),
            ),
            InlineKeyboardButton(text="✖ Закрыть", callback_data=_callback("close")),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_public_notification_keyboard(
    character_id: int,
    *,
    media_id: int = 0,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Открыть новый материал",
                    callback_data=_callback(
                        "open",
                        character_id=character_id,
                        offset=0,
                        media_id=media_id,
                    ),
                )
            ]
        ]
    )
