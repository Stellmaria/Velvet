from __future__ import annotations

import asyncio
import io
from collections.abc import Sequence

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)


async def download_telegram_file(
    bot: Bot,
    file_id: str,
    *,
    attempts: int = 3,
    timeout_seconds: int = 90,
    retry_delays: Sequence[float] = (1.0, 3.0),
    failure_label: str = "изображение",
    bad_request_type: type[BaseException] = TelegramBadRequest,
    network_error_types: tuple[type[BaseException], ...] = (
        TelegramNetworkError,
        TimeoutError,
        ConnectionError,
        OSError,
    ),
    api_error_type: type[BaseException] = TelegramAPIError,
) -> bytes:
    """Download a Telegram file with bounded retries and cancellation safety.

    Exception classes are injectable so compatibility facades and their regression tests
    keep the same observable behavior while the retry implementation becomes shared.
    """

    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    errors: list[BaseException] = []
    for attempt in range(1, attempts + 1):
        try:
            destination = io.BytesIO()
            await bot.download(
                file_id,
                destination=destination,
                timeout=timeout_seconds,
                seek=True,
            )
            value = destination.getvalue()
            if value:
                return value
            errors.append(RuntimeError("Telegram вернул пустой файл."))
        except asyncio.CancelledError:
            raise
        except Exception as error:  # p2-approved-boundary:typed-telegram-download-error-dispatch
            if isinstance(error, bad_request_type):
                errors.append(error)
                break
            if isinstance(error, network_error_types):
                errors.append(error)
                if attempt >= attempts:
                    break
                delay_index = min(attempt - 1, max(0, len(retry_delays) - 1))
                delay = retry_delays[delay_index] if retry_delays else 0.0
                if delay > 0:
                    await asyncio.sleep(delay)
                continue
            if isinstance(error, api_error_type):
                errors.append(error)
                break
            raise
    if errors:
        raise RuntimeError(f"Не удалось скачать {failure_label}: {errors[-1]}")
    raise RuntimeError("Telegram вернул пустой файл.")


__all__ = ("download_telegram_file",)
