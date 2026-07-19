from __future__ import annotations

from html import escape

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.archive_catalog import ArchivePage
from velvet_bot.character_directory import (
    CATEGORY_EMOJI,
    CATEGORY_LABELS,
    UNIVERSE_EMOJI,
    UNIVERSE_LABELS,
    CategorySummary,
    UniverseSummary,
)
from velvet_bot.public_catalog import PublicCharacterPage, PublicMediaState
from velvet_bot.story_catalog import StorySummary, universe_requires_story


class PublicArchiveCallback(CallbackData, prefix="pub"):
    action: str
    character_id: int = 0
    offset: int = 0
    media_id: int = 0
    page: int = 0
    category: str = ""
    universe: str = ""
    story_id: int = 0


def _callback(
    action: str,
    *,
    character_id: int = 0,
    offset: int = 0,
    media_id: int = 0,
    page: int = 0,
    category: str = "",
    universe: str = "",
    story_id: int = 0,
) -> str:
    return PublicArchiveCallback(
        action=action,
        character_id=character_id,
        offset=offset,
        media_id=media_id,
        page=page,
        category=category,
        universe=universe,
        story_id=story_id,
    ).pack()


def build_public_entry_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Открыть архив персонажей",
                    callback_data=_callback("categories"),
                )
            ]
        ]
    )


def format_public_categories(summaries: list[CategorySummary]) -> str:
    total = sum(item.character_count for item in summaries)
    return (
        "<b>Архив персонажей Velvet</b>\n\n"
        "Сначала выберите пол или состав персонажей, затем вселенную "
        "и историю.\n\n"
        f"Персонажей с материалами: <b>{total}</b>"
    )


def build_public_category_menu(
    summaries: list[CategorySummary],
) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{item.emoji} {item.label} · {item.character_count}",
            callback_data=_callback("universes", category=item.key),
        )
        for item in summaries
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(buttons), 2):
        rows.append(buttons[index : index + 2])
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


def format_public_universes(
    category: str,
    summaries: list[UniverseSummary],
) -> str:
    category_label = CATEGORY_LABELS.get(category, category)
    category_emoji = CATEGORY_EMOJI.get(category, "🗂")
    total = sum(item.character_count for item in summaries)
    return (
        f"<b>{category_emoji} {escape(category_label)}</b>\n\n"
        "Выберите вселенную или серию. Для визуальных новелл следующим "
        "шагом откроются истории.\n\n"
        f"Персонажей с материалами: <b>{total}</b>"
    )


def build_public_universe_menu(
    category: str,
    summaries: list[UniverseSummary],
) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{item.emoji} {item.label} · {item.character_count}",
            callback_data=_callback(
                "stories" if universe_requires_story(item.key) else "menu",
                category=category,
                universe=item.key,
            ),
        )
        for item in summaries
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Пол / состав",
                callback_data=_callback("categories"),
            ),
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=_callback("universes", category=category),
            ),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="✖ Закрыть", callback_data=_callback("close"))]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_public_stories(
    category: str,
    universe: str,
    summaries: list[StorySummary],
) -> str:
    category_label = CATEGORY_LABELS.get(category, category)
    category_emoji = CATEGORY_EMOJI.get(category, "🗂")
    universe_label = UNIVERSE_LABELS.get(universe, universe)
    universe_emoji = UNIVERSE_EMOJI.get(universe, "🎭")
    total = sum(item.character_count for item in summaries)
    return (
        f"<b>{category_emoji} {escape(category_label)} · "
        f"{universe_emoji} {escape(universe_label)}</b>\n\n"
        "Выберите историю. На кнопках сначала указано её сокращение "
        "из первых букв.\n\n"
        f"Персонажей с материалами: <b>{total}</b>"
    )


