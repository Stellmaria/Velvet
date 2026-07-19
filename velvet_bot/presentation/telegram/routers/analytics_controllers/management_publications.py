from __future__ import annotations

from html import escape

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.analytics_callbacks import AnalyticsManageCallback, dashboard_link, management_link
from velvet_bot.analytics_dashboard import PERIOD_LABELS
from velvet_bot.analytics_review import (
    PublicationReview,
    get_publication_review,
    list_publication_reviews,
    reclassify_automatic_publications,
    reset_publication_type_to_automatic,
    set_manual_publication_type,
)
from velvet_bot.database import Database
from velvet_bot.presentation.telegram.routers.analytics_controllers.management_common import (
    _date,
    _edit,
    _pager,
    _short,
)
from velvet_bot.post_classification import POST_TYPE_LABELS

_TYPE_BUTTON_LABELS = {
    "prompt": "📝 Промт",
    "art": "🖼 Арт",
    "announcement": "📣 Анонс",
    "giveaway": "🎁 Розыгрыш",
    "collaboration": "🤝 Совместная",
    "update": "🆕 Обновление",
    "service": "ℹ️ Служебный",
    "unknown": "❔ Не определено",
}
PUBLICATION_ACTIONS = frozenset({"review", "post", "ptype", "pauto", "reclassify"})

def _publication_button(item: PublicationReview) -> str:
    label = POST_TYPE_LABELS.get(item.post_type, item.post_type)
    excerpt = _short(item.text_content or item.media_type, 26)
    return f"{_date(item.posted_at)} · {label} {item.confidence}% · {excerpt}"

async def _show_publication_queue(
    callback: CallbackQuery,
    database: Database,
    *,
    channel_id: int,
    period: str,
    page_number: int,
    mode: str,
) -> None:
    low_only = mode != "all"
    page = await list_publication_reviews(
        database,
        channel_id,
        period=period,
        page=page_number,
        low_confidence_only=low_only,
    )
    rows: list[list[InlineKeyboardButton]] = []
    for raw_item in page.items:
        item = raw_item
        if not isinstance(item, PublicationReview):
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=_publication_button(item),
                    callback_data=management_link(
                        "post",
                        period=period,
                        page=page.page,
                        token_id=item.token_id,
                        value=mode,
                    ),
                )
            ]
        )
    pager = _pager(
        action="review",
        period=period,
        page=page,
        value=mode,
    )
    if pager:
        rows.append(pager)
    rows.append(
        [
            InlineKeyboardButton(
                text=("📚 Все публикации" if low_only else "⚠️ Только сомнительные"),
                callback_data=management_link(
                    "review",
                    period=period,
                    value="all" if low_only else "low",
                ),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Типы постов",
                callback_data=dashboard_link("types", period=period),
            )
        ]
    )
    title = "Публикации для проверки" if low_only else "Все классифицированные публикации"
    text = (
        f"<b>{title}</b>\n\n"
        f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
        f"Публикаций: <b>{page.total_items}</b>\n\n"
        + (
            "В очередь попадают автоматические результаты с уверенностью ниже 75% "
            "и публикации типа «Не определено»."
            if low_only
            else "Откройте публикацию, чтобы проверить или вручную изменить её тип."
        )
    )
    await _edit(callback, text, InlineKeyboardMarkup(inline_keyboard=rows))

