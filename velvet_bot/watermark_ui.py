from __future__ import annotations

from html import escape

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.domains.watermark.models import WatermarkWorkItem
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.workspace_watermark_ui import watermark_asset_callback


class WatermarkCallback(CallbackData, prefix="wm"):
    action: str
    job_id: int = 0
    value: str = ""


def _button(text: str, action: str, job_id: int, value: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=WatermarkCallback(action=action, job_id=job_id, value=value).pack(),
    )


def build_watermark_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("📎 Как отправить изображение", "help", 0)],
            [_button("↩️ Центр управления", "menu", 0)],
        ]
    )


def _settings_rows(item: WatermarkWorkItem) -> list[list[InlineKeyboardButton]]:
    job_id = item.job.id
    rows = [
        [
            _button("↖️", "position", job_id, "top_left"),
            _button("↗️", "position", job_id, "top_right"),
            _button("↙️", "position", job_id, "bottom_left"),
            _button("↘️", "position", job_id, "bottom_right"),
        ]
    ]
    if item.job.logo_kind == "builtin":
        rows.append(
            [
                _button("⚪ Белый", "color", job_id, "#ffffff"),
                _button("⚫ Чёрный", "color", job_id, "#000000"),
                _button("◐ Авто", "color", job_id, "auto"),
                _button("🎨 HEX", "custom_color", job_id),
            ]
        )
    rows.extend(
        [
            [_button("Прозр. −", "opacity", job_id, "-10"), _button("Прозр. +", "opacity", job_id, "10")],
            [_button("Размер −", "size", job_id, "-1.5"), _button("Размер +", "size", job_id, "1.5")],
            [_button("Отступ −", "margin", job_id, "-0.5"), _button("Отступ +", "margin", job_id, "0.5")],
            [_button("↩️ Предыдущая версия", "undo", job_id), _button("🚫 Без знака", "remove", job_id)],
        ]
    )
    return rows


def build_archive_watermark_review_keyboard(
    item: WatermarkWorkItem,
) -> InlineKeyboardMarkup:
    job_id = item.job.id
    rows = [
        [_button("✅ Использовать watermark", "archive_approve", job_id)],
        [_button("🔄 Переделать", "archive_edit", job_id)],
    ]
    if item.job.workspace_id != DEFAULT_WORKSPACE_ID:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🎨 Изменить шаблон",
                    callback_data=watermark_asset_callback(
                        "show",
                        workspace_id=item.job.workspace_id,
                    ),
                )
            ]
        )
    rows.append([_button("✖ Отмена", "cancel", job_id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_archive_watermark_edit_keyboard(
    item: WatermarkWorkItem,
) -> InlineKeyboardMarkup:
    rows = _settings_rows(item)
    rows.append([_button("✅ Использовать watermark", "archive_approve", item.job.id)])
    if item.job.workspace_id != DEFAULT_WORKSPACE_ID:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🎨 Изменить шаблон",
                    callback_data=watermark_asset_callback(
                        "show",
                        workspace_id=item.job.workspace_id,
                    ),
                )
            ]
        )
    rows.append([_button("✖ Отмена", "cancel", item.job.id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_watermark_keyboard(item: WatermarkWorkItem) -> InlineKeyboardMarkup:
    status = item.revision.status
    if status in {"draft", "error"}:
        rows = _settings_rows(item)
        rows.append(
            [_button("▶️ Сгенерировать preview", "generate", item.job.id)]
        )
        rows.append([_button("✖ Отмена", "cancel", item.job.id)])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    if status in {"pending", "processing"}:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _button(
                        "⏳ Генерация выполняется",
                        "draft_noop",
                        item.job.id,
                    )
                ],
                [_button("✖ Отмена", "cancel", item.job.id)],
            ]
        )
    if item.job.archive_media_id is not None:
        return build_archive_watermark_review_keyboard(item)
    rows = _settings_rows(item)
    rows.append([_button("✅ Скачать PNG без сжатия", "approve", item.job.id)])
    rows.append([_button("✖ Отмена", "cancel", item.job.id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_watermark_caption(item: WatermarkWorkItem, *, status_text: str | None = None) -> str:
    if item.revision.status == "draft":
        status_text = (
            "черновик: выберите все параметры и затем нажмите "
            "«Сгенерировать preview»"
        )
    elif item.revision.status == "error" and status_text is None:
        status_text = "ошибка: измените параметры или повторите генерацию"
    settings = item.revision.settings
    color = settings.color.upper() if settings.enabled else "без знака"
    logo = (
        "стандартный Velvet"
        if item.job.logo_kind == "builtin"
        else f"{item.job.logo_kind.upper()}: {item.job.logo_name or 'workspace logo'}"
    )
    status = status_text or item.revision.status
    archive_line = (
        f"\nАрхивный media_id: <code>{item.job.archive_media_id}</code>"
        if item.job.archive_media_id is not None
        else ""
    )
    return (
        f"<b>Водяной знак · задание {item.job.id}</b>\n\n"
        f"Версия: <b>{item.revision.revision}</b>\n"
        f"Пространство: <code>{item.job.workspace_id}</code>\n"
        f"Логотип: <b>{escape(logo)}</b>\n"
        f"Положение: <code>{escape(settings.position)}</code>\n"
        f"Цвет: <code>{escape(color)}</code>\n"
        f"Непрозрачность: <b>{settings.opacity}%</b>\n"
        f"Размер: <b>{settings.size:.1f}%</b>\n"
        f"Отступ: <b>{settings.margin:.1f}%</b>\n"
        f"Статус: <b>{escape(status)}</b>"
        f"{archive_line}"
    )


__all__ = (
    "WatermarkCallback",
    "build_archive_watermark_edit_keyboard",
    "build_archive_watermark_review_keyboard",
    "build_watermark_keyboard",
    "build_watermark_start_keyboard",
    "format_watermark_caption",
)
