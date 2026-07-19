from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.analytics_callbacks import (
    DashboardLinkCallback,
    dashboard_link,
    management_link,
)
from velvet_bot.analytics_dashboard import (
    PERIOD_LABELS,
    list_post_type_dashboard,
    normalize_period,
)
from velvet_bot.database import Database
from velvet_bot.post_classification import POST_TYPE_LABELS
from velvet_bot.presentation.telegram.routers.analytics_controllers.management_tags import (
    _show_unresolved_queue,
)

router = Router(name=__name__)


def _primary_channel_id(analytics_channel_ids: frozenset[int]) -> int | None:
    return sorted(analytics_channel_ids)[0] if analytics_channel_ids else None


def _period_row(action: str, period: str) -> list[InlineKeyboardButton]:
    labels = (("7d", "7 дней"), ("30d", "30 дней"), ("all", "Всё время"))
    return [
        InlineKeyboardButton(
            text=("● " if key == period else "") + label,
            callback_data=dashboard_link(action, period=key),
        )
        for key, label in labels
    ]


@router.callback_query(
    DashboardLinkCallback.filter(F.action.in_({"unresolved", "types"}))
)
async def handle_managed_dashboard_sections(
    callback: CallbackQuery,
    callback_data: DashboardLinkCallback,
    database: Database,
    analytics_channel_ids: frozenset[int],
) -> None:
    channel_id = _primary_channel_id(analytics_channel_ids)
    if channel_id is None:
        await callback.answer("Основной канал аналитики не настроен.", show_alert=True)
        return
    period = normalize_period(callback_data.period)

    if callback_data.action == "unresolved":
        await _show_unresolved_queue(
            callback,
            database,
            channel_id=channel_id,
            period=period,
            page_number=callback_data.page,
        )
        await callback.answer()
        return

    items = await list_post_type_dashboard(database, channel_id, period=period)
    lines = [
        f"• <b>{escape(POST_TYPE_LABELS.get(item.key, item.label))}</b> — "
        f"{item.count}; уверенность {item.secondary_count}%"
        for item in items
    ] or ["• данных пока нет"]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            _period_row("types", period),
            [
                InlineKeyboardButton(
                    text="⚠️ Проверить сомнительные",
                    callback_data=management_link(
                        "review",
                        period=period,
                        value="low",
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🤖 Пересчитать автоматические",
                    callback_data=management_link("reclassify", period=period),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Аналитика",
                    callback_data=dashboard_link("menu", period=period),
                )
            ],
        ]
    )
    await callback.message.edit_text(
        "<b>Типы публикаций</b>\n\n"
        f"Период: <b>{PERIOD_LABELS[period]}</b>\n\n"
        + "\n".join(lines),
        reply_markup=keyboard,
    )
    await callback.answer()


__all__ = ("router",)
