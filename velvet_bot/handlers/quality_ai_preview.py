from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.ai_quality import AIQualityItem, AIQualityRepository
from velvet_bot.database import Database
from velvet_bot.handlers import quality_ai as quality_ai_module
from velvet_bot.quality_ui import QualityCallback, quality_callback

logger = logging.getLogger(__name__)
router = Router(name=__name__)
_INSTALLED = False


async def _send_preview_with_fallback(
    bot: Bot,
    chat_id: int,
    item: AIQualityItem,
) -> bool:
    """Send the best available media representation.

    Telegram file identifiers are bound to their media type. A generated photo
    preview may become invalid even while the original image document remains
    downloadable. Try the preview first, then fall back to the original using the
    method matching its stored media type.
    """

    caption = f"Проверка качества · media #{item.media_id}\n{item.file_name}"
    attempts: list[tuple[str, str]] = []

    preview_file_id = str(item.preview_file_id or "").strip()
    original_file_id = str(item.telegram_file_id or "").strip()

    if preview_file_id:
        attempts.append(("preview_photo", preview_file_id))

    if original_file_id:
        if item.media_type == "photo":
            if original_file_id != preview_file_id:
                attempts.append(("original_photo", original_file_id))
        else:
            # Even when both identifiers happen to be equal, sending the original
            # as a document is a distinct and valid fallback after send_photo fails.
            attempts.append(("original_document", original_file_id))

    errors: list[str] = []
    for attempt_type, file_id in attempts:
        try:
            if attempt_type.endswith("photo"):
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=file_id,
                    caption=caption,
                    protect_content=False,
                )
            else:
                await bot.send_document(
                    chat_id=chat_id,
                    document=file_id,
                    caption=caption,
                    protect_content=False,
                )
            return True
        except TelegramAPIError as error:
            errors.append(f"{attempt_type}: {type(error).__name__}: {error}")

    logger.warning(
        "Quality preview unavailable media_id=%s media_type=%s attempts=%s last_error=%s",
        item.media_id,
        item.media_type,
        [attempt_type for attempt_type, _ in attempts],
        errors[-1] if errors else "no usable Telegram file id",
    )
    await bot.send_message(chat_id, f"{caption}\nПревью сейчас недоступно.")
    return False


def _install_preview_button() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original = quality_ai_module._report_keyboard

    def wrapped(
        item: AIQualityItem,
        *,
        section: str,
        page: int,
    ) -> InlineKeyboardMarkup:
        markup = original(item, section=section, page=page)
        rows = [list(row) for row in markup.inline_keyboard]
        preview_row = [
            InlineKeyboardButton(
                text="🖼 Посмотреть фото",
                callback_data=quality_callback(
                    "qpreview",
                    section=section,
                    page=page,
                    item_id=item.media_id,
                ),
            )
        ]
        insert_at = max(0, len(rows) - 1)
        rows.insert(insert_at, preview_row)
        return InlineKeyboardMarkup(inline_keyboard=rows)

    quality_ai_module._report_keyboard = wrapped
    quality_ai_module._send_preview = _send_preview_with_fallback
    _INSTALLED = True


_install_preview_button()


@router.callback_query(QualityCallback.filter(F.action == "qpreview"))
async def handle_quality_ai_preview(
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
        await callback.answer("Изображение больше недоступно.", show_alert=True)
        return

    sent = await _send_preview_with_fallback(bot, callback.message.chat.id, item)
    await callback.answer(
        "Изображение отправлено отдельным сообщением."
        if sent
        else "Оригинал и превью недоступны.",
        show_alert=not sent,
    )


__all__ = ("router",)
