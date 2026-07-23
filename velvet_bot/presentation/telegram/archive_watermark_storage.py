from __future__ import annotations

import logging
import os
from html import escape
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.domains.public_archive.watermark_repository import (
    PublicArchiveWatermarkRepository,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.onboarding import WorkspaceOnboardingRepository
from velvet_bot.domains.watermark.archive_output import (
    prepare_archive_watermark_output,
)
from velvet_bot.domains.watermark.models import WatermarkWorkItem
from velvet_bot.domains.watermark.repository import WatermarkRepository
from velvet_bot.domains.watermark.service import WatermarkService
from velvet_bot.domains.watermark.telegram_storage import (
    WatermarkStorageSettings,
    cleanup_watermark_job_files,
    storage_message_link,
    store_archive_watermark,
)
from velvet_bot.infrastructure.krita_bridge import KritaBridge, default_krita_bridge_dir
from velvet_bot.presentation.telegram.routers.workspace_guided_ui import (
    guided_workspace_callback,
)
from velvet_bot.watermark_ui import (
    WatermarkCallback,
    build_watermark_keyboard,
    format_watermark_caption,
)

logger = logging.getLogger(__name__)


def _watermark_enabled() -> bool:
    return os.getenv("KRITA_WATERMARK_ENABLED", "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
        "да",
    }


def _build_service(bot: Bot, database: Database) -> WatermarkService:
    return WatermarkService(
        bot=bot,
        repository=WatermarkRepository(database),
        bridge=KritaBridge(default_krita_bridge_dir()),
    )


def _command_media_id(command: CommandObject) -> int:
    raw = (command.args or "").strip().split(maxsplit=1)[0]
    if not raw:
        raise ValueError("Укажите media_id, например <code>/wm_file 77</code>.")
    try:
        media_id = int(raw)
    except ValueError as error:
        raise ValueError("media_id должен быть числом.") from error
    if media_id <= 0:
        raise ValueError("media_id должен быть положительным числом.")
    return media_id


async def _approve_or_resume(
    service: WatermarkService,
    *,
    job_id: int,
    owner_user_id: int,
) -> WatermarkWorkItem:
    current = await service.get_current(job_id, owner_user_id=owner_user_id)
    if current.job.status == "approved" and current.job.final_path:
        return current
    return await service.approve(job_id, owner_user_id=owner_user_id)


async def _safe_finish_card(callback: CallbackQuery, text: str) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        if callback.message.photo or callback.message.document:
            await callback.message.edit_caption(caption=text, reply_markup=None)
        else:
            await callback.message.edit_text(text, reply_markup=None)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


async def _configured_storage_settings(
    database: Database,
    *,
    workspace_id: int,
) -> WatermarkStorageSettings | None:
    if int(workspace_id) == DEFAULT_WORKSPACE_ID:
        return WatermarkStorageSettings.from_env()
    destinations = await WorkspaceOnboardingRepository(database).list_destinations(
        int(workspace_id)
    )
    destination = next(
        (item for item in destinations if item.destination_key == "watermarks"),
        None,
    )
    if destination is None:
        return None
    return WatermarkStorageSettings(
        chat_id=destination.chat_id,
        thread_id=destination.message_thread_id,
    )


def _fallback_storage_settings(message: Message) -> WatermarkStorageSettings:
    return WatermarkStorageSettings(
        chat_id=message.chat.id,
        thread_id=message.message_thread_id if message.is_topic_message else None,
    )


def _storage_setup_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚙️ Настроить Watermark-копии",
                    callback_data=guided_workspace_callback(
                        "connections",
                        workspace_id=workspace_id,
                    ),
                )
            ]
        ]
    )


