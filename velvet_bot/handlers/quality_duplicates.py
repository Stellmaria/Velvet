from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.media_quality import (
    decide_duplicate_candidate,
    get_duplicate_candidate,
    list_duplicate_candidates,
)
from velvet_bot.quality_ui import (
    QualityCallback,
    build_duplicate_list,
    quality_callback,
)

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


async def _send_preview(
    bot: Bot,
    chat_id: int,
    *,
    file_id: str,
    media_type: str,
    caption: str,
) -> None:
    try:
        if media_type == "photo":
            await bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption)
        else:
            await bot.send_document(chat_id=chat_id, document=file_id, caption=caption)
    except TelegramAPIError:
        await bot.send_message(
            chat_id,
            f"{caption}\n\nФайл сейчас недоступен в Telegram.",
        )


async def show_duplicate_list(
    message: Message,
    database: Database,
    *,
    status: str,
    page_number: int,
) -> None:
    page = await list_duplicate_candidates(
        database,
        status=status,
        page=page_number,
    )
    text, keyboard = build_duplicate_list(page, status=status)
    await _safe_edit(message, text, keyboard)


@router.callback_query(QualityCallback.filter(F.action == "duplicates"))
async def handle_duplicate_list(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await show_duplicate_list(
        callback.message,
        database,
        status=callback_data.section or "pending",
        page_number=callback_data.page,
    )
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "duplicate"))
async def handle_duplicate_open(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
    bot: Bot,
) -> None:
    candidate = await get_duplicate_candidate(database, callback_data.item_id)
    if candidate is None or not isinstance(callback.message, Message):
        await callback.answer("Пара больше не найдена.", show_alert=True)
        return

    await _send_preview(
        bot,
        callback.message.chat.id,
        file_id=candidate.first_file_id,
        media_type=candidate.first_media_type,
        caption=(
            f"A · media #{candidate.first_media_id}\n"
            f"{candidate.first_file_name}\n"
            f"Персонажи: {', '.join(candidate.first_characters) or '—'}"
        ),
    )
    await _send_preview(
        bot,
        callback.message.chat.id,
        file_id=candidate.second_file_id,
        media_type=candidate.second_media_type,
        caption=(
            f"B · media #{candidate.second_media_id}\n"
            f"{candidate.second_file_name}\n"
            f"Персонажи: {', '.join(candidate.second_characters) or '—'}"
        ),
    )

    text = (
        "<b>Сравнение изображений</b>\n\n"
        f"Сходство: <b>{candidate.similarity_score}%</b>\n"
        f"Точные байты: <b>{'да' if candidate.exact_bytes else 'нет'}</b>\n"
        f"pHash: <b>{candidate.phash_distance}</b>\n"
        f"Центральный pHash: <b>{candidate.center_distance}</b>\n"
        f"dHash: <b>{candidate.dhash_distance}</b>\n"
        f"aHash: <b>{candidate.ahash_distance}</b>\n\n"
        "Подтверждение только отмечает пару. Файлы автоматически не удаляются."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Это дубль",
                    callback_data=quality_callback(
                        "decide",
                        section="confirmed",
                        page=callback_data.page,
                        item_id=candidate.id,
                    ),
                ),
                InlineKeyboardButton(
                    text="🚫 Разные изображения",
                    callback_data=quality_callback(
                        "decide",
                        section="ignored",
                        page=callback_data.page,
                        item_id=candidate.id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К списку",
                    callback_data=quality_callback(
                        "duplicates",
                        section=callback_data.section or "pending",
                        page=callback_data.page,
                    ),
                )
            ],
        ]
    )
    await _safe_edit(callback.message, text, keyboard)
    await callback.answer("Оба файла отправлены выше.")


@router.callback_query(QualityCallback.filter(F.action == "decide"))
async def handle_duplicate_decision(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    updated = await decide_duplicate_candidate(
        database,
        callback_data.item_id,
        status=callback_data.section,
        decided_by=callback.from_user.id,
    )
    await callback.answer(
        "Решение сохранено." if updated else "Пара больше не найдена.",
        show_alert=True,
    )
    await show_duplicate_list(
        callback.message,
        database,
        status="pending",
        page_number=callback_data.page,
    )
