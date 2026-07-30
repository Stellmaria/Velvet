from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from html import escape
from pathlib import Path
from uuid import UUID

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import (
    AIBudgetExceeded,
    AIProviderResult,
    AIRequestContext,
    AIRequestExecutor,
    AITask,
    AITaskQueueService,
)
from velvet_bot.infrastructure.ai import KieClient, KieError

from .models import (
    KIE_GENERATION_TASK_TYPE,
    MAX_KIE_REFERENCE_BYTES,
    KieGenerationRequest,
    KiePricing,
    KieReferenceImage,
    KieTaskRecord,
    KieTaskState,
)

logger = logging.getLogger(__name__)
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_DOWNLOAD_RETRY_DELAYS = (1.0, 3.0)
_PROGRESS_WIDTH = 10


@dataclass(slots=True)
class _ProgressMessage:
    chat_id: int
    message_id: int | None
    last_percent: int = -1
    last_stage: str = ""


def render_progress_bar(percent: int, *, width: int = _PROGRESS_WIDTH) -> str:
    safe_percent = max(0, min(100, int(percent)))
    safe_width = max(5, min(20, int(width)))
    filled = round(safe_percent * safe_width / 100)
    return "█" * filled + "░" * (safe_width - filled)


class KieGenerationWorker:
    """Consume Kie media tasks without coupling Telegram handlers to provider calls."""

    def __init__(
        self,
        *,
        bot: Bot,
        queue: AITaskQueueService,
        client: KieClient,
        executor: AIRequestExecutor[KieTaskRecord],
        pricing: KiePricing,
        usd_to_rub: Decimal,
        worker_id: str = "kie-media-generation",
        heartbeat_seconds: int = 60,
    ) -> None:
        if usd_to_rub <= 0:
            raise ValueError("Курс USD/RUB для Kie worker должен быть больше нуля.")
        self._bot = bot
        self._queue = queue
        self._client = client
        self._executor = executor
        self._pricing = pricing
        self._usd_to_rub = usd_to_rub
        self._worker_id = worker_id.strip() or "kie-media-generation"
        self._heartbeat_seconds = max(15, int(heartbeat_seconds))

    async def process_once(self) -> int:
        task = await self._queue.claim_next(
            worker_id=self._worker_id,
            scopes=(AIBudgetScope.VISION,),
            task_types=(KIE_GENERATION_TASK_TYPE,),
        )
        if task is None:
            return 0

        progress: _ProgressMessage | None = None
        request: KieGenerationRequest | None = None
        try:
            request = _request_from_task(task)
            progress = await self._start_progress(task=task, request=request)
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=5,
                stage=(
                    "Автоповтор запущен."
                    if task.attempt_count > 1
                    else "Задача взята worker-ом."
                ),
            )
            estimated_cost_rub = self._pricing.estimate_rub(
                request,
                usd_to_rub=self._usd_to_rub,
            )
            provider_model = self._client.models.provider_model_for_request(request)
            chat_id = _optional_int(task.payload.get("chat_id"))
            user_id = _optional_int(task.payload.get("user_id"))
            context = AIRequestContext(
                scope=AIBudgetScope.VISION,
                provider="kie",
                model=provider_model,
                operation="media.generate",
                estimated_cost_rub=estimated_cost_rub,
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
                    "attempt": task.attempt_count,
                    "max_attempts": task.max_attempts,
                },
            )

            async def provider_operation() -> AIProviderResult[KieTaskRecord]:
                await self._publish_progress(
                    progress,
                    task=task,
                    request=request,
                    percent=10,
                    stage="Подготовка референсов.",
                )
                provider_request = await self._upload_references(
                    queue_task_id=task.id,
                    request=request,
                    task=task,
                    progress=progress,
                )
                await self._publish_progress(
                    progress,
                    task=task,
                    request=request,
                    percent=42,
                    stage="Отправка запроса в Kie.ai.",
                )
                provider_task_id = await self._client.create_task(provider_request)
                await self._publish_progress(
                    progress,
                    task=task,
                    request=request,
                    percent=50,
                    stage=f"Kie принял задачу {provider_task_id}.",
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

                record = await self._wait_with_heartbeat(
                    queue_task_id=task.id,
                    provider_task_id=provider_task_id,
                    on_update=on_provider_update,
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
                        "attempt": task.attempt_count,
                    },
                )

            record = await self._executor.execute(
                context=context,
                operation=provider_operation,
            )
            await self._queue.complete(
                task_id=task.id,
                worker_id=self._worker_id,
                result={
                    "provider": "kie",
                    "provider_task_id": record.task_id,
                    "model_alias": request.model.value,
                    "input_mode": request.input_mode.value,
                    "reference_count": len(request.references),
                    "content_mode": request.content_mode.value,
                    "result_urls": list(record.result_urls),
                    "consumed_credits": record.consumed_credits,
                    "estimated_cost_rub": str(estimated_cost_rub),
                    "attempt_count": task.attempt_count,
                },
            )
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=100,
                stage="Готово. Результат отправляется в Telegram.",
            )
            await self._deliver_best_effort(
                chat_id=chat_id,
                request=request,
                record=record,
            )
        except asyncio.CancelledError as error:
            await self._queue.fail(
                task_id=task.id,
                worker_id=self._worker_id,
                error=error,
                base_delay_seconds=5,
                max_delay_seconds=30,
            )
            raise
        except (
            AIBudgetExceeded,
            KieError,
            TimeoutError,
            ValueError,
            RuntimeError,
            OSError,
        ) as error:
            failure = await self._queue.fail(
                task_id=task.id,
                worker_id=self._worker_id,
                error=error,
                base_delay_seconds=5,
                max_delay_seconds=30,
            )
            if request is not None:
                if failure is not None and failure.will_retry:
                    delay = failure.retry_delay_seconds or 0
                    await self._publish_progress(
                        progress,
                        task=task,
                        request=request,
                        percent=max(5, progress.last_percent if progress else 5),
                        stage=(
                            "Генерация не удалась. "
                            f"Автоповтор {task.attempt_count + 1}/{task.max_attempts} "
                            f"через {delay} сек."
                        ),
                        force=True,
                    )
                else:
                    await self._publish_progress(
                        progress,
                        task=task,
                        request=request,
                        percent=100,
                        stage="Генерация завершилась ошибкой после автоповторов.",
                        force=True,
                    )
            if failure is not None and not failure.will_retry:
                await self._notify_terminal_failure_best_effort(task, error)
        return 1

    async def _start_progress(
        self,
        *,
        task: AITask,
        request: KieGenerationRequest,
    ) -> _ProgressMessage | None:
        chat_id = _optional_int(task.payload.get("chat_id"))
        if chat_id is None:
            return None
        text = _progress_text(
            task=task,
            request=request,
            percent=0,
            stage="Ожидание запуска.",
        )
        try:
            message = await self._bot.send_message(chat_id, text)
        except TelegramAPIError:
            logger.exception("Could not create Kie progress message for %s", task.id)
            return None
        return _ProgressMessage(
            chat_id=chat_id,
            message_id=_optional_int(getattr(message, "message_id", None)),
            last_percent=0,
            last_stage="Ожидание запуска.",
        )

    async def _publish_progress(
        self,
        progress: _ProgressMessage | None,
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
        normalized_stage = stage.strip()
        if (
            not force
            and safe_percent == progress.last_percent
            and normalized_stage == progress.last_stage
        ):
            return
        text = _progress_text(
            task=task,
            request=request,
            percent=safe_percent,
            stage=normalized_stage,
        )
        try:
            if progress.message_id is None:
                message = await self._bot.send_message(progress.chat_id, text)
                progress.message_id = _optional_int(
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
                    "Could not update Kie progress message for %s: %s",
                    task.id,
                    error,
                )
        except TelegramAPIError:
            logger.exception("Could not update Kie progress message for %s", task.id)

    async def _upload_references(
        self,
        *,
        queue_task_id: UUID,
        request: KieGenerationRequest,
        task: AITask,
        progress: _ProgressMessage | None,
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
        uploaded_urls: list[str] = []
        total = len(request.references)
        for index, reference in enumerate(request.references, start=1):
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=10 + round((index - 1) * 25 / total),
                stage=f"Загрузка референса {index}/{total}.",
            )
            payload = await self._download_reference(reference)
            safe_name = Path(reference.file_name or "reference.jpg").name
            uploaded = await self._client.upload_reference(
                payload,
                mime_type=reference.mime_type,
                file_name=f"{queue_task_id}-{index}-{safe_name}",
            )
            uploaded_urls.append(uploaded.file_url)
            await self._queue.heartbeat(
                task_id=queue_task_id,
                worker_id=self._worker_id,
            )
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=10 + round(index * 25 / total),
                stage=f"Референс {index}/{total} загружен.",
            )
        return request.with_image_urls(tuple(uploaded_urls))

    async def _download_reference(self, reference: KieReferenceImage) -> bytes:
        errors: list[BaseException] = []
        for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
            try:
                destination = io.BytesIO()
                await self._bot.download(
                    reference.telegram_file_id,
                    destination=destination,
                    timeout=_DOWNLOAD_TIMEOUT_SECONDS,
                    seek=True,
                )
                value = destination.getvalue()
                if not value:
                    raise RuntimeError("Telegram вернул пустой файл референса.")
                if len(value) > MAX_KIE_REFERENCE_BYTES:
                    raise ValueError("Референс для Kie.ai должен быть не больше 10 МБ.")
                return value
            except asyncio.CancelledError:
                raise
            except TelegramBadRequest as error:
                errors.append(error)
                break
            except (
                TelegramNetworkError,
                TimeoutError,
                ConnectionError,
                OSError,
            ) as error:
                errors.append(error)
                if attempt >= _DOWNLOAD_ATTEMPTS:
                    break
                await asyncio.sleep(_DOWNLOAD_RETRY_DELAYS[attempt - 1])
            except TelegramAPIError as error:
                errors.append(error)
                break
        if errors:
            raise RuntimeError(f"Не удалось скачать референс: {errors[-1]}")
        raise RuntimeError("Telegram вернул пустой файл референса.")

    async def _wait_with_heartbeat(
        self,
        *,
        queue_task_id: UUID,
        provider_task_id: str,
        on_update: Callable[[KieTaskRecord, int], Awaitable[None]],
    ) -> KieTaskRecord:
        stop = asyncio.Event()

        async def heartbeat_loop() -> None:
            while not stop.is_set():
                try:
                    await asyncio.wait_for(
                        stop.wait(),
                        timeout=self._heartbeat_seconds,
                    )
                except TimeoutError:
                    await self._queue.heartbeat(
                        task_id=queue_task_id,
                        worker_id=self._worker_id,
                    )

        heartbeat_task = asyncio.create_task(heartbeat_loop())
        try:
            return await self._client.wait_for_task(
                provider_task_id,
                on_update=on_update,
            )
        finally:
            stop.set()
            await heartbeat_task

    async def _deliver_best_effort(
        self,
        *,
        chat_id: int | None,
        request: KieGenerationRequest,
        record: KieTaskRecord,
    ) -> None:
        if chat_id is None:
            return
        caption = (
            f"<b>Мяу · {escape(request.model.display_name)}</b>\n"
            f"Качество: <b>{escape(request.resolution)}</b>\n"
            f"Референсов: <b>{len(request.references)}</b>\n"
            f"Контент: <b>{escape(request.content_mode.display_name)}</b>\n"
            f"Задача Kie: <code>{escape(record.task_id)}</code>"
        )
        try:
            if not record.result_urls:
                await self._bot.send_message(
                    chat_id,
                    caption + "\n\nKie завершил задачу без URL результата.",
                )
                return
            for index, url in enumerate(record.result_urls):
                item_caption = caption if index == 0 else None
                if request.model.is_video:
                    await self._bot.send_video(
                        chat_id,
                        video=url,
                        caption=item_caption,
                    )
                else:
                    await self._bot.send_photo(
                        chat_id,
                        photo=url,
                        caption=item_caption,
                    )
        except TelegramAPIError:
            logger.exception(
                "Kie task %s succeeded but Telegram delivery failed",
                record.task_id,
            )

    async def _notify_terminal_failure_best_effort(
        self,
        task: AITask,
        error: Exception,
    ) -> None:
        chat_id = _optional_int(task.payload.get("chat_id"))
        if chat_id is None:
            return
        try:
            await self._bot.send_message(
                chat_id,
                "<b>Мяу не смог завершить генерацию</b>\n\n"
                f"{escape(str(error))}\n"
                f"Задача: <code>{task.id}</code>",
            )
        except TelegramAPIError:
            logger.exception("Could not deliver terminal Kie failure for %s", task.id)