def build_public_story_menu(
    category: str,
    universe: str,
    summaries: list[StorySummary],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in summaries:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"📖 {item.short_label} · {item.title} "
                        f"· {item.character_count}"
                    ),
                    callback_data=_callback(
                        "menu",
                        category=category,
                        universe=universe,
                        story_id=item.id,
                    ),
                )
            ]
        )
    if not rows:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Пока нет назначенных персонажей",
                    callback_data=_callback("noop"),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Вселенные",
                callback_data=_callback("universes", category=category),
            ),
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=_callback(
                    "stories",
                    category=category,
                    universe=universe,
                ),
            ),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="✖ Закрыть", callback_data=_callback("close"))]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_public_menu(page: PublicCharacterPage) -> str:
    category_label = CATEGORY_LABELS.get(page.category, page.category)
    category_emoji = CATEGORY_EMOJI.get(page.category, "🗂")
    universe_key = page.universe or ""
    universe_label = UNIVERSE_LABELS.get(universe_key, universe_key)
    universe_emoji = UNIVERSE_EMOJI.get(universe_key, "🎭")
    parts = [
        f"{category_emoji} {escape(category_label)}",
        f"{universe_emoji} {escape(universe_label)}",
    ]
    if page.story_title:
        short = page.story_short_label or "📖"
        parts.append(f"📖 {escape(short)} · {escape(page.story_title)}")
    title = " · ".join(parts)
    if page.total_characters == 0:
        return f"<b>{title}</b>\n\nВ этом сочетании пока нет материалов."
    return (
        f"<b>{title}</b>\n\n"
        "Выберите персонажа. Список отсортирован по алфавиту.\n\n"
        f"Персонажей: <b>{page.total_characters}</b> · "
        f"страница <b>{page.page + 1}</b> из <b>{page.total_pages}</b>"
    )


def build_public_character_menu(page: PublicCharacterPage) -> InlineKeyboardMarkup:
    universe = page.universe or ""
    story_id = page.story_id or 0
    rows: list[list[InlineKeyboardButton]] = []
    for item in page.items:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🖼 {item.character.name} · {item.media_count}",
                    callback_data=_callback(
                        "open",
                        character_id=item.character.id,
                        offset=0,
                        page=page.page,
                        category=page.category,
                        universe=universe,
                        story_id=story_id,
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
                        category=page.category,
                        universe=universe,
                        story_id=story_id,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=_callback(
                        "noop",
                        page=page.page,
                        category=page.category,
                        universe=universe,
                        story_id=story_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_callback(
                        "menu",
                        page=(page.page + 1) % page.total_pages,
                        category=page.category,
                        universe=universe,
                        story_id=story_id,
                    ),
                ),
            ]
        )

    if universe_requires_story(universe):
        back_button = InlineKeyboardButton(
            text="↩️ Истории",
            callback_data=_callback(
                "stories",
                category=page.category,
                universe=universe,
            ),
        )
    else:
        back_button = InlineKeyboardButton(
            text="↩️ Вселенные",
            callback_data=_callback(
                "universes",
                category=page.category,
            ),
        )
    rows.append(
        [
            back_button,
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=_callback(
                    "menu",
                    page=page.page,
                    category=page.category,
                    universe=universe,
                    story_id=story_id,
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
    can_download: bool = False,
    menu_page: int = 0,
    category: str = "",
    universe: str = "",
    story_id: int = 0,
    prompt_post_url: str | None = None,
) -> InlineKeyboardMarkup:
    if page.media is None or page.total <= 0:
        return InlineKeyboardMarkup(inline_keyboard=[])

    media_id = page.media.id
    common = {
        "character_id": page.character.id,
        "page": menu_page,
        "category": category,
        "universe": universe,
        "story_id": story_id,
    }
    counter = InlineKeyboardButton(
        text=f"{page.offset + 1} / {page.total}",
        callback_data=_callback(
            "noop",
            offset=page.offset,
            media_id=media_id,
            **common,
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
                        offset=(page.offset - 1) % page.total,
                        **common,
                    ),
                ),
                counter,
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_callback(
                        "show",
                        offset=(page.offset + 1) % page.total,
                        **common,
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
                    offset=page.offset,
                    media_id=media_id,
                    **common,
                ),
            ),
            InlineKeyboardButton(
                text="🔕 Отписаться" if state.subscribed else "🔔 Подписаться",
                callback_data=_callback(
                    "sub",
                    offset=page.offset,
                    media_id=media_id,
                    **common,
                ),
            ),
        ]
    )

    effective_prompt_url = page.media.prompt_post_url
    if effective_prompt_url:
        rows.append(
            [InlineKeyboardButton(text="📝 Открыть промт", url=effective_prompt_url)]
        )

    if can_download:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📥 Скачать файлом",
                    callback_data=_callback(
                        "download",
                        offset=page.offset,
                        media_id=media_id,
                        **common,
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К персонажам",
                callback_data=_callback(
                    "back",
                    page=menu_page,
                    category=category,
                    universe=universe,
                    story_id=story_id,
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
