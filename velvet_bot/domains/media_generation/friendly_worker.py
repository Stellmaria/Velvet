from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import Mapping
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from pathlib import Path
from typing import Any

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from velvet_bot.domains.ai_usage import AITask
from velvet_bot.domains.media_generation.provider_contract import (
    grs_retry_stage,
    grs_terminal_stage,
    grs_violation_reason,
    is_grs_violation_error,
)
from velvet_bot.infrastructure.media_delivery_runtime import (
    MediaDeliveryRuntime,
    ensure_media_delivery_runtime,
)

from .economy_worker import KieGenerationWorker as EconomyKieGenerationWorker
from .models import KieGenerationRequest, KieModelAlias, KieTaskRecord
from .worker import ProgressMessage, optional_int, render_progress_bar

logger = logging.getLogger(__name__)
_MONEY_QUANTUM = Decimal("0.01")
_GRS_CREDITS = {
    KieModelAlias.NANO_BANANA_2: Decimal("1200"),
    KieModelAlias.NANO_BANANA_PRO: Decimal("1800"),
}
_REFERENCE_CACHE_TTL_SECONDS = 20 * 60
_REFERENCE_CACHE_MAX_ENTRIES = 256
_REFERENCE_UPLOAD_CONCURRENCY = 3
_REFERENCE_URL_CACHE: OrderedDict[str, tuple[float, str]] = OrderedDict()
_REFERENCE_CACHE_LOCK = asyncio.Lock()



def _reference_cache_key(reference: object) -> str:
    unique_id = str(getattr(reference, "telegram_file_unique_id", "") or "").strip()
    file_id = str(getattr(reference, "telegram_file_id", "") or "").strip()
    mime_type = str(getattr(reference, "mime_type", "") or "").strip().casefold()
    file_size = str(getattr(reference, "file_size", "") or "").strip()
    return "|".join((unique_id or file_id, mime_type, file_size))


async def _cached_reference_url(key: str) -> str | None:
    now = time.monotonic()
    async with _REFERENCE_CACHE_LOCK:
        expired = [
            cache_key
            for cache_key, (expires_at, _) in _REFERENCE_URL_CACHE.items()
            if expires_at <= now
        ]
        for cache_key in expired:
            _REFERENCE_URL_CACHE.pop(cache_key, None)
        cached = _REFERENCE_URL_CACHE.get(key)
        if cached is None:
            return None
        expires_at, url = cached
        if expires_at <= now:
            _REFERENCE_URL_CACHE.pop(key, None)
            return None
        _REFERENCE_URL_CACHE.move_to_end(key)
        return url


async def _remember_reference_url(key: str, url: str) -> None:
    async with _REFERENCE_CACHE_LOCK:
        _REFERENCE_URL_CACHE[key] = (
            time.monotonic() + _REFERENCE_CACHE_TTL_SECONDS,
            url,
        )
        _REFERENCE_URL_CACHE.move_to_end(key)
        while len(_REFERENCE_URL_CACHE) > _REFERENCE_CACHE_MAX_ENTRIES:
            _REFERENCE_URL_CACHE.popitem(last=False)


async def _forget_reference_urls(urls: tuple[str, ...]) -> None:
    if not urls:
        return
    stale = set(urls)
    async with _REFERENCE_CACHE_LOCK:
        for key in [
            key
            for key, (_, url) in _REFERENCE_URL_CACHE.items()
            if url in stale
        ]:
            _REFERENCE_URL_CACHE.pop(key, None)


