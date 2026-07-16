from __future__ import annotations

from aiogram.filters.callback_data import CallbackData

from velvet_bot.analytics_dashboard import normalize_period
from velvet_bot.handlers.analytics_dashboard import AnalyticsCallback as DashboardLinkCallback


class AnalyticsManageCallback(CallbackData, prefix="dashm"):
    action: str
    period: str = "all"
    page: int = 0
    token_id: int = 0
    character_id: int = 0
    alias_id: int = 0
    value: str = ""


def dashboard_link(
    action: str,
    *,
    period: str = "all",
    page: int = 0,
    source_id: int = 0,
) -> str:
    return DashboardLinkCallback(
        action=action,
        period=normalize_period(period),
        page=max(0, page),
        source_id=source_id,
    ).pack()


def management_link(
    action: str,
    *,
    period: str = "all",
    page: int = 0,
    token_id: int = 0,
    character_id: int = 0,
    alias_id: int = 0,
    value: str = "",
) -> str:
    return AnalyticsManageCallback(
        action=action,
        period=normalize_period(period),
        page=max(0, page),
        token_id=token_id,
        character_id=character_id,
        alias_id=alias_id,
        value=value,
    ).pack()


__all__ = (
    "AnalyticsManageCallback",
    "DashboardLinkCallback",
    "dashboard_link",
    "management_link",
)
