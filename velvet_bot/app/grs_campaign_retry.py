from __future__ import annotations

import importlib
from dataclasses import replace
from decimal import Decimal
from html import escape
from typing import Callable

from aiogram.exceptions import TelegramAPIError

import velvet_bot.app.grs_resilience as grs_resilience
from velvet_bot.domains.ai_usage import AITask
from velvet_bot.domains.media_generation.models import KieGenerationRequest
from velvet_bot.domains.media_generation.task_queue import KieTaskQueueService
from velvet_bot.domains.media_generation.worker import _ProgressMessage, _optional_int
from velvet_bot.infrastructure.ai import KieClient, KieError

_IMAGE_OUTPUT_GUARD = (
    "Generate the requested image and return image output only. "
    "Do not answer with text, disclaimers, or descriptions of your capabilities. "
    "If the request cannot be completed, return the provider's structured failure "
    "status instead of conversational text."
)
_MODEL_CHATTER_MARKERS = (
    "я просто языковая модель",
    "я всего лишь языковая модель",
    "я просто генерирую текст",
    "я могу только генерировать текст",
    "мои возможности ограничены",
    "эта задача не для меня",
    "в моей программе нет таких возможностей",
    "не могу создавать изображения",
    "не умею создавать изображения",
    "as a language model",
    "i am just a language model",
    "i'm just a language model",
    "i can only generate text",
    "i only generate text",
    "my capabilities are limited",
    "this task is not for me",
    "i cannot generate images",
    "i can't generate images",
)
_INSTALLED = False
_ORIGINAL_CREATE_GRS_TASK = KieClient._create_grs_task
_ORIGINAL_PROVIDER_REASON_TEXT: Callable[[object], str | None] = (
    grs_resilience._provider_reason_text
)


def _with_image_output_guard(request: KieGenerationRequest) -> KieGenerationRequest:
    """Keep the owner prompt intact while forcing the image endpoint to stay modal."""

    if not request.model.is_grs:
        return request
    provider_prompt = request.provider_prompt
    if _IMAGE_OUTPUT_GUARD.casefold() in provider_prompt.casefold():
        return request
    return replace(
        request,
        prompt=f"{provider_prompt}\n\n{_IMAGE_OUTPUT_GUARD}",
    )


async def _create_grs_task_with_image_output_guard(
    client: KieClient,
    request: KieGenerationRequest,
) -> str:
    return await _ORIGINAL_CREATE_GRS_TASK(
        client,
        _with_image_output_guard(request),
    )


def _provider_reason_without_model_chatter(value: object) -> str | None:
    """Reject conversational model refusals as moderation diagnostics."""

    text = _ORIGINAL_PROVIDER_REASON_TEXT(value)
    if text is None:
        return None
    normalized = text.casefold()
    if any(marker in normalized for marker in _MODEL_CHATTER_MARKERS):
        return None
    return text


def _retry_delays_for_error(
    error: BaseException,
    base_delay_seconds: int,
    max_delay_seconds: int,
) -> tuple[int, int]:
    """Return zero delay only for a confirmed GRS moderation rejection."""

    if grs_resilience._is_grs_violation_error(error):
        return 0, 0
    return (
        max(0, int(base_delay_seconds)),
        max(0, int(max_delay_seconds)),
    )


async def _queue_fail_with_instant_grs_violation(
    queue: KieTaskQueueService,
    *,
    task_id,
    worker_id: str,
    error: BaseException,
    base_delay_seconds: int,
    max_delay_seconds: int,
):
    effective_base, effective_max = _retry_delays_for_error(
        error,
        base_delay_seconds,
        max_delay_seconds,
    )
    return await grs_resilience._ORIGINAL_QUEUE_FAIL(
        queue,
        task_id=task_id,
        worker_id=worker_id,
        error=error,
        base_delay_seconds=effective_base,
        max_delay_seconds=effective_max,
    )


def _violation_retry_stage(
    *,
    provider_attempt: int,
    max_attempts: int,
    delay_seconds: int,
    reason_text: str,
) -> str:
    attempt = max(1, int(provider_attempt))
    limit = max(attempt, int(max_attempts))
    del delay_seconds
    return (
        f"GRS AI отклонил попытку {attempt}/{limit}. "
        f"{reason_text} Следующая последовательная попытка запускается сразу."
    )


