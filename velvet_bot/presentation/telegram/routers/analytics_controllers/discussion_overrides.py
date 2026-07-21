from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.analytics_dashboard import (
    PERIOD_LABELS,
    DashboardPage,
    list_discussion_sources,
    normalize_period,
)
from velvet_bot.database import Database
from velvet_bot.discussion_insights import (
    WEEKDAY_LABELS,
    DiscussedPostPage,
    format_delay,
    get_activity_breakdown,
    get_discussed_post,
    get_discussion_summary,
    list_active_participants,
    list_activity_spikes,
    list_discussed_characters,
    list_discussed_posts,
    list_discussed_stories,
    list_discussed_universes,
    list_most_replied_participants,
    list_publications_without_comments,
    list_reaction_leaders,
    rebuild_discussion_threads,
)
from velvet_bot.discussion_queries import get_discussion_parent_channel_id
from velvet_bot.presentation.telegram.navigation import compact_button_text
from velvet_bot.presentation.telegram.analytics_navigation import (
    AnalyticsCallback,
    _cb,
    _period_row,
)
from velvet_bot.safe_analytics_edit import safe_analytics_edit

router = Router(name=__name__)


class DiscussionInsightCallback(CallbackData, prefix="d5"):
    action: str
    period: str = "30d"
    chat_id: int = 0
    page: int = 0
    item_id: int = 0


def _dcb(
    action: str,
    *,
    period: str,
    chat_id: int,
    parent_id: int = 0,
    page: int = 0,
    item_id: int = 0,
) -> str:
    # parent_id is intentionally not packed: it is resolved from tracked_channels.
    # This keeps callback_data below Telegram's 64-byte hard limit.
    del parent_id
    return DiscussionInsightCallback(
        action=action,
        period=normalize_period(period),
        chat_id=int(chat_id),
        page=max(0, int(page)),
        item_id=max(0, int(item_id)),
    ).pack()


async def _resolve_parent_id(database: Database, chat_id: int) -> int | None:
    return await get_discussion_parent_channel_id(database, chat_id)


def _dperiod_row(
    action: str,
    period: str,
    *,
    chat_id: int,
    parent_id: int,
    item_id: int = 0,
) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text=("● " if key == period else "") + label,
            callback_data=_dcb(
                action,
                period=key,
                chat_id=chat_id,
                parent_id=parent_id,
                item_id=item_id,
            ),
        )
        for key, label in (("7d", "7 дней"), ("30d", "30 дней"), ("all", "Всё"))
    ]


