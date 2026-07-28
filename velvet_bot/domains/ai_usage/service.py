from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Generic, TypeVar
from uuid import uuid4
from zoneinfo import ZoneInfo

from velvet_bot.core.ai_budget import AIBudgetDecision, AIBudgetPolicy
from velvet_bot.domains.ai_usage.models import (
    AIProviderResult,
    AIRequestContext,
    AIReservation,
    AIUsageTotals,
)
from velvet_bot.domains.ai_usage.repository import AIUsageRepository

T = TypeVar("T")


class AIBudgetExceeded(RuntimeError):
    def __init__(
        self,
        decision: AIBudgetDecision,
        *,
        pause_reason: str | None = None,
    ) -> None:
        self.decision = decision
        self.pause_reason = pause_reason
        message = decision.reason
        if pause_reason:
            message = f"{message} Причина: {pause_reason}"
        super().__init__(message)


class AIUsageService:
    def __init__(
        self,
        repository: AIUsageRepository,
        policy: AIBudgetPolicy,
        *,
        budget_timezone: str = "Europe/Warsaw",
    ) -> None:
        self._repository = repository
        self.policy = policy
        try:
            self._timezone = ZoneInfo(budget_timezone)
        except Exception as error:
            raise ValueError(f"Неизвестная timezone AI-бюджета: {budget_timezone}") from error

    async def reserve(self, context: AIRequestContext) -> AIReservation:
        now = datetime.now(self._timezone)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        decision, reservation, pause_reason = await self._repository.reserve_if_allowed(
            request_id=uuid4(),
            context=context,
            policy=self.policy,
            day_start=day_start,
            month_start=month_start,
        )
        if reservation is None:
            raise AIBudgetExceeded(decision, pause_reason=pause_reason)
        return reservation

    async def complete(
        self,
        reservation: AIReservation,
        result: AIProviderResult[object],
        *,
        latency_ms: int,
    ) -> None:
        updated = await self._repository.complete(
            request_id=reservation.request_id,
            actual_cost_rub=result.actual_cost_rub,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency_ms,
        )
        if not updated:
            raise RuntimeError("AI reservation уже завершена или не найдена.")

    async def fail(
        self,
        reservation: AIReservation,
        error: BaseException,
        *,
        latency_ms: int,
    ) -> None:
        await self._repository.fail(
            request_id=reservation.request_id,
            latency_ms=latency_ms,
            error=error,
        )

    async def cancel(self, reservation: AIReservation, *, reason: str) -> None:
        await self._repository.cancel(
            request_id=reservation.request_id,
            reason=reason,
        )

    async def totals(self) -> AIUsageTotals:
        now = datetime.now(self._timezone)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        return await self._repository.totals(
            day_start=day_start,
            month_start=month_start,
        )

    async def pause(self, *, reason: str, updated_by: int | None) -> None:
        await self._repository.set_paused(
            paused=True,
            reason=reason,
            updated_by=updated_by,
        )

    async def resume(self, *, updated_by: int | None) -> None:
        await self._repository.set_paused(
            paused=False,
            reason=None,
            updated_by=updated_by,
        )


class AIRequestExecutor(Generic[T]):
    """Reserve budget, run a provider call and persist its actual usage."""

    def __init__(self, usage_service: AIUsageService) -> None:
        self._usage_service = usage_service

    async def execute(
        self,
        *,
        context: AIRequestContext,
        operation: Callable[[], Awaitable[AIProviderResult[T]]],
    ) -> T:
        reservation = await self._usage_service.reserve(context)
        started = time.monotonic()
        try:
            result = await operation()
        except asyncio.CancelledError:
            await self._usage_service.cancel(
                reservation,
                reason="AI request task was cancelled.",
            )
            raise
        except BaseException as error:
            latency_ms = _latency_ms(started)
            await self._usage_service.fail(
                reservation,
                error,
                latency_ms=latency_ms,
            )
            raise

        latency_ms = _latency_ms(started)
        await self._usage_service.complete(
            reservation,
            result,  # type: ignore[arg-type]
            latency_ms=latency_ms,
        )
        return result.value


def _latency_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


__all__ = ("AIBudgetExceeded", "AIRequestExecutor", "AIUsageService")
