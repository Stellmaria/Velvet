from __future__ import annotations

import logging
import os
from typing import Any

from velvet_bot.domains.watermark import WatermarkRepository
from velvet_bot.domains.watermark.remote_worker import KritaRemoteRepository
from velvet_bot.infrastructure.krita_bridge import KritaBridge, default_krita_bridge_dir
from velvet_bot.infrastructure.krita_remote_api import (
    KritaRemoteCoordinator,
    KritaRemoteSettings,
    KritaRemoteWorkerServer,
    RemoteWatermarkService,
)
from velvet_bot.workers import PeriodicWorkerSpec, WorkerManager

logger = logging.getLogger(__name__)
_installed = False
_runtime: "KritaRemoteRuntime | None" = None


class KritaRemoteRuntime:
    def __init__(
        self,
        *,
        server: KritaRemoteWorkerServer,
        service: RemoteWatermarkService,
    ) -> None:
        self._server = server
        self._service = service
        self._started = False

    async def process_once(self) -> int:
        if not self._started:
            await self._server.start()
            self._started = True
        return await self._service.process_once()

    async def stop(self) -> None:
        if self._started:
            self._started = False
            await self._server.stop()


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().casefold() in {
        "1", "true", "yes", "on", "да"
    }


def _build_runtime(*, bot: Any, database: Any) -> KritaRemoteRuntime:
    settings = KritaRemoteSettings.from_env()
    remote_repository = KritaRemoteRepository(database)
    repository = WatermarkRepository(database)
    bridge = KritaBridge(default_krita_bridge_dir())
    service = RemoteWatermarkService(
        bot=bot,
        repository=repository,
        bridge=bridge,
        remote_repository=remote_repository,
    )
    coordinator = KritaRemoteCoordinator(
        repository=repository,
        remote_repository=remote_repository,
        bridge=bridge,
        settings=settings,
    )
    return KritaRemoteRuntime(
        server=KritaRemoteWorkerServer(coordinator=coordinator, settings=settings),
        service=service,
    )


def install_krita_remote_worker() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    if not _enabled("KRITA_REMOTE_WORKER_ENABLED"):
        return
    if not _enabled("KRITA_WATERMARK_ENABLED"):
        raise RuntimeError(
            "KRITA_REMOTE_WORKER_ENABLED=true требует KRITA_WATERMARK_ENABLED=true."
        )

    from velvet_bot.app import bootstrap
    from velvet_bot.app import workers as workers_module

    original_build = bootstrap.build_worker_manager
    original_close = bootstrap._close_application_resources

    def build_worker_manager_remote(*args: Any, **kwargs: Any) -> WorkerManager:
        global _runtime
        previous = os.environ.get("KRITA_WATERMARK_ENABLED")
        os.environ["KRITA_WATERMARK_ENABLED"] = "false"
        try:
            manager = original_build(*args, **kwargs)
        finally:
            if previous is None:
                os.environ.pop("KRITA_WATERMARK_ENABLED", None)
            else:
                os.environ["KRITA_WATERMARK_ENABLED"] = previous
        bot = kwargs.get("bot")
        database = kwargs.get("database")
        if bot is None or database is None:
            raise RuntimeError("Krita remote installer требует bot и database kwargs.")
        _runtime = _build_runtime(bot=bot, database=database)
        manager.register(
            PeriodicWorkerSpec(
                name="krita-watermark-remote",
                description="Удалённый Windows Krita worker через SSH tunnel",
                interval_seconds=2,
                runner=_runtime.process_once,
            )
        )
        logger.info("Installed remote Krita watermark worker runtime")
        return manager

    async def close_with_krita(*args: Any, **kwargs: Any) -> None:
        runtime = _runtime
        if runtime is not None:
            try:
                await runtime.stop()
            except (OSError, RuntimeError):
                logger.exception("Could not stop Krita remote worker API")
        await original_close(*args, **kwargs)

    workers_module.build_worker_manager = build_worker_manager_remote  # type: ignore[assignment]
    bootstrap.build_worker_manager = build_worker_manager_remote  # type: ignore[assignment]
    bootstrap._close_application_resources = close_with_krita  # type: ignore[assignment]


__all__ = ("install_krita_remote_worker",)