class FriendlyKieGenerationWorker(EconomyKieGenerationWorker):
    """Provider-aware generation worker with canonical durable delivery."""

    def __init__(
        self,
        *,
        media_delivery_runtime: MediaDeliveryRuntime | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        runtime = media_delivery_runtime or ensure_media_delivery_runtime(
            bot=self._bot,
            database=self._queue.database,
            provider_client=self._client,
        )
        self._media_delivery_runtime = runtime
        self._queue.configure_durable_delivery(
            resolver=runtime.resolver,
            delivery=runtime.delivery,
        )
        self._provider_balances: dict[str, Decimal | None] = {}

    async def _deliver_best_effort(
        self,
        *,
        chat_id: int | None,
        request: KieGenerationRequest,
        record: KieTaskRecord,
    ) -> None:
        """Disable the legacy worker delivery phase.

        Provider completion is persisted by the queue and delivered only by the
        durable media-delivery use case. Keeping this explicit override prevents
        the inherited best-effort transport path from sending a duplicate result.
        """

        del chat_id, request, record

    async def process_once(self) -> bool:
        await self._recover_durable_delivery(phase="before-generation")
        processed = await super().process_once()
        if processed:
            # A provider may finish without URLs in the first success payload, or
            # durable registration may need the now-committed ai_tasks row. Run the
            # task-independent recovery immediately instead of waiting for the next
            # periodic tick while the user sees a completed progress message.
            await self._recover_durable_delivery(phase="after-generation")
        return processed

    async def _recover_durable_delivery(self, *, phase: str) -> None:
        try:
            await self._media_delivery_runtime.recover_once()
        except Exception as error:  # p2-approved-boundary: isolate-durable-recovery-tick
            from velvet_bot.application.media_delivery import (
                classify_media_delivery_error,
                raise_if_programming_error,
            )

            failure = classify_media_delivery_error(
                error,
                phase=f"durable_recovery_{phase}",
            )
            logger.error(
                "durable_media_recovery_failed phase=%s code=%s fingerprint=%s",
                phase,
                failure.code,
                failure.fingerprint,
            )
            raise_if_programming_error(
                error,
                phase=f"durable_recovery_{phase}",
            )


    async def _upload_references(
        self,
        *,
        queue_task_id: object,
        request: KieGenerationRequest,
        task: AITask,
        progress: ProgressMessage | None,
    ) -> KieGenerationRequest:
        if not request.references:
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=35,
                stage="Референсы не требуются.",
            )
            return request

        total = len(request.references)
        await self._publish_progress(
            progress,
            task=task,
            request=request,
            percent=10,
            stage=f"Параллельно подготавливаю референсы: {total} шт.",
        )
        semaphore = asyncio.Semaphore(_REFERENCE_UPLOAD_CONCURRENCY)

        async def prepare(index: int, reference: object) -> str:
            key = _reference_cache_key(reference)
            cached = await _cached_reference_url(key)
            if cached is not None:
                return cached
            async with semaphore:
                cached_after_wait = await _cached_reference_url(key)
                if cached_after_wait is not None:
                    return cached_after_wait
                payload = await self._download_reference(reference)
                safe_name = Path(
                    str(getattr(reference, "file_name", "reference.jpg") or "reference.jpg")
                ).name
                uploaded = await self._client.upload_reference(
                    payload,
                    mime_type=str(getattr(reference, "mime_type", "image/jpeg")),
                    file_name=f"{queue_task_id}-{index}-{safe_name}",
                )
                await _remember_reference_url(key, uploaded.file_url)
                return uploaded.file_url

        urls = await asyncio.gather(
            *(
                prepare(index, reference)
                for index, reference in enumerate(request.references, start=1)
            )
        )
        await self._queue.heartbeat(
            task_id=queue_task_id,
            worker_id=self._worker_id,
        )
        await self._publish_progress(
            progress,
            task=task,
            request=request,
            percent=35,
            stage=f"Референсы готовы: {total}/{total}.",
        )
        return request.with_image_urls(tuple(urls))

    async def _record_provider_result(
        self,
        *,
        task: AITask,
        runtime: dict[str, object],
        record: KieTaskRecord,
        status: str,
    ) -> dict[str, object]:
        cached_urls = (
            tuple(
                str(value).strip()
                for value in runtime.get("image_urls", ())
                if str(value).strip()
            )
            if isinstance(runtime.get("image_urls"), (list, tuple))
            else ()
        )
        updated = await super()._record_provider_result(
            task=task,
            runtime=runtime,
            record=record,
            status=status,
        )
        if status == "fail":
            details = " ".join(
                value
                for value in (record.failure_code, record.failure_message)
                if value
            ).casefold()
            if any(token in details for token in ("expired", "download url", "image url")):
                await _forget_reference_urls(cached_urls)
        return updated

    async def _report_retry_or_terminal(
        self,
        *,
        task: AITask,
        request: KieGenerationRequest | None,
        progress: ProgressMessage | None,
        failure: object,
        provider_attempt: int,
        error: Exception,
    ) -> None:
        if not is_grs_violation_error(error):
            await super()._report_retry_or_terminal(
                task=task,
                request=request,
                progress=progress,
                failure=failure,
                provider_attempt=provider_attempt,
                error=error,
            )
            return
        reason = grs_violation_reason(error)
        reason_text = (
            f"Причина сервиса: {reason}"
            if reason is not None
            else "Сервис не передал конкретную причину блокировки."
        )
        will_retry = bool(getattr(failure, "will_retry", False))
        if request is not None and will_retry:
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=max(5, progress.last_percent if progress else 5),
                stage=grs_retry_stage(
                    provider_attempt=provider_attempt,
                    max_attempts=task.max_attempts,
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
                stage=grs_terminal_stage(
                    provider_attempt=provider_attempt,
                    max_attempts=task.max_attempts,
                    reason_text=reason_text,
                ),
                force=True,
            )
        await self._notify_terminal_failure_best_effort(task, error)

    async def _start_progress(
        self,
        *,
        task: AITask,
        request: KieGenerationRequest,
    ) -> ProgressMessage | None:
        chat_id = optional_int(task.payload.get("chat_id"))
        if chat_id is None:
            return None

        # Balance is intentionally read only from the dedicated owner screen.
        # Starting a generation must not block on a second provider request.
        self._provider_balances[str(task.id)] = None

        stage = "Задача принята. Готовлю всё для генерации."
        text = self._friendly_progress_text(
            task=task,
            request=request,
            percent=0,
            stage=stage,
        )
        try:
            message = await self._bot.send_message(chat_id, text)
        except TelegramAPIError:
            logger.exception("Could not create friendly progress message for %s", task.id)
            return None
        return ProgressMessage(
            chat_id=chat_id,
            message_id=optional_int(getattr(message, "message_id", None)),
            last_percent=0,
            last_stage=stage,
        )

    async def _publish_progress(
        self,
        progress: ProgressMessage | None,
        *,
        task: AITask,
        request: KieGenerationRequest,
        percent: int,
        stage: str,
        force: bool = False,
    ) -> None:
        if progress is None:
            return
        safe_percent = max(0, min(100, int(percent)))
        normalized_stage = friendly_stage(request, stage)
        if (
            not force
            and safe_percent == progress.last_percent
            and normalized_stage == progress.last_stage
        ):
            return
        text = self._friendly_progress_text(
            task=task,
            request=request,
            percent=safe_percent,
            stage=normalized_stage,
        )
        try:
            if progress.message_id is None:
                message = await self._bot.send_message(progress.chat_id, text)
                progress.message_id = optional_int(
                    getattr(message, "message_id", None)
                )
            else:
                await self._bot.edit_message_text(
                    text,
                    chat_id=progress.chat_id,
                    message_id=progress.message_id,
                )
            progress.last_percent = safe_percent
            progress.last_stage = normalized_stage
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                logger.warning(
                    "Could not update friendly progress message for %s: %s",
                    task.id,
                    error,
                )
        except TelegramAPIError:
            logger.exception("Could not update friendly progress message for %s", task.id)

    def _friendly_progress_text(
        self,
        *,
        task: AITask,
        request: KieGenerationRequest,
        percent: int,
        stage: str,
    ) -> str:
        provider = "GRS AI" if request.model.is_grs else "Kie.ai"
        estimated_usd = self._pricing.estimate_usd(request)
        estimated_rub = self._pricing.estimate_rub(
            request,
            usd_to_rub=self._usd_to_rub,
        )
        attempt_label = (
            f"Повтор: <b>{task.attempt_count}/{task.max_attempts}</b>"
            if task.attempt_count > 1
            else f"Попытка: <b>{task.attempt_count}/{task.max_attempts}</b>"
        )
        finance_lines = [
            f"Ожидаемая стоимость: <b>${_money(estimated_usd)} · "
            f"{_money(estimated_rub)} ₽</b>"
        ]
        expected_credits = _GRS_CREDITS.get(request.model)
        if expected_credits is not None:
            finance_lines[0] = (
                f"Ожидаемое списание: <b>≈ {_credits(expected_credits)} кредитов · "
                f"${_money(estimated_usd)} · {_money(estimated_rub)} ₽</b>"
            )
            balance = self._provider_balances.get(str(task.id))
            if balance is None:
                finance_lines.append("Баланс GRS: <b>не удалось проверить</b>")
            else:
                remaining = max(Decimal("0"), balance - expected_credits)
                finance_lines.append(
                    f"Баланс GRS: <b>{_credits(balance)}</b> кредитов "
                    f"· после запуска ≈ <b>{_credits(remaining)}</b>"
                )

        safe_percent = max(0, min(100, int(percent)))
        return (
            f"<b>Мяу создаёт · {escape(request.model.display_name)}</b>\n\n"
            f"<code>{render_progress_bar(safe_percent)}</code> <b>{safe_percent}%</b>\n"
            f"✨ {escape(friendly_stage(request, stage))}\n\n"
            f"Провайдер: <b>{provider}</b>\n"
            f"Режим: <b>{escape(request.input_mode.display_name)}</b>\n"
            f"Качество: <b>{escape(request.resolution)}</b>\n"
            f"Референсы: <b>{len(request.references)}</b>\n"
            f"Контент: <b>{escape(request.content_mode.display_name)}</b>\n\n"
            + "\n".join(finance_lines)
            + "\n\n"
            f"{attempt_label}\n"
            f"Задача: <code>{task.id}</code>"
        )

    async def _notify_terminal_failure_best_effort(
        self,
        task: AITask,
        error: Exception,
    ) -> None:
        chat_id = optional_int(task.payload.get("chat_id"))
        if chat_id is None:
            return
        request = _request_from_payload(task.payload)
        message = friendly_error(request, str(error))
        if is_grs_violation_error(error):
            reason = grs_violation_reason(error)
            message = (
                "Запрос не прошёл автоматическую проверку содержимого."
                + (f" Причина сервиса: {reason}" if reason else "")
            )
        try:
            await self._bot.send_message(
                chat_id,
                "<b>Ауф не смог завершить генерацию</b>\n\n"
                f"{escape(message)}\n\n"
                "Повторная платная отправка автоматически не выполнялась.",
            )
        except TelegramAPIError:
            logger.exception("Could not deliver terminal failure for %s", task.id)
        finally:
            self._provider_balances.pop(str(task.id), None)


