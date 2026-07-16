from __future__ import annotations

import asyncio
import io
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from velvet_bot.domains.media_quality.models import MediaQualityRunResult, MediaScanTarget
from velvet_bot.domains.media_quality.repository import MediaQualityRepository
from velvet_bot.visual_fingerprint import build_visual_fingerprint, compare_fingerprints

logger = logging.getLogger(__name__)


class MediaQualityService:
    """Coordinate Telegram I/O, fingerprinting and repository operations."""

    def __init__(self, *, bot: Bot, repository: MediaQualityRepository) -> None:
        self._bot = bot
        self._repository = repository

    async def process_once(self) -> MediaQualityRunResult:
        targets = await self._repository.claim_pending_images()
        for target in targets:
            await self.scan_target(target)

        file_checks = await self._repository.claim_file_checks()
        for target in file_checks:
            await self.verify_file(
                media_id=target.media_id,
                telegram_file_id=target.telegram_file_id,
            )

        return MediaQualityRunResult(
            fingerprint_targets=len(targets),
            file_checks=len(file_checks),
        )

    async def scan_target(self, target: MediaScanTarget) -> None:
        try:
            destination = io.BytesIO()
            await self._bot.download(
                target.telegram_file_id,
                destination=destination,
                seek=True,
            )
            fingerprint = await asyncio.to_thread(
                build_visual_fingerprint,
                destination.getvalue(),
            )
            comparisons = []
            stored_fingerprints = await self._repository.load_other_fingerprints(
                target.media_id
            )
            for stored in stored_fingerprints:
                comparison = compare_fingerprints(fingerprint, stored.fingerprint)
                if comparison.is_candidate:
                    comparisons.append((stored.media_id, comparison))

            await self._repository.store_fingerprint_and_candidates(
                target.media_id,
                fingerprint,
                comparisons,
            )
            logger.info(
                "Visual fingerprint ready media_id=%s candidates=%s",
                target.media_id,
                len(comparisons),
            )
        except TelegramBadRequest as error:
            if "file is too big" in str(error).casefold():
                logger.info(
                    "Visual fingerprint skipped media_id=%s: file exceeds Bot API limit",
                    target.media_id,
                )
                await self._repository.mark_scan_error(
                    media_id=target.media_id,
                    error=RuntimeError(
                        "Пропущено: файл превышает лимит скачивания Telegram Bot API, "
                        "а сохранённое превью отсутствует."
                    ),
                    broken_file=False,
                )
                return
            await self._handle_telegram_scan_error(target, error)
        except TelegramAPIError as error:
            await self._handle_telegram_scan_error(target, error)
        except Exception as error:
            logger.exception("Visual fingerprint failed media_id=%s", target.media_id)
            await self._repository.mark_scan_error(
                media_id=target.media_id,
                error=error,
                broken_file=False,
            )

    async def _handle_telegram_scan_error(
        self,
        target: MediaScanTarget,
        error: TelegramAPIError,
    ) -> None:
        logger.warning(
            "Visual fingerprint Telegram error media_id=%s: %s",
            target.media_id,
            error,
        )
        await self._repository.mark_scan_error(
            media_id=target.media_id,
            error=error,
            broken_file=True,
        )

    async def verify_file(self, *, media_id: int, telegram_file_id: str) -> None:
        status = "ok"
        error_text: str | None = None
        try:
            await self._bot.get_file(telegram_file_id)
        except TelegramAPIError as error:
            status = "broken"
            error_text = str(error)[:2000]

        await self._repository.record_file_check(
            media_id=media_id,
            status=status,
            error_text=error_text,
        )


__all__ = ("MediaQualityService",)
