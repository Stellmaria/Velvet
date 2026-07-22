from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from velvet_bot.analytics_dashboard import PERIOD_LABELS, normalize_period
from velvet_bot.character_directory import category_label, universe_label
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.analytics_access import AnalyticsWorkspaceContext
from velvet_bot.domains.workspaces.analytics_queries import (
    list_workspace_character_dashboard,
    list_workspace_character_usage_stats,
)
from velvet_bot.presentation.telegram.analytics_navigation import AnalyticsCallback
from velvet_bot.presentation.telegram.routers.analytics_controllers.channel import (
    _character_lines,
)
from velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard import (
    _page_keyboard,
    _rank_lines,
)
from velvet_bot.presentation.telegram.routers.workspace_analytics import (
    PersonalAnalyticsWorkspaceFilter,
    _reject_access,
)
from velvet_bot.safe_analytics_edit import safe_analytics_edit

router = Router(name=__name__)


@router.message(
    Command("characterstats"),
    PersonalAnalyticsWorkspaceFilter(),
)
async def handle_workspace_character_stats(
    message: Message,
    database: Database,
    personal_analytics_context: AnalyticsWorkspaceContext,
) -> None:
    if await _reject_access(message, personal_analytics_context):
        return
    channel_id = personal_analytics_context.primary_channel_id
    if channel_id is None:
        await message.answer("Канал аналитики пространства не настроен.")
        return
    items = await list_workspace_character_usage_stats(
        database,
        channel_id,
        workspace_id=personal_analytics_context.workspace_id,
        limit=30,
    )
    await message.answer(
        "<b>Персонажи, задействованные в канале пространства</b>\n\n"
        f"{_character_lines(items, limit=30)}"
    )


@router.callback_query(
    AnalyticsCallback.filter(F.action == "characters"),
    PersonalAnalyticsWorkspaceFilter(),
)
async def handle_workspace_character_dashboard(
    callback: CallbackQuery,
    callback_data: AnalyticsCallback,
    database: Database,
    personal_analytics_context: AnalyticsWorkspaceContext,
) -> None:
    await _handle_workspace_character_dashboard(
        callback,
        callback_data,
        database,
        personal_analytics_context,
    )


async def _handle_workspace_character_dashboard(
    callback: CallbackQuery,
    callback_data: AnalyticsCallback,
    database: Database,
    context: AnalyticsWorkspaceContext,
) -> None:
    if await _reject_access(callback, context):
        return
    channel_id = context.primary_channel_id
    if channel_id is None:
        await callback.answer(
            "Канал аналитики пространства не настроен.",
            show_alert=True,
        )
        return
    period = normalize_period(callback_data.period)
    page = await list_workspace_character_dashboard(
        database,
        channel_id,
        workspace_id=context.workspace_id,
        period=period,
        page=callback_data.page,
    )
    normalized_items = []
    for item in page.items:
        parts = (item.detail or "").split(" / ") if item.detail else []
        if parts:
            parts[0] = category_label(parts[0])
        if len(parts) > 1:
            parts[1] = universe_label(parts[1])
        normalized_items.append(
            type(item)(
                key=item.key,
                label=item.label,
                count=item.count,
                secondary_count=item.secondary_count,
                detail=" / ".join(parts) if parts else None,
            )
        )
    page = type(page)(
        items=normalized_items,
        page=page.page,
        page_size=page.page_size,
        total_items=page.total_items,
    )
    text = (
        "<b>Персонажи канала пространства</b>\n\n"
        f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
        f"Задействовано: <b>{page.total_items}</b>\n\n"
        f"{_rank_lines(page, kind='characters')}"
    )
    await safe_analytics_edit(
        callback,
        text,
        _page_keyboard("characters", period, page),
    )
    await callback.answer()


__all__ = ("router",)
