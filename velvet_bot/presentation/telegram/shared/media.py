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
) -> bytes:
    """Download a Telegram file with bounded retries and cancellation safety."""

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
        except TelegramBadRequest as error:
            errors.append(error)
            break
        except (TelegramNetworkError, TimeoutError, ConnectionError, OSError) as error:
            errors.append(error)
            if attempt >= attempts:
                break
            delay_index = min(attempt - 1, max(0, len(retry_delays) - 1))
            delay = retry_delays[delay_index] if retry_delays else 0.0
            if delay > 0:
                await asyncio.sleep(delay)
        except TelegramAPIError as error:
            errors.append(error)
            break
    if errors:
        raise RuntimeError(f"Не удалось скачать {failure_label}: {errors[-1]}")
    raise RuntimeError("Telegram вернул пустой файл.")


__all__ = ("download_telegram_file",)
