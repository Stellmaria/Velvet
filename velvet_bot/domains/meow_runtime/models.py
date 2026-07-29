from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class MeowProvider(StrEnum):
    KIE = "kie"
    GRS = "grs"

    @property
    def display_name(self) -> str:
        return "Kie.ai" if self is self.KIE else "GRS AI"

    @property
    def model_aliases(self) -> tuple[str, ...]:
        if self is self.GRS:
            return ("nano_banana_2", "nano_banana_pro")
        return (
            "seedream_5_pro",
            "grok_imagine_video",
            "seedance_15_pro_video",
            "wan_26_image_to_video",
        )


@dataclass(frozen=True, slots=True)
class MeowRuntimeSettings:
    kie_concurrency_limit: int
    grs_concurrency_limit: int
    workspace_default_limit: int
    workspace_max_limit: int
    configured: bool
    setup_notice_sent_at: datetime | None
    updated_by_user_id: int | None
    updated_at: datetime

    def limit_for(self, provider: MeowProvider) -> int:
        return (
            self.kie_concurrency_limit
            if provider is MeowProvider.KIE
            else self.grs_concurrency_limit
        )


@dataclass(frozen=True, slots=True)
class WorkspaceMeowSettings:
    workspace_id: int
    concurrency_limit: int
    updated_by_user_id: int | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MeowProviderSnapshot:
    provider: MeowProvider
    queued: int
    running: int


@dataclass(frozen=True, slots=True)
class MeowCancellationResult:
    task_id: UUID
    status: str
    cancel_requested: bool
    provider_task_started: bool


__all__ = (
    "MeowCancellationResult",
    "MeowProvider",
    "MeowProviderSnapshot",
    "MeowRuntimeSettings",
    "WorkspaceMeowSettings",
)
