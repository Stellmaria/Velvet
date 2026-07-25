from __future__ import annotations

import io

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.archive_catalog import delete_archive_item, get_archive_page
from velvet_bot.archive_ui import format_delete_caption
from velvet_bot.database import Database
from velvet_bot.domains.archive.models import ArchivedMedia
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.protected_bot import ProtectedMediaBot
from velvet_bot.presentation.telegram.workspace_archive_access import (
    load_workspace_archive_action_page,
    resolve_workspace_archive_access,
)
from velvet_bot.presentation.telegram.workspace_archive_navigation import (
    replace_workspace_archive_page,
)
from velvet_bot.presentation.telegram.workspace_personal_archive_contract import (
    WorkspacePersonalArchiveAction,
    WorkspacePersonalArchiveActionFilter,
    workspace_personal_archive_callback,
)

_DELIVERY_ACTIONS = frozenset({"download", "delete", "deleteconfirm"})


def build_workspace_archive_delete_keyboard(
    *,
    workspace_id: int,
    character_id: int,
    offset: int,
    media_id: int,
) -> InlineKeyboardMarkup:
    common = {
        "workspace_id": workspace_id,
        "character_id": character_id,
        "offset": offset,
        "media_id": media_id,
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=workspace_personal_archive_callback(
                        "deleteconfirm", **common
                    ),
                ),
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=workspace_personal_archive_callback("show", **common),
                ),
            ]
        ]
    )


async def send_workspace_owner_original(
    bot: Bot,
    *,
    user_id: int,
    media: ArchivedMedia,
) -> None:
    source_file_id = media.original_download_file_id
    if isinstance(bot, ProtectedMediaBot):
        bot.allow_unprotected_private_user(user_id)
    if media.media_type == "document":
        await bot.send_document(
            chat_id=user_id,
            document=source_file_id,
            caption="Оригинал из вашего личного архива",
        )
        return

    payload = io.BytesIO()
    await bot.download(source_file_id, destination=payload, seek=True)
    raw = payload.getvalue()
    if not raw:
        raise RuntimeError("Telegram вернул пустой файл.")
    await bot.send_document(
        chat_id=user_id,
        document=BufferedInputFile(raw, filename=media.display_file_name),
        caption="Оригинал из вашего личного архива",
    )


async def handle_workspace_archive_delivery(
    callback: CallbackQuery,
    archive_action: WorkspacePersonalArchiveAction,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace, owner_access = await resolve_workspace_archive_access(
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=archive_action.workspace_id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    if not owner_access:
        await callback.answer(
            "Эта кнопка доступна только владельцу пространства.",
            show_alert=True,
        )
        return

    page = await load_workspace_archive_action_page(
        callback,
        archive_action,
        database,
        workspace=workspace,
    )
    if page is None or page.media is None:
        return

    if archive_action.action == "download":
        try:
            await send_workspace_owner_original(
                bot,
                user_id=callback.from_user.id,
                media=page.media,
            )
        except (TelegramAPIError, RuntimeError):
            await callback.answer("Не удалось отправить оригинал.", show_alert=True)
            return
        await callback.answer("Оригинал отправлен вам в личный чат.")
        return

    if archive_action.action == "delete":
        if not isinstance(callback.message, Message):
            await callback.answer(
                "Сообщение архива больше недоступно.",
                show_alert=True,
            )
            return
        try:
            await callback.message.edit_caption(
                caption=format_delete_caption(page),
                reply_markup=build_workspace_archive_delete_keyboard(
                    workspace_id=workspace.id,
                    character_id=page.character.id,
                    offset=page.offset,
                    media_id=page.media.id,
                ),
            )
        except TelegramBadRequest:
            await callback.answer(
                "Не удалось открыть подтверждение.",
                show_alert=True,
            )
            return
        await callback.answer()
        return

    deleted = await delete_archive_item(
        database,
        archive_action.character_id,
        archive_action.media_id or page.media.id,
        workspace_id=workspace.id,
    )
    if deleted is None:
        await callback.answer("Материал уже удалён.", show_alert=True)
        return
    if (
        deleted.media.archive_message_id is not None
        and deleted.character.archive_chat_id is not None
    ):
        try:
            await bot.delete_message(
                chat_id=deleted.character.archive_chat_id,
                message_id=deleted.media.archive_message_id,
            )
        except TelegramAPIError:
            pass

    if deleted.remaining_total == 0:
        if isinstance(callback.message, Message):
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
        await callback.answer(
            "Удалено. Архив персонажа пуст.",
            show_alert=True,
        )
        return

    next_page = await get_archive_page(
        database,
        archive_action.character_id,
        min(page.offset, deleted.remaining_total - 1),
        workspace_id=workspace.id,
        include_adult_restricted=True,
        include_oversized_images=True,
    )
    if next_page is None or next_page.media is None:
        await callback.answer("Материал удалён.", show_alert=True)
        return
    await replace_workspace_archive_page(
        callback,
        bot,
        database=database,
        workspace_product_service=workspace_product_service,
        user_id=callback.from_user.id,
        workspace_id=workspace.id,
        page=next_page,
        owner_access=True,
    )


def register_workspace_archive_delivery(router: Router) -> None:
    router.callback_query.register(
        handle_workspace_archive_delivery,
        WorkspacePersonalArchiveActionFilter(*sorted(_DELIVERY_ACTIONS)),
    )


__all__ = (
    "build_workspace_archive_delete_keyboard",
    "handle_workspace_archive_delivery",
    "register_workspace_archive_delivery",
    "send_workspace_owner_original",
)
