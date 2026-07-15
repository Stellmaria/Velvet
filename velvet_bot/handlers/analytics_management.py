from __future__ import annotations

import re
from html import escape

from aiogram import F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.alias_management import (
    delete_character_alias_by_id,
    get_character_alias_summary,
)
from velvet_bot.analytics_callbacks import (
    AnalyticsManageCallback,
    dashboard_link,
    management_link,
)
from velvet_bot.analytics_dashboard import PERIOD_LABELS, normalize_period
from velvet_bot.analytics_review import (
    CharacterPickerItem,
    PublicationReview,
    ReviewPage,
    UnresolvedTagReview,
    assign_unresolved_tag,
    get_publication_review,
    get_unresolved_tag_review,
    list_character_picker,
    list_publication_reviews,
    list_unresolved_tag_reviews,
    reclassify_automatic_publications,
    reset_publication_type_to_automatic,
    set_manual_publication_type,
)
from velvet_bot.character_aliases import add_character_alias
from velvet_bot.character_directory import category_label, universe_label
from velvet_bot.database import Database
from velvet_bot.post_classification import POST_TYPE_LABELS

router = Router(name=__name__)

_ALIAS_REPLY_RE = re.compile(r"ALIAS_CHARACTER:(\d+)")
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


def _primary_channel_id(analytics_channel_ids: frozenset[int]) -> int | None:
    return sorted(analytics_channel_ids)[0] if analytics_channel_ids else None


def _short(value: str, limit: int = 42) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(1, limit - 1)].rstrip() + "…"


def _date(value) -> str:
    return value.astimezone().strftime("%d.%m.%Y") if value else "—"


async def _edit(
    callback: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await callback.message.edit_text(text, reply_markup=keyboard)


def _pager(
    *,
    action: str,
    period: str,
    page: ReviewPage,
    token_id: int = 0,
    character_id: int = 0,
    value: str = "",
) -> list[InlineKeyboardButton]:
    if page.total_pages <= 1:
        return []
    return [
        InlineKeyboardButton(
            text="◀️",
            callback_data=management_link(
                action,
                period=period,
                page=(page.page - 1) % page.total_pages,
                token_id=token_id,
                character_id=character_id,
                value=value,
            ),
        ),
        InlineKeyboardButton(
            text=f"{page.page + 1} / {page.total_pages}",
            callback_data=management_link("noop"),
        ),
        InlineKeyboardButton(
            text="▶️",
            callback_data=management_link(
                action,
                period=period,
                page=(page.page + 1) % page.total_pages,
                token_id=token_id,
                character_id=character_id,
                value=value,
            ),
        ),
    ]


def _character_detail(item: CharacterPickerItem) -> str:
    details = [category_label(item.category), universe_label(item.universe)]
    if item.story_short_label:
        details.append(item.story_short_label)
    return " / ".join(value for value in details if value)


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


async def _show_character_picker(
    callback: CallbackQuery,
    database: Database,
    *,
    action: str,
    period: str,
    page_number: int,
    token_id: int = 0,
) -> None:
    page = await list_character_picker(database, page=page_number)
    rows: list[list[InlineKeyboardButton]] = []
    for raw_item in page.items:
        item = raw_item
        if not isinstance(item, CharacterPickerItem):
            continue
        target_action = "tagassign" if action == "tagchars" else "aliaschar"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{_short(item.name, 30)} · {_short(_character_detail(item), 22)}",
                    callback_data=management_link(
                        target_action,
                        period=period,
                        token_id=token_id,
                        character_id=item.id,
                        page=page.page,
                    ),
                )
            ]
        )
    pager = _pager(
        action=action,
        period=period,
        page=page,
        token_id=token_id,
    )
    if pager:
        rows.append(pager)
    back_data = (
        management_link("tag", period=period, token_id=token_id)
        if action == "tagchars"
        else dashboard_link("menu", period=period)
    )
    rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=back_data)])
    title = "Назначить хэштег персонажу" if action == "tagchars" else "Алиасы персонажей"
    text = (
        f"<b>{title}</b>\n\n"
        f"Персонажей: <b>{page.total_items}</b>\n"
        "Выберите персонажа из списка."
    )
    await _edit(callback, text, InlineKeyboardMarkup(inline_keyboard=rows))


async def _show_character_aliases(
    callback: CallbackQuery,
    database: Database,
    *,
    character_id: int,
    period: str,
    return_page: int,
) -> None:
    name, items = await get_character_alias_summary(
        database,
        character_id=character_id,
    )
    if name is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    lines = []
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        suffix = " · основное имя" if item.source == "name" else ""
        lines.append(f"• <code>#{escape(item.alias)}</code>{suffix}")
        if item.source != "name":
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🗑 Удалить #{_short(item.alias, 30)}",
                        callback_data=management_link(
                            "aliasdel",
                            period=period,
                            character_id=character_id,
                            alias_id=item.id,
                            page=return_page,
                        ),
                    )
                ]
            )
    rows.append(
        [
            InlineKeyboardButton(
                text="➕ Добавить алиас",
                callback_data=management_link(
                    "aliasadd",
                    period=period,
                    character_id=character_id,
                    page=return_page,
                ),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К персонажам",
                callback_data=management_link(
                    "aliases",
                    period=period,
                    page=return_page,
                ),
            )
        ]
    )
    text = (
        f"<b>Алиасы: {escape(name)}</b>\n\n"
        + ("\n".join(lines) if lines else "• алиасов пока нет")
        + "\n\nОсновное имя удалить нельзя. Ручные варианты можно удалить кнопками."
    )
    await _edit(callback, text, InlineKeyboardMarkup(inline_keyboard=rows))


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


