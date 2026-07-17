from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.analytics_dashboard import (
    PERIOD_LABELS,
    DashboardPage,
    get_dashboard_overview,
    get_discussion_dashboard,
    get_prompt_dashboard,
    list_character_dashboard,
    list_discussion_participants,
    list_discussion_sources,
    list_hashtag_dashboard,
    list_post_type_dashboard,
    normalize_period,
)
from velvet_bot.character_directory import category_label, universe_label
from velvet_bot.database import Database
from velvet_bot.post_classification import POST_TYPE_LABELS
from velvet_bot.presentation.telegram.analytics_navigation import (
    AnalyticsCallback,
    _cb,
    _period_row,
)

router = Router(name=__name__)


def _primary_channel_id(analytics_channel_ids: frozenset[int]) -> int | None:
    return sorted(analytics_channel_ids)[0] if analytics_channel_ids else None


def _percent(part: int, total: int) -> str:
    return "0%" if total <= 0 else f"{part * 100 / total:.1f}%"


def _date(value) -> str:
    return value.astimezone().strftime("%d.%m.%Y") if value else "—"


def _main_keyboard(period: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            _period_row("menu", period),
            [
                InlineKeyboardButton(
                    text="📊 Обзор канала",
                    callback_data=_cb("overview", period=period),
                ),
                InlineKeyboardButton(
                    text="📝 Промты",
                    callback_data=_cb("prompts", period=period),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="👥 Персонажи",
                    callback_data=_cb("characters", period=period),
                ),
                InlineKeyboardButton(
                    text="#️⃣ Хэштеги",
                    callback_data=_cb("hashtags", period=period),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏷 Типы постов",
                    callback_data=_cb("types", period=period),
                ),
                InlineKeyboardButton(
                    text="❓ Не распознано",
                    callback_data=_cb("unresolved", period=period),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💬 Обсуждения",
                    callback_data=_cb("discussions", period=period),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=_cb("menu", period=period),
                ),
                InlineKeyboardButton(text="✖ Закрыть", callback_data=_cb("close")),
            ],
        ]
    )


def _back_keyboard(
    action: str,
    period: str,
    *,
    source_id: int = 0,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            _period_row(action, period, source_id=source_id),
            [
                InlineKeyboardButton(
                    text="↩️ Аналитика",
                    callback_data=_cb("menu", period=period),
                ),
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=_cb(action, period=period, source_id=source_id),
                ),
            ],
        ]
    )


