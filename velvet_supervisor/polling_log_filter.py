from __future__ import annotations

import velvet_supervisor.runtime as runtime

_TRANSIENT_NETWORK_MARKERS = (
    "serverdisconnectederror",
    "server disconnected",
    "clientconnectorerror",
    "clientoserror",
    "cannot connect to host api.telegram.org",
    "превышен таймаут семафора",
    "semaphore timeout",
    "winerror 1236",
    "подключение к сети было разорвано локальной системой",
    "connection reset by peer",
    "connection timed out",
)


def is_recoverable_polling_line(line: str) -> bool:
    """Return True for aiogram polling failures that are retried automatically."""

    lowered = line.casefold()
    if "aiogram.dispatcher" not in lowered:
        return False
    if "sleep for " in lowered and "seconds and try again" in lowered:
        return True
    return (
        "failed to fetch updates" in lowered
        and "telegramnetworkerror" in lowered
        and any(marker in lowered for marker in _TRANSIENT_NETWORK_MARKERS)
    )


def install_supervisor_polling_filter() -> None:
    """Extend the legacy Supervisor log filter without rewriting its runtime."""

    runtime._is_recoverable_polling_disconnect = is_recoverable_polling_line


__all__ = ("install_supervisor_polling_filter", "is_recoverable_polling_line")
