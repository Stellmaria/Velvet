from __future__ import annotations

import json
import logging
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile
from PIL import Image

from velvet_bot.domains.watermark.models import (
    WatermarkSettings,
    WatermarkWorkItem,
)
from velvet_bot.domains.watermark.repository import CancelResult, WatermarkRepository
from velvet_bot.infrastructure.krita_bridge import KritaBridge
from velvet_bot.watermark_ui import build_watermark_keyboard, format_watermark_caption

logger = logging.getLogger(__name__)


def _processing_stale_seconds() -> int:
    raw = os.getenv("KRITA_PROCESSING_STALE_SECONDS", "600").strip()
    try:
        return max(30, int(raw))
    except ValueError:
        logger.warning("Invalid KRITA_PROCESSING_STALE_SECONDS=%r; using 600", raw)
        return 600


class WatermarkService:
    def __init__(
        self,
        *,
        bot: Bot,
        repository: WatermarkRepository,
        bridge: KritaBridge,
        processing_stale_seconds: int | None = None,
    ) -> None:
        self._bot = bot
        self._repository = repository
        self._bridge = bridge
        self._processing_stale_seconds = (
            max(30, processing_stale_seconds)
            if processing_stale_seconds is not None
            else _processing_stale_seconds()
        )

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
        workspace_id: int = 1,
        logo_kind: str = "builtin",
        logo_path: str | None = None,
        logo_width: float | None = None,
        logo_height: float | None = None,
        logo_name: str | None = None,
    ) -> WatermarkWorkItem:
        return await self._repository.create_job(
            owner_user_id=owner_user_id,
            chat_id=chat_id,
            source_message_id=source_message_id,
            source_file_id=source_file_id,
            source_file_unique_id=source_file_unique_id,
            source_path=source_path,
            settings=WatermarkSettings(),
            workspace_id=workspace_id,
            logo_kind=logo_kind,
            logo_path=logo_path,
            logo_width=logo_width,
            logo_height=logo_height,
            logo_name=logo_name,
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
        current = await self.get_current(job_id, owner_user_id=owner_user_id)
        candidate = self._bridge.validate_response_output(
            current.revision.output_path or "",
            expected_path=current.revision.output_path,
        )
        if not candidate.is_file():
            raise ValueError("Финальный файл не найден в разрешённом каталоге bridge.")
        item = await self._repository.approve(job_id)
        approved = self._bridge.validate_response_output(
            item.job.final_path or "",
            expected_path=item.revision.output_path,
        )
        if approved != candidate:
            raise ValueError("Подтверждённый output изменился; обновите карточку.")
        return item

    async def cancel(self, job_id: int, *, owner_user_id: int) -> CancelResult:
        await self.get_current(job_id, owner_user_id=owner_user_id)
        return await self._repository.cancel(job_id)

    async def process_once(self) -> int:
        processed = 0
        for item in await self._repository.list_processing(limit=20):
            if not item.revision.response_path or not item.revision.request_path:
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

            recovery = self._bridge.recover_processing(
                request_path=item.revision.request_path,
                response_path=item.revision.response_path,
                stale_after_seconds=self._processing_stale_seconds,
            )
            if recovery == "requeued":
                logger.warning(
                    "Recovered stale Krita request job=%s revision=%s path=%s",
                    item.job.id,
                    item.revision.revision,
                    item.revision.request_path,
                )
                processed += 1
                continue
            if recovery == "retry_failed":
                logger.warning(
                    "Could not requeue stale Krita request job=%s revision=%s",
                    item.job.id,
                    item.revision.revision,
                )
                continue
            if recovery == "missing" and self._is_revision_stale(item):
                await self._mark_recovery_error(
                    item,
                    "Krita request исчез: нет request, processing и response файлов.",
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
        try:
            payload = self._bridge.read_response(response_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            await self._mark_recovery_error(item, f"Некорректный response Krita: {error}")
            return True
        if payload is None:
            return False

        try:
            response_job_id = int(payload.get("job_id", item.job.id))
            response_revision = int(payload.get("revision", item.revision.revision))
        except (TypeError, ValueError):
            response_job_id = -1
            response_revision = -1
        if response_job_id != item.job.id or response_revision != item.revision.revision:
            await self._mark_recovery_error(item, "Ответ Krita не совпадает с job/revision.")
            return True

        if payload.get("status") != "ok":
            error = str(payload.get("error") or "Krita bridge вернул ошибку.")
            await self._mark_recovery_error(item, error)
            return True

        try:
            output_path = self._bridge.validate_response_output(
                str(payload.get("output_path") or ""),
                expected_path=item.revision.output_path,
            )
        except ValueError as error:
            await self._mark_recovery_error(item, f"Небезопасный output_path: {error}")
            return True
        if not output_path.is_file():
            await self._mark_recovery_error(
                item,
                "Krita сообщила успех, но итоговый файл не найден.",
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

    async def _mark_recovery_error(self, item: WatermarkWorkItem, error: str) -> None:
        logger.error(
            "Krita watermark job failed job=%s revision=%s: %s",
            item.job.id,
            item.revision.revision,
            error,
        )
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

    def _is_revision_stale(self, item: WatermarkWorkItem) -> bool:
        created_at = item.revision.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return (datetime.now(UTC) - created_at).total_seconds() >= self._processing_stale_seconds

    def _build_telegram_preview(self, output_path: Path, item: WatermarkWorkItem) -> Path:
        preview_path = self._bridge.paths.ensure_in(
            self._bridge.paths.previews
            / f"job-{item.job.id}-r{item.revision.revision}.jpg",
            self._bridge.paths.previews,
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