async def _requeue_missing_output(
    *,
    callback: CallbackQuery,
    bot: Bot,
    database: Database,
    item: WatermarkWorkItem,
) -> bool:
    output_path = item.revision.output_path or item.job.final_path or ""
    if output_path and Path(output_path).is_file():
        return False
    if not Path(item.job.source_path).is_file():
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "❌ Исходник и готовый PNG уже очищены. Откройте материал и снова "
                "нажмите «Быстрый watermark»."
            )
        return True

    repository = WatermarkRepository(database)
    regenerated = await repository.create_job(
        owner_user_id=item.job.owner_user_id,
        chat_id=item.job.chat_id,
        source_message_id=item.job.source_message_id,
        source_file_id=item.job.source_file_id,
        source_file_unique_id=item.job.source_file_unique_id,
        source_path=item.job.source_path,
        settings=item.revision.settings,
        workspace_id=item.job.workspace_id,
        logo_kind=item.job.logo_kind,
        logo_path=item.job.logo_path,
        logo_width=item.job.logo_width,
        logo_height=item.job.logo_height,
        logo_name=item.job.logo_name,
    )
    if isinstance(callback.message, Message):
        control = await callback.message.answer(
            format_watermark_caption(
                regenerated,
                status_text="готовый файл исчез, поставлено на безопасную пересборку",
            ),
            reply_markup=build_watermark_keyboard(regenerated),
        )
        await repository.set_control_message(regenerated.job.id, control.message_id)
    logger.info(
        "Requeued missing archive watermark output old_job=%s new_job=%s",
        item.job.id,
        regenerated.job.id,
    )
    return True


