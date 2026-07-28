from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from velvet_bot.core.ai_budget import (
    AIBudgetDecision,
    AIBudgetGuard,
    AIBudgetPolicy,
    AIUsageSnapshot,
)
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage.models import (
    AIRequestContext,
    AIReservation,
    AIUsageTotals,
)


class AIUsageRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def reserve_if_allowed(
        self,
        *,
        request_id: UUID,
        context: AIRequestContext,
        policy: AIBudgetPolicy,
        day_start: datetime,
        month_start: datetime,
    ) -> tuple[AIBudgetDecision, AIReservation | None, str | None]:
        guard = AIBudgetGuard(policy)
        async with self._database.acquire() as connection:
            async with connection.transaction():
                runtime = await connection.fetchrow(
                    """SELECT paused,pause_reason
                       FROM ai_runtime_state
                       WHERE singleton_id=1
                       FOR UPDATE"""
                )
                if runtime is None:
                    raise RuntimeError("AI runtime state не инициализирован.")
                if bool(runtime["paused"]):
                    decision = AIBudgetDecision(
                        allowed=False,
                        reason="AI-запросы приостановлены владельцем.",
                        estimated_cost_rub=context.estimated_cost_rub,
                        daily_remaining_rub=Decimal("0"),
                        monthly_remaining_rub=Decimal("0"),
                    )
                    return decision, None, str(runtime["pause_reason"] or "") or None

                totals = await self._fetch_totals(
                    connection,
                    day_start=day_start,
                    month_start=month_start,
                )
                usage = AIUsageSnapshot(
                    today_rub=totals.today_rub + totals.reserved_today_rub,
                    month_rub=totals.month_rub + totals.reserved_month_rub,
                )
                decision = guard.evaluate(
                    scope=context.scope,
                    estimated_cost_rub=context.estimated_cost_rub,
                    usage=usage,
                )
                if not decision.allowed:
                    return decision, None, None

                row = await connection.fetchrow(
                    """INSERT INTO ai_usage_events(
                           request_id,scope,provider,model,operation,status,
                           estimated_cost_rub,user_id,chat_id,metadata)
                       VALUES(
                           $1::UUID,$2::VARCHAR,$3::VARCHAR,$4::VARCHAR,$5::VARCHAR,
                           'reserved',$6::NUMERIC,$7::BIGINT,$8::BIGINT,$9::JSONB)
                       RETURNING created_at""",
                    request_id,
                    context.scope.value,
                    context.provider.strip(),
                    context.model.strip(),
                    context.operation.strip(),
                    context.estimated_cost_rub,
                    context.user_id,
                    context.chat_id,
                    json.dumps(dict(context.metadata), ensure_ascii=False, default=str),
                )
                if row is None:
                    raise RuntimeError("Не удалось зарезервировать AI-бюджет.")
                reservation = AIReservation(
                    request_id=request_id,
                    context=context,
                    created_at=row["created_at"],
                    daily_remaining_rub=decision.daily_remaining_rub,
                    monthly_remaining_rub=decision.monthly_remaining_rub,
                    warning_percent=decision.warning_percent,
                )
                return decision, reservation, None

    async def complete(
        self,
        *,
        request_id: UUID,
        actual_cost_rub: Decimal,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        return await self._finish(
            request_id=request_id,
            status="success",
            actual_cost_rub=actual_cost_rub,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            metadata=metadata,
            error_type=None,
            error_message=None,
        )

    async def fail(
        self,
        *,
        request_id: UUID,
        latency_ms: int,
        error: BaseException,
        actual_cost_rub: Decimal = Decimal("0"),
        input_tokens: int = 0,
        output_tokens: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        return await self._finish(
            request_id=request_id,
            status="error",
            actual_cost_rub=actual_cost_rub,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            metadata=metadata,
            error_type=type(error).__name__[:160],
            error_message=str(error)[:8000],
        )

    async def cancel(self, *, request_id: UUID, reason: str) -> bool:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """UPDATE ai_usage_events
                   SET status='cancelled',completed_at=NOW(),error_message=$2::TEXT
                   WHERE request_id=$1::UUID AND status='reserved'""",
                request_id,
                reason[:8000],
            )
        return result.endswith(" 1")

    async def totals(
        self,
        *,
        day_start: datetime,
        month_start: datetime,
    ) -> AIUsageTotals:
        async with self._database.acquire() as connection:
            return await self._fetch_totals(
                connection,
                day_start=day_start,
                month_start=month_start,
            )

    async def set_paused(
        self,
        *,
        paused: bool,
        reason: str | None,
        updated_by: int | None,
    ) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """UPDATE ai_runtime_state
                   SET paused=$1::BOOLEAN,pause_reason=$2::TEXT,
                       updated_by=$3::BIGINT,updated_at=NOW()
                   WHERE singleton_id=1""",
                bool(paused),
                (reason or "").strip() or None,
                updated_by,
            )

    async def runtime_state(self) -> dict[str, object]:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT paused,pause_reason,updated_by,updated_at
                   FROM ai_runtime_state WHERE singleton_id=1"""
            )
        if row is None:
            raise RuntimeError("AI runtime state не найден.")
        return {
            "paused": bool(row["paused"]),
            "pause_reason": str(row["pause_reason"] or "") or None,
            "updated_by": int(row["updated_by"]) if row["updated_by"] is not None else None,
            "updated_at": row["updated_at"],
        }

    async def release_stale_reservations(self, *, older_than: datetime) -> int:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """UPDATE ai_usage_events
                   SET status='cancelled',completed_at=NOW(),
                       error_type='StaleReservation',
                       error_message='Reservation expired before provider completion.'
                   WHERE status='reserved' AND created_at<$1::TIMESTAMPTZ""",
                older_than,
            )
        return _command_count(result)

    async def recent_events(self, *, limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 200))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """SELECT request_id,scope,provider,model,operation,status,
                          estimated_cost_rub,actual_cost_rub,input_tokens,
                          output_tokens,latency_ms,user_id,chat_id,created_at,
                          completed_at,error_type,error_message
                   FROM ai_usage_events
                   ORDER BY id DESC LIMIT $1::INTEGER""",
                safe_limit,
            )
        return [dict(row) for row in rows]

    async def _finish(
        self,
        *,
        request_id: UUID,
        status: str,
        actual_cost_rub: Decimal,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        metadata: dict[str, object] | None,
        error_type: str | None,
        error_message: str | None,
    ) -> bool:
        if actual_cost_rub < 0:
            raise ValueError("Фактическая стоимость не может быть отрицательной.")
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Количество токенов не может быть отрицательным.")
        patch = json.dumps(metadata or {}, ensure_ascii=False, default=str)
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """UPDATE ai_usage_events
                   SET status=$2::VARCHAR,actual_cost_rub=$3::NUMERIC,
                       input_tokens=$4::BIGINT,output_tokens=$5::BIGINT,
                       latency_ms=$6::BIGINT,
                       metadata=metadata || $7::JSONB,
                       error_type=$8::VARCHAR,error_message=$9::TEXT,
                       completed_at=NOW()
                   WHERE request_id=$1::UUID AND status='reserved'""",
                request_id,
                status,
                actual_cost_rub,
                int(input_tokens),
                int(output_tokens),
                max(0, int(latency_ms)),
                patch,
                error_type,
                error_message,
            )
        return result.endswith(" 1")

    @staticmethod
    async def _fetch_totals(
        connection: Any,
        *,
        day_start: datetime,
        month_start: datetime,
    ) -> AIUsageTotals:
        row = await connection.fetchrow(
            """SELECT
                   COALESCE(SUM(actual_cost_rub) FILTER (
                       WHERE status IN ('success','error') AND created_at >= $1
                   ),0) AS today_rub,
                   COALESCE(SUM(actual_cost_rub) FILTER (
                       WHERE status IN ('success','error') AND created_at >= $2
                   ),0) AS month_rub,
                   COALESCE(SUM(estimated_cost_rub) FILTER (
                       WHERE status='reserved' AND created_at >= $1
                   ),0) AS reserved_today_rub,
                   COALESCE(SUM(estimated_cost_rub) FILTER (
                       WHERE status='reserved' AND created_at >= $2
                   ),0) AS reserved_month_rub
               FROM ai_usage_events
               WHERE created_at >= $2::TIMESTAMPTZ""",
            day_start,
            month_start,
        )
        if row is None:
            return AIUsageTotals(today_rub=Decimal("0"), month_rub=Decimal("0"))
        return AIUsageTotals(
            today_rub=Decimal(row["today_rub"] or 0),
            month_rub=Decimal(row["month_rub"] or 0),
            reserved_today_rub=Decimal(row["reserved_today_rub"] or 0),
            reserved_month_rub=Decimal(row["reserved_month_rub"] or 0),
        )


def _command_count(result: str) -> int:
    try:
        return int(result.rsplit(" ", 1)[-1])
    except (TypeError, ValueError):
        return 0


__all__ = ("AIUsageRepository",)
