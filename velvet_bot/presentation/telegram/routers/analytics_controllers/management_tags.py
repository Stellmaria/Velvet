from __future__ import annotations

from html import escape

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.analytics_callbacks import AnalyticsManageCallback, dashboard_link, management_link
from velvet_bot.analytics_dashboard import PERIOD_LABELS
from velvet_bot.analytics_review import (
    UnresolvedTagReview,
    assign_unresolved_tag,
    get_unresolved_tag_review,
    list_unresolved_tag_reviews,
)
from velvet_bot.database import Database
from velvet_bot.presentation.telegram.routers.analytics_controllers.management_common import (
    _edit,
    _pager,
    _short,
    _show_character_picker,
)

TAG_ACTIONS = frozenset({"unresolved", "tag", "tagchars", "tagassign"})

async def _show_unresolved_queue(
    callback: CallbackQuery,
    database: Database,
    *,
    channel_id: int,
    period: str,
    page_number: int,
) -> None:
    page = await list_unresolved_tag_reviews(
        database,
        channel_id,
        period=period,
        page=page_number,
    )
    rows: list[list[InlineKeyboardButton]] = []
    for raw_item in page.items:
        item = raw_item
        if not isinstance(item, UnresolvedTagReview):
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"#{_short(item.hashtag, 28)} · "
                        f"{item.publication_count} публикаций"
                    ),
                    callback_data=management_link(
                        "tag",
                        period=period,
                        page=page.page,
                        token_id=item.token_id,
                    ),
                )
            ]
        )
    pager = _pager(action="unresolved", period=period, page=page)
    if pager:
        rows.append(pager)
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Аналитика",
                callback_data=dashboard_link("menu", period=period),
            ),
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=management_link(
                    "unresolved",
                    period=period,
                    page=page.page,
                ),
            ),
        ]
    )
    text = (
        "<b>Очередь нераспознанных хэштегов</b>\n\n"
        f"Период: <b>{PERIOD_LABELS[period]}</b>\n"
        f"Осталось тегов: <b>{page.total_items}</b>\n\n"
        + (
            "Нажмите на тег и назначьте его существующему персонажу. "
            "После сохранения старые публикации пересчитаются автоматически."
            if page.total_items
            else "Все хэштеги этого периода уже разобраны. Редкий момент порядка."
        )
    )
    await _edit(callback, text, InlineKeyboardMarkup(inline_keyboard=rows))

async def _show_tag_detail(
    callback: CallbackQuery,
    database: Database,
    *,
    token_id: int,
    period: str,
    return_page: int,
) -> None:
    item = await get_unresolved_tag_review(database, token_id=token_id)
    if item is None:
        await callback.answer("Хэштег больше не найден.", show_alert=True)
        return
    assigned = (
        f"\nПерсонаж: <b>{escape(item.character_name)}</b>"
        if item.character_name
        else ""
    )
    rows = []
    if item.character_id is None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="👤 Выбрать персонажа",
                    callback_data=management_link(
                        "tagchars",
                        period=period,
                        token_id=token_id,
                        page=0,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К тегам",
                callback_data=management_link(
                    "unresolved",
                    period=period,
                    page=return_page,
                ),
            )
        ]
    )
    text = (
        f"<b>#{escape(item.hashtag)}</b>\n\n"
        f"Публикаций: <b>{item.publication_count}</b>\n"
        f"Из них промтов: <b>{item.prompt_count}</b>"
        f"{assigned}\n\n"
        + (
            "Выберите точного персонажа. Бот не предлагает похожие имена, "
            "чтобы не спутать Каина с Каэлем одним уверенным нажатием."
            if item.character_id is None
            else "Тег уже связан с персонажем."
        )
    )
    await _edit(callback, text, InlineKeyboardMarkup(inline_keyboard=rows))

async def handle_tag_action(
    callback: CallbackQuery,
    callback_data: AnalyticsManageCallback,
    database: Database,
    *,
    channel_id: int,
    period: str,
) -> bool:
    action = callback_data.action
    if action not in TAG_ACTIONS:
        return False

    if action == "unresolved":
        await _show_unresolved_queue(
            callback,
            database,
            channel_id=channel_id,
            period=period,
            page_number=callback_data.page,
        )
    elif action == "tag":
        await _show_tag_detail(
            callback,
            database,
            token_id=callback_data.token_id,
            period=period,
            return_page=callback_data.page,
        )
    elif action == "tagchars":
        await _show_character_picker(
            callback,
            database,
            action=action,
            period=period,
            page_number=callback_data.page,
            token_id=callback_data.token_id,
        )
    else:
        try:
            alias = await assign_unresolved_tag(
                database,
                token_id=callback_data.token_id,
                character_id=callback_data.character_id,
                changed_by=callback.from_user.id,
            )
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return True
        await _show_unresolved_queue(
            callback,
            database,
            channel_id=channel_id,
            period=period,
            page_number=0,
        )
        await callback.answer(
            f"#{alias.alias} назначен персонажу {alias.character_name}.",
            show_alert=True,
        )
        return True

    await callback.answer()
    return True


__all__ = ("TAG_ACTIONS", "handle_tag_action")
