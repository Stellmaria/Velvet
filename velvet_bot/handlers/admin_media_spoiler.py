from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from velvet_bot.archive_catalog import (
    get_archive_page,
    toggle_archive_media_spoiler,
)
from velvet_bot.archive_ui import ArchiveMediaCallback
from velvet_bot.database import Database
from velvet_bot.handlers.admin_media_display import replace_admin_archive_page

router = Router(name=__name__)


@router.callback_query(ArchiveMediaCallback.filter(F.action == "spoiler"))
async def handle_admin_media_spoiler(
    callback: CallbackQuery,
    callback_data: ArchiveMediaCallback,
    database: Database,
    bot: Bot,
) -> None:
    enabled = await toggle_archive_media_spoiler(
        database,
        character_id=callback_data.character_id,
        media_id=callback_data.media_id,
    )
    if enabled is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return

    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return

    await replace_admin_archive_page(callback, bot, page)
