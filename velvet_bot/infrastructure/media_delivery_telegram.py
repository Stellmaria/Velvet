from __future__ import annotations

import asyncio
import logging
import urllib.error
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile

from velvet_bot.application.media_delivery import (
    DownloadedMedia,
    MediaDeliveryItem,
    MediaDeliveryJob,
    MediaUrlExpired,
)
from velvet_bot.domains.media_generation.file_delivery_worker import (
    DEFAULT_RESULT_USER_AGENT,
    RESULT_DOWNLOAD_TIMEOUT_SECONDS,
    RESULT_MAX_BYTES,
    download_result_http,
    result_filename,
)
from velvet_bot.domains.media_generation.model_catalog import media_model_display_name
from velvet_bot.presentation.telegram.shared.retry import (
    TelegramRetryPolicy,
    retry_telegram_operation,
)

logger = logging.getLogger(__name__)


class TelegramMediaDeliveryTransport:
    def __init__(
        self,
        bot: Bot,
        *,
        retry_attempts: int = 5,
    ) -> None:
        self._bot = bot
        self._retry_attempts = max(1, int(retry_attempts))

    async def download(
        self,
        *,
        job: MediaDeliveryJob,
        item: MediaDeliveryItem,
    ) -> DownloadedMedia:
        try:
            downloaded = await asyncio.to_thread(
                download_result_http,
                item.result_url,
                timeout_seconds=RESULT_DOWNLOAD_TIMEOUT_SECONDS,
                max_bytes=RESULT_MAX_BYTES,
                user_agent=DEFAULT_RESULT_USER_AGENT,
            )
        except urllib.error.HTTPError as error:
            if error.code in {404, 410}:
                raise MediaUrlExpired(
                    f"URL результата {item.result_index} истёк (HTTP {error.code})."
                ) from error
            raise
        filename = result_filename(
            url=item.result_url,
            provider_task_id=job.provider_task_id,
            index=item.result_index,
            mime_type=downloaded.mime_type,
            video=job.media_kind == "video",
        )
        return DownloadedMedia(
            payload=downloaded.payload,
            file_name=filename,
            content_type=downloaded.mime_type,
        )

    async def send_original(
        self,
        *,
        job: MediaDeliveryJob,
        item: MediaDeliveryItem,
        media: DownloadedMedia,
    ) -> None:
        self._require_chat(job)
        await self._retry(
            "media original",
            lambda: self._bot.send_document(
                job.chat_id,
                document=BufferedInputFile(media.payload, filename=media.file_name),
                caption=self._original_caption(job, item),
                disable_content_type_detection=True,
            ),
        )

    async def send_preview(
        self,
        *,
        job: MediaDeliveryJob,
        item: MediaDeliveryItem,
        media: DownloadedMedia,
    ) -> None:
        self._require_chat(job)
        if job.media_kind == "video":
            await self._retry(
                "media video preview",
                lambda: self._bot.send_video(
                    job.chat_id,
                    video=BufferedInputFile(media.payload, filename=media.file_name),
                    caption=self._preview_caption(job, item),
                    supports_streaming=True,
                ),
            )
        else:
            await self._retry(
                "media image preview",
                lambda: self._bot.send_photo(
                    job.chat_id,
                    photo=BufferedInputFile(media.payload, filename=media.file_name),
                    caption=self._preview_caption(job, item),
                ),
            )

    async def send_direct_preview(
        self,
        *,
        job: MediaDeliveryJob,
        item: MediaDeliveryItem,
    ) -> None:
        self._require_chat(job)
        caption = self._preview_caption(job, item) + (
            "\n\nОригинал пока не скачан ботом; предпросмотр отправлен напрямую "
            "по сохранённому URL провайдера."
        )
        if job.media_kind == "video":
            await self._retry(
                "direct video preview",
                lambda: self._bot.send_video(
                    job.chat_id,
                    video=item.result_url,
                    caption=caption,
                    supports_streaming=True,
                ),
            )
        else:
            await self._retry(
                "direct image preview",
                lambda: self._bot.send_photo(
                    job.chat_id,
                    photo=item.result_url,
                    caption=caption,
                ),
            )

    async def notify(self, *, job: MediaDeliveryJob, text: str) -> None:
        self._require_chat(job)
        await self._retry(
            "media delivery notification",
            lambda: self._bot.send_message(
                job.chat_id,
                "<b>Доставка результата</b>\n\n"
                f"{escape(text)}\n"
                f"Задача: <code>{job.task_id}</code>",
            ),
        )

    async def _retry(self, operation_name: str, operation):
        policy = TelegramRetryPolicy(
            attempts=self._retry_attempts,
            delays=tuple(
                float(min(30, 2 ** max(0, attempt - 1)))
                for attempt in range(1, self._retry_attempts)
            ),
        )

        def report_retry(next_attempt: int, error: TelegramAPIError) -> None:
            logger.warning(
                "Telegram media delivery retry operation=%s attempt=%s/%s: %s",
                operation_name,
                next_attempt,
                self._retry_attempts,
                error,
            )

        return await retry_telegram_operation(
            operation,
            policy=policy,
            on_retry=report_retry,
        )

    @staticmethod
    def _require_chat(job: MediaDeliveryJob) -> None:
        if job.chat_id is None:
            raise RuntimeError("Для доставки результата не сохранён chat_id.")

    @staticmethod
    def _model_name(job: MediaDeliveryJob) -> str:
        return media_model_display_name(
            str(job.request.get("model") or "").strip(),
            fallback="Генерация",
        )

    def _original_caption(self, job: MediaDeliveryJob, item: MediaDeliveryItem) -> str:
        return (
            f"<b>Ауф · {escape(self._model_name(job))}</b>\n"
            "Оригинальный файл без сжатия Telegram.\n"
            f"Результат: <b>{item.result_index}/{len(job.items)}</b>\n"
            f"Задача провайдера: <code>{escape(job.provider_task_id)}</code>"
        )

    def _preview_caption(self, job: MediaDeliveryJob, item: MediaDeliveryItem) -> str:
        return (
            f"Предпросмотр · <b>{escape(self._model_name(job))}</b>\n"
            f"Результат: <b>{item.result_index}/{len(job.items)}</b>"
        )




__all__ = ("TelegramMediaDeliveryTransport",)
