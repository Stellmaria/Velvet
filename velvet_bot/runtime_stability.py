from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

_INSTALLED = False
_ORIGINAL_ERROR_CENTER_START = None
_ORIGINAL_BUILD_WORKER_MANAGER: Any = None

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

_EXPECTED_SHUTDOWN_MARKERS = (
    "received sigterm signal",
    "received sigint signal",
)

_ASYNCIO_CLOSE_NETWORK_MARKERS = (
    "connectionabortederror",
    "connectionreseterror",
    "brokenpipeerror",
    "подключение к сети было разорвано",
    "connection was closed in the middle of operation",
    "connection reset by peer",
)

_QWEN_UNAVAILABLE_MARKERS = (
    "qwen quality service is unavailable",
    "workspace qwen service is unavailable",
    "ai vision service is unavailable",
)

_LOOP_GUARD_INSTALLED: set[int] = set()


def _record_message(record: logging.LogRecord) -> str:
    try:
        return record.getMessage().casefold()
    except (TypeError, ValueError, RuntimeError):
        return str(record.msg).casefold()


def is_recoverable_aiogram_polling_record(record: logging.LogRecord) -> bool:
    """Return True for known runtime noise that does not require owner action."""

    message = _record_message(record)
    if any(marker in message for marker in _QWEN_UNAVAILABLE_MARKERS):
        return True
    if record.name == "asyncio":
        return (
            "task exception was never retrieved" in message
            and "connection.close()" in message
            and any(marker in message for marker in _ASYNCIO_CLOSE_NETWORK_MARKERS)
        )
    if record.name != "aiogram.dispatcher":
        return False

    if any(message.startswith(marker) for marker in _EXPECTED_SHUTDOWN_MARKERS):
        return True

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
    """Close old non-actionable incidents so owner digests stay useful."""

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
                              OR LOWER(summary) LIKE 'received sigterm signal%'
                              OR LOWER(summary) LIKE 'received sigint signal%'
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
                    OR (
                           LOWER(summary) LIKE '%qwen quality service is unavailable%'
                        OR LOWER(summary) LIKE '%workspace qwen service is unavailable%'
                        OR LOWER(summary) LIKE '%ai vision service is unavailable%'
                    )
                  )
            """
        )
    try:
        return int(str(result).rsplit(" ", 1)[-1])
    except (TypeError, ValueError):
        return 0


def _nbrb_rate_enabled() -> bool:
    return os.getenv("KIE_NBRB_RATE_ENABLED", "true").strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "нет",
    }


def _nbrb_timeout_seconds() -> int:
    try:
        value = int(os.getenv("KIE_NBRB_TIMEOUT_SECONDS", "20").strip())
    except (AttributeError, TypeError, ValueError):
        value = 20
    return max(5, min(value, 120))


def _install_nbrb_worker_wrapper() -> None:
    global _ORIGINAL_BUILD_WORKER_MANAGER

    import velvet_bot.app.workers as workers_module
    from velvet_bot.domains.media_generation.worker import KieGenerationWorker
    from velvet_bot.presentation.telegram.routers.workspace_auf_balance import (
        DailyNbrbExchangeRateService,
        NbrbExchangeRateRepository,
        NbrbRateClient,
    )
    from velvet_bot.workers import PeriodicWorkerSpec

    if _ORIGINAL_BUILD_WORKER_MANAGER is not None:
        return
    _ORIGINAL_BUILD_WORKER_MANAGER = workers_module.build_worker_manager

    def build_worker_manager_with_nbrb(*args: Any, **kwargs: Any):
        manager = _ORIGINAL_BUILD_WORKER_MANAGER(*args, **kwargs)
        if not _nbrb_rate_enabled():
            return manager
        if "kie-nbrb-exchange-rate" in manager.registered_names():
            return manager

        database = kwargs.get("database")
        if database is None:
            return manager

        kie_workers: list[KieGenerationWorker] = []
        for name, spec in manager._specs.items():
            if not name.startswith("kie-media-generation"):
                continue
            worker = getattr(spec.runner, "__self__", None)
            if isinstance(worker, KieGenerationWorker):
                kie_workers.append(worker)
        if not kie_workers:
            return manager

        def apply_usd_to_rub(value: Decimal) -> None:
            if value <= 0:
                return
            for worker in kie_workers:
                worker._usd_to_rub = value

        service = DailyNbrbExchangeRateService(
            repository=NbrbExchangeRateRepository(database),
            client=NbrbRateClient(
                base_url=os.getenv("KIE_NBRB_BASE_URL", "https://api.nbrb.by"),
                timeout_seconds=_nbrb_timeout_seconds(),
            ),
            timezone_name=os.getenv("KIE_NBRB_TIMEZONE", "Europe/Minsk"),
            on_rate=apply_usd_to_rub,
        )
        manager.register(
            PeriodicWorkerSpec(
                name="kie-nbrb-exchange-rate",
                description="Ежедневный официальный курс USD/RUB по НБРБ",
                interval_seconds=3600,
                runner=service.process_once,
            )
        )
        return manager

    workers_module.build_worker_manager = build_worker_manager_with_nbrb


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
                    "Acknowledged %s non-actionable runtime incidents",
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
                "Could not acknowledge legacy runtime incidents: %s",
                error,
            )
        await _ORIGINAL_ERROR_CENTER_START(self)

    error_center.ErrorIncidentCenter.start = start_with_polling_cleanup
    _install_nbrb_worker_wrapper()
    _INSTALLED = True


__all__ = (
    "acknowledge_legacy_polling_noise",
    "install_asyncio_exception_guard",
    "install_runtime_stability",
    "is_recoverable_aiogram_polling_record",
    "is_recoverable_asyncio_connection_close_context",
)
