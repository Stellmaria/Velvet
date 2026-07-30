from __future__ import annotations

from velvet_bot.presentation.telegram.shared.retry import (
    TelegramRetryPolicy,
    retry_telegram_operation,
)

import asyncio
import io
import logging
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html import escape
from pathlib import Path

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)
from aiogram.types import BufferedInputFile

from .models import (
    MAX_KIE_REFERENCE_BYTES,
    KieGenerationRequest,
    KieReferenceImage,
    KieTaskRecord,
)
from .worker import KieGenerationWorker as BaseKieGenerationWorker

logger = logging.getLogger(__name__)

_RETRY_ATTEMPTS = 11
_RESULT_DOWNLOAD_TIMEOUT_SECONDS = 120
_REFERENCE_DOWNLOAD_TIMEOUT_SECONDS = 90
_RESULT_MAX_BYTES = 50 * 1024 * 1024
_DEFAULT_RESULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
}
_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
_MIME_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-m4v": ".m4v",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
}


@dataclass(frozen=True, slots=True)
class _DownloadedResult:
    payload: bytes
    mime_type: str | None


class KieGenerationWorker(BaseKieGenerationWorker):
    """Download Kie results, then send Telegram preview and original file."""

    @classmethod
    def install_delivery_handler(cls, handler) -> None:
        """Install a delivery implementation through an explicit class hook."""

        cls._deliver_best_effort = handler

    async def _download_reference(self, reference: KieReferenceImage) -> bytes:
        errors: list[BaseException] = []
        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                destination = io.BytesIO()
                await self._bot.download(
                    reference.telegram_file_id,
                    destination=destination,
                    timeout=_REFERENCE_DOWNLOAD_TIMEOUT_SECONDS,
                    seek=True,
                )
                value = destination.getvalue()
                if not value:
                    raise RuntimeError("Telegram вернул пустой файл референса.")
                if len(value) > MAX_KIE_REFERENCE_BYTES:
                    raise ValueError("Референс для Kie.ai должен быть не больше 10 МБ.")
                return value
            except asyncio.CancelledError:
                raise
            except TelegramBadRequest as error:
                errors.append(error)
                break
            except (
                TelegramNetworkError,
                TimeoutError,
                ConnectionError,
                OSError,
                TelegramAPIError,
            ) as error:
                errors.append(error)
                if attempt >= _RETRY_ATTEMPTS:
                    break
                await asyncio.sleep(_retry_delay(attempt))
            except (RuntimeError, ValueError) as error:
                errors.append(error)
                break
        if errors:
            raise RuntimeError(f"Не удалось скачать референс: {errors[-1]}") from errors[-1]
        raise RuntimeError("Telegram вернул пустой файл референса.")

    async def _deliver_best_effort(
        self,
        *,
        chat_id: int | None,
        request: KieGenerationRequest,
        record: KieTaskRecord,
    ) -> None:
        if chat_id is None:
            return
        media_name = "Видео" if request.model.is_video else "Изображение"
        caption = (
            f"<b>Мяу · {escape(request.model.display_name)}</b>\n"
            f"{media_name}: <b>готово</b>\n"
            f"Качество: <b>{escape(request.resolution)}</b>\n"
            f"Референсов: <b>{len(request.references)}</b>\n"
            f"Контент: <b>{escape(request.content_mode.display_name)}</b>\n"
            f"Задача Kie: <code>{escape(record.task_id)}</code>\n\n"
            "Результат скачан ботом напрямую с Kie. Ниже отправлены "
            "предпросмотр и оригинальный файл."
        )
        try:
            if not record.result_urls:
                await self._send_telegram_with_retry(
                    "empty result notice",
                    lambda: self._bot.send_message(
                        chat_id,
                        caption + "\n\nKie завершил задачу без URL результата.",
                    ),
                )
                return
            for index, url in enumerate(record.result_urls, start=1):
                item_caption = caption if index == 1 else None
                result = await self._download_result(url)
                filename = _result_filename(
                    url=url,
                    provider_task_id=record.task_id,
                    index=index,
                    mime_type=result.mime_type,
                    video=request.model.is_video,
                )
                if request.model.is_video:
                    await self._send_video_and_document(
                        chat_id=chat_id,
                        payload=result.payload,
                        filename=filename,
                        caption=item_caption,
                    )
                else:
                    await self._send_image_and_document(
                        chat_id=chat_id,
                        payload=result.payload,
                        filename=filename,
                        caption=item_caption,
                    )
        except TelegramAPIError:
            logger.exception(
                "Kie task %s succeeded but Telegram file delivery failed",
                record.task_id,
            )
        except (RuntimeError, ValueError, OSError):
            logger.exception(
                "Kie task %s succeeded but original result download failed",
                record.task_id,
            )

    async def _send_image_and_document(
        self,
        *,
        chat_id: int,
        payload: bytes,
        filename: str,
        caption: str | None,
    ) -> None:
        preview_sent = True
        try:
            await self._send_telegram_with_retry(
                "image preview",
                lambda: self._bot.send_photo(
                    chat_id,
                    photo=BufferedInputFile(payload, filename=filename),
                    caption=caption,
                ),
            )
        except TelegramBadRequest as error:
            preview_sent = False
            logger.warning(
                "Telegram rejected Kie image preview; sending original document: %s",
                error,
            )
        document_caption = "Оригинальный файл изображения."
        if not preview_sent and caption:
            document_caption = caption + "\n\n" + document_caption
        await self._send_telegram_with_retry(
            "image document",
            lambda: self._bot.send_document(
                chat_id,
                document=BufferedInputFile(payload, filename=filename),
                caption=document_caption,
            ),
        )

    async def _send_video_and_document(
        self,
        *,
        chat_id: int,
        payload: bytes,
        filename: str,
        caption: str | None,
    ) -> None:
        preview_sent = True
        try:
            await self._send_telegram_with_retry(
                "video preview",
                lambda: self._bot.send_video(
                    chat_id,
                    video=BufferedInputFile(payload, filename=filename),
                    caption=caption,
                    supports_streaming=True,
                ),
            )
        except TelegramBadRequest as error:
            preview_sent = False
            logger.warning(
                "Telegram rejected Kie video preview; sending original document: %s",
                error,
            )
        document_caption = "Оригинальный видеофайл."
        if not preview_sent and caption:
            document_caption = caption + "\n\n" + document_caption
        await self._send_telegram_with_retry(
            "video document",
            lambda: self._bot.send_document(
                chat_id,
                document=BufferedInputFile(payload, filename=filename),
                caption=document_caption,
            ),
        )

    async def _send_telegram_with_retry(
        self,
        operation_name: str,
        operation: Callable[[], Awaitable[object]],
    ) -> object:
        policy = TelegramRetryPolicy(
            attempts=_RETRY_ATTEMPTS,
            delays=tuple(_retry_delay(attempt) for attempt in range(1, _RETRY_ATTEMPTS)),
        )

        def report_retry(next_attempt: int, error: TelegramAPIError) -> None:
            logger.warning(
                "Telegram Kie delivery retry operation=%s attempt=%s/%s: %s",
                operation_name,
                next_attempt,
                _RETRY_ATTEMPTS,
                error,
            )

        return await retry_telegram_operation(
            operation,
            policy=policy,
            on_retry=report_retry,
        )

    async def _download_result(self, url: str) -> _DownloadedResult:
        user_agent = str(
            getattr(self._client, "user_agent", _DEFAULT_RESULT_USER_AGENT)
            or _DEFAULT_RESULT_USER_AGENT
        ).strip()
        errors: list[BaseException] = []
        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                return await asyncio.to_thread(
                    _download_result_http,
                    url,
                    timeout_seconds=_RESULT_DOWNLOAD_TIMEOUT_SECONDS,
                    max_bytes=_RESULT_MAX_BYTES,
                    user_agent=user_agent,
                )
            except asyncio.CancelledError:
                raise
            except urllib.error.HTTPError as error:
                errors.append(error)
                retryable = error.code == 429 or error.code >= 500
                if not retryable or attempt >= _RETRY_ATTEMPTS:
                    break
                await asyncio.sleep(_retry_delay(attempt))
            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                OSError,
            ) as error:
                errors.append(error)
                if attempt >= _RETRY_ATTEMPTS:
                    break
                await asyncio.sleep(_retry_delay(attempt))
            except (RuntimeError, ValueError) as error:
                errors.append(error)
                break
        if errors:
            raise RuntimeError(
                f"Не удалось скачать оригинальный результат Kie: {errors[-1]}"
            ) from errors[-1]
        raise RuntimeError("Kie вернул пустой оригинальный файл.")


