from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Generic, Mapping, TypeVar
from uuid import UUID

from velvet_bot.core.ai_budget import AIBudgetScope

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class AIRequestContext:
    scope: AIBudgetScope
    provider: str
    model: str
    operation: str
    estimated_cost_rub: Decimal
    user_id: int | None = None
    chat_id: int | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("AI provider не может быть пустым.")
        if not self.model.strip():
            raise ValueError("AI model не может быть пустой.")
        if not self.operation.strip():
            raise ValueError("AI operation не может быть пустой.")
        if self.estimated_cost_rub < 0:
            raise ValueError("Оценочная стоимость AI-запроса не может быть отрицательной.")


@dataclass(frozen=True, slots=True)
class AIUsageTotals:
    today_rub: Decimal
    month_rub: Decimal
    reserved_today_rub: Decimal = Decimal("0")
    reserved_month_rub: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class AIReservation:
    request_id: UUID
    context: AIRequestContext
    created_at: datetime
    daily_remaining_rub: Decimal
    monthly_remaining_rub: Decimal
    warning_percent: int | None = None


@dataclass(frozen=True, slots=True)
class AIProviderResult(Generic[T]):
    value: T
    input_tokens: int = 0
    output_tokens: int = 0
    actual_cost_rub: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("Количество токенов не может быть отрицательным.")
        if self.actual_cost_rub < 0:
            raise ValueError("Фактическая стоимость не может быть отрицательной.")


__all__ = (
    "AIProviderResult",
    "AIRequestContext",
    "AIReservation",
    "AIUsageTotals",
)