def _summary_keyboard(
    period: str,
    *,
    chat_id: int,
    parent_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            _dperiod_row(
                "sum",
                period,
                chat_id=chat_id,
                parent_id=parent_id,
            ),
            [
                InlineKeyboardButton(
                    text="🔥 Публикации",
                    callback_data=_dcb(
                        "posts",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="👥 Участники",
                    callback_data=_dcb(
                        "active",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Кому отвечают",
                    callback_data=_dcb(
                        "replied",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="❤️ Реакции",
                    callback_data=_dcb(
                        "react",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎭 Персонажи",
                    callback_data=_dcb(
                        "chars",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="🌌 Вселенные",
                    callback_data=_dcb(
                        "worlds",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📚 Истории",
                    callback_data=_dcb(
                        "stories",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="⏱ Активность",
                    callback_data=_dcb(
                        "activity",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💤 Без комментариев",
                    callback_data=_dcb(
                        "silent",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="📈 Всплески",
                    callback_data=_dcb(
                        "spikes",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔗 Пересобрать связи",
                    callback_data=_dcb(
                        "relink",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Чаты",
                    callback_data=_dcb(
                        "sources",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=_dcb(
                        "sum",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                ),
            ],
        ]
    )


def _page_keyboard(
    action: str,
    period: str,
    page: DashboardPage | DiscussedPostPage,
    *,
    chat_id: int,
    parent_id: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        _dperiod_row(
            action,
            period,
            chat_id=chat_id,
            parent_id=parent_id,
        )
    ]
    if page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_dcb(
                        action,
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                        page=(page.page - 1) % page.total_pages,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=_dcb(
                        "noop",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_dcb(
                        action,
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                        page=(page.page + 1) % page.total_pages,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Обсуждение",
                callback_data=_dcb(
                    "sum",
                    period=period,
                    chat_id=chat_id,
                    parent_id=parent_id,
                ),
            ),
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=_dcb(
                    action,
                    period=period,
                    chat_id=chat_id,
                    parent_id=parent_id,
                    page=page.page,
                ),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _rank_lines(
    page: DashboardPage,
    *,
    count_label: str,
    secondary_label: str,
) -> str:
    if not page.items:
        return "• данных пока нет"
    start = page.page * page.page_size
    lines: list[str] = []
    for index, item in enumerate(page.items, start=start + 1):
        detail = f" · {escape(item.detail)}" if item.detail else ""
        lines.append(
            f"{index}. <b>{escape(item.label)}</b> — "
            f"{item.count} {count_label}; "
            f"{secondary_label} {item.secondary_count}{detail}"
        )
    return "\n".join(lines)


def _snippet(value: str, limit: int = 110) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        return "Публикация без текста"
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


async def _render_sources(
    callback: CallbackQuery,
    database: Database,
    *,
    parent_channel_id: int,
    period: str,
) -> None:
    raw_sources = await list_discussion_sources(
        database,
        parent_channel_id=parent_channel_id,
    )
    sources = list({source.chat_id: source for source in raw_sources}.values())
    rows = [
        [
            InlineKeyboardButton(
                text=compact_button_text(f"💬 {source.title}"),
                callback_data=_dcb(
                    "sum",
                    period=period,
                    chat_id=source.chat_id,
                    parent_id=parent_channel_id,
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
            )
        ]
    )
    text = (
        "<b>Обсуждения канала</b>\n\n"
        f"📣 Канал: <code>{parent_channel_id}</code>\n"
        f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
        f"Подключено чатов: <b>{len(sources)}</b>\n\n"
        + (
            "Выберите чат для расширенного отчёта."
            if sources
            else "Связанный чат пока не подключён."
        )
    )
    await safe_analytics_edit(
        callback,
        text,
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _render_summary(
    callback: CallbackQuery,
    database: Database,
    *,
    chat_id: int,
    parent_id: int,
    period: str,
) -> None:
    item = await get_discussion_summary(
        database,
        chat_id,
        parent_id,
        period=period,
    )
    text = (
        "<b>💬 Расширенная аналитика обсуждения</b>\n\n"
        f"📣 Канал: <code>{parent_id}</code>\n"
        f"💬 Чат: <code>{chat_id}</code>\n"
        f"Период: <b>{PERIOD_LABELS[period]}</b>\n\n"
        f"Связанных публикаций: <b>{item.linked_threads}</b>\n"
        f"Комментариев: <b>{item.total_comments}</b>\n"
        f"Уникальных участников: <b>{item.unique_participants}</b>\n"
        f"Реакций на комментарии: <b>{item.total_comment_reactions}</b>\n"
        f"Публикаций канала: <b>{item.published_publications}</b>\n"
        f"Среднее комментариев на публикацию: "
        f"<b>{item.average_comments_per_publication:.1f}</b>\n"
        f"Без комментариев: <b>{item.publications_without_comments}</b>"
    )
    await safe_analytics_edit(
        callback,
        text,
        _summary_keyboard(period, chat_id=chat_id, parent_id=parent_id),
    )


@router.callback_query(
    AnalyticsCallback.filter(F.action.in_({"discussions", "discussion"}))
)
async def handle_discussion_entry(
    callback: CallbackQuery,
    callback_data: AnalyticsCallback,
    database: Database,
    analytics_channel_ids: frozenset[int],
) -> None:
    period = normalize_period(callback_data.period)
    parent_id = sorted(analytics_channel_ids)[0] if analytics_channel_ids else None
    if parent_id is None:
        await callback.answer("Основной канал аналитики не настроен.", show_alert=True)
        return
    if callback_data.action == "discussions":
        await _render_sources(
            callback,
            database,
            parent_channel_id=parent_id,
            period=period,
        )
    else:
        await _render_summary(
            callback,
            database,
            chat_id=int(callback_data.source_id),
            parent_id=parent_id,
            period=period,
        )
    await callback.answer()


@router.callback_query(DiscussionInsightCallback.filter())
async def handle_discussion_insight(
    callback: CallbackQuery,
    callback_data: DiscussionInsightCallback,
    database: Database,
    publication_timezone: str,
) -> None:
    action = callback_data.action
    period = normalize_period(callback_data.period)
    chat_id = int(callback_data.chat_id)

    if action == "noop":
        await callback.answer()
        return

    parent_id = await _resolve_parent_id(database, chat_id)
    if parent_id is None:
        await callback.answer("Связанный канал обсуждения не найден.", show_alert=True)
        return

    if action == "sources":
        await _render_sources(
            callback,
            database,
            parent_channel_id=parent_id,
            period=period,
        )
    elif action == "sum":
        await _render_summary(
            callback,
            database,
            chat_id=chat_id,
            parent_id=parent_id,
            period=period,
        )
    elif action == "posts":
        page = await list_discussed_posts(
            database,
            chat_id,
            parent_id,
            period=period,
            page=callback_data.page,
        )
        start = page.page * page.page_size
        lines = []
        post_rows: list[list[InlineKeyboardButton]] = []
        for index, item in enumerate(page.items, start=start + 1):
            lines.append(
                f"{index}. <b>{escape(_snippet(item.text_content, 76))}</b>\n"
                f"   💬 {item.comment_count} · 👥 {item.unique_participants} · "
                f"❤️ {item.comment_reactions} · первый {format_delay(item.first_comment_seconds)}"
            )
            post_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🔎 Публикация {index}",
                        callback_data=_dcb(
                            "post",
                            period=period,
                            chat_id=chat_id,
                            parent_id=parent_id,
                            item_id=item.post_id,
                        ),
                    )
                ]
            )
        keyboard = _page_keyboard(
            action,
            period,
            page,
            chat_id=chat_id,
            parent_id=parent_id,
        )
        keyboard.inline_keyboard[1:1] = post_rows
        text = (
            "<b>🔥 Самые обсуждаемые публикации</b>\n\n"
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
            f"Публикаций: <b>{page.total_items}</b>\n\n"
            + ("\n\n".join(lines) if lines else "• данных пока нет")
        )
        await safe_analytics_edit(callback, text, keyboard)
    elif action == "post":
        item = await get_discussed_post(
            database,
            chat_id,
            parent_id,
            callback_data.item_id,
            period=period,
        )
        if item is None:
            await callback.answer("Публикация больше не найдена.", show_alert=True)
            return
        rows = [
            _dperiod_row(
                "post",
                period,
                chat_id=chat_id,
                parent_id=parent_id,
                item_id=item.post_id,
            )
        ]
        if item.message_url:
            rows.append(
                [InlineKeyboardButton(text="📣 Открыть публикацию", url=item.message_url)]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text="↩️ Рейтинг публикаций",
                    callback_data=_dcb(
                        "posts",
                        period=period,
                        chat_id=chat_id,
                        parent_id=parent_id,
                    ),
                )
            ]
        )
        text = (
            "<b>Публикация и её обсуждение</b>\n\n"
            f"{escape(_snippet(item.text_content, 360))}\n\n"
            f"Просмотры: <b>{item.view_count}</b>\n"
            f"Реакции канала: <b>{item.channel_reactions}</b>\n"
            f"Комментарии: <b>{item.comment_count}</b>\n"
            f"Первый комментарий: <b>{format_delay(item.first_comment_seconds)}</b>\n"
            f"Уникальных участников: <b>{item.unique_participants}</b>\n"
            f"Реакций на комментарии: <b>{item.comment_reactions}</b>"
        )
        await safe_analytics_edit(
            callback,
            text,
            InlineKeyboardMarkup(inline_keyboard=rows),
        )
    elif action in {"active", "replied", "react", "chars", "worlds", "stories"}:
        if action == "active":
            page = await list_active_participants(
                database,
                chat_id,
                period=period,
                page=callback_data.page,
            )
            title = "👥 Самые активные участники"
            labels = ("сообщ.", "ответов")
        elif action == "replied":
            page = await list_most_replied_participants(
                database,
                chat_id,
                period=period,
                page=callback_data.page,
            )
            title = "↩️ Участники, которым чаще отвечают"
            labels = ("ответов", "авторов")
        elif action == "react":
            page = await list_reaction_leaders(
                database,
                chat_id,
                period=period,
                page=callback_data.page,
            )
            title = "❤️ Реакции на комментарии"
            labels = ("реакций", "коммент.")
        elif action == "chars":
            page = await list_discussed_characters(
                database,
                chat_id,
                parent_id,
                period=period,
                page=callback_data.page,
            )
            title = "🎭 Самые обсуждаемые персонажи"
            labels = ("коммент.", "публикаций")
        elif action == "worlds":
            page = await list_discussed_universes(
                database,
                chat_id,
                parent_id,
                period=period,
                page=callback_data.page,
            )
            title = "🌌 Самые обсуждаемые вселенные"
            labels = ("коммент.", "публикаций")
        else:
            page = await list_discussed_stories(
                database,
                chat_id,
                parent_id,
                period=period,
                page=callback_data.page,
            )
            title = "📚 Самые обсуждаемые истории"
            labels = ("коммент.", "публикаций")
        text = (
            f"<b>{title}</b>\n\n"
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
            f"Позиций: <b>{page.total_items}</b>\n\n"
            + _rank_lines(
                page,
                count_label=labels[0],
                secondary_label=labels[1],
            )
        )
        await safe_analytics_edit(
            callback,
            text,
            _page_keyboard(
                action,
                period,
                page,
                chat_id=chat_id,
                parent_id=parent_id,
            ),
        )
    elif action == "silent":
        page = await list_publications_without_comments(
            database,
            chat_id,
            parent_id,
            period=period,
            page=callback_data.page,
        )
        lines = [
            f"{page.page * page.page_size + index}. "
            f"<b>{escape(item.label)}</b> · {escape(item.detail or '')}"
            for index, item in enumerate(page.items, start=1)
        ] or ["• таких публикаций нет"]
        text = (
            "<b>💤 Публикации без комментариев</b>\n\n"
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
            f"Количество: <b>{page.total_items}</b>\n\n"
            + "\n".join(lines)
        )
        await safe_analytics_edit(
            callback,
            text,
            _page_keyboard(
                action,
                period,
                page,
                chat_id=chat_id,
                parent_id=parent_id,
            ),
        )
    elif action == "activity":
        activity = await get_activity_breakdown(
            database,
            chat_id,
            period=period,
            timezone_name=publication_timezone,
        )
        weekday_lines = [
            f"• {label}: <b>{count}</b>"
            for label, count in zip(WEEKDAY_LABELS, activity.weekdays, strict=True)
        ]
        busiest = sorted(
            enumerate(activity.hours),
            key=lambda item: (-item[1], item[0]),
        )[:8]
        hour_lines = [
            f"• {hour:02d}:00–{(hour + 1) % 24:02d}:00: <b>{count}</b>"
            for hour, count in busiest
            if count > 0
        ] or ["• данных пока нет"]
        text = (
            "<b>⏱ Активность обсуждения</b>\n\n"
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
            f"Часовой пояс: <code>{escape(publication_timezone)}</code>\n\n"
            "<b>По дням недели</b>\n"
            + "\n".join(weekday_lines)
            + "\n\n<b>Самые активные часы</b>\n"
            + "\n".join(hour_lines)
        )
        page_stub = DashboardPage(items=[], page=0, page_size=1, total_items=0)
        await safe_analytics_edit(
            callback,
            text,
            _page_keyboard(
                action,
                period,
                page_stub,
                chat_id=chat_id,
                parent_id=parent_id,
            ),
        )
    elif action == "spikes":
        spikes = await list_activity_spikes(
            database,
            chat_id,
            period=period,
            timezone_name=publication_timezone,
        )
        lines = [
            f"• <b>{item.day.strftime('%d.%m.%Y')}</b> — "
            f"{item.comment_count} комментариев, "
            f"в {item.ratio:.1f}× выше среднего {item.baseline:.1f}"
            for item in spikes
        ] or ["• резких всплесков не найдено"]
        text = (
            "<b>📈 Всплески активности</b>\n\n"
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n\n"
            + "\n".join(lines)
        )
        page_stub = DashboardPage(items=[], page=0, page_size=1, total_items=0)
        await safe_analytics_edit(
            callback,
            text,
            _page_keyboard(
                action,
                period,
                page_stub,
                chat_id=chat_id,
                parent_id=parent_id,
            ),
        )
    elif action == "relink":
        result = await rebuild_discussion_threads(database, chat_id)
        await _render_summary(
            callback,
            database,
            chat_id=chat_id,
            parent_id=parent_id,
            period=period,
        )
        await callback.answer(
            "Связи пересобраны: "
            f"корней {result.roots_marked}, "
            f"сообщений {result.comments_linked}, "
            f"веток {result.threads_linked}."
        )
        return
    else:
        await callback.answer("Неизвестный раздел обсуждений.", show_alert=True)
        return

    await callback.answer()