def _retry_delay(attempt: int) -> float:
    return float(min(30, 2 ** max(0, int(attempt) - 1)))


def _download_result_http(
    url: str,
    *,
    timeout_seconds: float,
    max_bytes: int,
    user_agent: str,
) -> _DownloadedResult:
    normalized_url = url.strip()
    parsed = urllib.parse.urlparse(normalized_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Kie вернул некорректный URL результата.")
    request = urllib.request.Request(
        normalized_url,
        headers={
            "User-Agent": user_agent,
            "Accept": "video/*,image/*,application/octet-stream;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        content_length = _optional_int(response.headers.get("Content-Length"))
        if content_length is not None and content_length > max_bytes:
            raise ValueError("Оригинальный результат Kie превышает 50 МБ.")
        payload = bytearray()
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > max_bytes:
                raise ValueError("Оригинальный результат Kie превышает 50 МБ.")
        if not payload:
            raise RuntimeError("Kie вернул пустой оригинальный файл.")
        mime_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0]
        return _DownloadedResult(
            payload=bytes(payload),
            mime_type=mime_type.strip().casefold() or None,
        )


def _result_filename(
    *,
    url: str,
    provider_task_id: str,
    index: int,
    mime_type: str | None,
    video: bool,
) -> str:
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    suffix = Path(path).suffix.casefold()
    allowed_suffixes = _VIDEO_SUFFIXES if video else _IMAGE_SUFFIXES
    if suffix not in allowed_suffixes:
        fallback = ".mp4" if video else ".png"
        suffix = _MIME_SUFFIXES.get((mime_type or "").casefold(), fallback)
    safe_task_id = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in provider_task_id
    ).strip("-")
    if not safe_task_id:
        safe_task_id = "result"
    return f"meow-{safe_task_id}-{max(1, int(index))}{suffix}"


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


__all__ = ("KieGenerationWorker",)


DEFAULT_RESULT_USER_AGENT = _DEFAULT_RESULT_USER_AGENT
RESULT_DOWNLOAD_TIMEOUT_SECONDS = _RESULT_DOWNLOAD_TIMEOUT_SECONDS
RESULT_MAX_BYTES = _RESULT_MAX_BYTES
download_result_http = _download_result_http
result_filename = _result_filename
