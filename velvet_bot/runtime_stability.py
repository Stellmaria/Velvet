from __future__ import annotations

import asyncio
import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

_INSTALLED = False
_ORIGINAL_ERROR_CENTER_START = None

_NETWORK_FAILURE_MARKERS = (
    "serverdisconnectederror",
    "server disconnected",
    "clientconnectorerror",
    "cannot connect to host api.telegram.org",
    "превышен таймаут семафора",
    "semaphore timeout",
    "connection reset by peer",
    "connection timed out",
)

_BACKOFF_MARKERS = (
    "sleep for ",
    " seconds and try again",
)


def _record_message(record: logging.LogRecord) -> str:
    try:
        return record.getMessage().casefold()
    except (TypeError, ValueError, RuntimeError):
        return str(record.msg).casefold()


def is_recoverable_aiogram_polling_record(record: logging.LogRecord) -> bool:
    """Return True for transient Telegram polling noise that aiogram retries itself."""

    if record.name != "aiogram.dispatcher":
        return False

    message = _record_message(record)
    if all(marker in message for marker in _BACKOFF_MARKERS):
        return True

    return (
        "failed to fetch updates" in message
        and "telegramnetworkerror" in message
        and any(marker in message for marker in _NETWORK_FAILURE_MARKERS)
    )


async def acknowledge_legacy_polling_noise(repository: Any) -> int:
    """Close old recoverable polling incidents so owner digests become useful again."""

    database = getattr(repository, "_database", None)
    if database is None:
        return 0

    async with database.acquire() as connection:
        result = await connection.execute(
            """
            UPDATE error_incidents
            SET acknowledged_at = COALESCE(acknowledged_at, NOW()),
                acknowledged_by = COALESCE(acknowledged_by, 0)
            WHERE acknowledged_at IS NULL
              AND logger_name = 'aiogram.dispatcher'
              AND (
                    (
                        LOWER(summary) LIKE '%failed to fetch updates%'
                        AND LOWER(summary) LIKE '%telegramnetworkerror%'
                        AND (
                               LOWER(summary) LIKE '%serverdisconnectederror%'
                            OR LOWER(summary) LIKE '%server disconnected%'
                            OR LOWER(summary) LIKE '%clientconnectorerror%'
                            OR LOWER(summary) LIKE '%cannot connect to host api.telegram.org%'
                            OR LOWER(summary) LIKE '%превышен таймаут семафора%'
                            OR LOWER(summary) LIKE '%semaphore timeout%'
                            OR LOWER(summary) LIKE '%connection reset by peer%'
                            OR LOWER(summary) LIKE '%connection timed out%'
                        )
                    )
                    OR LOWER(summary) LIKE 'sleep for % seconds and try again%'
                  )
            """
        )
    try:
        return int(str(result).rsplit(" ", 1)[-1])
    except (TypeError, ValueError):
        return 0


def install_runtime_stability() -> None:
    """Install production guards before application bootstrap creates the error center."""

    global _INSTALLED, _ORIGINAL_ERROR_CENTER_START
    if _INSTALLED:
        return

    import velvet_bot.error_center as error_center

    error_center._is_recoverable_aiogram_polling_record = (
        is_recoverable_aiogram_polling_record
    )
    _ORIGINAL_ERROR_CENTER_START = error_center.ErrorIncidentCenter.start

    async def start_with_polling_cleanup(self) -> None:
        try:
            closed = await acknowledge_legacy_polling_noise(self._repository)
            if closed:
                logger.info(
                    "Acknowledged %s recoverable Telegram polling incidents",
                    closed,
                )
        except asyncio.CancelledError:
            raise
        except (
            asyncpg.PostgresError,
            asyncpg.InterfaceError,
            OSError,
            RuntimeError,
            TimeoutError,
        ) as error:
            logger.warning(
                "Could not acknowledge legacy Telegram polling incidents: %s",
                error,
            )
        await _ORIGINAL_ERROR_CENTER_START(self)

    error_center.ErrorIncidentCenter.start = start_with_polling_cleanup
    _INSTALLED = True


__all__ = (
    "acknowledge_legacy_polling_noise",
    "install_runtime_stability",
    "is_recoverable_aiogram_polling_record",
)
