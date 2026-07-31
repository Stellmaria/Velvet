from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

ProcessTerminator = Callable[[], None]


def terminate_current_process() -> None:
    """Terminate this process so its external runtime can start a fresh copy.

    Docker Compose uses ``restart: unless-stopped`` in production, while the
    historical desktop Supervisor watches the child process. Sending SIGTERM
    therefore gives both runtimes the same restart contract without granting
    the Telegram bot access to Docker, systemd, or the host filesystem.
    """

    logger.warning("Process self-restart requested; sending SIGTERM")
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except (AttributeError, OSError):
        # SIGTERM is the graceful path. The fallback is intentionally abrupt:
        # remaining alive after the owner confirmed a restart is worse than
        # letting the external runtime recreate the process.
        os._exit(75)


@dataclass(slots=True)
class ProcessRestartCoordinator:
    terminator: ProcessTerminator = terminate_current_process
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock | None = field(default=None, init=False, repr=False)

    def _active_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def request(self, *, delay_seconds: float = 1.5) -> bool:
        """Schedule one restart and reject duplicate taps while it is pending."""

        delay = max(0.1, min(float(delay_seconds), 30.0))
        async with self._active_lock():
            if self._task is not None and not self._task.done():
                return False
            self._task = asyncio.create_task(
                self._terminate_after_delay(delay),
                name="velvet-process-self-restart",
            )
            return True

    async def _terminate_after_delay(self, delay_seconds: float) -> None:
        await asyncio.sleep(delay_seconds)
        self.terminator()

    @property
    def pending(self) -> bool:
        return self._task is not None and not self._task.done()


process_restart_coordinator = ProcessRestartCoordinator()


__all__ = (
    "ProcessRestartCoordinator",
    "process_restart_coordinator",
    "terminate_current_process",
)
