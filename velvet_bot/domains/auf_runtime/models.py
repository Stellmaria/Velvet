from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class AufProvider(StrEnum):
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
            "qwen2_image_edit",
            "wan_27_image",
            "flux_2_pro_image",
            "grok_imagine_video",
            "grok_imagine_video_15",
            "seedance_15_pro_video",
            "wan_26_image_to_video",
        )


@dataclass(frozen=True, slots=True)
class AufRuntimeSettings:
    kie_concurrency_limit: int
    grs_concurrency_limit: int
    workspace_default_limit: int
    workspace_max_limit: int
    configured: bool
    setup_notice_sent_at: datetime | None
    updated_by_user_id: int | None
    updated_at: datetime

    def limit_for(self, provider: AufProvider) -> int:
        return (
            self.kie_concurrency_limit
            if provider is AufProvider.KIE
            else self.grs_concurrency_limit
        )


@dataclass(frozen=True, slots=True)
class WorkspaceAufSettings:
    workspace_id: int
    concurrency_limit: int
    updated_by_user_id: int | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AufProviderSnapshot:
    provider: AufProvider
    queued: int
    running: int


@dataclass(frozen=True, slots=True)
class AufCancellationResult:
    task_id: UUID
    status: str
    cancel_requested: bool
    provider_task_started: bool


__all__ = (
    "AufCancellationResult",
    "AufProvider",
    "AufProviderSnapshot",
    "AufRuntimeSettings",
    "WorkspaceAufSettings",
)
