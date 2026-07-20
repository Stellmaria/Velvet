from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import Awaitable, Callable

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)
from aiogram.types import Message, PhotoSize
from asyncpg.exceptions import PostgresError

from velvet_bot.ai_vision import (
    MediaAIVisionService,
    VisionAnalysisError,
    VisionAnalysisTarget,
)
from velvet_bot.database import Database
from velvet_bot.infrastructure.telegram.archive_previews import message_thumbnail
from velvet_bot.ollama_vision import ReliableMediaAIRepository

logger = logging.getLogger(__name__)

_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_RETRY_DELAYS_SECONDS = (1.0, 3.0)
_RESPONSE_VERSION = 4


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
        async with self._database.acquire() as connection:
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
                        OR LOWER(error_message) LIKE '%file is too big%'
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
            async with self._database.acquire() as connection:
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

    async def save_preview_file_id(self, media_id: int, preview_file_id: str) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE media_files
                SET preview_file_id = $2::TEXT
                WHERE id = $1::BIGINT
                  AND preview_file_id IS DISTINCT FROM $2::TEXT
                """,
                int(media_id),
                str(preview_file_id),
            )


class ResilientMediaAIVisionService(MediaAIVisionService):
    """Retry Telegram downloads and recover previews for oversized documents."""

    _cache_chat_id: int | None = None

    def set_cache_chat_id(self, chat_id: int | None) -> None:
        self._cache_chat_id = int(chat_id) if chat_id is not None else None

    async def _download_file_id(self, *, media_id: int, file_id: str) -> bytes:
        errors: list[BaseException] = []
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
                raise VisionAnalysisError("Telegram вернул пустое изображение.")
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
                    media_id,
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
            raise errors[-1]
        raise VisionAnalysisError("Telegram вернул пустое изображение.")

    async def _recover_document_thumbnail(
        self,
        target: VisionAnalysisTarget,
    ) -> PhotoSize | None:
        if self._cache_chat_id is None:
            logger.info(
                "Oversized Telegram document has no cache chat media_key=m%s",
                target.media_id,
            )
            return None

        temporary: Message | None = None
        try:
            temporary = await self._bot.send_document(
                chat_id=self._cache_chat_id,
                document=target.telegram_file_id,
                disable_notification=True,
            )
            thumbnail = message_thumbnail(temporary)
            if thumbnail is None:
                logger.info(
                    "Telegram did not generate a thumbnail for oversized media_key=m%s",
                    target.media_id,
                )
            return thumbnail
        except asyncio.CancelledError:
            raise
        except TelegramAPIError as error:
            logger.info(
                "Could not recover thumbnail for oversized media_key=m%s: %s",
                target.media_id,
                error,
            )
            return None
        finally:
            if temporary is not None:
                try:
                    await self._bot.delete_message(
                        chat_id=self._cache_chat_id,
                        message_id=temporary.message_id,
                    )
                except TelegramAPIError:
                    pass

    async def _persist_recovered_thumbnail(
        self,
        *,
        media_id: int,
        thumbnail: PhotoSize,
    ) -> None:
        saver = getattr(self._repository, "save_preview_file_id", None)
        if not callable(saver):
            return
        typed_saver: Callable[[int, str], Awaitable[None]] = saver
        try:
            await typed_saver(int(media_id), str(thumbnail.file_id))
        except PostgresError:
            logger.info(
                "Could not persist recovered AI thumbnail media_key=m%s",
                media_id,
                exc_info=True,
            )

    @staticmethod
    def _oversized_terminal_error(target: VisionAnalysisTarget) -> VisionAnalysisError:
        return VisionAnalysisError(
            "Крупное изображение недоступно для AI-анализа "
            f"media_key=m{target.media_id}: file is too big, а Telegram не предоставил "
            "доступную миниатюру. Повтор автоматически не требуется."
        )

    async def _download_target(self, target: VisionAnalysisTarget) -> bytes:
        errors: list[BaseException] = []
        file_ids = [target.telegram_file_id]
        if target.preview_file_id and target.preview_file_id not in file_ids:
            file_ids.append(target.preview_file_id)

        for file_id in file_ids:
            try:
                return await self._download_file_id(
                    media_id=target.media_id,
                    file_id=file_id,
                )
            except asyncio.CancelledError:
                raise
            except (
                TelegramAPIError,
                VisionAnalysisError,
                TimeoutError,
                ConnectionError,
                OSError,
            ) as error:
                errors.append(error)

        oversized = any("file is too big" in str(error).casefold() for error in errors)
        if oversized:
            thumbnail = await self._recover_document_thumbnail(target)
            if thumbnail is None:
                raise self._oversized_terminal_error(target)
            await self._persist_recovered_thumbnail(
                media_id=target.media_id,
                thumbnail=thumbnail,
            )
            try:
                return await self._download_file_id(
                    media_id=target.media_id,
                    file_id=thumbnail.file_id,
                )
            except asyncio.CancelledError:
                raise
            except (
                TelegramAPIError,
                VisionAnalysisError,
                TimeoutError,
                ConnectionError,
                OSError,
            ):
                raise self._oversized_terminal_error(target) from None

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
