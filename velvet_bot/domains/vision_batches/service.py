from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.core.config import Settings
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import (
    AITaskQueueService,
    AITaskRequest,
    AITokenPricing,
    AIUsageService,
    load_token_pricing,
)
from velvet_bot.domains.vision_batches.models import (
    VisionBatchError,
    VisionBatchPlan,
    VisionBatchProgress,
    VisionBatchStatus,
)
from velvet_bot.domains.vision_batches.repository import VisionBatchRepository


VISION_BATCH_TASK_TYPE = "vision.semantic-profile"
_MAX_ESTIMATED_INPUT_TOKENS = 6000
_MAX_OUTPUT_TOKENS = 1200


class VisionBatchService:
    def __init__(
        self,
        *,
        repository: VisionBatchRepository,
        queue_service: AITaskQueueService,
        usage_service: AIUsageService,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._queue = queue_service
        self._usage = usage_service
        self._settings = settings

    @property
    def queue_enabled(self) -> bool:
        return _env_enabled("AI_VISION_QUEUE_ENABLED")

    @property
    def prompt_version(self) -> int:
        return _bounded_int(
            os.getenv("AI_VISION_PROMPT_VERSION", "1"),
            default=1,
            minimum=1,
            maximum=1_000_000,
        )

    @property
    def max_cost_per_item_rub(self) -> Decimal:
        if not self._settings.ai_vision_enabled:
            return Decimal("0")
        return _vision_cascade_max_cost(self._settings)

    async def plan(
        self,
        *,
        limit: int,
        created_by: int | None,
    ) -> VisionBatchPlan:
        if not self._settings.ai_vision_enabled:
            raise VisionBatchError(
                "Сначала настройте и включите AI_VISION_ENABLED=true."
            )
        candidate_ids = await self._repository.find_candidates(limit=limit)
        per_item = self.max_cost_per_item_rub
        estimated = per_item * len(candidate_ids)
        budget = await self._usage.status()
        available = min(
            budget.daily_remaining_rub,
            budget.ordinary_month_remaining_rub,
        )
        ttl_seconds = _bounded_int(
            os.getenv("AI_VISION_BATCH_PLAN_TTL_SECONDS", "900"),
            default=900,
            minimum=60,
            maximum=86400,
        )
        return await self._repository.create_plan(
            plan_id=uuid4(),
            candidate_ids=candidate_ids,
            max_cost_per_item_rub=per_item,
            estimated_cost_rub=estimated,
            prompt_version=self.prompt_version,
            created_by=created_by,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
            metadata={
                "queue_enabled": self.queue_enabled,
                "daily_remaining_rub": str(budget.daily_remaining_rub),
                "ordinary_month_remaining_rub": str(
                    budget.ordinary_month_remaining_rub
                ),
                "max_request_rub": str(budget.max_request_rub),
                "within_per_request_limit": per_item <= budget.max_request_rub,
                "within_current_budget": estimated <= available,
            },
        )

    async def start(
        self,
        *,
        plan_id: UUID,
        created_by: int | None,
    ) -> VisionBatchPlan:
        if not self._settings.ai_vision_enabled:
            raise VisionBatchError("VL-контур выключен: AI_VISION_ENABLED=false.")
        if not self.queue_enabled:
            raise VisionBatchError(
                "Пакетная очередь выключена: AI_VISION_QUEUE_ENABLED=false."
            )
        plan = await self._repository.get(plan_id=plan_id)
        if plan is None:
            raise VisionBatchError("План VL-партии не найден.")
        if plan.status is not VisionBatchStatus.PLANNED:
            raise VisionBatchError(
                f"План нельзя запустить из статуса {plan.status.value}."
            )
        if plan.expires_at <= datetime.now(timezone.utc):
            await self._repository.claim_start(plan_id=plan_id)
            raise VisionBatchError("Срок подтверждения VL-партии истёк.")
        budget = await self._usage.status()
        if budget.paused:
            reason = f" Причина: {budget.pause_reason}" if budget.pause_reason else ""
            raise VisionBatchError("AI-контур приостановлен." + reason)
        if plan.max_cost_per_item_rub > budget.max_request_rub:
            raise VisionBatchError(
                "Максимальная стоимость одного VL-запроса превышает per-request лимит."
            )
        if plan.estimated_cost_rub > budget.daily_remaining_rub:
            raise VisionBatchError(
                "Максимальная стоимость партии превышает дневной остаток бюджета."
            )
        if plan.estimated_cost_rub > budget.ordinary_month_remaining_rub:
            raise VisionBatchError(
                "Максимальная стоимость партии превышает обычный месячный остаток."
            )

        claimed = await self._repository.claim_start(plan_id=plan_id)
        if claimed is None:
            raise VisionBatchError("План уже запущен, отменён либо истёк.")
        try:
            requests = tuple(
                AITaskRequest(
                    scope=AIBudgetScope.VISION,
                    task_type=VISION_BATCH_TASK_TYPE,
                    payload={
                        "media_id": media_id,
                        "prompt_version": claimed.prompt_version,
                        "batch_id": str(claimed.id),
                    },
                    priority=100,
                    dedupe_key=(
                        f"{VISION_BATCH_TASK_TYPE}:{media_id}:"
                        f"v{claimed.prompt_version}"
                    ),
                    max_attempts=self._settings.ai_vision_max_attempts,
                    created_by=created_by,
                    estimated_cost_rub=claimed.max_cost_per_item_rub,
                )
                for media_id in claimed.candidate_ids
            )
            results = await self._queue.enqueue_many(requests)
            created_ids = tuple(
                result.task.id for result in results if result.created
            )
            await self._repository.attach_created_tasks(
                plan_id=claimed.id,
                task_ids=created_ids,
            )
            return await self._repository.mark_queued(
                plan_id=claimed.id,
                created_task_count=len(created_ids),
                deduplicated_task_count=len(results) - len(created_ids),
            )
        except Exception as error:
            await self._repository.mark_error(plan_id=claimed.id, error=error)
            raise

    async def status(
        self,
        *,
        plan_id: UUID | None,
        created_by: int | None,
    ) -> VisionBatchProgress | None:
        plan = (
            await self._repository.get(plan_id=plan_id)
            if plan_id is not None
            else await self._repository.latest(created_by=created_by)
        )
        if plan is None:
            return None
        return await self._repository.progress(plan_id=plan.id)

    async def cancel(
        self,
        *,
        plan_id: UUID,
        reason: str,
    ) -> VisionBatchPlan | None:
        return await self._repository.cancel(plan_id=plan_id, reason=reason)


def build_vision_batch_service(
    *,
    settings: Settings,
    database: Database,
    usage_service: AIUsageService,
    queue_service: AITaskQueueService,
) -> VisionBatchService:
    return VisionBatchService(
        repository=VisionBatchRepository(database),
        queue_service=queue_service,
        usage_service=usage_service,
        settings=settings,
    )


def _vision_cascade_max_cost(settings: Settings) -> Decimal:
    routes: tuple[tuple[str, str], ...] = (
        (
            "FLASH",
            os.getenv("AI_VISION_FLASH_MODEL", "").strip()
            or settings.ai_vision_model,
        ),
        (
            "PRO",
            os.getenv("AI_VISION_PRO_MODEL", "").strip()
            or settings.ai_vision_compare_model
            or "",
        ),
        (
            "SENSITIVE",
            os.getenv("AI_VISION_SENSITIVE_MODEL", "").strip()
            or settings.ai_vision_fallback_model
            or "",
        ),
    )
    total = Decimal("0")
    for route, model in routes:
        if not model:
            continue
        prefix = f"AI_VISION_{route}"
        provider = (
            os.getenv(f"{prefix}_PROVIDER", "").strip().casefold()
            or settings.ai_vision_provider
        )
        pricing = (
            AITokenPricing(
                input_rub_per_million=Decimal("0"),
                output_rub_per_million=Decimal("0"),
            )
            if provider == "ollama"
            else load_token_pricing(prefix)
        )
        total += pricing.cost(
            input_tokens=_MAX_ESTIMATED_INPUT_TOKENS,
            output_tokens=_MAX_OUTPUT_TOKENS,
        )
    return total


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
        "да",
    }


def _bounded_int(
    value: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value.strip())
    except (AttributeError, TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


__all__ = (
    "VISION_BATCH_TASK_TYPE",
    "VisionBatchService",
    "build_vision_batch_service",
)