def friendly_stage(request: KieGenerationRequest, stage: str) -> str:
    text = str(stage or "").strip()
    if not request.model.is_grs:
        return text.replace("worker-ом", "обработчиком")
    exact = {
        "Экономная кампания взята worker-ом.": "Задача принята. Подготавливаю генерацию.",
        "Подготовка сохранённого референса.": "Проверяю и подготавливаю референсы.",
        "Kie завершил генерацию.": "GRS AI завершил генерацию.",
        "Kie сообщил об ошибке генерации.": "GRS AI сообщил об ошибке генерации.",
        "Задача ожидает вычислительных ресурсов Kie.": "Задача ожидает свободные ресурсы GRS AI.",
        "Kie готовит задачу к генерации.": "GRS AI готовит задачу к генерации.",
    }
    if text in exact:
        return exact[text]
    text = text.replace(
        "Используем уже загруженный референс Kie без повторной загрузки.",
        "Использую уже подготовленные референсы без повторной загрузки.",
    )
    text = text.replace("createTask", "запрос GRS AI")
    text = text.replace("Kie.ai", "GRS AI")
    text = text.replace("Kie-кампании", "GRS-генерации")
    text = text.replace("Kie ", "GRS AI ")
    text = text.replace("Экономная кампания", "Безопасная генерация")
    text = text.replace("worker-ом", "обработчиком")
    return text