def _violation_terminal_stage(
    *,
    provider_attempt: int,
    max_attempts: int,
    reason_text: str,
) -> str:
    attempt = max(1, int(provider_attempt))
    limit = max(attempt, int(max_attempts))
    return (
        f"GRS AI отклонил попытку {attempt}/{limit}. "
        f"{reason_text} Лимит последовательной кампании исчерпан."
    )


class CampaignGrsGenerationWorker(
    grs_resilience.ResilientFriendlyKieGenerationWorker
):
    """Retry confirmed GRS violations sequentially through the full campaign limit."""

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
        if not grs_resilience._is_grs_violation_error(error):
            await super()._report_retry_or_terminal(
                task=task,
                request=request,
                progress=progress,
                failure=failure,
                provider_attempt=provider_attempt,
                error=error,
            )
            return

        reason_text = grs_resilience._reason_status_text(error)
        will_retry = bool(getattr(failure, "will_retry", False))
        if request is not None and will_retry:
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=max(5, progress.last_percent if progress else 5),
                stage=_violation_retry_stage(
                    provider_attempt=provider_attempt,
                    max_attempts=task.max_attempts,
                    delay_seconds=0,
                    reason_text=reason_text,
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
                stage=_violation_terminal_stage(
                    provider_attempt=provider_attempt,
                    max_attempts=task.max_attempts,
                    reason_text=reason_text,
                ),
                force=True,
            )
        await self._notify_terminal_failure_best_effort(task, error)

    async def _notify_terminal_failure_best_effort(
        self,
        task: AITask,
        error: Exception,
    ) -> None:
        if not grs_resilience._is_grs_violation_error(error):
            await super()._notify_terminal_failure_best_effort(task, error)
            return

        chat_id = _optional_int(task.payload.get("chat_id"))
        if chat_id is None:
            return
        balance: Decimal | None = None
        try:
            balance = await self._client.get_grs_credits()
        except KieError:
            balance = None
        balance_line = (
            f"Баланс GRS после остановки: <b>{grs_resilience._format_credits(balance)}</b> кредитов"
            if balance is not None
            else "Баланс GRS после остановки: <b>не удалось проверить</b>"
        )
        reason = grs_resilience._grs_violation_reason_from_error(error)
        reason_line = (
            f"<b>Причина GRS AI:</b> {escape(reason)}"
            if reason is not None
            else (
                "<b>Причина:</b> GRS AI не передал технической категории. "
                "Текстовый ответ модели отброшен как недостоверная диагностика."
            )
        )
        attempts = max(1, int(task.attempt_count))
        try:
            await self._bot.send_message(
                chat_id,
                "<b>Ауф не смог завершить генерацию</b>\n\n"
                "Провайдер: <b>GRS AI</b>\n"
                f"Последовательная кампания исчерпала <b>{attempts}/{task.max_attempts}</b> попыток.\n"
                f"{reason_line}\n"
                f"{balance_line}\n\n"
                "Параллельные платные задачи не запускались.\n"
                f"Задача: <code>{task.id}</code>",
            )
        except TelegramAPIError:
            return
        finally:
            self._provider_balances.pop(str(task.id), None)


def install_grs_campaign_retry() -> None:
    """Restore the full queue limit and harden GRS image-only submissions."""

    global _INSTALLED
    if _INSTALLED:
        return

    grs_resilience._provider_reason_text = _provider_reason_without_model_chatter
    KieClient._create_grs_task = _create_grs_task_with_image_output_guard  # type: ignore[method-assign]
    KieTaskQueueService.fail = _queue_fail_with_instant_grs_violation  # type: ignore[method-assign]

    workers = importlib.import_module("velvet_bot.app.workers")
    workers.KieGenerationWorker = CampaignGrsGenerationWorker
    _INSTALLED = True


__all__ = (
    "CampaignGrsGenerationWorker",
    "install_grs_campaign_retry",
)
