from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile
from PIL import Image

from velvet_bot.domains.watermark.models import (
    WatermarkSettings,
    WatermarkWorkItem,
)
from velvet_bot.domains.watermark.repository import WatermarkRepository
from velvet_bot.infrastructure.krita_bridge import KritaBridge
from velvet_bot.watermark_ui import build_watermark_keyboard, format_watermark_caption

logger = logging.getLogger(__name__)


class WatermarkService:
    def __init__(
        self,
        *,
        bot: Bot,
        repository: WatermarkRepository,
        bridge: KritaBridge,
    ) -> None:
        self._bot = bot
        self._repository = repository
        self._bridge = bridge

    @property
    def bridge(self) -> KritaBridge:
        return self._bridge

    async def create_job(
        self,
        *,
        owner_user_id: int,
        chat_id: int,
        source_message_id: int,
        source_file_id: str,
        source_file_unique_id: str | None,
        source_path: str,
    ) -> WatermarkWorkItem:
        return await self._repository.create_job(
            owner_user_id=owner_user_id,
            chat_id=chat_id,
            source_message_id=source_message_id,
            source_file_id=source_file_id,
            source_file_unique_id=source_file_unique_id,
            source_path=source_path,
            settings=WatermarkSettings(),
        )

    async def get_current(self, job_id: int, *, owner_user_id: int) -> WatermarkWorkItem:
        item = await self._repository.get_current(job_id)
        if item is None:
            raise ValueError("Задание водяного знака не найдено.")
        if item.job.owner_user_id != owner_user_id:
            raise ValueError("Это задание принадлежит другому владельцу.")
        return item

    async def set_control_message(self, job_id: int, message_id: int) -> None:
        await self._repository.set_control_message(job_id, message_id)

    async def revise(
        self,
        job_id: int,
        *,
        owner_user_id: int,
        position: str | None = None,
        color: str | None = None,
        opacity_delta: int = 0,
        size_delta: float = 0.0,
        margin_delta: float = 0.0,
        enabled: bool | None = None,
    ) -> WatermarkWorkItem:
        current = await self.get_current(job_id, owner_user_id=owner_user_id)
        settings = current.revision.settings
        next_settings = replace(
            settings,
            position=position if position is not None else settings.position,
            color=color if color is not None else settings.color,
            opacity=settings.opacity + opacity_delta,
            size=settings.size + size_delta,
            margin=settings.margin + margin_delta,
            enabled=enabled if enabled is not None else settings.enabled,
        ).normalized()
        return await self._repository.create_revision(job_id, settings=next_settings)

    async def undo(self, job_id: int, *, owner_user_id: int) -> WatermarkWorkItem:
        await self.get_current(job_id, owner_user_id=owner_user_id)
        return await self._repository.undo(job_id)

    async def approve(self, job_id: int, *, owner_user_id: int) -> WatermarkWorkItem:
        await self.get_current(job_id, owner_user_id=owner_user_id)
        return await self._repository.approve(job_id)

    async def cancel(self, job_id: int, *, owner_user_id: int) -> None:
        await self.get_current(job_id, owner_user_id=owner_user_id)
        await self._repository.cancel(job_id)

    async def process_once(self) -> int:
        processed = 0
        for item in await self._repository.list_processing(limit=20):
            if not item.revision.response_path:
                request_path, output_path, response_path = self._bridge.dispatch(item)
                await self._repository.set_dispatched_paths(
                    job_id=item.job.id,
                    revision=item.revision.revision,
                    request_path=str(request_path),
                    output_path=str(output_path),
                    response_path=str(response_path),
                )
                processed += 1
                continue
            if await self._complete_if_ready(item):
                processed += 1

        pending = await self._repository.claim_pending()
        if pending is not None:
            request_path, output_path, response_path = self._bridge.dispatch(pending)
            await self._repository.set_dispatched_paths(
                job_id=pending.job.id,
                revision=pending.revision.revision,
                request_path=str(request_path),
                output_path=str(output_path),
                response_path=str(response_path),
            )
            processed += 1
        return processed

    async def _complete_if_ready(self, item: WatermarkWorkItem) -> bool:
        response_path = item.revision.response_path
        if not response_path:
            return False
        payload = self._bridge.read_response(response_path)
        if payload is None:
            return False

        if int(payload.get("job_id", item.job.id)) != item.job.id or int(
            payload.get("revision", item.revision.revision)
        ) != item.revision.revision:
            await self._repository.mark_error(
                job_id=item.job.id,
                revision=item.revision.revision,
                error="Ответ Krita не совпадает с job/revision.",
            )
            return True

        if payload.get("status") != "ok":
            error = str(payload.get("error") or "Krita bridge вернул ошибку.")
            await self._repository.mark_error(
                job_id=item.job.id,
                revision=item.revision.revision,
                error=error,
            )
            if item.job.current_revision == item.revision.revision:
                await self._safe_send_message(
                    item.job.chat_id,
                    f"❌ Водяной знак: {error[:1500]}",
                )
            return True

        output_path = Path(str(payload.get("output_path") or item.revision.output_path or ""))
        if not output_path.exists():
            await self._repository.mark_error(
                job_id=item.job.id,
                revision=item.revision.revision,
                error="Krita сообщила успех, но итоговый файл не найден.",
            )
            return True

        current = await self._repository.get_current(item.job.id)
        if current is None:
            return True
        if current.revision.revision != item.revision.revision:
            await self._repository.mark_ready(
                job_id=item.job.id,
                revision=item.revision.revision,
                telegram_preview_file_id=None,
            )
            return True

        preview_path = self._build_telegram_preview(output_path, item)
        message = await self._bot.send_photo(
            chat_id=item.job.chat_id,
            photo=FSInputFile(preview_path),
            caption=format_watermark_caption(current, status_text="preview готов"),
            reply_markup=build_watermark_keyboard(current),
        )
        preview_file_id = message.photo[-1].file_id if message.photo else None
        still_current = await self._repository.mark_ready(
            job_id=item.job.id,
            revision=item.revision.revision,
            telegram_preview_file_id=preview_file_id,
        )
        if not still_current:
            try:
                await message.delete()
            except TelegramAPIError:
                pass
            return True

        previous_message_id = await self._repository.set_preview_message(
            item.job.id,
            message.message_id,
        )
        if previous_message_id and previous_message_id != message.message_id:
            try:
                await self._bot.delete_message(item.job.chat_id, previous_message_id)
            except TelegramAPIError:
                pass
        return True

    def _build_telegram_preview(self, output_path: Path, item: WatermarkWorkItem) -> Path:
        preview_path = self._bridge.paths.previews / (
            f"job-{item.job.id}-r{item.revision.revision}.jpg"
        )
        with Image.open(output_path) as image:
            image = image.convert("RGB")
            image.thumbnail((1600, 1600))
            image.save(preview_path, format="JPEG", quality=88, optimize=True)
        return preview_path

    async def _safe_send_message(self, chat_id: int, text: str) -> None:
        try:
            await self._bot.send_message(chat_id, text)
        except TelegramAPIError:
            logger.exception("Could not send watermark bridge error to chat=%s", chat_id)


__all__ = ("WatermarkService",)
