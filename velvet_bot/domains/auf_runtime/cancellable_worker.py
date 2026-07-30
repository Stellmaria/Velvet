from __future__ import annotations

from typing import Any

from velvet_bot.domains.ai_usage import AITask
from velvet_bot.domains.ai_usage.task_models import AITaskStatus
from velvet_bot.domains.media_generation.models import KieGenerationRequest
from velvet_bot.domains.media_generation.worker import _ProgressMessage


class AufCancellationRequested(RuntimeError):
    """The user stopped a task before a provider job had been submitted."""


def build_cancellable_worker_class(base_class: type[Any]) -> type[Any]:
    class CancellableAufWorker(base_class):
        async def _prepare_provider_request(
            self,
            *,
            task: AITask,
            request: KieGenerationRequest,
            runtime: dict[str, object],
            progress: _ProgressMessage | None,
        ) -> KieGenerationRequest:
            provider_request = await super()._prepare_provider_request(
                task=task,
                request=request,
                runtime=runtime,
                progress=progress,
            )
            active_provider_task_id = str(
                runtime.get("active_provider_task_id") or ""
            ).strip()
            if (
                not active_provider_task_id
                and await self._campaign_queue.cancellation_requested(task_id=task.id)
            ):
                raise AufCancellationRequested(
                    "Задача остановлена до отправки платного запроса провайдеру."
                )
            return provider_request

        async def _finish_terminal(
            self,
            *,
            task: AITask,
            request: KieGenerationRequest | None,
            progress: _ProgressMessage | None,
            error: Exception,
        ) -> None:
            cancellation_requested = isinstance(
                error, AufCancellationRequested
            ) or await self._campaign_queue.cancellation_requested(task_id=task.id)
            if not cancellation_requested:
                await super()._finish_terminal(
                    task=task,
                    request=request,
                    progress=progress,
                    error=error,
                )
                return

            cancelled = await self._campaign_queue.finish_cancelled(
                task_id=task.id,
                worker_id=self._worker_id,
                reason=str(error),
            )
            if cancelled is None:
                return
            if request is not None:
                await self._publish_progress(
                    progress,
                    task=task,
                    request=request,
                    percent=100,
                    stage=(
                        "Задача остановлена. Новый платный запрос провайдеру не отправлен."
                    ),
                    force=True,
                )

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
            failure_task = getattr(failure, "task", None)
            status = getattr(failure_task, "status", None)
            if status is AITaskStatus.CANCELLED or str(status) == AITaskStatus.CANCELLED.value:
                if request is not None:
                    await self._publish_progress(
                        progress,
                        task=task,
                        request=request,
                        percent=100,
                        stage=(
                            "Остановка выполнена. Завершившаяся ошибкой попытка не будет "
                            "запущена повторно."
                        ),
                        force=True,
                    )
                return
            await super()._report_retry_or_terminal(
                task=task,
                request=request,
                progress=progress,
                failure=failure,
                provider_attempt=provider_attempt,
                error=error,
            )

    CancellableAufWorker.__name__ = f"Cancellable{base_class.__name__}"
    CancellableAufWorker.__qualname__ = CancellableAufWorker.__name__
    return CancellableAufWorker


__all__ = (
    "AufCancellationRequested",
    "build_cancellable_worker_class",
)
