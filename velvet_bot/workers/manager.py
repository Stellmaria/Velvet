from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

WorkerRunner = Callable[[], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class PeriodicWorkerSpec:
    name: str
    description: str
    interval_seconds: float
    runner: WorkerRunner
    run_immediately: bool = True

    def __post_init__(self) -> None:
        cleaned = self.name.strip()
        if not cleaned:
            raise ValueError("Имя фонового процесса не может быть пустым.")
        if self.interval_seconds < 1:
            raise ValueError("Интервал фонового процесса не может быть меньше секунды.")
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

    @property
    def healthy(self) -> bool:
        return self.state == "running" and self.consecutive_failures == 0


class WorkerManager:
    """Own periodic task lifecycle and expose immutable runtime snapshots."""

    def __init__(self) -> None:
        self._specs: dict[str, PeriodicWorkerSpec] = {}
        self._snapshots: dict[str, WorkerSnapshot] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._started = False

    def register(self, spec: PeriodicWorkerSpec) -> None:
        if self._started:
            raise RuntimeError("Нельзя регистрировать фоновые процессы после запуска.")
        if spec.name in self._specs:
            raise ValueError(f"Фоновый процесс {spec.name!r} уже зарегистрирован.")
        self._specs[spec.name] = spec
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

    async def start_all(self) -> None:
        async with self._lock:
            if self._started:
                return
            self._started = True
            now = datetime.now(UTC)
            for name, spec in self._specs.items():
                self._snapshots[name] = replace(
                    self._snapshots[name],
                    state="starting",
                    started_at=now,
                    stopped_at=None,
                    next_run_at=(
                        now
                        if spec.run_immediately
                        else now + timedelta(seconds=spec.interval_seconds)
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

    async def _run_periodic(self, spec: PeriodicWorkerSpec) -> None:
        if not spec.run_immediately:
            await asyncio.sleep(spec.interval_seconds)
        try:
            while True:
                started_at = datetime.now(UTC)
                current = self._snapshots[spec.name]
                self._snapshots[spec.name] = replace(
                    current,
                    state="running",
                    last_started_at=started_at,
                    next_run_at=None,
                )
                try:
                    await spec.runner()
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    failed_at = datetime.now(UTC)
                    current = self._snapshots[spec.name]
                    self._snapshots[spec.name] = replace(
                        current,
                        state="failed",
                        last_error_at=failed_at,
                        last_error=str(error)[:2000],
                        failed_runs=current.failed_runs + 1,
                        consecutive_failures=current.consecutive_failures + 1,
                        next_run_at=failed_at
                        + timedelta(seconds=spec.interval_seconds),
                    )
                    logger.exception("Background worker failed name=%s", spec.name)
                else:
                    completed_at = datetime.now(UTC)
                    current = self._snapshots[spec.name]
                    self._snapshots[spec.name] = replace(
                        current,
                        state="running",
                        last_success_at=completed_at,
                        last_error=None,
                        successful_runs=current.successful_runs + 1,
                        consecutive_failures=0,
                        next_run_at=completed_at
                        + timedelta(seconds=spec.interval_seconds),
                    )
                await asyncio.sleep(spec.interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as error:
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
