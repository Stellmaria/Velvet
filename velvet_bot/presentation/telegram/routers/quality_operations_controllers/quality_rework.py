from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.domains.media_rework import MediaReworkItem, MediaReworkRepository
from velvet_bot.quality_ui import QualityCallback, quality_callback

_STATUS_LABELS = {
    "needs_fix": "🛠 требуется доработка",
    "checking": "🔄 повторная проверка Qwen",
    "ready_for_review": "👁 готово к решению администратора",
    "accepted": "✅ принято",
    "dismissed": "🗑 снято с доработки",
}
_SOURCE_LABELS = {
    "qwen": "Qwen",
    "admin": "Стэл",
    "mixed": "Стэл + Qwen",
}


async def _safe_edit(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


def _list_keyboard(page) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in page.items:
        score = f"{item.qwen_score}%" if item.qwen_score is not None else "ручная"
        status = {
            "needs_fix": "🛠",
            "checking": "🔄",
            "ready_for_review": "👁",
        }.get(item.status, "•")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {score} · #{item.media_id} · {item.file_name}"[:46],
                    callback_data=quality_callback(
                        "rework",
                        page=page.page,
                        item_id=item.media_id,
                    ),
                )
            ]
        )
    if page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=quality_callback(
                        "reworks",
                        page=(page.page - 1) % page.total_pages,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=quality_callback("noop"),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=quality_callback(
                        "reworks",
                        page=(page.page + 1) % page.total_pages,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄",
                callback_data=quality_callback("reworks", page=page.page),
            ),
            InlineKeyboardButton(
                text="↩️ Qwen",
                callback_data=quality_callback("ai_menu"),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_list(message: Message, database: Database, *, page_number: int) -> None:
    repository = MediaReworkRepository(database)
    page = await repository.list_active(page=page_number)
    summary = await repository.summary()
    text = "\n".join(
        [
            "<b>🛠 Единая очередь доработки</b>",
            "",
            f"Активно: <b>{summary.active}</b>",
            f"Нужно исправить: <b>{summary.needs_fix}</b> · "
            f"проверяется: <b>{summary.checking}</b> · "
            f"ждёт решения: <b>{summary.ready_for_review}</b>",
            f"Стэл: <b>{summary.stel_priority}</b> · Qwen: <b>{summary.qwen_only}</b>",
            f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>",
            "",
            "Работы Стэл показаны первыми. Активная доработка временно скрыта из публичного архива.",
        ]
    )
    await _safe_edit(message, text, _list_keyboard(page))


def _detail_text(item: MediaReworkItem) -> str:
    characters = ", ".join(item.character_names) or "не привязан"
    score = f"{item.qwen_score} / 100" if item.qwen_score is not None else "—"
    verdict = item.qwen_verdict or "—"
    lines = [
        f"<b>🛠 Доработка media #{item.media_id}</b>",
        "",
        f"Файл: <code>{escape(item.file_name)}</code>",
        f"Персонажи: <b>{escape(characters)}</b>",
        f"Статус: <b>{escape(_STATUS_LABELS.get(item.status, item.status))}</b>",
        f"Источник: <b>{escape(_SOURCE_LABELS.get(item.source, item.source))}</b>",
        f"Qwen: <b>{escape(verdict)}</b> · оценка <b>{score}</b>",
        "",
        f"<b>Причина:</b> {escape(item.reason or 'Причина не указана.')}",
    ]
    report = item.quality_report or {}
    for title, key, emoji in (
        ("Критичные проблемы", "critical_issues", "🚨"),
        ("Замечания", "warnings", "⚠️"),
    ):
        values = report.get(key)
        if isinstance(values, list) and values:
            lines.extend(["", f"<b>{emoji} {title}</b>"])
            lines.extend(f"• {escape(str(value))}" for value in values[:8])
    return "\n".join(lines)[:4090]


def _detail_keyboard(item: MediaReworkItem, *, page: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if item.status in {"needs_fix", "ready_for_review", "checking"}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Принять",
                    callback_data=quality_callback(
                        "raccept", page=page, item_id=item.media_id
                    ),
                ),
                InlineKeyboardButton(
                    text="🗑 Снять",
                    callback_data=quality_callback(
                        "rdismiss", page=page, item_id=item.media_id
                    ),
                ),
            ]
        )
    if item.status in {"needs_fix", "ready_for_review"}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Qwen-проверка",
                    callback_data=quality_callback(
                        "rretry", page=page, item_id=item.media_id
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Очередь",
                callback_data=quality_callback("reworks", page=page),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_preview(bot: Bot, chat_id: int, item: MediaReworkItem) -> None:
    caption = f"Доработка · media #{item.media_id}\n{item.file_name}"
    try:
        if item.media_type == "photo" or item.preview_file_id:
            await bot.send_photo(
                chat_id=chat_id,
                photo=item.preview_file_id or item.telegram_file_id,
                caption=caption,
                protect_content=False,
            )
        else:
            await bot.send_document(
                chat_id=chat_id,
                document=item.telegram_file_id,
                caption=caption,
                protect_content=False,
            )
    except TelegramAPIError:
        await bot.send_message(chat_id, f"{caption}\nПревью сейчас недоступно.")


async def handle_rework_list(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await _show_list(callback.message, database, page_number=callback_data.page)
    await callback.answer()


async def handle_rework_open(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
    bot: Bot,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    item = await MediaReworkRepository(database).get_item(callback_data.item_id)
    if item is None:
        await callback.answer("Запись доработки больше не найдена.", show_alert=True)
        return
    await _send_preview(bot, callback.message.chat.id, item)
    await _safe_edit(
        callback.message,
        _detail_text(item),
        _detail_keyboard(item, page=callback_data.page),
    )
    await callback.answer("Изображение отправлено выше.")


async def _apply_action(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
    *,
    action: str,
) -> None:
    repository = MediaReworkRepository(database)
    if action == "accept":
        changed = await repository.accept(callback_data.item_id, callback.from_user.id)
        message = "Работа принята. Публичная видимость восстановлена."
    elif action == "retry":
        changed = await repository.retry(callback_data.item_id, callback.from_user.id)
        message = "Работа возвращена на проверку Qwen."
    elif action == "dismiss":
        changed = await repository.dismiss(callback_data.item_id, callback.from_user.id)
        message = "Работа снята. Публичная видимость восстановлена."
    else:
        raise ValueError("Неизвестное действие очереди доработки.")
    await callback.answer(
        message if changed else "Статус уже изменился.",
        show_alert=not changed,
    )
    if isinstance(callback.message, Message):
        await _show_list(callback.message, database, page_number=callback_data.page)


async def handle_rework_accept(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    await _apply_action(callback, callback_data, database, action="accept")


async def handle_rework_retry(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    await _apply_action(callback, callback_data, database, action="retry")


async def handle_rework_dismiss(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    await _apply_action(callback, callback_data, database, action="dismiss")


def register_quality_rework_handlers(router: Router) -> None:
    router.callback_query.register(
        handle_rework_list,
        QualityCallback.filter(F.action == "reworks"),
    )
    router.callback_query.register(
        handle_rework_open,
        QualityCallback.filter(F.action == "rework"),
    )
    router.callback_query.register(
        handle_rework_accept,
        QualityCallback.filter(F.action == "raccept"),
    )
    router.callback_query.register(
        handle_rework_retry,
        QualityCallback.filter(F.action == "rretry"),
    )
    router.callback_query.register(
        handle_rework_dismiss,
        QualityCallback.filter(F.action == "rdismiss"),
    )


__all__ = ("register_quality_rework_handlers",)
