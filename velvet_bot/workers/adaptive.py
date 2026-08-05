from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from enum import StrEnum
from collections.abc import Callable
from typing import Protocol


class WorkerIterationOutcome(StrEnum):
    PROCESSED = "processed"
    EMPTY = "empty"
    SKIPPED = "skipped"
    TRANSIENT_FAILURE = "transient_failure"
    TERMINAL_FAILURE = "terminal_failure"


@dataclass(frozen=True, slots=True, eq=False)
class WorkerIterationResult:
    outcome: WorkerIterationOutcome
    processed_items: int = 0
    oldest_queued_age_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.processed_items < 0:
            raise ValueError("processed_items не может быть отрицательным.")
        if self.oldest_queued_age_seconds is not None and self.oldest_queued_age_seconds < 0:
            raise ValueError("oldest_queued_age_seconds не может быть отрицательным.")

    def __int__(self) -> int:
        return self.processed_items

    def __eq__(self, other: object) -> bool:
        if isinstance(other, int):
            return self.processed_items == other
        if not isinstance(other, WorkerIterationResult):
            return NotImplemented
        return (
            self.outcome is other.outcome
            and self.processed_items == other.processed_items
            and self.oldest_queued_age_seconds == other.oldest_queued_age_seconds
        )


@dataclass(frozen=True, slots=True)
class WorkerWaitSnapshot:
    last_outcome: str | None = None
    current_interval_seconds: float | None = None
    empty_runs: int = 0
    processed_items: int = 0
    wakeups: int = 0
    fallback_polls: int = 0
    listener_reconnects: int = 0
    listener_errors: int = 0
    oldest_queued_age_seconds: float | None = None


class WakeupSource(Protocol):
    async def wait(self, timeout_seconds: float) -> bool: ...

    async def close(self) -> None: ...

    @property
    def wakeups(self) -> int: ...

    @property
    def fallback_polls(self) -> int: ...

    @property
    def reconnects(self) -> int: ...

    @property
    def errors(self) -> int: ...


class AdaptiveQueueWait:
    """Back off only after empty claims and wake early on a best-effort signal."""

    def __init__(
        self,
        wakeup: WakeupSource,
        *,
        empty_delays_seconds: tuple[float, ...] = (3.0, 5.0, 10.0, 20.0, 30.0),
        jitter_ratio: float = 0.1,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        if not empty_delays_seconds or any(value <= 0 for value in empty_delays_seconds):
            raise ValueError("empty_delays_seconds должен содержать положительные интервалы.")
        if not 0 <= jitter_ratio <= 0.5:
            raise ValueError("jitter_ratio должен быть от 0 до 0.5.")
        self._wakeup = wakeup
        self._delays = tuple(float(value) for value in empty_delays_seconds)
        self._jitter_ratio = float(jitter_ratio)
        self._random_value = random_value
        self._empty_index = 0
        self._last_outcome: WorkerIterationOutcome | None = None
        self._current_interval: float | None = None
        self._empty_runs = 0
        self._processed_items = 0
        self._oldest_queued_age_seconds: float | None = None

    def delay_for(
        self,
        result: object,
        *,
        default_interval_seconds: float,
    ) -> float:
        if not isinstance(result, WorkerIterationResult):
            self._last_outcome = None
            self._current_interval = float(default_interval_seconds)
            self._empty_index = 0
            return self._current_interval

        self._last_outcome = result.outcome
        self._oldest_queued_age_seconds = result.oldest_queued_age_seconds
        self._processed_items += result.processed_items

        if result.outcome is WorkerIterationOutcome.PROCESSED:
            self._empty_index = 0
            self._current_interval = 0.0
            return 0.0

        if result.outcome is WorkerIterationOutcome.EMPTY:
            self._empty_runs += 1
            base = self._delays[min(self._empty_index, len(self._delays) - 1)]
            self._empty_index = min(self._empty_index + 1, len(self._delays) - 1)
            spread = base * self._jitter_ratio
            jitter = (float(self._random_value()) * 2.0 - 1.0) * spread
            self._current_interval = max(0.05, base + jitter)
            return self._current_interval

        self._empty_index = 0
        self._current_interval = float(default_interval_seconds)
        return self._current_interval

    async def wait(self, delay_seconds: float) -> bool:
        if delay_seconds <= 0:
            await asyncio.sleep(0)
            return False
        woke = await self._wakeup.wait(delay_seconds)
        if woke:
            self._empty_index = 0
            self._current_interval = 0.0
        return woke

    async def close(self) -> None:
        await self._wakeup.close()

    def snapshot(self) -> WorkerWaitSnapshot:
        return WorkerWaitSnapshot(
            last_outcome=(self._last_outcome.value if self._last_outcome else None),
            current_interval_seconds=self._current_interval,
            empty_runs=self._empty_runs,
            processed_items=self._processed_items,
            wakeups=self._wakeup.wakeups,
            fallback_polls=self._wakeup.fallback_polls,
            listener_reconnects=self._wakeup.reconnects,
            listener_errors=self._wakeup.errors,
            oldest_queued_age_seconds=self._oldest_queued_age_seconds,
        )


__all__ = (
    "AdaptiveQueueWait",
    "WakeupSource",
    "WorkerIterationOutcome",
    "WorkerIterationResult",
    "WorkerWaitSnapshot",
)