async def handle_watermark_storage_lookup(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    try:
        media_id = _command_media_id(command)
    except ValueError as error:
        await message.answer(str(error))
        return
    stored = await PublicArchiveWatermarkRepository(database).get_storage(media_id)
    if stored is None:
        await message.answer(
            f"Watermark для media_id <code>{media_id}</code> в Telegram-хранилище не найден."
        )
        return
    size = (
        f"{stored.file_size / 1024 / 1024:.2f} МБ"
        if stored.file_size is not None
        else "неизвестно"
    )
    sha = stored.sha256 or "не сохранён"
    link = storage_message_link(stored.chat_id, stored.message_id)
    await message.answer(
        f"<b>Watermark media_id {media_id}</b>\n"
        f"Размер: <b>{size}</b>\n"
        f"SHA256: <code>{sha}</code>\n"
        f'<a href="{link}">Открыть в Telegram-хранилище</a>\n\n'
        f"Скачать через бота: <code>/wm_download {media_id}</code>"
    )


async def handle_watermark_storage_download(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    try:
        media_id = _command_media_id(command)
    except ValueError as error:
        await message.answer(str(error))
        return
    stored = await PublicArchiveWatermarkRepository(database).get_storage(media_id)
    if stored is None:
        await message.answer(
            f"Watermark для media_id <code>{media_id}</code> в Telegram-хранилище не найден."
        )
        return
    await message.answer_document(
        document=stored.telegram_file_id,
        caption=(
            f"✅ Watermark media_id <code>{media_id}</code> из Telegram-хранилища.\n"
            f"SHA256: <code>{stored.sha256 or 'не сохранён'}</code>"
        ),
    )


async def handle_archive_watermark_storage_approve(
    callback: CallbackQuery,
    callback_data: WatermarkCallback,
    bot: Bot,
    database: Database,
) -> None:
    if not _watermark_enabled():
        await callback.answer("Krita bridge выключен.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение preview больше недоступно.", show_alert=True)
        return

    await callback.answer("Сохраняю PNG…")
    service = _build_service(bot, database)
    repository = PublicArchiveWatermarkRepository(database)

    try:
        current = await service.get_current(
            callback_data.job_id,
            owner_user_id=callback.from_user.id,
        )
        if await _requeue_missing_output(
            callback=callback,
            bot=bot,
            database=database,
            item=current,
        ):
            return

        item = await _approve_or_resume(
            service,
            job_id=callback_data.job_id,
            owner_user_id=callback.from_user.id,
        )
        media_id = item.job.archive_media_id
        if media_id is None:
            raise ValueError("Задание не связано с публичным архивом.")
        if not item.job.final_path:
            raise ValueError("Финальный путь задания не сохранён.")

        output = prepare_archive_watermark_output(
            item.job.source_path,
            item.job.final_path,
        )
        source = await repository.get_source(media_id)
        if source is None:
            raise ValueError("Исходный материал публичного архива больше не найден.")

        configured = await _configured_storage_settings(
            database,
            workspace_id=item.job.workspace_id,
        )
        storage_settings = configured or _fallback_storage_settings(callback.message)
        stored = await store_archive_watermark(
            bot=bot,
            item=item,
            media_id=media_id,
            output=output,
            source_name=source.file_name,
            character_names=source.character_names,
            settings=storage_settings,
        )
        document = stored.message.document
        if document is None:
            raise ValueError("Telegram не вернул file_id PNG.")

        updated = await repository.approve_replacement(
            media_id=media_id,
            telegram_file_id=document.file_id,
            telegram_file_unique_id=document.file_unique_id,
            file_size=stored.file_size,
            approved_by=callback.from_user.id,
            settings=item.revision.settings,
            storage_chat_id=storage_settings.chat_id,
            storage_thread_id=storage_settings.thread_id,
            storage_message_id=stored.message.message_id,
            storage_sha256=stored.sha256,
        )
        if not updated:
            try:
                await bot.delete_message(
                    chat_id=storage_settings.chat_id,
                    message_id=stored.message.message_id,
                )
            except TelegramAPIError:
                logger.warning(
                    "Could not remove orphan watermark storage message chat=%s message=%s",
                    storage_settings.chat_id,
                    stored.message.message_id,
                )
            raise ValueError("Материал публичного архива больше не найден.")

        deleted_files, freed_bytes = cleanup_watermark_job_files(item, service.bridge)
        if deleted_files:
            await repository.mark_local_cleaned(media_id)
        logger.info(
            "Stored archive watermark media=%s chat=%s thread=%s message=%s "
            "sha256=%s deleted_files=%s freed_bytes=%s fallback=%s",
            media_id,
            storage_settings.chat_id,
            storage_settings.thread_id,
            stored.message.message_id,
            stored.sha256,
            deleted_files,
            freed_bytes,
            configured is None,
        )

        if configured is None:
            await callback.message.answer(
                "✅ Watermark сохранён и заменил копию архива. Отдельное хранилище "
                "не подключено, поэтому готовый PNG отправлен сюда.\n"
                f"Media ID: <code>{media_id}</code> · "
                f"SHA: <code>{stored.sha256[:12]}</code>",
                reply_markup=_storage_setup_keyboard(item.job.workspace_id),
            )
            status = "одобрен, отправлен владельцу и заменён в архиве"
        else:
            await callback.message.answer(
                "✅ Watermark сохранён в закрытом Telegram-хранилище и заменил "
                "файл публичного архива.\n"
                f"Media ID: <code>{media_id}</code> · "
                f"SHA: <code>{stored.sha256[:12]}</code>\n"
                f'<a href="{stored.message_link}">Открыть файл в хранилище</a>'
            )
            status = "одобрен, сохранён в Telegram и заменён в архиве"
        await _safe_finish_card(
            callback,
            format_watermark_caption(item, status_text=status),
        )
    except (OSError, TelegramAPIError, TypeError, ValueError) as error:
        logger.warning(
            "Could not store approved archive watermark job=%s: %s",
            callback_data.job_id,
            error,
        )
        await callback.message.answer(f"❌ {escape(str(error))}")


def register_archive_watermark_storage_handler(router: Router) -> None:
    router.message.register(
        handle_watermark_storage_lookup,
        Command("wm_file", "wm_storage"),
    )
    router.message.register(
        handle_watermark_storage_download,
        Command("wm_download"),
    )
    router.callback_query.register(
        handle_archive_watermark_storage_approve,
        WatermarkCallback.filter(F.action == "archive_approve"),
    )


__all__ = ("register_archive_watermark_storage_handler",)
