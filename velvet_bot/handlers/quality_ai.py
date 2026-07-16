from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.ai_quality import AIQualityItem, AIQualityRepository
from velvet_bot.database import Database
from velvet_bot.quality_ui import QualityCallback, quality_callback

router = Router(name=__name__)

_SECTION_TITLES = {
    "review": "На проверке",
    "accepted": "Приняты владельцем",
    "fix": "Возвращены на исправление",
    "errors": "Ошибки анализа",
}
_VERDICT_EMOJI = {
    "ready": "✅",
    "review": "⚠️",
    "critical": "🚨",
}
_CHECK_LABELS = {
    "anatomy": "Анатомия",
    "hands": "Руки",
    "face": "Лицо",
    "hair": "Волосы",
    "skin_texture": "Текстура кожи",
    "lighting": "Освещение",
    "exposure": "Экспозиция",
    "sharpness": "Резкость",
    "background": "Фон",
    "reflections": "Отражения",
    "composition": "Композиция",
    "compression": "Сжатие",
    "text_watermarks": "Текст и водяные знаки",
    "ui_artifacts": "Интерфейс и служебные элементы",
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


def _tabs(section: str) -> list[list[InlineKeyboardButton]]:
    return [
        [
            InlineKeyboardButton(
                text=("• " if section == "review" else "") + "🧠 На проверке",
                callback_data=quality_callback("qchecks", section="review"),
            ),
            InlineKeyboardButton(
                text=("• " if section == "fix" else "") + "🛠 На исправление",
                callback_data=quality_callback("qchecks", section="fix"),
            ),
        ],
        [
            InlineKeyboardButton(
                text=("• " if section == "accepted" else "") + "✅ Приняты",
                callback_data=quality_callback("qchecks", section="accepted"),
            ),
            InlineKeyboardButton(
                text=("• " if section == "errors" else "") + "❌ Ошибки",
                callback_data=quality_callback("qchecks", section="errors"),
            ),
        ],
    ]


async def _show_list(
    message: Message,
    database: Database,
    *,
    section: str,
    page_number: int,
) -> None:
    repository = AIQualityRepository(database)
    page = await repository.list_items(section, page=page_number)
    summary = await repository.summary()

    lines = [
        f"<b>🧠 Qwen · {_SECTION_TITLES.get(section, section)}</b>",
        "",
        f"Найдено: <b>{page.total_items}</b>",
        f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>",
        "",
        (
            "Общая очередь: "
            f"<b>{summary.pending + summary.processing}</b> · "
            f"готово <b>{summary.ready}</b> · "
            f"ошибок <b>{summary.errors + summary.skipped}</b>"
        ),
    ]
    if section == "review":
        lines.extend(
            [
                "",
                f"🚨 критично: <b>{summary.critical}</b> · "
                f"⚠️ замечания: <b>{summary.warnings}</b> · "
                f"✅ чисто: <b>{summary.clean}</b>",
            ]
        )

    rows = _tabs(section)
    for item in page.items:
        emoji = _VERDICT_EMOJI.get(item.verdict, "❌")
        score = f"{item.quality_score}%" if item.quality_score is not None else "ошибка"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{emoji} {score} · #{item.media_id} · {item.file_name}"[:60],
                    callback_data=quality_callback(
                        "qcheck",
                        section=section,
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
                        "qchecks",
                        section=section,
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
                        "qchecks",
                        section=section,
                        page=(page.page + 1) % page.total_pages,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=quality_callback(
                    "qchecks",
                    section=section,
                    page=page.page,
                ),
            ),
            InlineKeyboardButton(
                text="↩️ К аудиту",
                callback_data=quality_callback("menu"),
            ),
        ]
    )
    await _safe_edit(
        message,
        "\n".join(lines),
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


def _list_block(title: str, values: object, emoji: str) -> list[str]:
    if not isinstance(values, list) or not values:
        return []
    lines = ["", f"<b>{emoji} {escape(title)}</b>"]
    for value in values[:8]:
        lines.append(f"• {escape(str(value))}")
    return lines


def _report_text(item: AIQualityItem) -> str:
    if item.status in {"error", "skipped"}:
        return "\n".join(
            [
                f"<b>❌ Ошибка проверки media #{item.media_id}</b>",
                "",
                f"Файл: <code>{escape(item.file_name)}</code>",
                f"Статус: <code>{escape(item.status)}</code>",
                "",
                f"<code>{escape(item.error_message or 'Причина не сохранена.')}</code>",
            ]
        )

    report = item.report or {}
    verdict = item.verdict or str(report.get("verdict") or "review")
    emoji = _VERDICT_EMOJI.get(verdict, "⚠️")
    verdict_label = {
        "ready": "готово к публикации",
        "review": "нужна ручная проверка",
        "critical": "рекомендуется исправление",
    }.get(verdict, verdict)
    decision = {
        None: "не принято",
        "accepted": "✅ принято владельцем",
        "fix_required": "🛠 отправлено на исправление",
    }.get(item.decision, item.decision or "не принято")

    lines = [
        f"<b>{emoji} Проверка качества media #{item.media_id}</b>",
        "",
        f"Файл: <code>{escape(item.file_name)}</code>",
        f"Вердикт: <b>{escape(verdict_label)}</b>",
        f"Качество: <b>{item.quality_score if item.quality_score is not None else '—'} / 100</b>",
        f"Уверенность Qwen: <b>{item.confidence if item.confidence is not None else '—'}%</b>",
        f"Решение: <b>{escape(decision)}</b>",
        "",
        f"<b>Итог:</b> {escape(str(report.get('summary_ru') or '—'))}",
    ]
    lines.extend(_list_block("Критичные проблемы", report.get("critical_issues"), "🚨"))
    lines.extend(_list_block("Замечания", report.get("warnings"), "⚠️"))
    lines.extend(_list_block("Сильные стороны", report.get("strengths"), "✅"))
    lines.extend(_list_block("Неуверенные области", report.get("uncertain_areas"), "🔎"))

    checks = report.get("checks")
    if isinstance(checks, dict) and checks:
        weakest = sorted(
            (
                (str(key), int(value))
                for key, value in checks.items()
                if isinstance(value, int)
            ),
            key=lambda pair: pair[1],
        )[:7]
        if weakest:
            lines.extend(["", "<b>Оценки по областям:</b>"])
            for key, value in weakest:
                lines.append(f"• {escape(_CHECK_LABELS.get(key, key))}: <b>{value}/100</b>")

    return "\n".join(lines)[:4090]


def _report_keyboard(
    item: AIQualityItem,
    *,
    section: str,
    page: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if item.status == "ready":
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Принять",
                    callback_data=quality_callback(
                        "qaccept",
                        section=section,
                        page=page,
                        item_id=item.media_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="🛠 На исправление",
                    callback_data=quality_callback(
                        "qfix",
                        section=section,
                        page=page,
                        item_id=item.media_id,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Проверить заново",
                callback_data=quality_callback(
                    "qretry",
                    section=section,
                    page=page,
                    item_id=item.media_id,
                ),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К списку",
                callback_data=quality_callback(
                    "qchecks",
                    section=section,
                    page=page,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_preview(bot: Bot, chat_id: int, item: AIQualityItem) -> None:
    caption = f"Проверка качества · media #{item.media_id}\n{item.file_name}"
    file_id = item.preview_file_id or item.telegram_file_id
    try:
        if item.media_type == "photo" or item.preview_file_id:
            await bot.send_photo(
                chat_id=chat_id,
                photo=file_id,
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


@router.callback_query(QualityCallback.filter(F.action == "qchecks"))
async def handle_quality_ai_list(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    section = callback_data.section or "review"
    await _show_list(
        callback.message,
        database,
        section=section,
        page_number=callback_data.page,
    )
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "qcheck"))
async def handle_quality_ai_open(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
    bot: Bot,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    item = await AIQualityRepository(database).get_item(callback_data.item_id)
    if item is None:
        await callback.answer("Проверка больше недоступна.", show_alert=True)
        return
    await _send_preview(bot, callback.message.chat.id, item)
    await _safe_edit(
        callback.message,
        _report_text(item),
        _report_keyboard(
            item,
            section=callback_data.section or "review",
            page=callback_data.page,
        ),
    )
    await callback.answer("Изображение отправлено выше.")


async def _apply_decision(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
    decision: str,
) -> None:
    repository = AIQualityRepository(database)
    changed = await repository.set_decision(
        callback_data.item_id,
        decision,
        callback.from_user.id,
    )
    item = await repository.get_item(callback_data.item_id)
    if isinstance(callback.message, Message) and item is not None:
        await _safe_edit(
            callback.message,
            _report_text(item),
            _report_keyboard(
                item,
                section=callback_data.section or "review",
                page=callback_data.page,
            ),
        )
    await callback.answer(
        "Решение сохранено." if changed else "Решение не изменено.",
        show_alert=not changed,
    )


@router.callback_query(QualityCallback.filter(F.action == "qaccept"))
async def handle_quality_ai_accept(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    await _apply_decision(callback, callback_data, database, "accepted")


@router.callback_query(QualityCallback.filter(F.action == "qfix"))
async def handle_quality_ai_fix(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    await _apply_decision(callback, callback_data, database, "fix_required")


@router.callback_query(QualityCallback.filter(F.action == "qretry"))
async def handle_quality_ai_retry(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    changed = await AIQualityRepository(database).retry(callback_data.item_id)
    if isinstance(callback.message, Message):
        await _show_list(
            callback.message,
            database,
            section=callback_data.section or "review",
            page_number=callback_data.page,
        )
    await callback.answer(
        "Изображение возвращено в очередь." if changed else "Проверка не найдена.",
        show_alert=True,
    )


__all__ = ("router",)