def _provider_progress(record: KieTaskRecord, poll_count: int) -> tuple[int, str]:
    if record.state is KieTaskState.SUCCESS:
        return 96, "Kie завершил генерацию."
    if record.state is KieTaskState.FAIL:
        return 95, "Kie сообщил об ошибке генерации."
    if record.state is KieTaskState.GENERATING:
        return min(92, 62 + max(1, poll_count) * 5), "Модель генерирует изображение."
    if record.state is KieTaskState.QUEUING:
        return 58, "Задача ожидает вычислительных ресурсов Kie."
    return 54, "Kie готовит задачу к генерации."


def _progress_text(
    *,
    task: AITask,
    request: KieGenerationRequest,
    percent: int,
    stage: str,
) -> str:
    safe_percent = max(0, min(100, int(percent)))
    attempt_label = (
        f"Автоповтор: <b>{task.attempt_count}/{task.max_attempts}</b>\n"
        if task.attempt_count > 1
        else f"Попытка: <b>{task.attempt_count}/{task.max_attempts}</b>\n"
    )
    return (
        f"<b>Мяу · {escape(request.model.display_name)}</b>\n\n"
        f"<code>{render_progress_bar(safe_percent)}</code> <b>{safe_percent}%</b>\n"
        f"{escape(stage)}\n\n"
        f"{attempt_label}"
        f"Качество: <b>{escape(request.resolution)}</b>\n"
        f"Референсов: <b>{len(request.references)}</b>\n"
        f"Задача: <code>{task.id}</code>"
    )


def _request_from_task(task: AITask) -> KieGenerationRequest:
    request_value = task.payload.get("request")
    if not isinstance(request_value, Mapping):
        raise ValueError("Kie AI-задача не содержит объект request.")
    return KieGenerationRequest.from_task_payload(request_value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


__all__ = ("KieGenerationWorker", "render_progress_bar")


ProgressMessage = _ProgressMessage
optional_int = _optional_int
