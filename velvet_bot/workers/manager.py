from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from velvet_bot.infrastructure.transient_connections import (
    is_transient_connection_error,
)
from velvet_bot.workers.adaptive import WorkerWaitSnapshot

logger = logging.getLogger(__name__)

WorkerRunner = Callable[[], Awaitable[Any]]
TransientFailureHandler = Callable[[BaseException], Awaitable[None]]
_TRANSIENT_ALERT_AFTER = 3
_TRANSIENT_ALERT_REPEAT = 10


class WorkerWaitController(Protocol):
    def delay_for(
        self,
        result: object,
        *,
        default_interval_seconds: float,
    ) -> float: ...

    async def wait(self, delay_seconds: float) -> bool: ...

    async def close(self) -> None: ...

    def snapshot(self) -> WorkerWaitSnapshot: ...


@dataclass(frozen=True, slots=True)
class PeriodicWorkerSpec:
    name: str
    description: str
    interval_seconds: float
    runner: WorkerRunner
    run_immediately: bool = True
    wait_controller: WorkerWaitController | None = None

    def __post_init__(self) -> None:
        cleaned = self.name.strip()
        if not cleaned:
            raise ValueError("Имя фонового процесса не может быть пустым.")
        if self.interval_seconds <= 0:
            raise ValueError("Интервал фонового процесса должен быть положительным.")
        object.__setattr__(self, "name", cleaned)
        object.__setattr__(self, "description", self.description.strip() or cleaned)


@dataclass(frozen=True, slots=True)
class WorkerSnapshot:
    name: str
    description: str
    state: str
    interval_seconds: float
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    last_started_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    next_run_at: datetime | None = None
    last_error: str | None = None
    successful_runs: int = 0
    failed_runs: int = 0
    consecutive_failures: int = 0
    last_outcome: str | None = None
    current_interval_seconds: float | None = None
    empty_runs: int = 0
    processed_items: int = 0
    wakeups: int = 0
    fallback_polls: int = 0
    listener_reconnects: int = 0
    listener_errors: int = 0
    oldest_queued_age_seconds: float | None = None

    @property
    def healthy(self) -> bool:
        return self.state == "running" and self.consecutive_failures == 0


