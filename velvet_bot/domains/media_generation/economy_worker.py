from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from aiogram import Bot

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import (
    AIBudgetExceeded,
    AIProviderResult,
    AIRequestContext,
    AIRequestExecutor,
    AITask,
)
from velvet_bot.infrastructure.ai import (
    KieClient,
    KieError,
    KieProtocolError,
    KieTaskFailed,
    KieTransientError,
)

from .file_delivery_worker import KieGenerationWorker as DeliveryKieGenerationWorker
from .models import (
    KIE_GENERATION_TASK_TYPE,
    KieGenerationRequest,
    KiePricing,
    KieTaskRecord,
)
from .task_queue import KieTaskQueueService
from .worker import (
    _ProgressMessage,
    _optional_int,
    _provider_progress,
    _request_from_task,
)

logger = logging.getLogger(__name__)
_CAMPAIGN_KEY = "kie_campaign"
_HISTORY_LIMIT = 50


class KieSubmissionUncertain(RuntimeError):
    """createTask may have been accepted, so an automatic duplicate is unsafe."""


class KieCampaignExhausted(RuntimeError):
    pass


class KieCampaignPersistenceError(RuntimeError):
    pass


class KieGenerationWorker(DeliveryKieGenerationWorker):
    """Run one paid Kie attempt at a time and stop on the first success."""

    def __init__(
        self,
        *,
        bot: Bot,
        queue: KieTaskQueueService,
        client: KieClient,
        executor: AIRequestExecutor[KieTaskRecord],
        pricing: KiePricing,
        usd_to_rub: Decimal,
        worker_id: str = "kie-media-generation",
        heartbeat_seconds: int = 60,
    ) -> None:
        super().__init__(
            bot=bot,
            queue=queue,
            client=client,
            executor=executor,
            pricing=pricing,
            usd_to_rub=usd_to_rub,
            worker_id=worker_id,
            heartbeat_seconds=heartbeat_seconds,
        )
        self._campaign_queue = queue

    async def process_once(self) -> int:
        task = await self._campaign_queue.claim_next(
            worker_id=self._worker_id,
            scopes=(AIBudgetScope.VISION,),
            task_types=(KIE_GENERATION_TASK_TYPE,),
        )
        if task is None:
            return 0

        progress: _ProgressMessage | None = None
        request: KieGenerationRequest | None = None
        runtime = _campaign_runtime(task.payload)
        provider_attempt = _non_negative_int(runtime.get("provider_attempt_count"))
        active_provider_task_id = _optional_text(runtime.get("active_provider_task_id"))
        estimated_cost_rub = Decimal("0")
        chat_id: int | None = None

        try:
            request = _request_from_task(task)
            progress = await self._start_progress(task=task, request=request)
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=5,
                stage=(
                    f"Продолжаем уже созданную задачу Kie {active_provider_task_id}."
                    if active_provider_task_id
                    else "Экономная кампания взята worker-ом."
                ),
            )
            estimated_cost_rub = self._pricing.estimate_rub(
                request,
                usd_to_rub=self._usd_to_rub,
            )
            provider_model = self._client.models.provider_model_for_request(request)
            chat_id = _optional_int(task.payload.get("chat_id"))
            user_id = _optional_int(task.payload.get("user_id"))
            new_paid_attempt = active_provider_task_id is None
            context = AIRequestContext(
                scope=AIBudgetScope.VISION,
                provider=request.model.provider_name,
                model=provider_model,
                operation="media.generate",
                estimated_cost_rub=(estimated_cost_rub if new_paid_attempt else Decimal("0")),
                user_id=user_id,
                chat_id=chat_id,
                metadata={
                    "queue_task_id": str(task.id),
                    "model_alias": request.model.value,
                    "input_mode": request.input_mode.value,
                    "reference_count": len(request.references),
                    "content_mode": request.content_mode.value,
                    "aspect_ratio": request.aspect_ratio,
                    "resolution": request.resolution,
                    "queue_attempt": task.attempt_count,
                    "provider_attempt": provider_attempt + (1 if new_paid_attempt else 0),
                    "campaign_max_attempts": task.max_attempts,
                    "resuming_provider_task": not new_paid_attempt,
                },
            )

            async def provider_operation() -> AIProviderResult[KieTaskRecord]:
                nonlocal provider_attempt, active_provider_task_id, runtime
                await self._publish_progress(
                    progress,
                    task=task,
                    request=request,
                    percent=10,
                    stage="Подготовка сохранённого референса.",
                )
                provider_request = await self._prepare_provider_request(
                    task=task,
                    request=request,
                    runtime=runtime,
                    progress=progress,
                )

                provider_task_id = active_provider_task_id
                if provider_task_id is None:
                    if provider_attempt >= task.max_attempts:
                        raise KieCampaignExhausted(
                            f"Использованы все {task.max_attempts} платных попыток Kie."
                        )
                    provider_attempt += 1
                    await self._publish_progress(
                        progress,
                        task=task,
                        request=request,
                        percent=42,
                        stage=(
                            f"Платная попытка {provider_attempt}/{task.max_attempts}: "
                            "отправка в Kie.ai."
                        ),
                    )
                    try:
                        provider_task_id = await self._client.create_task(provider_request)
                    except KieTransientError as error:
                        raise KieSubmissionUncertain(
                            "Ответ createTask потерян или не подтверждён. Экономный режим "
                            "остановил автоповтор, чтобы не создать оплаченный дубликат."
                        ) from error
                    active_provider_task_id = provider_task_id
                    runtime.update(
                        {
                            "mode": "economy",
                            "provider_attempt_count": provider_attempt,
                            "active_provider_task_id": provider_task_id,
                            "last_provider_task_id": provider_task_id,
                            "status": "running",
                        }
                    )
                    await self._persist_runtime(task=task, runtime=runtime)
                    await self._publish_progress(
                        progress,
                        task=task,
                        request=request,
                        percent=50,
                        stage=(
                            f"Kie принял попытку {provider_attempt}/{task.max_attempts}: "
                            f"{provider_task_id}."
                        ),
                    )
                else:
                    await self._publish_progress(
                        progress,
                        task=task,
                        request=request,
                        percent=50,
                        stage=(
                            f"Возобновляем polling оплаченной попытки "
                            f"{provider_attempt}/{task.max_attempts}: {provider_task_id}."
                        ),
                    )

                async def on_provider_update(
                    record: KieTaskRecord,
                    poll_count: int,
                ) -> None:
                    percent, stage = _provider_progress(record, poll_count)
                    await self._publish_progress(
                        progress,
                        task=task,
                        request=request,
                        percent=percent,
                        stage=stage,
                    )

                try:
                    record = await self._wait_with_heartbeat(
                        queue_task_id=task.id,
                        provider_task_id=provider_task_id,
                        on_update=on_provider_update,
                    )
                except KieTaskFailed as error:
                    runtime = await self._record_provider_result(
                        task=task,
                        runtime=runtime,
                        record=error.record,
                        status="fail",
                    )
                    active_provider_task_id = None
                    raise

                runtime = await self._record_provider_result(
                    task=task,
                    runtime=runtime,
                    record=record,
                    status="success",
                )
                return AIProviderResult(
                    value=record,
                    actual_cost_rub=estimated_cost_rub,
                    metadata={
                        "provider_task_id": record.task_id,
                        "consumed_credits": record.consumed_credits,
                        "result_count": len(record.result_urls),
                        "model_alias": request.model.value,
                        "reference_count": len(request.references),
                        "content_mode": request.content_mode.value,
                        "provider_attempt": provider_attempt,
                        "campaign_max_attempts": task.max_attempts,
                        "campaign_mode": "economy",
                    },
                )

            def failure_usage(error: BaseException) -> AIProviderResult[object] | None:
                if not isinstance(error, KieTaskFailed):
                    return None
                record = error.record
                return AIProviderResult(
                    value=None,
                    actual_cost_rub=(
                        estimated_cost_rub
                        if record.consumed_credits > 0
                        else Decimal("0")
                    ),
                    metadata={
                        "provider_task_id": record.task_id,
                        "consumed_credits": record.consumed_credits,
                        "provider_state": record.state.value,
                        "failure_code": record.failure_code,
                        "failure_message": record.failure_message,
                        "provider_attempt": provider_attempt,
                        "campaign_max_attempts": task.max_attempts,
                        "campaign_mode": "economy",
                    },
                )

            record = await self._executor.execute(
                context=context,
                operation=provider_operation,
                failure_usage=failure_usage,
            )
            await self._campaign_queue.complete(
                task_id=task.id,
                worker_id=self._worker_id,
                result={
                    "provider": request.model.provider_name,
                    "provider_task_id": record.task_id,
                    "model_alias": request.model.value,
                    "input_mode": request.input_mode.value,
                    "reference_count": len(request.references),
                    "content_mode": request.content_mode.value,
                    "result_urls": list(record.result_urls),
                    "consumed_credits": record.consumed_credits,
                    "estimated_cost_rub": str(estimated_cost_rub),
                    "queue_attempt_count": task.attempt_count,
                    "provider_attempt_count": provider_attempt,
                    "campaign_mode": "economy",
                },
            )
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=100,
                stage=(
                    f"Готово на платной попытке {provider_attempt}/{task.max_attempts}. "
                    "Новые попытки остановлены."
                ),
            )
            await self._deliver_best_effort(
                chat_id=chat_id,
                request=request,
                record=record,
            )
        except asyncio.CancelledError as error:
            await self._campaign_queue.fail(
                task_id=task.id,
                worker_id=self._worker_id,
                error=error,
                base_delay_seconds=5,
                max_delay_seconds=30,
            )
            raise
        except KieTaskFailed as error:
            failure = await self._campaign_queue.fail(
                task_id=task.id,
                worker_id=self._worker_id,
                error=error,
                base_delay_seconds=5,
                max_delay_seconds=30,
            )
            await self._report_retry_or_terminal(
                task=task,
                request=request,
                progress=progress,
                failure=failure,
                provider_attempt=provider_attempt,
                error=error,
            )
        except (
            KieSubmissionUncertain,
            KieCampaignPersistenceError,
            KieCampaignExhausted,
            AIBudgetExceeded,
            KieProtocolError,
            ValueError,
        ) as error:
            await self._finish_terminal(
                task=task,
                request=request,
                progress=progress,
                error=error,
            )
        except KieTransientError as error:
            failure = await self._campaign_queue.fail(
                task_id=task.id,
                worker_id=self._worker_id,
                error=error,
                base_delay_seconds=5,
                max_delay_seconds=30,
            )
            await self._report_retry_or_terminal(
                task=task,
                request=request,
                progress=progress,
                failure=failure,
                provider_attempt=provider_attempt,
                error=error,
            )
        except KieError as error:
            await self._finish_terminal(
                task=task,
                request=request,
                progress=progress,
                error=error,
            )
        except (TimeoutError, RuntimeError, OSError) as error:
            failure = await self._campaign_queue.fail(
                task_id=task.id,
                worker_id=self._worker_id,
                error=error,
                base_delay_seconds=5,
                max_delay_seconds=30,
            )
            await self._report_retry_or_terminal(
                task=task,
                request=request,
                progress=progress,
                failure=failure,
                provider_attempt=provider_attempt,
                error=error,
            )
        return 1

    async def _prepare_provider_request(
        self,
        *,
        task: AITask,
        request: KieGenerationRequest,
        runtime: dict[str, object],
        progress: _ProgressMessage | None,
    ) -> KieGenerationRequest:
        if not request.references:
            return request
        cached_urls = _string_tuple(runtime.get("image_urls"))
        if len(cached_urls) == len(request.references):
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=35,
                stage="Используем уже загруженный референс Kie без повторной загрузки.",
            )
            return request.with_image_urls(cached_urls)

        provider_request = await super()._upload_references(
            queue_task_id=task.id,
            request=request,
            task=task,
            progress=progress,
        )
        runtime["image_urls"] = list(provider_request.image_urls)
        runtime["reference_file_names"] = [
            Path(reference.file_name or "reference.jpg").name
            for reference in request.references
        ]
        await self._persist_runtime(task=task, runtime=runtime)
        return provider_request

    async def _record_provider_result(
        self,
        *,
        task: AITask,
        runtime: dict[str, object],
        record: KieTaskRecord,
        status: str,
    ) -> dict[str, object]:
        history = _history(runtime.get("attempt_history"))
        history.append(
            {
                "attempt": _non_negative_int(runtime.get("provider_attempt_count")),
                "provider_task_id": record.task_id,
                "status": status,
                "consumed_credits": record.consumed_credits,
                "failure_code": record.failure_code,
                "failure_message": record.failure_message,
                "result_count": len(record.result_urls),
            }
        )
        runtime["attempt_history"] = history[-_HISTORY_LIMIT:]
        runtime["status"] = status
        runtime["last_provider_task_id"] = record.task_id
        runtime["last_consumed_credits"] = record.consumed_credits
        runtime["active_provider_task_id"] = None
        if status == "fail" and _reference_url_failure(record):
            runtime.pop("image_urls", None)
        await self._persist_runtime(task=task, runtime=runtime)
        return runtime

    async def _persist_runtime(
        self,
        *,
        task: AITask,
        runtime: Mapping[str, object],
    ) -> None:
        saved = await self._campaign_queue.patch_payload(
            task_id=task.id,
            worker_id=self._worker_id,
            patch={_CAMPAIGN_KEY: dict(runtime)},
        )
        if not saved:
            raise KieCampaignPersistenceError(
                "Не удалось сохранить taskId и состояние Kie-кампании. "
                "Автоповтор остановлен, чтобы не создать платный дубликат."
            )

    async def _finish_terminal(
        self,
        *,
        task: AITask,
        request: KieGenerationRequest | None,
        progress: _ProgressMessage | None,
        error: Exception,
    ) -> None:
        await self._campaign_queue.fail_terminal(
            task_id=task.id,
            worker_id=self._worker_id,
            error=error,
        )
        if request is not None:
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=100,
                stage=f"Экономная кампания остановлена без нового платного повтора: {error}",
                force=True,
            )
        await self._notify_terminal_failure_best_effort(task, error)

    async def _report_retry_or_terminal(
        self,
        *,
        task: AITask,
        request: KieGenerationRequest | None,
        progress: _ProgressMessage | None,
        failure: object,
        provider_attempt: int,
        error: Exception,
    ) -> None:
        will_retry = bool(getattr(failure, "will_retry", False))
        if request is not None and will_retry:
            delay = int(getattr(failure, "retry_delay_seconds", 0) or 0)
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=max(5, progress.last_percent if progress else 5),
                stage=(
                    f"Попытка Kie {provider_attempt}/{task.max_attempts} не дала результат. "
                    f"Следующая последовательная попытка через {delay} сек."
                ),
                force=True,
            )
            return
        if request is not None:
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=100,
                stage="Экономная кампания завершилась ошибкой после доступных попыток.",
                force=True,
            )
        await self._notify_terminal_failure_best_effort(task, error)


def _campaign_runtime(payload: Mapping[str, object]) -> dict[str, object]:
    value = payload.get(_CAMPAIGN_KEY)
    if isinstance(value, Mapping):
        return dict(value)
    return {
        "mode": "economy",
        "provider_attempt_count": 0,
        "attempt_history": [],
    }


def _history(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(text for item in value if (text := str(item or "").strip()))


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(str(value or "0").strip()))
    except (TypeError, ValueError):
        return 0


def _reference_url_failure(record: KieTaskRecord) -> bool:
    details = " ".join(
        value
        for value in (record.failure_code, record.failure_message)
        if value
    ).casefold()
    return any(token in details for token in ("expired", "download url", "image url"))


__all__ = (
    "KieCampaignExhausted",
    "KieCampaignPersistenceError",
    "KieGenerationWorker",
    "KieSubmissionUncertain",
)
