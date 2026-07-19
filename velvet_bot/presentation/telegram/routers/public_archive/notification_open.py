from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from velvet_bot.archive_catalog import get_archive_page
from velvet_bot.database import Database
from velvet_bot.handlers.public_archive import _send_public_archive_page
from velvet_bot.public_adult_access import has_adult_channel_access
from velvet_bot.public_media_lookup import get_character_media_offset
from velvet_bot.public_ui import PublicArchiveCallback

router = Router(name=__name__)
logger = logging.getLogger(__name__)


@router.callback_query(
    PublicArchiveCallback.filter(
        (F.action == "open") & (F.media_id > 0)
    )
)
async def handle_exact_notification_media(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    adult_channel_id: int,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Уведомление больше недоступно.", show_alert=True)
        return

    offset = await get_character_media_offset(
        database,
        character_id=callback_data.character_id,
        media_id=callback_data.media_id,
        public_only=True,
    )
    if offset is None:
        await callback.answer(
            "Это изображение удалено или скрыто из публичного архива.",
            show_alert=True,
        )
        return

    page = await get_archive_page(
        database,
        callback_data.character_id,
        offset,
        public_only=True,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return
    if page.media.requires_adult_channel and not await has_adult_channel_access(
        bot,
        callback.from_user.id,
        channel_id=adult_channel_id,
    ):
        await callback.answer(
            "Этот материал доступен только подписчикам канала Velvet +18.",
            show_alert=True,
        )
        return

    try:
        await _send_public_archive_page(
            bot=bot,
            database=database,
            chat_id=callback.message.chat.id,
            page=page,
            viewer_user_id=callback.from_user.id,
            menu_page=callback_data.page,
        )
    except TelegramBadRequest:
        logger.exception("Failed to open exact notification media")
        await callback.answer(
            "Telegram больше не может открыть этот материал.",
            show_alert=True,
        )
        return
    await callback.answer()
