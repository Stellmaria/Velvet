from __future__ import annotations

import asyncio
import logging
from html import escape
from typing import Any

from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile

from velvet_bot.domains.media_generation.file_delivery_worker import (
    KieGenerationWorker as FileDeliveryKieGenerationWorker,
)
from velvet_bot.domains.media_generation.friendly_worker import FriendlyKieGenerationWorker

logger = logging.getLogger(__name__)
_INSTALLED = False
_DELIVERY_ERRORS = (TelegramAPIError, RuntimeError, ValueError, OSError)


async def _send_video_and_document_reliably(
    self: FileDeliveryKieGenerationWorker,
    *,
    chat_id: int,
    payload: bytes,
    filename: str,
    caption: str | None,
) -> None:
    """Send the untouched video as a document before the Telegram preview.

    Delivery failures are isolated from each other. A failed document upload must
    never prevent the preview from being attempted, and neither failure starts a
    new paid provider generation.
    """

    original_sent = False
    preview_sent = False
    original_error: BaseException | None = None
    preview_error: BaseException | None = None

    document_caption = "Оригинальный видеофайл без сжатия Telegram."
    if caption:
        document_caption = f"{caption}\n\n{document_caption}"

    try:
        await self._send_telegram_with_retry(
            "video original document",
            lambda: self._bot.send_document(
                chat_id,
                document=BufferedInputFile(payload, filename=filename),
                caption=document_caption,
                disable_content_type_detection=True,
            ),
        )
        original_sent = True
    except asyncio.CancelledError:
        raise
    except _DELIVERY_ERRORS as error:
        original_error = error
        logger.exception("Original video document delivery failed filename=%s", filename)

    try:
        await self._send_telegram_with_retry(
            "video preview",
            lambda: self._bot.send_video(
                chat_id,
                video=BufferedInputFile(payload, filename=filename),
                caption=("Предпросмотр видео." if original_sent else caption),
                supports_streaming=True,
            ),
        )
        preview_sent = True
    except asyncio.CancelledError:
        raise
    except _DELIVERY_ERRORS as error:
        preview_error = error
        logger.exception("Video preview delivery failed filename=%s", filename)

    if original_sent and preview_sent:
        return

    lines = ["<b>Видео сгенерировано, но доставка выполнена не полностью</b>"]
    if not original_sent:
        lines.append("Оригинальный файл: <b>не отправлен</b>")
    else:
        lines.append("Оригинальный файл: <b>отправлен</b>")
    if not preview_sent:
        lines.append("Предпросмотр: <b>не отправлен</b>")
    else:
        lines.append("Предпросмотр: <b>отправлен</b>")
    lines.append("Новая платная генерация не запускалась.")

    details: list[str] = []
    if original_error is not None:
        details.append(f"Файл: {escape(str(original_error)[:300])}")
    if preview_error is not None:
        details.append(f"Предпросмотр: {escape(str(preview_error)[:300])}")
    if details:
        lines.extend(("", *details))

    try:
        await self._send_telegram_with_retry(
            "video delivery warning",
            lambda: self._bot.send_message(chat_id, "\n".join(lines)),
        )
    except asyncio.CancelledError:
        raise
    except _DELIVERY_ERRORS:
        logger.exception("Could not report partial video delivery filename=%s", filename)


def install_original_video_delivery_hotfix() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    FileDeliveryKieGenerationWorker._send_video_and_document = (
        _send_video_and_document_reliably
    )
    FriendlyKieGenerationWorker._send_video_and_document = (
        _send_video_and_document_reliably
    )
    _INSTALLED = True


__all__ = ("install_original_video_delivery_hotfix",)