class WorkerManager:
    """Own periodic task lifecycle and expose immutable runtime snapshots."""

    def __init__(
        self,
        *,
        transient_failure_handler: TransientFailureHandler | None = None,
    ) -> None:
        self._specs: dict[str, PeriodicWorkerSpec] = {}
        self._snapshots: dict[str, WorkerSnapshot] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._run_locks: dict[str, asyncio.Lock] = {}
        self._lock = asyncio.Lock()
        self._started = False
        self._transient_failure_handler = transient_failure_handler

    @property
    def started(self) -> bool:
        return self._started

    def register(self, spec: PeriodicWorkerSpec) -> None:
        if self._started:
            raise RuntimeError("Нельзя регистрировать фоновые процессы после запуска.")
        if spec.name in self._specs:
            raise ValueError(f"Фоновый процесс {spec.name!r} уже зарегистрирован.")
        self._specs[spec.name] = spec
        self._run_locks[spec.name] = asyncio.Lock()
        self._snapshots[spec.name] = WorkerSnapshot(
            name=spec.name,
            description=spec.description,
            state="stopped",
            interval_seconds=spec.interval_seconds,
        )

    def registered_names(self) -> tuple[str, ...]:
        return tuple(self._specs)

    def snapshots(self) -> tuple[WorkerSnapshot, ...]:
        return tuple(self._snapshots[name] for name in self._specs)

    def snapshot(self, name: str) -> WorkerSnapshot | None:
        return self._snapshots.get(name)

    def _require_spec(self, name: str) -> PeriodicWorkerSpec:
        try:
            return self._specs[name]
        except KeyError as error:
            raise ValueError(f"Фоновый процесс {name!r} не зарегистрирован.") from error

    async def start_all(self) -> None:
        async with self._lock:
            if self._started:
                return
            self._started = True
            for name, spec in self._specs.items():
                self._start_task(name, spec)

    def _start_task(self, name: str, spec: PeriodicWorkerSpec) -> None:
        now = datetime.now(UTC)
        self._snapshots[name] = replace(
            self._snapshots[name],
            state="starting",
            started_at=now,
            stopped_at=None,
            next_run_at=(
                now if spec.run_immediately else now + timedelta(seconds=spec.interval_seconds)
            ),
            last_error=None,
            consecutive_failures=0,
        )
        self._tasks[name] = asyncio.create_task(
            self._run_periodic(spec),
            name=f"worker:{name}",
        )

    async def stop_all(self) -> None:
        async with self._lock:
            tasks = tuple(self._tasks.values())
            for task in tasks:
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        async with self._lock:
            stopped_at = datetime.now(UTC)
            for name in self._specs:
                snapshot = self._snapshots[name]
                self._snapshots[name] = replace(
                    snapshot,
                    state="stopped",
                    stopped_at=stopped_at,
                    next_run_at=None,
                )
            self._tasks.clear()
            self._started = False

    async def run_now(self, name: str) -> bool:
        """Execute one worker iteration without allowing overlapping runs."""
        if not self._started:
            raise RuntimeError("Менеджер фоновых процессов ещё не запущен.")
        spec = self._require_spec(name)
        succeeded, _ = await self._execute_once(spec)
        return succeeded

    async def restart(self, name: str) -> None:
        """Cancel and recreate one periodic task while preserving its counters."""
        spec = self._require_spec(name)
        async with self._lock:
            if not self._started:
                raise RuntimeError("Менеджер фоновых процессов ещё не запущен.")
            task = self._tasks.get(name)
            if task is not None:
                task.cancel()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        async with self._lock:
            if not self._started:
                return
            self._start_task(name, spec)

    async def _handle_transient_failure(
        self,
        *,
        spec: PeriodicWorkerSpec,
        error: BaseException,
        consecutive_failures: int,
    ) -> None:
        handler = self._transient_failure_handler
        if handler is not None:
            await handler(error)

        if (
            consecutive_failures == _TRANSIENT_ALERT_AFTER
            or consecutive_failures % _TRANSIENT_ALERT_REPEAT == 0
        ):
            logger.error(
                "Background workers cannot reach a network dependency; "
                "transient outage persists"
            )
            return
        logger.info(
            "Background worker transient connection failure name=%s "
            "consecutive=%s; retrying on the next scheduled iteration: %s",
            spec.name,
            consecutive_failures,
            error,
        )

    async def _execute_once(self, spec: PeriodicWorkerSpec) -> tuple[bool, Any]:
        async with self._run_locks[spec.name]:
            started_at = datetime.now(UTC)
            current = self._snapshots[spec.name]
            self._snapshots[spec.name] = replace(
                current,
                state="running",
                last_started_at=started_at,
                next_run_at=None,
            )
            try:
                result = await spec.runner()
            except asyncio.CancelledError:
                raise
            except Exception as error:  # p2-approved-boundary: isolate-worker-iteration-failure
                failed_at = datetime.now(UTC)
                current = self._snapshots[spec.name]
                consecutive_failures = current.consecutive_failures + 1
                self._snapshots[spec.name] = replace(
                    current,
                    state="failed",
                    last_error_at=failed_at,
                    last_error=str(error)[:2000],
                    failed_runs=current.failed_runs + 1,
                    consecutive_failures=consecutive_failures,
                    next_run_at=failed_at + timedelta(seconds=spec.interval_seconds),
                )
                if is_transient_connection_error(error):
                    await self._handle_transient_failure(
                        spec=spec,
                        error=error,
                        consecutive_failures=consecutive_failures,
                    )
                else:
                    logger.exception("Background worker failed name=%s", spec.name)
                return False, None

            completed_at = datetime.now(UTC)
            current = self._snapshots[spec.name]
            self._snapshots[spec.name] = replace(
                current,
                state="running",
                last_success_at=completed_at,
                last_error=None,
                successful_runs=current.successful_runs + 1,
                consecutive_failures=0,
                next_run_at=completed_at + timedelta(seconds=spec.interval_seconds),
            )
            return True, result

    def _apply_wait_snapshot(
        self,
        spec: PeriodicWorkerSpec,
        *,
        next_run_at: datetime | None = None,
    ) -> None:
        controller = spec.wait_controller
        if controller is None:
            return
        wait = controller.snapshot()
        current = self._snapshots[spec.name]
        self._snapshots[spec.name] = replace(
            current,
            next_run_at=next_run_at if next_run_at is not None else current.next_run_at,
            last_outcome=wait.last_outcome,
            current_interval_seconds=wait.current_interval_seconds,
            empty_runs=wait.empty_runs,
            processed_items=wait.processed_items,
            wakeups=wait.wakeups,
            fallback_polls=wait.fallback_polls,
            listener_reconnects=wait.listener_reconnects,
            listener_errors=wait.listener_errors,
            oldest_queued_age_seconds=wait.oldest_queued_age_seconds,
        )

    async def _run_periodic(self, spec: PeriodicWorkerSpec) -> None:
        if not spec.run_immediately:
            await asyncio.sleep(spec.interval_seconds)
        try:
            while True:
                succeeded, result = await self._execute_once(spec)
                controller = spec.wait_controller
                if not succeeded or controller is None:
                    await asyncio.sleep(spec.interval_seconds)
                    continue
                delay = controller.delay_for(
                    result,
                    default_interval_seconds=spec.interval_seconds,
                )
                self._apply_wait_snapshot(
                    spec,
                    next_run_at=datetime.now(UTC) + timedelta(seconds=delay),
                )
                woke = await controller.wait(delay)
                self._apply_wait_snapshot(
                    spec,
                    next_run_at=datetime.now(UTC) if woke else None,
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:  # p2-approved-boundary: isolate-worker-loop-failure
            failed_at = datetime.now(UTC)
            current = self._snapshots[spec.name]
            self._snapshots[spec.name] = replace(
                current,
                state="failed",
                last_error_at=failed_at,
                last_error=f"Worker loop stopped: {error}"[:2000],
                failed_runs=current.failed_runs + 1,
                consecutive_failures=current.consecutive_failures + 1,
                next_run_at=None,
            )
            logger.exception("Background worker loop stopped name=%s", spec.name)
        finally:
            if spec.wait_controller is not None:
                await spec.wait_controller.close()
