from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton

from velvet_bot.analytics_dashboard import normalize_period


class AnalyticsCallback(CallbackData, prefix="dash"):
    action: str
    period: str = "all"
    page: int = 0
    source_id: int = 0


def _cb(
    action: str,
    *,
    period: str = "all",
    page: int = 0,
    source_id: int = 0,
) -> str:
    return AnalyticsCallback(
        action=action,
        period=normalize_period(period),
        page=max(0, page),
        source_id=source_id,
    ).pack()


def _period_row(
    action: str,
    period: str,
    *,
    source_id: int = 0,
) -> list[InlineKeyboardButton]:
    labels = (("7d", "7 дней"), ("30d", "30 дней"), ("all", "Всё время"))
    return [
        InlineKeyboardButton(
            text=("● " if key == period else "") + label,
            callback_data=_cb(action, period=key, source_id=source_id),
        )
        for key, label in labels
    ]


__all__ = ("AnalyticsCallback", "_cb", "_period_row")
