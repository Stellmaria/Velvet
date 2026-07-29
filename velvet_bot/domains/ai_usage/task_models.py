from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Mapping
from uuid import UUID

from velvet_bot.core.ai_budget import AIBudgetScope


class AITaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AITaskRequest:
    scope: AIBudgetScope
    task_type: str
    payload: Mapping[str, object] = field(default_factory=dict)
    priority: int = 100
    dedupe_key: str | None = None
    max_attempts: int = 2
    not_before: datetime | None = None
    created_by: int | None = None
    estimated_cost_rub: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.task_type.strip():
            raise ValueError("AI task_type не может быть пустым.")
        if not 0 <= int(self.priority) <= 1000:
            raise ValueError("AI priority должен быть от 0 до 1000.")
        if not 1 <= int(self.max_attempts) <= 50:
            raise ValueError("AI max_attempts должен быть от 1 до 50.")
        if self.estimated_cost_rub < 0:
            raise ValueError("Оценочная стоимость AI-задачи не может быть отрицательной.")
        if self.dedupe_key is not None and not self.dedupe_key.strip():
            raise ValueError("AI dedupe_key не может быть пустой строкой.")


@dataclass(frozen=True, slots=True)
class AITask:
    id: UUID
    scope: AIBudgetScope
    task_type: str
    status: AITaskStatus
    priority: int
    payload: Mapping[str, object]
    result: Mapping[str, object]
    dedupe_key: str | None
    attempt_count: int
    max_attempts: int
    not_before: datetime
    locked_by: str | None
    locked_at: datetime | None
    last_error_type: str | None
    last_error: str | None
    last_retry_delay_seconds: int | None
    estimated_cost_rub: Decimal
    created_by: int | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @property
    def terminal(self) -> bool:
        return self.status in {
            AITaskStatus.SUCCESS,
            AITaskStatus.ERROR,
            AITaskStatus.CANCELLED,
        }


@dataclass(frozen=True, slots=True)
class AITaskEnqueueResult:
    task: AITask
    created: bool


@dataclass(frozen=True, slots=True)
class AITaskFailureResult:
    task: AITask
    will_retry: bool
    retry_delay_seconds: int | None


@dataclass(frozen=True, slots=True)
class AITaskQueueSnapshot:
    queued: int = 0
    running: int = 0
    success: int = 0
    error: int = 0
    cancelled: int = 0
    paused: bool = False
    pause_reason: str | None = None

    @property
    def active(self) -> int:
        return self.queued + self.running


__all__ = (
    "AITask",
    "AITaskEnqueueResult",
    "AITaskFailureResult",
    "AITaskQueueSnapshot",
    "AITaskRequest",
    "AITaskStatus",
)
