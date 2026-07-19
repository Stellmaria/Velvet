from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from velvet_bot.analytics_callbacks import AnalyticsManageCallback
from velvet_bot.analytics_dashboard import normalize_period
from velvet_bot.database import Database
from velvet_bot.handlers.analytics_management_aliases import (
    ALIAS_ACTIONS,
    _ALIAS_REPLY_RE,
    handle_alias_action,
    handle_alias_reply_message,
)
from velvet_bot.handlers.analytics_management_common import _primary_channel_id, _short
from velvet_bot.handlers.analytics_management_publications import (
    PUBLICATION_ACTIONS,
    _TYPE_BUTTON_LABELS,
    handle_publication_action,
)
from velvet_bot.handlers.analytics_management_tags import TAG_ACTIONS, handle_tag_action

router = Router(name=__name__)


@router.callback_query(AnalyticsManageCallback.filter())
async def handle_analytics_management(
    callback: CallbackQuery,
    callback_data: AnalyticsManageCallback,
    database: Database,
    analytics_channel_ids: frozenset[int],
) -> None:
    action = callback_data.action
    period = normalize_period(callback_data.period)

    if action == "noop":
        await callback.answer()
        return

    if action in ALIAS_ACTIONS:
        await handle_alias_action(
            callback,
            callback_data,
            database,
            period=period,
        )
        return

    channel_id = _primary_channel_id(analytics_channel_ids)
    if action in TAG_ACTIONS or action in PUBLICATION_ACTIONS:
        if channel_id is None:
            await callback.answer(
                "Основной канал аналитики не настроен.",
                show_alert=True,
            )
            return

    if action in TAG_ACTIONS:
        await handle_tag_action(
            callback,
            callback_data,
            database,
            channel_id=channel_id,
            period=period,
        )
        return

    if action in PUBLICATION_ACTIONS:
        await handle_publication_action(
            callback,
            callback_data,
            database,
            channel_id=channel_id,
            period=period,
        )
        return

    await callback.answer("Неизвестное действие аналитики.", show_alert=True)


@router.message(F.reply_to_message.text.contains("ALIAS_CHARACTER:"))
async def handle_alias_reply(message: Message, database: Database) -> None:
    await handle_alias_reply_message(message, database)


__all__ = (
    "_ALIAS_REPLY_RE",
    "_TYPE_BUTTON_LABELS",
    "_short",
    "router",
)