async def _show_publication_detail(
    callback: CallbackQuery,
    database: Database,
    *,
    token_id: int,
    period: str,
    return_page: int,
    mode: str,
) -> None:
    item = await get_publication_review(database, token_id=token_id)
    if item is None:
        await callback.answer("Публикация больше не найдена.", show_alert=True)
        return
    hashtags = " ".join(f"#{escape(tag)}" for tag, _ in item.hashtags[:20]) or "—"
    excerpt = escape(_short(item.text_content, 900)) if item.text_content else "—"
    source_label = "ручная" if item.source == "manual" else "автоматическая"
    rows: list[list[InlineKeyboardButton]] = []
    type_buttons = [
        InlineKeyboardButton(
            text=("✅ " if key == item.post_type else "") + label,
            callback_data=management_link(
                "ptype",
                period=period,
                page=return_page,
                token_id=token_id,
                value=f"{mode}|{key}",
            ),
        )
        for key, label in _TYPE_BUTTON_LABELS.items()
    ]
    for index in range(0, len(type_buttons), 2):
        rows.append(type_buttons[index : index + 2])
    rows.append(
        [
            InlineKeyboardButton(
                text="🤖 Вернуть автоматическую",
                callback_data=management_link(
                    "pauto",
                    period=period,
                    page=return_page,
                    token_id=token_id,
                    value=mode,
                ),
            )
        ]
    )
    if item.message_url:
        rows.append([InlineKeyboardButton(text="📣 Открыть пост", url=item.message_url)])
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К проверке",
                callback_data=management_link(
                    "review",
                    period=period,
                    page=return_page,
                    value=mode,
                ),
            )
        ]
    )
    text = (
        "<b>Проверка классификации</b>\n\n"
        f"Дата: <b>{_date(item.posted_at)}</b>\n"
        f"Тип: <b>{escape(POST_TYPE_LABELS.get(item.post_type, item.post_type))}</b>\n"
        f"Уверенность: <b>{item.confidence}%</b>\n"
        f"Источник: <b>{source_label}</b>\n"
        f"Элементов альбома: <b>{item.media_count}</b>\n"
        f"Хэштеги: {hashtags}\n\n"
        f"<b>Текст</b>\n{excerpt}"
    )
    await _edit(callback, text, InlineKeyboardMarkup(inline_keyboard=rows))

async def handle_publication_action(
    callback: CallbackQuery,
    callback_data: AnalyticsManageCallback,
    database: Database,
    *,
    channel_id: int,
    period: str,
) -> bool:
    action = callback_data.action
    if action not in PUBLICATION_ACTIONS:
        return False

    if action == "review":
        await _show_publication_queue(
            callback,
            database,
            channel_id=channel_id,
            period=period,
            page_number=callback_data.page,
            mode=callback_data.value or "low",
        )
    elif action == "post":
        await _show_publication_detail(
            callback,
            database,
            token_id=callback_data.token_id,
            period=period,
            return_page=callback_data.page,
            mode=callback_data.value or "low",
        )
    elif action == "ptype":
        mode, _, post_type = callback_data.value.partition("|")
        try:
            item = await set_manual_publication_type(
                database,
                token_id=callback_data.token_id,
                post_type=post_type,
                changed_by=callback.from_user.id,
            )
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return True
        await _show_publication_detail(
            callback,
            database,
            token_id=callback_data.token_id,
            period=period,
            return_page=callback_data.page,
            mode=mode or "low",
        )
        await callback.answer(
            f"Тип сохранён: {POST_TYPE_LABELS.get(item.post_type, item.post_type)}.",
            show_alert=True,
        )
        return True
    elif action == "pauto":
        try:
            item = await reset_publication_type_to_automatic(
                database,
                token_id=callback_data.token_id,
                changed_by=callback.from_user.id,
            )
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return True
        await _show_publication_detail(
            callback,
            database,
            token_id=callback_data.token_id,
            period=period,
            return_page=callback_data.page,
            mode=callback_data.value or "low",
        )
        await callback.answer(
            f"Автоматический тип: {POST_TYPE_LABELS.get(item.post_type, item.post_type)}.",
            show_alert=True,
        )
        return True
    else:
        await callback.answer("Пересчитываю автоматические типы…")
        changed, total = await reclassify_automatic_publications(
            database,
            channel_id=channel_id,
            changed_by=callback.from_user.id,
        )
        await _show_publication_queue(
            callback,
            database,
            channel_id=channel_id,
            period=period,
            page_number=0,
            mode="low",
        )
        if isinstance(callback.message, Message):
            await callback.message.answer(
                f"<b>Классификация пересчитана.</b>\n\n"
                f"Проверено публикаций: <b>{total}</b>\n"
                f"Изменилось: <b>{changed}</b>."
            )
        return True

    await callback.answer()
    return True


__all__ = ("PUBLICATION_ACTIONS", "handle_publication_action")
