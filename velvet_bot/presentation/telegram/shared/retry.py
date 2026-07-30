from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class TelegramRetryPolicy:
    attempts: int = 4
    delays: tuple[float, ...] = (1.0, 2.0, 4.0)

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be at least 1")
        if any(delay < 0 for delay in self.delays):
            raise ValueError("retry delays must be non-negative")

    def delay_for_attempt(self, attempt: int) -> float:
        if not self.delays:
            return 0.0
        index = min(max(0, int(attempt) - 1), len(self.delays) - 1)
        return float(self.delays[index])


async def retry_telegram_operation(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: TelegramRetryPolicy = TelegramRetryPolicy(),
    on_retry: Callable[[int, TelegramAPIError], None] | None = None,
) -> T:
    """Retry Telegram API failures while keeping bad requests non-retryable."""

    errors: list[TelegramAPIError] = []
    for attempt in range(1, policy.attempts + 1):
        try:
            return await operation()
        except asyncio.CancelledError:
            raise
        except TelegramBadRequest:
            raise
        except TelegramAPIError as error:
            errors.append(error)
            if attempt >= policy.attempts:
                break
            if on_retry is not None:
                on_retry(attempt + 1, error)
            delay = policy.delay_for_attempt(attempt)
            if delay > 0:
                await asyncio.sleep(delay)
    if errors:
        raise errors[-1]
    raise RuntimeError("Telegram operation did not execute.")


__all__ = ("TelegramRetryPolicy", "retry_telegram_operation")
