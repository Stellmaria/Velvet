from __future__ import annotations

import logging
import os
from pathlib import Path
from uuid import uuid4

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message
from PIL import Image, UnidentifiedImageError

from velvet_bot.access import AccessPolicy
from velvet_bot.archive_catalog import get_archive_page
from velvet_bot.database import Database
from velvet_bot.domains.public_archive.watermark_repository import (
    PublicArchiveWatermarkRepository,
)
from velvet_bot.domains.watermark.repository import WatermarkRepository
from velvet_bot.domains.watermark.service import WatermarkService
from velvet_bot.infrastructure.krita_bridge import KritaBridge, default_krita_bridge_dir
from velvet_bot.krita_supervisor import build_krita_supervisor_client
from velvet_bot.public_manager_access import has_public_manager_access
from velvet_bot.public_ui import PublicArchiveCallback
from velvet_bot.supervisor_client import SupervisorClientError
from velvet_bot.watermark_ui import build_watermark_keyboard, format_watermark_caption

logger = logging.getLogger(__name__)

_MIME_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/tiff": ".tiff",
    "image/bmp": ".bmp",
}
_SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}


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


async def _wake_krita() -> str | None:
    client = build_krita_supervisor_client()
    if client is None:
        return None
    try:
        await client.ensure_krita()
    except SupervisorClientError as error:
        logger.warning("Could not wake Krita for public archive watermark: %s", error)
        return str(error)
    return None


def _source_suffix(file_name: str, mime_type: str | None) -> str | None:
    suffix = Path(file_name).suffix.casefold()
    if suffix in _SUPPORTED_SUFFIXES:
        return suffix
    return _MIME_SUFFIXES.get((mime_type or "").strip().casefold())


async def handle_manager_fast_watermark(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    access_policy: AccessPolicy,
) -> None:
    if not has_public_manager_access(callback.from_user, access_policy):
        await callback.answer("Управление watermark для вас закрыто.", show_alert=True)
        return
    if not _watermark_enabled():
        await callback.answer(
            "Krita bridge выключен. Включите KRITA_WATERMARK_ENABLED=true.",
            show_alert=True,
        )
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Карточка архива больше недоступна.", show_alert=True)
        return

    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return
    if callback_data.media_id and page.media.id != callback_data.media_id:
        await callback.answer("Архив изменился. Откройте материал заново.", show_alert=True)
        return

    source = await PublicArchiveWatermarkRepository(database).get_source(page.media.id)
    if source is None:
        await callback.answer("Watermark доступен только для изображений.", show_alert=True)
        return
    suffix = _source_suffix(source.file_name, source.mime_type)
    if suffix is None:
        await callback.answer("Формат изображения не поддерживается Krita bridge.", show_alert=True)
        return

    service = _build_service(bot, database)
    source_path = service.bridge.paths.ensure_in(
        service.bridge.paths.sources
        / f"archive-media-{source.media_id}-{uuid4().hex}{suffix}",
        service.bridge.paths.sources,
    )
    try:
        await bot.download(source.telegram_file_id, destination=source_path)
        with Image.open(source_path) as image:
            image.verify()
    except (TelegramAPIError, OSError, UnidentifiedImageError, ValueError) as error:
        source_path.unlink(missing_ok=True)
        logger.info(
            "Public archive watermark source unavailable media=%s: %s",
            source.media_id,
            error,
        )
        await callback.answer(
            "Не удалось получить исходник через Bot API. Для файлов сверх лимита "
            "нужен локальный исходник.",
            show_alert=True,
        )
        return

    wake_error = await _wake_krita()
    item = await service.create_job(
        owner_user_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
        source_message_id=-source.media_id,
        source_file_id=source.telegram_file_id,
        source_file_unique_id=None,
        source_path=str(source_path),
    )
    status = "поставлено в очередь"
    if wake_error:
        status += "; Krita нужно открыть вручную"
    control = await callback.message.answer(
        format_watermark_caption(item, status_text=status),
        reply_markup=build_watermark_keyboard(item),
    )
    await service.set_control_message(item.job.id, control.message_id)
    await callback.answer("Watermark поставлен в очередь.")


__all__ = ("handle_manager_fast_watermark",)