def friendly_error(
    request: KieGenerationRequest | None,
    message: str,
) -> str:
    text = str(message or "").strip()
    if request is None or not request.model.is_grs:
        return text
    if "Ответ createTask потерян или не подтверждён" in text:
        return (
            "GRS AI не подтвердил приём задачи. Статус первой отправки неизвестен, "
            "поэтому автоматический платный повтор остановлен, чтобы исключить двойное списание."
        )
    return friendly_stage(request, text)


def install_friendly_media_worker() -> None:
    """Install the provider-aware worker in the application composition root."""

    from velvet_bot.app.media_delivery_ui_install import install_media_delivery_ui

    install_media_delivery_ui()


def _request_from_payload(payload: Mapping[str, object]) -> KieGenerationRequest | None:
    value = payload.get("request")
    if not isinstance(value, Mapping):
        return None
    try:
        return KieGenerationRequest.from_task_payload(value)
    except ValueError:
        return None


def _money(value: Decimal) -> str:
    return format(value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP), ".2f").replace(
        ".", ","
    )


def _credits(value: Decimal) -> str:
    integral = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(integral):,}".replace(",", " ")


__all__ = (
    "FriendlyKieGenerationWorker",
    "friendly_error",
    "friendly_stage",
    "install_friendly_media_worker",
)
