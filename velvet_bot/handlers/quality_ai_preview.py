from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.ai_quality import AIQualityItem, AIQualityRepository
from velvet_bot.database import Database
from velvet_bot.handlers import quality_ai as quality_ai_module
from velvet_bot.quality_ui import QualityCallback, quality_callback

router = Router(name=__name__)
_INSTALLED = False


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

    await quality_ai_module._send_preview(bot, callback.message.chat.id, item)
    await callback.answer("Изображение отправлено отдельным сообщением.")


__all__ = ("router",)
