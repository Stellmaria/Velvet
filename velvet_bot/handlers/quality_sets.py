from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.ai_vision import MediaAIRepository
from velvet_bot.database import Database
from velvet_bot.media_sets import (
    MediaSetCandidate,
    create_media_set,
    decide_media_set_candidate,
    discover_media_set_candidates,
    get_media_set_candidate,
    list_media_set_candidates,
    toggle_media_set_candidate_item,
)
from velvet_bot.quality_ui import QualityCallback, quality_callback

router = Router(name=__name__)


async def _safe_edit(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except Exception as error:
        if "message is not modified" not in str(error).casefold():
            raise


def _candidate_text(candidate: MediaSetCandidate) -> str:
    prompt_state = (
        "<b>будет привязан ко всему сету</b>"
        if candidate.prompt_post_url
        else "не указан, его можно привязать позже из любого материала сета"
    )
    lines = [
        "<b>🎞 Предложение медиасета</b>",
        "",
        f"Название: <b>{escape(candidate.suggested_title)}</b>",
        f"Уверенность: <b>{candidate.score}%</b>",
        f"Причина: {escape(candidate.reason)}",
        f"Промт: {prompt_state}",
        "",
        f"Выбрано: <b>{candidate.selected_count}</b> из <b>{len(candidate.items)}</b>",
        "Нажмите на материал, чтобы включить или исключить его из будущего сета.",
    ]
    for item in candidate.items:
        marker = "✅" if item.selected else "⬜"
        characters = ", ".join(item.characters) or "без персонажа"
        lines.extend(
            [
                "",
                f"{marker} <b>media #{item.media_id}</b> · {escape(characters)}",
                f"<code>{escape(item.file_name)}</code>",
            ]
        )
    return "\n".join(lines)


def _candidate_keyboard(candidate: MediaSetCandidate, *, list_page: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in candidate.items:
        marker = "✅" if item.selected else "⬜"
        label = ", ".join(item.characters[:2]) or item.file_name
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker} #{item.media_id} · {label[:30]}",
                    callback_data=quality_callback(
                        "settoggle",
                        page=item.media_id,
                        item_id=candidate.id,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=f"✅ Создать сет из {candidate.selected_count}",
                callback_data=quality_callback(
                    "setcreate",
                    page=list_page,
                    item_id=candidate.id,
                ),
            ),
            InlineKeyboardButton(
                text="🚫 Отклонить",
                callback_data=quality_callback(
                    "setignore",
                    page=list_page,
                    item_id=candidate.id,
                ),
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К предложениям",
                callback_data=quality_callback("sets", section="pending", page=list_page),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_candidate_previews(
    bot: Bot,
    chat_id: int,
    candidate: MediaSetCandidate,
) -> None:
    for item in candidate.items:
        characters = ", ".join(item.characters) or "—"
        caption = (
            f"media #{item.media_id}\n"
            f"Персонажи: {characters}\n"
            f"Контекст: {item.context_score}%"
        )
        try:
            if item.media_type == "photo":
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=item.telegram_file_id,
                    caption=caption,
                    protect_content=True,
                )
            else:
                await bot.send_document(
                    chat_id=chat_id,
                    document=item.telegram_file_id,
                    caption=caption,
                    protect_content=True,
                )
        except TelegramAPIError:
            await bot.send_message(
                chat_id,
                f"{caption}\nФайл сейчас недоступен в Telegram.",
            )


async def show_media_set_candidates(
    message: Message,
    database: Database,
    *,
    page_number: int,
) -> None:
    await discover_media_set_candidates(database)
    page = await list_media_set_candidates(
        database,
        status="pending",
        page=page_number,
    )
    ai = await MediaAIRepository(database).summary()
    lines = [
        "<b>🎞 Предложения медиасетов</b>",
        "",
        f"На проверке: <b>{page.total_items}</b>",
        f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>",
        "",
        (
            "ИИ-профили: "
            f"готово <b>{ai.ready}</b>, "
            f"в очереди <b>{ai.pending + ai.processing}</b>, "
            f"ошибок/пропусков <b>{ai.errors + ai.skipped}</b>."
        ),
        "",
        "Глубокий анализ сравнивает тему, жанр, эпоху, локацию, окружение, "
        "предметы, одежду, композицию, свет и настроение независимо от лица "
        "персонажа. Общий промт и ручные предложения сохраняются. Слабые "
        "совпадения только по времени или имени файла скрываются после появления "
        "ИИ-профилей.",
        "",
        "Бот создаёт только предложения. Сет формируется после вашего выбора.",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for candidate in page.items:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{candidate.score}% · {candidate.suggested_title[:34]} "
                        f"· {len(candidate.items)} фото"
                    ),
                    callback_data=quality_callback(
                        "set",
                        page=page.page,
                        item_id=candidate.id,
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
                        "sets",
                        section="pending",
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
                        "sets",
                        section="pending",
                        page=(page.page + 1) % page.total_pages,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Обновить предложения",
                callback_data=quality_callback("sets", section="pending", page=page.page),
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


@router.callback_query(QualityCallback.filter(F.action == "sets"))
async def handle_media_set_list(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await show_media_set_candidates(
        callback.message,
        database,
        page_number=callback_data.page,
    )
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "set"))
async def handle_media_set_open(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
    bot: Bot,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    candidate = await get_media_set_candidate(database, callback_data.item_id)
    if candidate is None or candidate.status != "pending":
        await callback.answer("Предложение больше недоступно.", show_alert=True)
        return
    await _send_candidate_previews(bot, callback.message.chat.id, candidate)
    await _safe_edit(
        callback.message,
        _candidate_text(candidate),
        _candidate_keyboard(candidate, list_page=callback_data.page),
    )
    await callback.answer("Материалы отправлены выше.")


@router.callback_query(QualityCallback.filter(F.action == "settoggle"))
async def handle_media_set_toggle(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    selected = await toggle_media_set_candidate_item(
        database,
        candidate_id=callback_data.item_id,
        media_id=callback_data.page,
    )
    candidate = await get_media_set_candidate(database, callback_data.item_id)
    if selected is None or candidate is None:
        await callback.answer("Материал или предложение больше недоступны.", show_alert=True)
        return
    await _safe_edit(
        callback.message,
        _candidate_text(candidate),
        _candidate_keyboard(candidate, list_page=0),
    )
    await callback.answer("Добавлен в сет." if selected else "Исключён из сета.")


@router.callback_query(QualityCallback.filter(F.action == "setcreate"))
async def handle_media_set_create(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    try:
        created = await create_media_set(
            database,
            candidate_id=callback_data.item_id,
            created_by=callback.from_user.id,
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer(
        f"Сет создан: {len(created.media_ids)} материалов.",
        show_alert=True,
    )
    await show_media_set_candidates(
        callback.message,
        database,
        page_number=callback_data.page,
    )


@router.callback_query(QualityCallback.filter(F.action == "setignore"))
async def handle_media_set_ignore(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    updated = await decide_media_set_candidate(
        database,
        candidate_id=callback_data.item_id,
        status="ignored",
        decided_by=callback.from_user.id,
    )
    await callback.answer(
        "Предложение отклонено." if updated else "Предложение больше не найдено.",
        show_alert=True,
    )
    await show_media_set_candidates(
        callback.message,
        database,
        page_number=callback_data.page,
    )


__all__ = ("router", "show_media_set_candidates")
