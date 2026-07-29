from __future__ import annotations

import asyncio
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html import escape
from pathlib import Path

from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile

from .models import KieGenerationRequest, KieTaskRecord
from .worker import KieGenerationWorker as BaseKieGenerationWorker

logger = logging.getLogger(__name__)

_RESULT_DOWNLOAD_ATTEMPTS = 3
_RESULT_DOWNLOAD_TIMEOUT_SECONDS = 90
_RESULT_DOWNLOAD_RETRY_DELAYS = (1.0, 3.0)
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
_MIME_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}


@dataclass(frozen=True, slots=True)
class _DownloadedResult:
    payload: bytes
    mime_type: str | None


class KieGenerationWorker(BaseKieGenerationWorker):
    """Deliver image generations as original files instead of compressed photos."""

    async def _deliver_best_effort(
        self,
        *,
        chat_id: int | None,
        request: KieGenerationRequest,
        record: KieTaskRecord,
    ) -> None:
        if chat_id is None:
            return
        caption = (
            f"<b>Мяу · {escape(request.model.display_name)}</b>\n"
            f"Качество: <b>{escape(request.resolution)}</b>\n"
            f"Референсов: <b>{len(request.references)}</b>\n"
            f"Контент: <b>{escape(request.content_mode.display_name)}</b>\n"
            f"Задача Kie: <code>{escape(record.task_id)}</code>\n\n"
            "Оригинальный файл без сжатия Telegram."
        )
        try:
            if not record.result_urls:
                await self._bot.send_message(
                    chat_id,
                    caption + "\n\nKie завершил задачу без URL результата.",
                )
                return
            for index, url in enumerate(record.result_urls, start=1):
                item_caption = caption if index == 1 else None
                if request.model.is_video:
                    await self._bot.send_video(
                        chat_id,
                        video=url,
                        caption=item_caption,
                    )
                    continue
                result = await self._download_result(url)
                filename = _result_filename(
                    url=url,
                    provider_task_id=record.task_id,
                    index=index,
                    mime_type=result.mime_type,
                )
                await self._bot.send_document(
                    chat_id,
                    document=BufferedInputFile(
                        result.payload,
                        filename=filename,
                    ),
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

    async def _download_result(self, url: str) -> _DownloadedResult:
        user_agent = str(
            getattr(self._client, "user_agent", _DEFAULT_RESULT_USER_AGENT)
            or _DEFAULT_RESULT_USER_AGENT
        ).strip()
        errors: list[BaseException] = []
        for attempt in range(1, _RESULT_DOWNLOAD_ATTEMPTS + 1):
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
                if not retryable or attempt >= _RESULT_DOWNLOAD_ATTEMPTS:
                    break
                await asyncio.sleep(_RESULT_DOWNLOAD_RETRY_DELAYS[attempt - 1])
            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                OSError,
            ) as error:
                errors.append(error)
                if attempt >= _RESULT_DOWNLOAD_ATTEMPTS:
                    break
                await asyncio.sleep(_RESULT_DOWNLOAD_RETRY_DELAYS[attempt - 1])
            except (RuntimeError, ValueError) as error:
                errors.append(error)
                break
        if errors:
            raise RuntimeError(
                f"Не удалось скачать оригинальный результат Kie: {errors[-1]}"
            ) from errors[-1]
        raise RuntimeError("Kie вернул пустой оригинальный файл.")


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
            "Accept": "image/*,application/octet-stream;q=0.9,*/*;q=0.8",
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
) -> str:
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    suffix = Path(path).suffix.casefold()
    if suffix not in _IMAGE_SUFFIXES:
        suffix = _MIME_SUFFIXES.get((mime_type or "").casefold(), ".png")
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