def _page_keyboard(
    action: str,
    period: str,
    page: DashboardPage,
    *,
    source_id: int = 0,
    back_action: str = "menu",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [_period_row(action, period, source_id=source_id)]
    if page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_cb(
                        action,
                        period=period,
                        page=(page.page - 1) % page.total_pages,
                        source_id=source_id,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=_cb("noop"),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_cb(
                        action,
                        period=period,
                        page=(page.page + 1) % page.total_pages,
                        source_id=source_id,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Назад" if back_action != "menu" else "↩️ Аналитика",
                callback_data=_cb(back_action, period=period, source_id=source_id),
            ),
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=_cb(
                    action,
                    period=period,
                    page=page.page,
                    source_id=source_id,
                ),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _main_text(period: str) -> str:
    return (
        "<b>Аналитический центр Velvet</b>\n\n"
        f"Период: <b>{PERIOD_LABELS[period]}</b>\n\n"
        "Здесь собраны канал, промты, персонажи, хэштеги, "
        "классификация публикаций и обсуждения. Выберите раздел кнопкой."
    )


def _rank_lines(page: DashboardPage, *, kind: str) -> str:
    if not page.items:
        return "• данных пока нет"
    lines = []
    start = page.page * page.page_size
    for index, item in enumerate(page.items, start=start + 1):
        detail = f" · {escape(item.detail)}" if item.detail else ""
        secondary_label = "промтов" if kind != "participants" else "ответов"
        lines.append(
            f"{index}. <b>{escape(item.label)}</b> — {item.count}; "
            f"{secondary_label} {item.secondary_count}{detail}"
        )
    return "\n".join(lines)


async def _edit(callback: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.message(Command("analytics", "analyticsmenu"))
async def handle_analytics_menu(message: Message) -> None:
    await message.answer(_main_text("all"), reply_markup=_main_keyboard("all"))


@router.callback_query(AnalyticsCallback.filter())
async def handle_analytics_callback(
    callback: CallbackQuery,
    callback_data: AnalyticsCallback,
    database: Database,
    analytics_channel_ids: frozenset[int],
) -> None:
    action = callback_data.action
    period = normalize_period(callback_data.period)
    channel_id = _primary_channel_id(analytics_channel_ids)

    if action == "noop":
        await callback.answer()
        return
    if action == "close":
        if isinstance(callback.message, Message):
            await callback.message.delete()
        await callback.answer()
        return
    if channel_id is None:
        await callback.answer("Основной канал аналитики не настроен.", show_alert=True)
        return
    if action == "menu":
        await _edit(callback, _main_text(period), _main_keyboard(period))
        await callback.answer()
        return

    if action == "overview":
        item = await get_dashboard_overview(database, channel_id, period=period)
        text = (
            "<b>Обзор основного канала</b>\n\n"
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
            f"Данные: <b>{_date(item.first_post_at)}</b> — "
            f"<b>{_date(item.last_post_at)}</b>\n\n"
            f"Публикаций: <b>{item.total_publications}</b>\n"
            f"Сообщений в альбомах: <b>{item.total_messages}</b>\n"
            f"Промтов: <b>{item.prompt_publications}</b> "
            f"({_percent(item.prompt_publications, item.total_publications)})\n"
            f"Медиа: <b>{item.media_messages}</b>\n"
            f"Под спойлером: <b>{item.spoiler_messages}</b>\n"
            f"Редактировалось: <b>{item.edited_messages}</b>\n"
            f"Персонажей: <b>{item.unique_characters}</b>\n"
            f"Хэштегов: <b>{item.unique_hashtags}</b>\n"
            f"Реакций: <b>{item.total_reactions}</b>\n"
            f"Просмотров: <b>{item.captured_views}</b>\n"
            f"Пересылок: <b>{item.captured_forwards}</b>\n"
            f"Средняя длина текста: <b>{item.average_text_length:.0f}</b>"
        )
        await _edit(callback, text, _back_keyboard(action, period))

    elif action == "prompts":
        item = await get_prompt_dashboard(database, channel_id, period=period)
        text = (
            "<b>Структура промтов</b>\n\n"
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
            f"Промтов: <b>{item.total}</b>\n"
            f"Средняя длина: <b>{item.average_length:.0f}</b>\n\n"
            f"ВАЖНО: <b>{item.with_important}</b> "
            f"({_percent(item.with_important, item.total)})\n"
            f"СТРОГО: <b>{item.with_strict}</b> "
            f"({_percent(item.with_strict, item.total)})\n"
            f"Negative: <b>{item.with_negative}</b> "
            f"({_percent(item.with_negative, item.total)})\n"
            f"Технический блок: <b>{item.with_technical}</b> "
            f"({_percent(item.with_technical, item.total)})\n"
            f"HEX-палитра: <b>{item.with_palette}</b> "
            f"({_percent(item.with_palette, item.total)})"
        )
        await _edit(callback, text, _back_keyboard(action, period))

    elif action in {"hashtags", "unresolved"}:
        unresolved = action == "unresolved"
        page = await list_hashtag_dashboard(
            database,
            channel_id,
            period=period,
            page=callback_data.page,
            unresolved_only=unresolved,
        )
        title = "Нераспознанные хэштеги" if unresolved else "Хэштеги канала"
        explanation = (
            "\n\nДобавьте тег как алиас персонажа, чтобы старые публикации "
            "пересчитались автоматически."
            if unresolved
            else ""
        )
        text = (
            f"<b>{title}</b>\n\n"
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
            f"Уникальных тегов: <b>{page.total_items}</b>\n\n"
            f"{_rank_lines(page, kind='hashtags')}"
            f"{explanation}"
        )
        await _edit(callback, text, _page_keyboard(action, period, page))

    elif action == "characters":
        page = await list_character_dashboard(
            database,
            channel_id,
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
            "<b>Персонажи канала</b>\n\n"
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
            f"Задействовано: <b>{page.total_items}</b>\n\n"
            f"{_rank_lines(page, kind='characters')}"
        )
        await _edit(callback, text, _page_keyboard(action, period, page))

    elif action == "types":
        items = await list_post_type_dashboard(database, channel_id, period=period)
        lines = [
            f"• <b>{escape(POST_TYPE_LABELS.get(item.key, item.label))}</b> — "
            f"{item.count}; уверенность {item.secondary_count}%"
            for item in items
        ] or ["• данных пока нет"]
        text = (
            "<b>Автоматическая классификация постов</b>\n\n"
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n\n"
            + "\n".join(lines)
            + "\n\nНизкая уверенность означает, что посту не хватило явных "
            "хэштегов или характерных формулировок."
        )
        await _edit(callback, text, _back_keyboard(action, period))

    elif action == "discussions":
        sources = await list_discussion_sources(database, parent_channel_id=channel_id)
        rows = [
            [
                InlineKeyboardButton(
                    text=f"💬 {source.title}",
                    callback_data=_cb(
                        "discussion",
                        period=period,
                        source_id=source.chat_id,
                    ),
                )
            ]
            for source in sources
        ]
        rows.append(_period_row(action, period))
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
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
            f"Подключено чатов: <b>{len(sources)}</b>\n\n"
            + (
                "Выберите чат для подробного отчёта."
                if sources
                else "Сначала выполните <code>/trackdiscussion</code> внутри чата."
            )
        )
        await _edit(callback, text, InlineKeyboardMarkup(inline_keyboard=rows))

    elif action == "discussion":
        source_id = callback_data.source_id
        item = await get_discussion_dashboard(database, source_id, period=period)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                _period_row(action, period, source_id=source_id),
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
                            action,
                            period=period,
                            source_id=source_id,
                        ),
                    ),
                ],
            ]
        )
        text = (
            f"<b>{escape(item.title)}</b>\n\n"
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
            f"Данные: <b>{_date(item.first_message_at)}</b> — "
            f"<b>{_date(item.last_message_at)}</b>\n\n"
            f"Сообщений: <b>{item.total_messages}</b>\n"
            f"Участников: <b>{item.unique_participants}</b>\n"
            f"Ответов: <b>{item.reply_messages}</b>\n"
            f"Медиа: <b>{item.media_messages}</b>\n"
            f"Под спойлером: <b>{item.spoiler_messages}</b>\n"
            f"Промтов в обсуждении: <b>{item.prompt_messages}</b>\n"
            f"Реакций: <b>{item.total_reactions}</b>"
        )
        await _edit(callback, text, keyboard)

    elif action == "participants":
        source_id = callback_data.source_id
        page = await list_discussion_participants(
            database,
            source_id,
            period=period,
            page=callback_data.page,
        )
        text = (
            "<b>Активные участники обсуждения</b>\n\n"
            f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
            f"Участников: <b>{page.total_items}</b>\n\n"
            f"{_rank_lines(page, kind='participants')}"
        )
        await _edit(
            callback,
            text,
            _page_keyboard(
                action,
                period,
                page,
                source_id=source_id,
                back_action="discussion",
            ),
        )
    else:
        await callback.answer("Неизвестный раздел аналитики.", show_alert=True)
        return

    await callback.answer()
