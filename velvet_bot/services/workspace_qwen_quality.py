from __future__ import annotations

import asyncio
import io
import logging
import time

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)

from velvet_bot.ai_quality import QualityVisionClient
from velvet_bot.ai_vision import VisionAnalysisError, VisionProviderUnavailable
from velvet_bot.calibrated_ai_quality import apply_calibration_to_report
from velvet_bot.domains.workspaces.qwen_repository import (
    WorkspaceQwenRepository,
    WorkspaceQwenTarget,
)


logger = logging.getLogger(__name__)


class WorkspaceQwenQualityService:
    """Processes one pending Qwen quality check across enabled personal workspaces."""

    def __init__(
        self,
        *,
        bot: Bot,
        repository: WorkspaceQwenRepository,
        client: QualityVisionClient,
        max_attempts: int = 3,
    ) -> None:
        self._bot = bot
        self._repository = repository
        self._client = client
        self._max_attempts = max(1, min(int(max_attempts), 10))
        self._last_health_check = 0.0
        self._healthy = False
        self._last_warning = 0.0

    async def _provider_available(self) -> bool:
        now = time.monotonic()
        if now - self._last_health_check < 30:
            return self._healthy
        self._last_health_check = now
        self._healthy = await self._client.health()
        if not self._healthy and now - self._last_warning >= 300:
            self._last_warning = now
            logger.warning(
                "Workspace Qwen service is unavailable provider=%s base_url=%s model=%s",
                self._client.provider,
                self._client.base_url,
                self._client.model,
            )
        return self._healthy

    async def _download_file(self, file_id: str) -> bytes:
        errors: list[BaseException] = []
        for attempt in range(1, 4):
            try:
                destination = io.BytesIO()
                await self._bot.download(
                    file_id,
                    destination=destination,
                    timeout=90,
                    seek=True,
                )
                data = destination.getvalue()
                if data:
                    return data
                errors.append(RuntimeError("Telegram вернул пустой файл."))
            except asyncio.CancelledError:
                raise
            except TelegramBadRequest as error:
                errors.append(error)
                break
            except (TelegramNetworkError, TimeoutError, ConnectionError, OSError) as error:
                errors.append(error)
                if attempt < 3:
                    await asyncio.sleep((1.0, 3.0)[attempt - 1])
            except TelegramAPIError as error:
                errors.append(error)
                break
        raise RuntimeError(
            f"Не удалось скачать изображение для Qwen: {errors[-1] if errors else 'нет данных'}"
        )

    async def _download_target(self, target: WorkspaceQwenTarget) -> bytes:
        file_ids = tuple(
            dict.fromkeys(
                value
                for value in (target.preview_file_id, target.telegram_file_id)
                if value
            )
        )
        errors: list[BaseException] = []
        for file_id in file_ids:
            try:
                return await self._download_file(file_id)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # p2-approved-boundary: workspace-qwen-file-fallback
                errors.append(error)
        if errors:
            raise errors[-1]
        raise RuntimeError("У материала отсутствует Telegram file_id.")

    async def process_once(self) -> int:
        if not await self._provider_available():
            return 0
        target = await self._repository.claim_next(
            provider=self._client.provider,
            model=self._client.model,
            max_attempts=self._max_attempts,
        )
        if target is None:
            return 0
        try:
            source = await self._download_target(target)
            raw_report = await self._client.analyze(source)
            profile = await self._repository.calibration_profile(
                workspace_id=target.workspace_id,
                provider=self._client.provider,
                model=self._client.model,
            )
            report = apply_calibration_to_report(raw_report, profile)
            await self._repository.mark_ready(
                workspace_id=target.workspace_id,
                media_id=target.media_id,
                report=report,
            )
            logger.info(
                "Workspace Qwen report ready workspace_id=%s media_id=%s verdict=%s score=%s",
                target.workspace_id,
                target.media_id,
                report.get("verdict"),
                report.get("quality_score"),
            )
            return 1
        except asyncio.CancelledError:
            raise
        except VisionProviderUnavailable as error:
            self._healthy = False
            await self._repository.mark_error(
                workspace_id=target.workspace_id,
                media_id=target.media_id,
                error=error,
                max_attempts=self._max_attempts,
            )
            return 0
        except Exception as error:  # p2-approved-boundary: compensate-workspace-qwen-check
            permanent = isinstance(error, VisionAnalysisError) and (
                "прочитать как изображение" in str(error)
                or "file is too big" in str(error).casefold()
            )
            log = logger.info if permanent else logger.warning
            log(
                "Workspace Qwen analysis failed workspace_id=%s media_id=%s: %s",
                target.workspace_id,
                target.media_id,
                error,
            )
            await self._repository.mark_error(
                workspace_id=target.workspace_id,
                media_id=target.media_id,
                error=error,
                max_attempts=self._max_attempts,
                permanent=permanent,
            )
            return 0


__all__ = ("WorkspaceQwenQualityService",)
