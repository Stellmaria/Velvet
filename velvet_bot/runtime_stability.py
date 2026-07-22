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

_ASYNCIO_CLOSE_NETWORK_MARKERS = (
    "connectionabortederror",
    "connectionreseterror",
    "brokenpipeerror",
    "подключение к сети было разорвано",
    "connection was closed in the middle of operation",
    "connection reset by peer",
)
_LOOP_GUARD_INSTALLED: set[int] = set()


def _record_message(record: logging.LogRecord) -> str:
    try:
        return record.getMessage().casefold()
    except (TypeError, ValueError, RuntimeError):
        return str(record.msg).casefold()


def is_recoverable_aiogram_polling_record(record: logging.LogRecord) -> bool:
    """Return True for transient transport noise already handled by a retry loop."""

    message = _record_message(record)
    if record.name == "asyncio":
        return (
            "task exception was never retrieved" in message
            and "connection.close()" in message
            and any(marker in message for marker in _ASYNCIO_CLOSE_NETWORK_MARKERS)
        )
    if record.name != "aiogram.dispatcher":
        return False

    if all(marker in message for marker in _BACKOFF_MARKERS):
        return True

    return (
        "failed to fetch updates" in message
        and "telegramnetworkerror" in message
        and any(marker in message for marker in _NETWORK_FAILURE_MARKERS)
    )


def is_recoverable_asyncio_connection_close_context(
    context: dict[str, Any],
) -> bool:
    """Identify asyncpg close tasks that fail only because the socket already died."""

    message = str(context.get("message") or "").casefold()
    future = context.get("future") or context.get("task")
    future_text = repr(future).casefold()
    error = context.get("exception")
    error_text = f"{type(error).__name__}: {error}".casefold() if error else ""
    return (
        "task exception was never retrieved" in message
        and "connection.close()" in future_text
        and any(marker in error_text for marker in _ASYNCIO_CLOSE_NETWORK_MARKERS)
    )


def install_asyncio_exception_guard(loop: asyncio.AbstractEventLoop) -> None:
    """Suppress only the known asyncpg close-after-network-drop task failure."""

    identity = id(loop)
    if identity in _LOOP_GUARD_INSTALLED:
        return
    previous = loop.get_exception_handler()

    def handle(
        current_loop: asyncio.AbstractEventLoop,
        context: dict[str, Any],
    ) -> None:
        if is_recoverable_asyncio_connection_close_context(context):
            logger.info(
                "Ignored transient asyncpg connection close failure: %s",
                context.get("exception"),
            )
            return
        if previous is not None:
            previous(current_loop, context)
        else:
            current_loop.default_exception_handler(context)

    loop.set_exception_handler(handle)
    _LOOP_GUARD_INSTALLED.add(identity)


async def acknowledge_legacy_polling_noise(repository: Any) -> int:
    """Close old recoverable Telegram transport incidents so owner digests stay useful."""

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
    AND (
          (
              logger_name = 'aiogram.dispatcher'
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
          )
          OR (
              logger_name = 'velvet_bot.presentation.telegram.router'
              AND LOWER(summary) LIKE '%unhandled bot error%'
              AND (
                     LOWER(summary) LIKE '%clientconnectorerror%'
                  OR LOWER(summary) LIKE '%cannot connect to host api.telegram.org%'
                  OR LOWER(summary) LIKE '%превышен таймаут семафора%'
                  OR LOWER(summary) LIKE '%подключение к сети было разорвано%'
                  OR LOWER(summary) LIKE '%semaphore timeout%'
                  OR LOWER(summary) LIKE '%connection reset by peer%'
                  OR LOWER(summary) LIKE '%connection timed out%'
              )
          )
          OR (
              logger_name = 'asyncio'
              AND LOWER(summary) LIKE '%task exception was never retrieved%'
              AND LOWER(summary) LIKE '%connection.close()%'
              AND (
                     LOWER(summary) LIKE '%connectionabortederror%'
                  OR LOWER(summary) LIKE '%connectionreseterror%'
                  OR LOWER(summary) LIKE '%подключение к сети было разорвано%'
                  OR LOWER(summary) LIKE '%connection was closed in the middle of operation%'
              )
          )
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
        install_asyncio_exception_guard(asyncio.get_running_loop())
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
    "install_asyncio_exception_guard",
    "install_runtime_stability",
    "is_recoverable_aiogram_polling_record",
    "is_recoverable_asyncio_connection_close_context",
)
