from __future__ import annotations

from html import escape

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.media_quality import DuplicatePage
from velvet_bot.quality_audit import QualityPage, QualitySummary


class QualityCallback(CallbackData, prefix="quality"):
    action: str
    section: str = ""
    page: int = 0
    item_id: int = 0


def quality_callback(
    action: str,
    *,
    section: str = "",
    page: int = 0,
    item_id: int = 0,
) -> str:
    return QualityCallback(
        action=action,
        section=section,
        page=max(0, page),
        item_id=item_id,
    ).pack()


def build_quality_dashboard(
    summary: QualitySummary,
) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "<b>Контроль качества Velvet Archive</b>\n\n"
        f"Найдено проблем: <b>{summary.total_problems}</b>\n"
        f"Визуальное сканирование: <b>{summary.pending_scans}</b> в очереди, "
        f"ошибок <b>{summary.scan_errors}</b>\n"
        f"Проверка Telegram-файлов: <b>{summary.unchecked_files}</b> в очереди\n\n"
        "Выберите раздел. Исправления открываются через существующие карточки "
        "персонажей и материалов."
    )
    rows = [
        [
            InlineKeyboardButton(
                text=f"🧬 Дубли · {summary.pending_duplicates}",
                callback_data=quality_callback("duplicates", section="pending"),
            ),
            InlineKeyboardButton(
                text=f"✅ Подтверждены · {summary.confirmed_duplicates}",
                callback_data=quality_callback("duplicates", section="confirmed"),
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"👥 Без категории · {summary.missing_category}",
                callback_data=quality_callback("section", section="missing_category"),
            ),
            InlineKeyboardButton(
                text=f"🌌 Без вселенной · {summary.missing_universe}",
                callback_data=quality_callback("section", section="missing_universe"),
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"📖 Без истории · {summary.missing_story}",
                callback_data=quality_callback("section", section="missing_story"),
            ),
            InlineKeyboardButton(
                text=f"📦 Без материалов · {summary.empty_characters}",
                callback_data=quality_callback("section", section="empty_characters"),
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"📝 Без поста · {summary.media_without_prompt}",
                callback_data=quality_callback("section", section="media_without_prompt"),
            ),
            InlineKeyboardButton(
                text=f"🔗 Битые файлы · {summary.broken_files}",
                callback_data=quality_callback("section", section="broken_files"),
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"⚠ Ошибки сканирования · {summary.scan_errors}",
                callback_data=quality_callback("section", section="scan_errors"),
            ),
            InlineKeyboardButton(
                text=f"#️⃣ Не распознано · {summary.unresolved_hashtags}",
                callback_data=quality_callback("section", section="unresolved_hashtags"),
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"🗃 Сиротские записи · {summary.orphan_media}",
                callback_data=quality_callback("orphan_info"),
            )
        ],
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data=quality_callback("menu")),
            InlineKeyboardButton(text="✖ Закрыть", callback_data=quality_callback("close")),
        ],
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def page_navigation(
    *,
    page: int,
    total_pages: int,
    action: str,
    section: str,
) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    if total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=quality_callback(
                        action,
                        section=section,
                        page=(page - 1) % total_pages,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page + 1} / {total_pages}",
                    callback_data=quality_callback("noop"),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=quality_callback(
                        action,
                        section=section,
                        page=(page + 1) % total_pages,
                    ),
                ),
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="↩️ К аудиту", callback_data=quality_callback("menu"))]
    )
    return rows


def build_duplicate_list(
    page: DuplicatePage,
    *,
    status: str,
) -> tuple[str, InlineKeyboardMarkup]:
    status_label = {
        "pending": "Требуют проверки",
        "confirmed": "Подтверждённые дубли",
        "ignored": "Отмечены как разные",
    }.get(status, status)
    text = (
        f"<b>🧬 {escape(status_label)}</b>\n\n"
        f"Пар: <b>{page.total_items}</b>\n"
        f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>"
    )
    rows: list[list[InlineKeyboardButton]] = []
    for item in page.items:
        marker = "точно" if item.exact_bytes else f"pHash {item.phash_distance}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{item.similarity_score}% · "
                        f"{item.first_media_id}/{item.second_media_id} · {marker}"
                    ),
                    callback_data=quality_callback(
                        "duplicate",
                        section=status,
                        page=page.page,
                        item_id=item.id,
                    ),
                )
            ]
        )
    rows.extend(
        page_navigation(
            page=page.page,
            total_pages=page.total_pages,
            action="duplicates",
            section=status,
        )
    )
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def build_quality_page(
    page: QualityPage,
    *,
    section: str,
    title: str,
    item_rows: list[list[InlineKeyboardButton]],
    extra_rows: list[list[InlineKeyboardButton]] | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    lines = [
        f"<b>{escape(title)}</b>",
        "",
        f"Найдено: <b>{page.total_items}</b>",
        f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>",
    ]
    for item in page.items:
        lines.extend(["", f"• <b>{escape(item.label)}</b>", escape(item.detail)])
    rows = list(item_rows)
    if extra_rows:
        rows.extend(extra_rows)
    rows.extend(
        page_navigation(
            page=page.page,
            total_pages=page.total_pages,
            action="section",
            section=section,
        )
    )
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)
