from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.archive_catalog import ArchivePage
from velvet_bot.character_directory import (
    CATEGORY_EMOJI,
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    UNIVERSE_EMOJI,
    UNIVERSE_LABELS,
    UNIVERSE_ORDER,
)
from velvet_bot.public_ui import (
    PublicArchiveCallback,
    build_public_archive_keyboard,
)
from velvet_bot.story_catalog import StoryPage, universe_requires_story


def manager_callback(
    action: str,
    *,
    character_id: int,
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


def build_manager_archive_keyboard(
    page: ArchivePage,
    state,
    *,
    category: str,
    universe: str,
    story_id: int,
) -> InlineKeyboardMarkup:
    if page.media is None:
        return InlineKeyboardMarkup(inline_keyboard=[])
    base = build_public_archive_keyboard(
        page,
        state,
        viewer_user_id=0,
        can_download=True,
        category=category,
        universe=universe,
        story_id=story_id,
    )
    rows = [list(row) for row in base.inline_keyboard]
    final_row = rows.pop() if rows else []
    common = {
        "character_id": page.character.id,
        "offset": page.offset,
        "media_id": page.media.id,
    }
    watermark_label = (
        "🔄 Переделать watermark"
        if getattr(state, "watermark_approved", False)
        else "⚡ Быстрый watermark"
    )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=watermark_label,
                    callback_data=manager_callback("pwm", **common),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "👁 Вернуть в публичный"
                        if not page.media.is_public
                        else "🙈 Скрыть из публичного"
                    ),
                    callback_data=manager_callback("ppub", **common),
                ),
                InlineKeyboardButton(
                    text=(
                        "🔞 Снять отметку +18"
                        if page.media.requires_adult_channel
                        else "🔞 Пометить как +18"
                    ),
                    callback_data=manager_callback("p18", **common),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "🌫 Убрать блюр"
                        if page.media.is_spoiler
                        else "🌫 Включить блюр"
                    ),
                    callback_data=manager_callback("psp", **common),
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=manager_callback("pdel", **common),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="👥 Пол / состав",
                    callback_data=manager_callback("pcats", **common),
                ),
                InlineKeyboardButton(
                    text="🎭 Вселенная",
                    callback_data=manager_callback("punis", **common),
                ),
            ],
        ]
    )
    if universe_requires_story(universe):
        rows.append(
            [
                InlineKeyboardButton(
                    text="📖 История",
                    callback_data=manager_callback("psts", **common),
                )
            ]
        )
    if final_row:
        rows.append(final_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_manager_category_picker(page: ArchivePage) -> InlineKeyboardMarkup:
    if page.media is None:
        return InlineKeyboardMarkup(inline_keyboard=[])
    common = {
        "character_id": page.character.id,
        "offset": page.offset,
        "media_id": page.media.id,
    }
    buttons = [
        InlineKeyboardButton(
            text=f"{CATEGORY_EMOJI[key]} {CATEGORY_LABELS[key]}",
            callback_data=manager_callback("pcat", category=key, **common),
        )
        for key in CATEGORY_ORDER
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Назад",
                callback_data=manager_callback("pback", **common),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_manager_universe_picker(page: ArchivePage) -> InlineKeyboardMarkup:
    if page.media is None:
        return InlineKeyboardMarkup(inline_keyboard=[])
    common = {
        "character_id": page.character.id,
        "offset": page.offset,
        "media_id": page.media.id,
    }
    buttons = [
        InlineKeyboardButton(
            text=f"{UNIVERSE_EMOJI[key]} {UNIVERSE_LABELS[key]}",
            callback_data=manager_callback("puni", universe=key, **common),
        )
        for key in UNIVERSE_ORDER
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Назад",
                callback_data=manager_callback("pback", **common),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_manager_story_picker(
    page: ArchivePage,
    story_page: StoryPage,
) -> InlineKeyboardMarkup:
    if page.media is None:
        return InlineKeyboardMarkup(inline_keyboard=[])
    common = {
        "character_id": page.character.id,
        "offset": page.offset,
        "media_id": page.media.id,
    }
    rows = [
        [
            InlineKeyboardButton(
                text=f"📖 {story.short_label} · {story.title}",
                callback_data=manager_callback("pst", story_id=story.id, **common),
            )
        ]
        for story in story_page.items
    ]
    if story_page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️ Новее",
                    callback_data=manager_callback(
                        "pstp",
                        page=(story_page.page - 1) % story_page.total_pages,
                        **common,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{story_page.page + 1} / {story_page.total_pages}",
                    callback_data=manager_callback("pnoop", **common),
                ),
                InlineKeyboardButton(
                    text="Старее ▶️",
                    callback_data=manager_callback(
                        "pstp",
                        page=(story_page.page + 1) % story_page.total_pages,
                        **common,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Назад",
                callback_data=manager_callback("pback", **common),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_manager_delete_confirmation(page: ArchivePage) -> InlineKeyboardMarkup:
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
                    text="✅ Удалить",
                    callback_data=manager_callback("pdelok", **common),
                ),
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=manager_callback("pdelno", **common),
                ),
            ]
        ]
    )
