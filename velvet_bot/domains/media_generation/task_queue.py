from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import replace
from uuid import UUID

from velvet_bot.application.media_delivery import DeliverMediaResult, ResolveProviderResult
from velvet_bot.application.media_tasks import task_payload_mapping, task_result_urls
from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import (
    AITask,
    AITaskFailureResult,
    AITaskQueueService,
    AITaskRepository,
)

logger = logging.getLogger(__name__)
_VIDEO_MODELS = frozenset(
    {
        "grok_imagine_video",
        "grok_imagine_video_15",
        "seedance_15_pro_video",
        "wan_26_image_to_video",
    }
)
_GRS_MODELS = frozenset({"nano_banana_2", "nano_banana_pro"})


class KieTaskQueueService(AITaskQueueService):
    """AI task queue plus durable provider-result delivery registration."""

    def __init__(
        self,
        *,
        database: Database,
        max_attempts: int = 50,
        delivery_resolver: ResolveProviderResult | None = None,
        delivery: DeliverMediaResult | None = None,
    ) -> None:
        super().__init__(AITaskRepository(database))
        self._database = database
        self._max_attempts = max(1, min(50, int(max_attempts)))
        self._delivery_resolver = delivery_resolver
        self._delivery = delivery

    @property
    def database(self) -> Database:
        return self._database

    @property
    def durable_delivery_enabled(self) -> bool:
        return self._delivery_resolver is not None and self._delivery is not None

    def configure_durable_delivery(
        self,
        *,
        resolver: ResolveProviderResult,
        delivery: DeliverMediaResult,
    ) -> None:
        """Bind the one application delivery runtime to an existing queue."""

        if self._delivery_resolver is None:
            self._delivery_resolver = resolver
        if self._delivery is None:
            self._delivery = delivery

    async def claim_next(
        self,
        *,
        worker_id: str,
        scopes: tuple[AIBudgetScope, ...] | None = None,
        task_types: tuple[str, ...] | None = None,
    ) -> AITask | None:
        task = await super().claim_next(
            worker_id=worker_id,
            scopes=scopes,
            task_types=task_types,
        )
        if task is None:
            return None
        task = await self._restore_successful_provider_task(
            task=task,
            worker_id=worker_id,
        )
        if task.max_attempts >= self._max_attempts:
            return task

        async with self._database.acquire() as connection:
            result = await connection.execute(
                """UPDATE ai_tasks
                   SET max_attempts=GREATEST(max_attempts,$2::INTEGER),updated_at=NOW()
                   WHERE id=$1::UUID AND status='running' AND locked_by=$3::VARCHAR""",
                task.id,
                self._max_attempts,
                worker_id.strip(),
            )
        if not result.endswith(" 1"):
            return task
        return replace(task, max_attempts=self._max_attempts)


    async def _restore_successful_provider_task(
        self,
        *,
        task: AITask,
        worker_id: str,
    ) -> AITask:
        """Resume polling the paid provider task after a pre-completion crash."""

        payload = task_payload_mapping(task.payload)
        runtime = task_payload_mapping(payload.get("kie_campaign"))
        provider_task_id = _first_text(runtime.get("last_provider_task_id"))
        if (
            str(runtime.get("status") or "").strip() != "success"
            or _first_text(runtime.get("active_provider_task_id")) is not None
            or provider_task_id is None
        ):
            return task

        runtime["active_provider_task_id"] = provider_task_id
        runtime["status"] = "running"
        payload["kie_campaign"] = runtime
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """UPDATE ai_tasks
                   SET payload=$3::JSONB,updated_at=NOW(),locked_at=NOW()
                   WHERE id=$1::UUID AND status='running' AND locked_by=$2::VARCHAR""",
                task.id,
                worker_id.strip(),
                json.dumps(payload, ensure_ascii=False, default=str),
            )
        if not result.endswith(" 1"):
            return task
        logger.warning(
            "Recovered successful provider task before queue completion task=%s provider_task=%s",
            task.id,
            provider_task_id,
        )
        return replace(task, payload=payload)

    async def patch_payload(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        patch: Mapping[str, object],
    ) -> bool:
        """Persist campaign state and register a submitted provider task id."""

        if not patch:
            return True
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """UPDATE ai_tasks
                   SET payload=payload || $3::JSONB,updated_at=NOW(),locked_at=NOW()
                   WHERE id=$1::UUID AND status='running' AND locked_by=$2::VARCHAR""",
                task_id,
                worker_id.strip(),
                json.dumps(dict(patch), ensure_ascii=False, default=str),
            )
        saved = result.endswith(" 1")
        if saved:
            await self._record_submission_best_effort(task_id=task_id, patch=patch)
        return saved

    async def complete(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        result: Mapping[str, object] | None = None,
    ) -> AITask | None:
        """Complete financial work, then deliver from separately durable state."""

        task = await super().complete(
            task_id=task_id,
            worker_id=worker_id,
            result=result,
        )
        if task is None:
            return None
        await self._record_success_best_effort(task=task, result=result or {})
        delivery = self._delivery
        if delivery is not None:
            try:
                await delivery.execute(task_id=task.id)
            except Exception:
                # Provider success and ai_tasks.result are already durable. Recovery
                # imports/retries this delivery without calling generation again.
                logger.exception(
                    "Durable media delivery failed after task completion task=%s",
                    task.id,
                )
        return task

    async def fail_terminal(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        error: BaseException,
    ) -> AITaskFailureResult | None:
        """Finish a permanent or financially ambiguous failure without retrying."""

        normalized_worker = worker_id.strip()
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """UPDATE ai_tasks
                   SET max_attempts=GREATEST(1,attempt_count),updated_at=NOW()
                   WHERE id=$1::UUID AND status='running' AND locked_by=$2::VARCHAR""",
                task_id,
                normalized_worker,
            )
        if not result.endswith(" 1"):
            return None
        return await super().fail(
            task_id=task_id,
            worker_id=normalized_worker,
            error=error,
            base_delay_seconds=0,
            max_delay_seconds=0,
        )

    async def _record_submission_best_effort(
        self,
        *,
        task_id: UUID,
        patch: Mapping[str, object],
    ) -> None:
        resolver = self._delivery_resolver
        if resolver is None:
            return
        runtime = task_payload_mapping(patch.get("kie_campaign"))
        provider_task_id = _first_text(
            runtime.get("active_provider_task_id"),
            runtime.get("last_provider_task_id"),
        )
        if provider_task_id is None:
            return
        try:
            async with self._database.acquire() as connection:
                payload_value = await connection.fetchval(
                    "SELECT payload FROM ai_tasks WHERE id=$1::UUID",
                    task_id,
                )
            payload = task_payload_mapping(payload_value)
            request = task_payload_mapping(payload.get("request"))
            model = str(request.get("model") or "").strip()
            await resolver.provider_submitted(
                task_id=task_id,
                provider=("grs" if model in _GRS_MODELS else "kie"),
                provider_task_id=provider_task_id,
                chat_id=_optional_int(payload.get("chat_id")),
                media_kind=("video" if model in _VIDEO_MODELS else "image"),
                request=_delivery_metadata(request),
            )
        except Exception:
            logger.exception(
                "Could not persist provider submission for media delivery task=%s",
                task_id,
            )

    async def _record_success_best_effort(
        self,
        *,
        task: AITask,
        result: Mapping[str, object],
    ) -> None:
        resolver = self._delivery_resolver
        if resolver is None:
            return
        payload = task_payload_mapping(task.payload)
        request = task_payload_mapping(payload.get("request"))
        runtime = task_payload_mapping(payload.get("kie_campaign"))
        model = str(request.get("model") or "").strip()
        provider_task_id = _first_text(
            result.get("provider_task_id"),
            runtime.get("last_provider_task_id"),
            runtime.get("active_provider_task_id"),
        )
        if provider_task_id is None:
            logger.error("Successful media task has no provider task id task=%s", task.id)
            return
        try:
            await resolver.provider_succeeded(
                task_id=task.id,
                provider=str(
                    result.get("provider")
                    or ("grs" if model in _GRS_MODELS else "kie")
                ).strip(),
                provider_task_id=provider_task_id,
                chat_id=_optional_int(payload.get("chat_id")),
                media_kind=("video" if model in _VIDEO_MODELS else "image"),
                request=_delivery_metadata(request),
                result_urls=task_result_urls(result),
            )
        except Exception:
            logger.exception(
                "Could not normalize provider success for media delivery task=%s",
                task.id,
            )


def _delivery_metadata(request: Mapping[str, object]) -> dict[str, object]:
    references = request.get("references")
    return {
        "model": str(request.get("model") or "").strip(),
        "resolution": str(request.get("resolution") or "").strip(),
        "aspect_ratio": str(request.get("aspect_ratio") or "").strip(),
        "content_mode": str(request.get("content_mode") or "").strip(),
        "reference_count": len(references) if isinstance(references, (list, tuple)) else 0,
    }


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


__all__ = ("KieTaskQueueService",)
