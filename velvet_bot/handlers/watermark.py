from __future__ import annotations

import os
import re
from html import escape
from pathlib import Path
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, FSInputFile, Message

from velvet_bot.database import Database
from velvet_bot.domains.watermark.models import WatermarkWorkItem
from velvet_bot.domains.watermark.repository import WatermarkRepository
from velvet_bot.domains.watermark.service import WatermarkService
from velvet_bot.infrastructure.krita_bridge import KritaBridge, default_krita_bridge_dir
from velvet_bot.watermark_ui import (
    WatermarkCallback,
    build_watermark_keyboard,
    build_watermark_start_keyboard,
    format_watermark_caption,
)

router = Router(name=__name__)
_INPUT_MARKER = "#watermark-input"
_COLOR_MARKER = re.compile(r"#watermark-color:(\d+)")


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


class WatermarkInputReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        reply = message.reply_to_message
        return bool(reply and _INPUT_MARKER in (reply.text or reply.caption or ""))


class WatermarkColorReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> dict | bool:
        reply = message.reply_to_message
        match = _COLOR_MARKER.search((reply.text or reply.caption or "") if reply else "")
        if match is None:
            return False
        return {"watermark_job_id": int(match.group(1))}


def _source_file(message: Message):
    if message.photo:
        photo = message.photo[-1]
        return photo.file_id, photo.file_unique_id, ".jpg"
    document = message.document
    if document is None or not (document.mime_type or "").startswith("image/"):
        return None
    suffix = Path(document.file_name or "image.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
        suffix = ".png"
    return document.file_id, document.file_unique_id, suffix


async def _create_job_from_message(
    *,
    message: Message,
    source_message: Message,
    bot: Bot,
    watermark_service: WatermarkService,
) -> WatermarkWorkItem | None:
    source = _source_file(source_message)
    if source is None:
        await message.answer("Нужно изображение, отправленное как фото или image-документ.")
        return None
    file_id, file_unique_id, suffix = source
    source_path = watermark_service.bridge.paths.sources / (
        f"tg-{message.chat.id}-{source_message.message_id}-{uuid4().hex}{suffix}"
    )
    source_path = watermark_service.bridge.paths.ensure_in(
        source_path,
        watermark_service.bridge.paths.sources,
    )
    await bot.download(file_id, destination=source_path)
    item = await watermark_service.create_job(
        owner_user_id=message.from_user.id,
        chat_id=message.chat.id,
        source_message_id=source_message.message_id,
        source_file_id=file_id,
        source_file_unique_id=file_unique_id,
        source_path=str(source_path),
    )
    control = await message.answer(
        format_watermark_caption(item, status_text="поставлено в очередь"),
        reply_markup=build_watermark_keyboard(item),
    )
    await watermark_service.set_control_message(item.job.id, control.message_id)
    return item


async def _safe_edit(
    callback: CallbackQuery,
    text: str,
    item: WatermarkWorkItem | None = None,
) -> None:
    if not isinstance(callback.message, Message):
        return
    keyboard = build_watermark_keyboard(item) if item is not None else None
    try:
        if callback.message.photo or callback.message.document:
            await callback.message.edit_caption(caption=text, reply_markup=keyboard)
        else:
            await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


@router.message(Command("watermark"))
async def handle_watermark_command(
    message: Message,
    bot: Bot,
    database: Database,
) -> None:
    if not _watermark_enabled():
        await message.answer("Krita bridge выключен. Включите KRITA_WATERMARK_ENABLED=true.")
        return
    source = message.reply_to_message
    if source is None:
        await message.answer(
            "Ответьте командой <code>/watermark</code> на изображение. "
            "Команда является аварийным резервом; обычный вход доступен из меню."
        )
        return
    await _create_job_from_message(
        message=message,
        source_message=source,
        bot=bot,
        watermark_service=_build_service(bot, database),
    )


@router.message(WatermarkInputReplyFilter(), F.photo | F.document)
async def handle_watermark_form_image(
    message: Message,
    bot: Bot,
    database: Database,
) -> None:
    if not _watermark_enabled():
        await message.answer("Krita bridge выключен.")
        return
    await _create_job_from_message(
        message=message,
        source_message=message,
        bot=bot,
        watermark_service=_build_service(bot, database),
    )


@router.message(WatermarkColorReplyFilter(), F.text)
async def handle_watermark_custom_color(
    message: Message,
    watermark_job_id: int,
    bot: Bot,
    database: Database,
) -> None:
    if not _watermark_enabled():
        await message.answer("Krita bridge выключен.")
        return
    service = _build_service(bot, database)
    color = (message.text or "").strip()
    try:
        item = await service.revise(
            watermark_job_id,
            owner_user_id=message.from_user.id,
            color=color,
            enabled=True,
        )
    except ValueError as error:
        await message.answer(f"❌ {escape(str(error))}")
        return
    await message.answer(
        format_watermark_caption(item, status_text="новый цвет поставлен в очередь"),
        reply_markup=build_watermark_keyboard(item),
    )


@router.callback_query(WatermarkCallback.filter())
async def handle_watermark_callback(
    callback: CallbackQuery,
    callback_data: WatermarkCallback,
    bot: Bot,
    database: Database,
) -> None:
    action = callback_data.action
    if action != "menu" and not _watermark_enabled():
        await callback.answer("Krita bridge выключен.", show_alert=True)
        return
    if action in {"start", "help"}:
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "<b>Водяной знак Velvet Anatomy</b>\n\n"
                "Ответьте изображением на это сообщение. Бот сохранит неизменяемый "
                "исходник, а Krita будет строить отдельные preview.\n\n"
                f"<code>{_INPUT_MARKER}</code>",
                reply_markup=build_watermark_start_keyboard(),
            )
        return
    if action == "menu":
        await callback.answer()
        if isinstance(callback.message, Message):
            from velvet_bot.handlers.owner_menu import show_owner_menu

            await show_owner_menu(callback.message)
        return

    await callback.answer("Принято, готовлю новую версию…")
    service = _build_service(bot, database)
    owner_user_id = callback.from_user.id
    job_id = callback_data.job_id

    if action == "custom_color":
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "Ответьте на это сообщение HEX-цветом, например "
                "<code>#D8C8B8</code>.\n\n"
                f"<code>#watermark-color:{job_id}</code>"
            )
        return

    try:
        if action == "position":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                position=callback_data.value,
                enabled=True,
            )
        elif action == "color":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                color=callback_data.value,
                enabled=True,
            )
        elif action == "opacity":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                opacity_delta=int(callback_data.value),
            )
        elif action == "size":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                size_delta=float(callback_data.value),
            )
        elif action == "margin":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                margin_delta=float(callback_data.value),
            )
        elif action == "undo":
            item = await service.undo(job_id, owner_user_id=owner_user_id)
        elif action == "remove":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                enabled=False,
            )
        elif action == "approve":
            item = await service.approve(job_id, owner_user_id=owner_user_id)
            final_path = item.job.final_path
            if not final_path:
                raise ValueError("Финальный путь задания не сохранён.")
            if isinstance(callback.message, Message):
                await callback.message.answer_document(
                    FSInputFile(final_path),
                    caption=f"✅ Финальный файл задания <b>{job_id}</b>.",
                )
            await _safe_edit(
                callback,
                format_watermark_caption(item, status_text="сохранено"),
                None,
            )
            return
        elif action == "cancel":
            result = await service.cancel(job_id, owner_user_id=owner_user_id)
            if result == "approved":
                text = f"Задание <b>{job_id}</b> уже подтверждено. Отмена проигнорирована."
            elif result == "already_cancelled":
                text = f"Задание <b>{job_id}</b> уже отменено."
            else:
                text = f"Задание <b>{job_id}</b> отменено."
            await _safe_edit(callback, text)
            return
        else:
            raise ValueError("Неизвестное действие водяного знака.")
    except (TypeError, ValueError) as error:
        if isinstance(callback.message, Message):
            await callback.message.answer(f"❌ {escape(str(error))}")
        return

    await _safe_edit(
        callback,
        format_watermark_caption(item, status_text="поставлено в очередь"),
        item,
    )


__all__ = ("router",)
