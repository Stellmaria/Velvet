from __future__ import annotations

import errno
import logging
from collections.abc import Iterator
from typing import Any, Final

import asyncpg

_TRANSIENT_ERRNOS: Final[frozenset[int]] = frozenset(
    value
    for value in (
        getattr(errno, "ECONNABORTED", None),
        getattr(errno, "ECONNRESET", None),
        getattr(errno, "ECONNREFUSED", None),
        getattr(errno, "ETIMEDOUT", None),
        getattr(errno, "ENETDOWN", None),
        getattr(errno, "ENETUNREACH", None),
        getattr(errno, "EHOSTUNREACH", None),
    )
    if value is not None
)
_TRANSIENT_WINERRORS: Final[frozenset[int]] = frozenset(
    {
        64,     # The specified network name is no longer available.
        121,    # The semaphore timeout period has expired.
        1236,   # The network connection was aborted by the local system.
        10053,  # Connection aborted by software on the host machine.
        10054,  # Connection reset by peer.
        10060,  # Connection timed out.
        10061,  # Connection refused.
    }
)
_TRANSIENT_MESSAGE_MARKERS: Final[tuple[str, ...]] = (
    "connection was closed in the middle of operation",
    "connection closed in the middle of operation",
    "server closed the connection",
    "server disconnected",
    "connection reset by peer",
    "connection was reset",
    "connection aborted",
    "connection was aborted",
    "network connection was aborted",
    "network is unreachable",
    "connection timed out",
    "clientoserror",
    "clientconnectorerror",
    "winerror 64",
    "winerror 121",
    "winerror 1236",
    "winerror 10053",
    "winerror 10054",
    "winerror 10060",
    "winerror 10061",
)


def _exception_chain(error: BaseException) -> Iterator[BaseException]:
    stack: list[BaseException] = [error]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        yield current

        nested = getattr(current, "exceptions", None)
        if isinstance(nested, (list, tuple)):
            stack.extend(item for item in nested if isinstance(item, BaseException))
        if current.__cause__ is not None:
            stack.append(current.__cause__)
        elif current.__context__ is not None:
            stack.append(current.__context__)


def looks_like_transient_connection_message(value: str) -> bool:
    normalized = " ".join(str(value).casefold().split())
    return any(marker in normalized for marker in _TRANSIENT_MESSAGE_MARKERS)


def is_transient_connection_error(error: BaseException) -> bool:
    for current in _exception_chain(error):
        if isinstance(current, asyncpg.ConnectionDoesNotExistError):
            return True
        if isinstance(current, (ConnectionAbortedError, ConnectionResetError, TimeoutError)):
            return True
        if isinstance(current, OSError):
            winerror = getattr(current, "winerror", None)
            if isinstance(winerror, int) and winerror in _TRANSIENT_WINERRORS:
                return True
            if isinstance(current.errno, int) and current.errno in _TRANSIENT_ERRNOS:
                return True
        if looks_like_transient_connection_message(str(current)):
            return True
    return False


async def recover_database_pool(database: Any, error: BaseException) -> None:
    """Expire pooled sessions after a local network interruption.

    The failed worker iteration is not replayed here. The next scheduled run
    acquires a replacement connection, avoiding duplicate external side effects.
    """

    del error
    pool = getattr(database, "_pool", None)
    if pool is None:
        return
    await pool.expire_connections()


class RecoverablePollingNoiseFilter(logging.Filter):
    """Keep normal aiogram reconnects out of the persistent incident center."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "aiogram.dispatcher":
            return True
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        normalized = message.casefold()
        recoverable = (
            "failed to fetch updates" in normalized
            and "telegramnetworkerror" in normalized
            and looks_like_transient_connection_message(normalized)
        )
        return not recoverable


def install_recoverable_polling_filter(error_center: Any) -> bool:
    handler = getattr(error_center, "_handler", None)
    if not isinstance(handler, logging.Handler):
        return False
    if any(isinstance(item, RecoverablePollingNoiseFilter) for item in handler.filters):
        return True
    handler.addFilter(RecoverablePollingNoiseFilter())
    return True


__all__ = (
    "RecoverablePollingNoiseFilter",
    "install_recoverable_polling_filter",
    "is_transient_connection_error",
    "looks_like_transient_connection_message",
    "recover_database_pool",
)