@router.callback_query(AnalyticsManageCallback.filter())
async def handle_analytics_management(
    callback: CallbackQuery,
    callback_data: AnalyticsManageCallback,
    database: Database,
    analytics_channel_ids: frozenset[int],
) -> None:
    action = callback_data.action
    period = normalize_period(callback_data.period)
    channel_id = _primary_channel_id(analytics_channel_ids)
    if action == "noop":
        await callback.answer()
        return
    if channel_id is None:
        await callback.answer("Основной канал аналитики не настроен.", show_alert=True)
        return

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
    elif action == "tagassign":
        try:
            alias = await assign_unresolved_tag(
                database,
                token_id=callback_data.token_id,
                character_id=callback_data.character_id,
                changed_by=callback.from_user.id,
            )
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
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
        return
    elif action == "aliases":
        await _show_character_picker(
            callback,
            database,
            action=action,
            period=period,
            page_number=callback_data.page,
        )
    elif action == "aliaschar":
        await _show_character_aliases(
            callback,
            database,
            character_id=callback_data.character_id,
            period=period,
            return_page=callback_data.page,
        )
    elif action == "aliasadd":
        name, _ = await get_character_alias_summary(
            database,
            character_id=callback_data.character_id,
        )
        if name is None or not isinstance(callback.message, Message):
            await callback.answer("Персонаж больше не найден.", show_alert=True)
            return
        marker = f"ALIAS_CHARACTER:{callback_data.character_id}"
        await callback.message.answer(
            f"<b>Новый алиас: {escape(name)}</b>\n\n"
            "Ответьте на это сообщение новым вариантом хэштега без обязательного символа #.\n"
            "Пример: <code>KaelLang</code>\n\n"
            f"<code>{marker}</code>",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="KaelLang",
            ),
        )
        await callback.answer("Пришлите алиас ответом на сообщение.")
        return
    elif action == "aliasdel":
        name, items = await get_character_alias_summary(
            database,
            character_id=callback_data.character_id,
        )
        item = next((value for value in items if value.id == callback_data.alias_id), None)
        if name is None or item is None or item.source == "name":
            await callback.answer("Алиас нельзя удалить.", show_alert=True)
            return
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗑 Да, удалить",
                        callback_data=management_link(
                            "aliasdelok",
                            period=period,
                            character_id=callback_data.character_id,
                            alias_id=item.id,
                            page=callback_data.page,
                        ),
                    ),
                    InlineKeyboardButton(
                        text="Отмена",
                        callback_data=management_link(
                            "aliaschar",
                            period=period,
                            character_id=callback_data.character_id,
                            page=callback_data.page,
                        ),
                    ),
                ]
            ]
        )
        await _edit(
            callback,
            f"Удалить алиас <code>#{escape(item.alias)}</code> у "
            f"<b>{escape(name)}</b>?\n\n"
            "Совпадающие старые хэштеги снова станут нераспознанными.",
            keyboard,
        )
    elif action == "aliasdelok":
        deleted = await delete_character_alias_by_id(
            database,
            alias_id=callback_data.alias_id,
        )
        if deleted is None:
            await callback.answer("Алиас уже удалён или защищён.", show_alert=True)
            return
        await _show_character_aliases(
            callback,
            database,
            character_id=deleted.character_id,
            period=period,
            return_page=callback_data.page,
        )
        await callback.answer(f"Алиас #{deleted.alias} удалён.", show_alert=True)
        return
    elif action == "review":
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
            return
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
        return
    elif action == "pauto":
        try:
            item = await reset_publication_type_to_automatic(
                database,
                token_id=callback_data.token_id,
                changed_by=callback.from_user.id,
            )
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
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
        return
    elif action == "reclassify":
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
        return
    else:
        await callback.answer("Неизвестное действие аналитики.", show_alert=True)
        return

    await callback.answer()


@router.message(F.reply_to_message.text.contains("ALIAS_CHARACTER:"))
async def handle_alias_reply(
    message: Message,
    database: Database,
) -> None:
    reply = message.reply_to_message
    if reply is None:
        return
    marker_source = reply.text or reply.caption or ""
    match = _ALIAS_REPLY_RE.search(marker_source)
    if match is None:
        return
    alias_text = (message.text or message.caption or "").strip().lstrip("#")
    if not alias_text:
        await message.answer("Пришлите текст алиаса, например <code>KaelLang</code>.")
        return
    character_id = int(match.group(1))
    try:
        item = await add_character_alias(
            database,
            character_id=character_id,
            alias=alias_text,
            created_by=message.from_user.id if message.from_user else None,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(
        f"Алиас <code>#{escape(item.alias)}</code> добавлен персонажу "
        f"<b>{escape(item.character_name)}</b>. Старые посты пересчитаны.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔤 Открыть алиасы",
                        callback_data=management_link(
                            "aliaschar",
                            character_id=item.character_id,
                        ),
                    )
                ]
            ]
        ),
    )
