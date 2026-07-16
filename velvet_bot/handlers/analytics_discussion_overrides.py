from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.analytics_dashboard import (
    PERIOD_LABELS,
    get_discussion_dashboard,
    list_discussion_sources,
    normalize_period,
)
from velvet_bot.database import Database
from velvet_bot.handlers.analytics_dashboard import AnalyticsCallback, _cb, _period_row
from velvet_bot.safe_analytics_edit import safe_analytics_edit

router = Router(name=__name__)


@router.callback_query(
    AnalyticsCallback.filter(F.action.in_({"discussions", "discussion"}))
)
async def handle_discussion_sections(
    callback: CallbackQuery,
    callback_data: AnalyticsCallback,
    database: Database,
    analytics_channel_ids: frozenset[int],
) -> None:
    period = normalize_period(callback_data.period)
    channel_id = sorted(analytics_channel_ids)[0] if analytics_channel_ids else None
    if channel_id is None:
        await callback.answer("Основной канал аналитики не настроен.", show_alert=True)
        return

    if callback_data.action == "discussions":
        raw_sources = await list_discussion_sources(
            database,
            parent_channel_id=channel_id,
        )
        sources = list({source.chat_id: source for source in raw_sources}.values())
        rows = [
            [
                InlineKeyboardButton(
                    text=f"💬 Обсуждение · {source.title}",
                    callback_data=_cb(
                        "discussion",
                        period=period,
                        source_id=source.chat_id,
                    ),
                )
            ]
            for source in sources
        ]
        rows.append(_period_row("discussions", period))
        rows.append(
            [
                InlineKeyboardButton(
                    text="↩️ Аналитика",
                    callback_data=_cb("menu", period=period),
                ),
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=_cb("discussions", period=period),
                ),
            ]
        )
        text = (
            "<b>Обсуждения канала</b>\n\n"
            f"📣 Канал: <code>{channel_id}</code>\n"
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
            f"Подключено чатов: <b>{len(sources)}</b>\n\n"
            + (
                "Выберите связанный чат обсуждений."
                if sources
                else "Связанный чат пока не подключён."
            )
        )
        await safe_analytics_edit(
            callback,
            text,
            InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await callback.answer()
        return

    source_id = callback_data.source_id
    item = await get_discussion_dashboard(database, source_id, period=period)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            _period_row("discussion", period, source_id=source_id),
            [
                InlineKeyboardButton(
                    text="👥 Участники",
                    callback_data=_cb(
                        "participants",
                        period=period,
                        source_id=source_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Чаты",
                    callback_data=_cb("discussions", period=period),
                ),
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=_cb(
                        "discussion",
                        period=period,
                        source_id=source_id,
                    ),
                ),
            ],
        ]
    )
    text = (
        f"<b>💬 Обсуждение · {escape(item.title)}</b>\n\n"
        f"📣 Канал: <code>{channel_id}</code>\n"
        f"💬 Чат: <code>{source_id}</code>\n"
        f"Период: <b>{PERIOD_LABELS[period]}</b>\n\n"
        f"Сообщений: <b>{item.total_messages}</b>\n"
        f"Участников: <b>{item.unique_participants}</b>\n"
        f"Ответов: <b>{item.reply_messages}</b>\n"
        f"Медиа: <b>{item.media_messages}</b>\n"
        f"Под спойлером: <b>{item.spoiler_messages}</b>\n"
        f"Промтов в обсуждении: <b>{item.prompt_messages}</b>\n"
        f"Реакций: <b>{item.total_reactions}</b>"
    )
    await safe_analytics_edit(callback, text, keyboard)
    await callback.answer()
