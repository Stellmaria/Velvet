from __future__ import annotations

import asyncio
import io
import logging
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Mapping
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
)

logger = logging.getLogger(__name__)
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_DOWNLOAD_RETRY_DELAYS = (1.0, 3.0)


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

        try:
            request = _request_from_task(task)
            estimated_cost_rub = self._pricing.estimate_rub(
                request,
                usd_to_rub=self._usd_to_rub,
            )
            provider_model = self._client.models.provider_model(request.model)
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
                },
            )

            async def provider_operation() -> AIProviderResult[KieTaskRecord]:
                provider_request = await self._upload_references(
                    queue_task_id=task.id,
                    request=request,
                )
                provider_task_id = await self._client.create_task(provider_request)
                record = await self._wait_with_heartbeat(
                    queue_task_id=task.id,
                    provider_task_id=provider_task_id,
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
                },
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
            )
            if failure is not None and not failure.will_retry:
                await self._notify_terminal_failure_best_effort(task, error)
        return 1

    async def _upload_references(
        self,
        *,
        queue_task_id: UUID,
        request: KieGenerationRequest,
    ) -> KieGenerationRequest:
        if not request.references:
            return request
        uploaded_urls: list[str] = []
        for index, reference in enumerate(request.references, start=1):
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
            return await self._client.wait_for_task(provider_task_id)
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


__all__ = ("KieGenerationWorker",)
