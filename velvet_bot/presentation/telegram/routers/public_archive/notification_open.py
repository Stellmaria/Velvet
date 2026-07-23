from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from velvet_bot.archive_catalog import get_archive_page
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.public_catalog import (
    record_public_media_view,
    resolve_public_download_source,
)
from velvet_bot.public_media_lookup import get_character_media_offset
from velvet_bot.public_preview_overrides import send_viewer_archive_page
from velvet_bot.public_ui import PublicArchiveCallback
from velvet_bot.presentation.telegram.public_notifications import (
    PublicNotificationCallback,
)
from velvet_bot.presentation.telegram.workspace_public_access import (
    has_workspace_adult_access,
    has_workspace_download_access,
)

router = Router(name=__name__)
logger = logging.getLogger(__name__)


async def _respond(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
    acknowledged: bool = False,
) -> None:
    if not acknowledged:
        await callback.answer(text, show_alert=show_alert)
        return
    if text and isinstance(callback.message, Message):
        await callback.message.answer(text)


async def _open_exact_notification_media(
    *,
    callback: CallbackQuery,
    character_id: int,
    media_id: int,
    workspace_id: int,
    menu_page: int,
    database: Database,
    bot: Bot,
    adult_channel_id: int,
    workspace_product_service: WorkspaceProductService,
    acknowledged: bool = False,
) -> None:
    if not isinstance(callback.message, Message):
        await _respond(
            callback,
            "Уведомление больше недоступно.",
            show_alert=True,
            acknowledged=acknowledged,
        )
        return

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
        character_id=character_id,
        media_id=media_id,
        public_only=True,
        include_restricted=member_access,
        include_oversized=(workspace_id != DEFAULT_WORKSPACE_ID or member_access),
        workspace_id=workspace_id,
    )
    if offset is None:
        await _respond(
            callback,
            "Это изображение удалено или скрыто из публичного архива.",
            show_alert=True,
            acknowledged=acknowledged,
        )
        return

    page = await get_archive_page(
        database,
        character_id,
        offset,
        public_only=True,
        include_adult_restricted=member_access,
        include_oversized_images=(workspace_id != DEFAULT_WORKSPACE_ID or member_access),
        workspace_id=workspace_id,
    )
    if page is None or page.media is None:
        await _respond(
            callback,
            "Материал больше недоступен.",
            show_alert=True,
            acknowledged=acknowledged,
        )
        return
    if page.media.requires_adult_channel and not member_access:
        await _respond(
            callback,
            "Этот материал доступен только участникам настроенного канала +18.",
            show_alert=True,
            acknowledged=acknowledged,
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
            menu_page=max(0, int(menu_page)),
        )
    except TelegramBadRequest:
        logger.exception("Failed to open exact notification media")
        await _respond(
            callback,
            "Telegram больше не может открыть этот материал.",
            show_alert=True,
            acknowledged=acknowledged,
        )
        return
    await _respond(callback, acknowledged=acknowledged)


async def handle_workspace_notification_media(
    callback: CallbackQuery,
    callback_data: PublicNotificationCallback,
    database: Database,
    bot: Bot,
    adult_channel_id: int,
    workspace_product_service: WorkspaceProductService,
) -> None:
    workspace_id = int(callback_data.workspace_id)
    if workspace_id != DEFAULT_WORKSPACE_ID:
        selected = await workspace_product_service.select_public_workspace(
            user_id=callback.from_user.id,
            workspace_id=workspace_id,
        )
        if not selected:
            await callback.answer(
                "Этот пользовательский архив больше не является публичным.",
                show_alert=True,
            )
            return
    await _open_exact_notification_media(
        callback=callback,
        character_id=callback_data.character_id,
        media_id=callback_data.media_id,
        workspace_id=workspace_id,
        menu_page=0,
        database=database,
        bot=bot,
        adult_channel_id=adult_channel_id,
        workspace_product_service=workspace_product_service,
    )


@router.callback_query(
    PublicArchiveCallback.filter((F.action == "open") & (F.media_id > 0))
)
async def handle_exact_notification_media(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    adult_channel_id: int,
    workspace_product_service: WorkspaceProductService,
) -> None:
    await callback.answer()
    workspace_id = await workspace_product_service.public_workspace_id_for_user(
        callback.from_user.id
    )
    await _open_exact_notification_media(
        callback=callback,
        character_id=callback_data.character_id,
        media_id=callback_data.media_id,
        workspace_id=workspace_id,
        menu_page=callback_data.page,
        database=database,
        bot=bot,
        adult_channel_id=adult_channel_id,
        workspace_product_service=workspace_product_service,
        acknowledged=True,
    )


router.callback_query.register(
    handle_workspace_notification_media,
    PublicNotificationCallback.filter(),
)


__all__ = ("router",)
