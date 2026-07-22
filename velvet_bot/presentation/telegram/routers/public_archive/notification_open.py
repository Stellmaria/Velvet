from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from velvet_bot.archive_catalog import get_archive_page
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.public_catalog import (
    record_public_media_view,
    resolve_public_download_source,
)
from velvet_bot.public_media_lookup import get_character_media_offset
from velvet_bot.public_preview_overrides import send_viewer_archive_page
from velvet_bot.public_ui import PublicArchiveCallback
from velvet_bot.presentation.telegram.workspace_public_access import (
    has_workspace_adult_access,
    has_workspace_download_access,
)

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
    workspace_product_service: WorkspaceProductService,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Уведомление больше недоступно.", show_alert=True)
        return

    workspace_id = await workspace_product_service.public_workspace_id_for_user(
        callback.from_user.id
    )
    member_access = await has_workspace_adult_access(
        bot=bot,
        user_id=callback.from_user.id,
        workspace_id=workspace_id,
        manager_access=False,
        default_adult_channel_id=adult_channel_id,
        workspace_product_service=workspace_product_service,
    )
    offset = await get_character_media_offset(
        database,
        character_id=callback_data.character_id,
        media_id=callback_data.media_id,
        public_only=True,
        include_restricted=member_access,
        include_oversized=(workspace_id != 1 or member_access),
        workspace_id=workspace_id,
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
        include_adult_restricted=member_access,
        include_oversized_images=(workspace_id != 1 or member_access),
        workspace_id=workspace_id,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return
    if page.media.requires_adult_channel and not member_access:
        await callback.answer(
            "Этот материал доступен только участникам настроенного канала +18.",
            show_alert=True,
        )
        return

    await record_public_media_view(
        database,
        character_id=page.character.id,
        media_id=page.media.id,
        user_id=callback.from_user.id,
        workspace_id=workspace_id,
    )
    download_access = await has_workspace_download_access(
        bot=bot,
        user_id=callback.from_user.id,
        workspace_id=workspace_id,
        member_access=member_access,
        manager_access=False,
        workspace_product_service=workspace_product_service,
    )
    download_source = await resolve_public_download_source(
        database,
        character_id=page.character.id,
        media_id=page.media.id,
        member_access=member_access,
        download_access=download_access,
        workspace_id=workspace_id,
    )
    try:
        await send_viewer_archive_page(
            bot=bot,
            database=database,
            chat_id=callback.message.chat.id,
            page=page,
            viewer_user_id=callback.from_user.id,
            member_access=member_access,
            can_download=download_source is not None,
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
