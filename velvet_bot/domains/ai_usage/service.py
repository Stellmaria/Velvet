from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Generic, TypeVar, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from velvet_bot.core.ai_budget import AIBudgetDecision, AIBudgetPolicy, AIBudgetScope
from velvet_bot.domains.ai_usage.ledger import AIUsageRepository
from velvet_bot.domains.ai_usage.models import (
    AIBudgetStatus,
    AIBudgetWarning,
    AIProviderResult,
    AIRequestContext,
    AIReservation,
    AIUsageEvent,
    AIUsageTotals,
)

T = TypeVar("T")
BudgetWarningHandler = Callable[[AIBudgetWarning], Awaitable[None]]


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
        warning_handler: BudgetWarningHandler | None = None,
    ) -> None:
        self._repository = repository
        self.policy = policy
        self._warning_handler = warning_handler
        try:
            self._timezone = ZoneInfo(budget_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Неизвестная timezone AI-бюджета: {budget_timezone}") from error

    def _period_bounds(self) -> tuple[datetime, datetime]:
        now = datetime.now(self._timezone)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return day_start, day_start.replace(day=1)

    async def reserve(self, context: AIRequestContext) -> AIReservation:
        day_start, month_start = self._period_bounds()
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
        result: AIProviderResult[T],
        *,
        latency_ms: int,
    ) -> None:
        updated = await self._repository.complete(
            request_id=reservation.request_id,
            actual_cost_rub=result.actual_cost_rub,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency_ms,
            metadata=dict(result.metadata),
        )
        if not updated:
            raise RuntimeError("AI reservation уже завершена или не найдена.")
        await self._emit_budget_warning_if_needed()

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
        day_start, month_start = self._period_bounds()
        return await self._repository.totals(
            day_start=day_start,
            month_start=month_start,
        )

    async def status(self) -> AIBudgetStatus:
        totals = await self.totals()
        runtime = await self._repository.runtime_state()
        today_with_reservations = totals.today_rub + totals.reserved_today_rub
        month_with_reservations = totals.month_rub + totals.reserved_month_rub
        ordinary_month_cap = max(
            Decimal("0"),
            self.policy.monthly_limit_rub - self.policy.hermes_reserve_rub,
        )
        return AIBudgetStatus(
            enabled=self.policy.enabled,
            daily_limit_rub=self.policy.daily_limit_rub,
            monthly_limit_rub=self.policy.monthly_limit_rub,
            max_request_rub=self.policy.max_request_rub,
            hermes_reserve_rub=self.policy.hermes_reserve_rub,
            today_rub=totals.today_rub,
            month_rub=totals.month_rub,
            reserved_today_rub=totals.reserved_today_rub,
            reserved_month_rub=totals.reserved_month_rub,
            daily_remaining_rub=max(
                Decimal("0"), self.policy.daily_limit_rub - today_with_reservations
            ),
            ordinary_month_remaining_rub=max(
                Decimal("0"), ordinary_month_cap - month_with_reservations
            ),
            total_month_remaining_rub=max(
                Decimal("0"), self.policy.monthly_limit_rub - month_with_reservations
            ),
            paused=bool(runtime["paused"]),
            pause_reason=cast(str | None, runtime["pause_reason"]),
            updated_by=cast(int | None, runtime["updated_by"]),
            updated_at=cast(datetime, runtime["updated_at"]),
            warning_month=cast(date | None, runtime["warning_month"]),
            warning_percent=cast(int | None, runtime["warning_percent"]),
        )

    async def recent_events(self, *, limit: int = 20) -> tuple[AIUsageEvent, ...]:
        rows = await self._repository.recent_events(limit=limit)
        return tuple(
            AIUsageEvent(
                request_id=cast(UUID, row["request_id"]),
                scope=AIBudgetScope(str(row["scope"])),
                provider=str(row["provider"]),
                model=str(row["model"]),
                operation=str(row["operation"]),
                status=str(row["status"]),
                estimated_cost_rub=Decimal(row["estimated_cost_rub"] or 0),
                actual_cost_rub=Decimal(row["actual_cost_rub"] or 0),
                input_tokens=int(row["input_tokens"] or 0),
                output_tokens=int(row["output_tokens"] or 0),
                latency_ms=(
                    int(row["latency_ms"])
                    if row["latency_ms"] is not None
                    else None
                ),
                user_id=int(row["user_id"]) if row["user_id"] is not None else None,
                chat_id=int(row["chat_id"]) if row["chat_id"] is not None else None,
                created_at=cast(datetime, row["created_at"]),
                completed_at=cast(datetime | None, row["completed_at"]),
                error_type=str(row["error_type"] or "") or None,
                error_message=str(row["error_message"] or "") or None,
            )
            for row in rows
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

    async def _emit_budget_warning_if_needed(self) -> None:
        if not self.policy.enabled or self._warning_handler is None:
            return
        if self.policy.monthly_limit_rub <= 0:
            return
        totals = await self.totals()
        projected_month = totals.month_rub + totals.reserved_month_rub
        ratio = projected_month * Decimal(100) / self.policy.monthly_limit_rub
        reached = tuple(
            percent for percent in self.policy.warning_percents if ratio >= percent
        )
        if not reached:
            return
        threshold = max(reached)
        _, month_start = self._period_bounds()
        claimed = await self._repository.claim_budget_warning(
            period_start=month_start.date(),
            threshold_percent=threshold,
        )
        if not claimed:
            return
        warning = AIBudgetWarning(
            threshold_percent=threshold,
            month_rub=projected_month,
            monthly_limit_rub=self.policy.monthly_limit_rub,
            remaining_rub=max(
                Decimal("0"), self.policy.monthly_limit_rub - projected_month
            ),
            period_start=month_start.date(),
        )
        await self._warning_handler(warning)


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
            result,
            latency_ms=latency_ms,
        )
        return result.value


def _latency_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


__all__ = (
    "AIBudgetExceeded",
    "AIRequestExecutor",
    "AIUsageService",
    "BudgetWarningHandler",
)
