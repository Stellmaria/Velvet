from __future__ import annotations

import asyncio
import io
import logging

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)

from velvet_bot.ai_vision import (
    MediaAIVisionService,
    VisionAnalysisError,
    VisionAnalysisTarget,
)
from velvet_bot.database import Database
from velvet_bot.ollama_vision import ReliableMediaAIRepository

logger = logging.getLogger(__name__)

_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_RETRY_DELAYS_SECONDS = (1.0, 3.0)
_RESPONSE_VERSION = 3


class ResilientMediaAIRepository(ReliableMediaAIRepository):
    """Requeue old transient Telegram failures once after retry support is deployed."""

    def __init__(self, database: Database) -> None:
        super().__init__(database)

    async def claim_targets(
        self,
        *,
        provider: str,
        model: str,
        max_attempts: int,
        limit: int = 1,
    ) -> tuple[VisionAnalysisTarget, ...]:
        async with self._database._require_pool().acquire() as connection:
            await connection.execute(
                """
                UPDATE media_ai_profiles
                SET status = 'pending',
                    attempt_count = 0,
                    error_message = NULL,
                    analyzed_at = NULL,
                    updated_at = NOW()
                WHERE analysis_version < $1::SMALLINT
                  AND status IN ('error', 'skipped')
                  AND (
                        error_message LIKE '%HTTP Client says%'
                        OR error_message LIKE '%ServerDisconnectedError%'
                        OR error_message LIKE '%TelegramNetworkError%'
                      )
                """,
                _RESPONSE_VERSION,
            )

        targets = await super().claim_targets(
            provider=provider,
            model=model,
            max_attempts=max_attempts,
            limit=limit,
        )
        if targets:
            async with self._database._require_pool().acquire() as connection:
                await connection.execute(
                    """
                    UPDATE media_ai_profiles
                    SET analysis_version = $2::SMALLINT,
                        updated_at = NOW()
                    WHERE media_id = ANY($1::BIGINT[])
                    """,
                    [target.media_id for target in targets],
                    _RESPONSE_VERSION,
                )
        return targets


class ResilientMediaAIVisionService(MediaAIVisionService):
    """Retry transient Telegram downloads before spending a profile attempt."""

    async def _download_target(self, target: VisionAnalysisTarget) -> bytes:
        errors: list[BaseException] = []
        file_ids = [target.telegram_file_id]
        if target.preview_file_id and target.preview_file_id not in file_ids:
            file_ids.append(target.preview_file_id)

        for file_id in file_ids:
            for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
                try:
                    destination = io.BytesIO()
                    await self._bot.download(
                        file_id,
                        destination=destination,
                        timeout=_DOWNLOAD_TIMEOUT_SECONDS,
                        seek=True,
                    )
                    value = destination.getvalue()
                    if value:
                        return value
                    errors.append(VisionAnalysisError("Telegram вернул пустое изображение."))
                    break
                except asyncio.CancelledError:
                    raise
                except TelegramBadRequest as error:
                    errors.append(error)
                    break
                except (TelegramNetworkError, TimeoutError, ConnectionError, OSError) as error:
                    errors.append(error)
                    if attempt >= _DOWNLOAD_ATTEMPTS:
                        break
                    delay = _RETRY_DELAYS_SECONDS[attempt - 1]
                    logger.warning(
                        "Transient Telegram download failure media_id=%s attempt=%s/%s; "
                        "retrying in %.1fs: %s",
                        target.media_id,
                        attempt,
                        _DOWNLOAD_ATTEMPTS,
                        delay,
                        error,
                    )
                    await asyncio.sleep(delay)
                except TelegramAPIError as error:
                    errors.append(error)
                    break

        if errors:
            raise VisionAnalysisError(
                "Не удалось скачать изображение из Telegram после повторов: "
                + str(errors[-1])
            )
        raise VisionAnalysisError("Telegram вернул пустое изображение.")


__all__ = (
    "ResilientMediaAIRepository",
    "ResilientMediaAIVisionService",
)
