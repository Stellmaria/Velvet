from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.analytics_dashboard import (
    PERIOD_LABELS,
    DiscussionDashboard,
    list_discussion_sources,
    normalize_period,
    period_since,
)
from velvet_bot.database import Database
from velvet_bot.handlers.analytics_dashboard import AnalyticsCallback, _cb, _period_row
from velvet_bot.safe_analytics_edit import safe_analytics_edit

router = Router(name=__name__)


async def _get_discussion_dashboard(
    database: Database,
    chat_id: int,
    *,
    period: str,
) -> DiscussionDashboard:
    since = period_since(period)
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                COALESCE(MAX(t.title), t.chat_id::TEXT) AS title,
                COUNT(p.id) AS total_messages,
                COUNT(DISTINCT p.sender_id) FILTER (WHERE p.sender_id IS NOT NULL)
                    AS unique_participants,
                COUNT(p.id) FILTER (WHERE p.reply_to_message_id IS NOT NULL)
                    AS reply_messages,
                COUNT(p.id) FILTER (WHERE p.media_type <> 'text') AS media_messages,
                COUNT(p.id) FILTER (WHERE p.has_spoiler) AS spoiler_messages,
                COUNT(p.id) FILTER (WHERE p.is_prompt) AS prompt_messages,
                COALESCE(SUM(p.reactions_total), 0) AS total_reactions,
                MIN(p.posted_at) AS first_message_at,
                MAX(p.posted_at) AS last_message_at
            FROM tracked_channels AS t
            LEFT JOIN channel_posts AS p
                ON p.channel_id = t.chat_id
               AND ($2::TIMESTAMPTZ IS NULL OR p.posted_at >= $2)
            WHERE t.chat_id = $1::BIGINT
            GROUP BY t.chat_id
            """,
            int(chat_id),
            since,
        )
    return DiscussionDashboard(
        chat_id=int(chat_id),
        title=str(row["title"] if row else chat_id),
        total_messages=int(row["total_messages"] or 0) if row else 0,
        unique_participants=int(row["unique_participants"] or 0) if row else 0,
        reply_messages=int(row["reply_messages"] or 0) if row else 0,
        media_messages=int(row["media_messages"] or 0) if row else 0,
        spoiler_messages=int(row["spoiler_messages"] or 0) if row else 0,
        prompt_messages=int(row["prompt_messages"] or 0) if row else 0,
        total_reactions=int(row["total_reactions"] or 0) if row else 0,
        first_message_at=row["first_message_at"] if row else None,
        last_message_at=row["last_message_at"] if row else None,
    )


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

    source_id = int(callback_data.source_id)
    item = await _get_discussion_dashboard(database, source_id, period=period)
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
