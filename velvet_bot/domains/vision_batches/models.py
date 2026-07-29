from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Mapping
from uuid import UUID


class VisionBatchStatus(StrEnum):
    PLANNED = "planned"
    STARTING = "starting"
    QUEUED = "queued"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class VisionBatchPlan:
    id: UUID
    task_type: str
    status: VisionBatchStatus
    candidate_ids: tuple[int, ...]
    candidate_count: int
    created_task_count: int
    deduplicated_task_count: int
    max_cost_per_item_rub: Decimal
    estimated_cost_rub: Decimal
    prompt_version: int
    created_by: int | None
    expires_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    last_error: str | None
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class VisionBatchProgress:
    plan: VisionBatchPlan
    queued: int = 0
    running: int = 0
    success: int = 0
    error: int = 0
    cancelled: int = 0

    @property
    def active(self) -> int:
        return self.queued + self.running

    @property
    def terminal(self) -> int:
        return self.success + self.error + self.cancelled

    @property
    def processed(self) -> int:
        return self.running + self.terminal


class VisionBatchError(RuntimeError):
    pass


__all__ = (
    "VisionBatchError",
    "VisionBatchPlan",
    "VisionBatchProgress",
    "VisionBatchStatus",
)
