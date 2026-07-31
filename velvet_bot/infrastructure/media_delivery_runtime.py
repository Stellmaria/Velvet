from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from aiogram import Bot

from velvet_bot.application.media_delivery import (
    DeliverMediaResult,
    MediaDeliveryTerminalError,
    MediaDeliveryTransientError,
    ProviderResultResolver,
    RedeliverMediaResult,
    ResolveProviderResult,
    classify_media_delivery_error,
    raise_if_programming_error,
)
from velvet_bot.application.workspace_tasks import get_owned_success_task
from velvet_bot.database import Database
from velvet_bot.domains.media_generation.models import KieTaskState
from velvet_bot.infrastructure.ai import KieClient
from velvet_bot.infrastructure.media_delivery_repository import (
    PostgresMediaDeliveryRepository,
)
from velvet_bot.infrastructure.media_delivery_telegram import (
    TelegramMediaDeliveryTransport,
)

logger = logging.getLogger(__name__)
_ACTIVE_RUNTIME: MediaDeliveryRuntime | None = None


class KieProviderResultResolver(ProviderResultResolver):
    """Provider adapter used only to resolve an already submitted paid task."""

    def __init__(self, client: KieClient) -> None:
        self._client = client

    async def resolve(
        self,
        *,
        provider: str,
        provider_task_id: str,
    ) -> tuple[str, ...]:
        del provider
        record = await self._client.get_task(provider_task_id)
        if record.state is KieTaskState.FAIL:
            raise MediaDeliveryTerminalError(
                "provider_result_failed",
                "Провайдер завершил сохранённую задачу ошибкой.",
            )
        if record.state is not KieTaskState.SUCCESS:
            raise MediaDeliveryTransientError(
                "provider_result_pending",
                "Провайдер ещё не подтвердил готовый результат.",
            )
        urls = tuple(
            url for value in record.result_urls if (url := str(value).strip())
        )
        if not urls:
            raise MediaDeliveryTransientError(
                "provider_result_urls_pending",
                "Провайдер подтвердил задачу, но URL результата ещё недоступен.",
            )
        return urls


class MediaDeliveryRuntime:
    def __init__(
        self,
        *,
        repository: PostgresMediaDeliveryRepository,
        resolver: ResolveProviderResult,
        delivery: DeliverMediaResult,
        redelivery: RedeliverMediaResult,
    ) -> None:
        self.repository = repository
        self.resolver = resolver
        self.delivery = delivery
        self.redelivery = redelivery

    async def recover_once(self) -> int:
        imported = await self.repository.backfill_missing_successes(limit=100)
        resolved = await self.resolver.execute()
        delivered = await self.delivery.execute()
        return imported + int(resolved) + int(delivered is not None)


def build_media_delivery_runtime(
    *,
    bot: Bot,
    database: Database,
    provider_client: KieClient,
    worker_id: str = "media-delivery",
) -> MediaDeliveryRuntime:
    repository = PostgresMediaDeliveryRepository(database)
    transport = TelegramMediaDeliveryTransport(bot)
    resolver = ResolveProviderResult(
        repository,
        KieProviderResultResolver(provider_client),
        worker_id=f"{worker_id}-resolver",
    )
    delivery = DeliverMediaResult(
        repository=repository,
        transport=transport,
        worker_id=worker_id,
    )
    return MediaDeliveryRuntime(
        repository=repository,
        resolver=resolver,
        delivery=delivery,
        redelivery=RedeliverMediaResult(
            repository=repository,
            delivery=delivery,
        ),
    )


def ensure_media_delivery_runtime(
    *,
    bot: Bot,
    database: Database,
    provider_client: KieClient,
) -> MediaDeliveryRuntime:
    runtime = _ACTIVE_RUNTIME
    if runtime is not None:
        return runtime
    runtime = build_media_delivery_runtime(
        bot=bot,
        database=database,
        provider_client=provider_client,
    )
    configure_media_delivery_runtime(runtime)
    return runtime


def configure_media_delivery_runtime(runtime: MediaDeliveryRuntime) -> None:
    global _ACTIVE_RUNTIME
    _ACTIVE_RUNTIME = runtime


def active_media_delivery_runtime() -> MediaDeliveryRuntime:
    runtime = _ACTIVE_RUNTIME
    if runtime is None:
        raise RuntimeError("Durable media delivery runtime is not configured.")
    return runtime


async def redeliver_owned_task(
    callback: Any,
    *,
    database: Database,
    workspace_id: int,
    task_id_text: str,
) -> None:
    try:
        task_id = UUID(str(task_id_text))
    except (TypeError, ValueError):
        await callback.answer("Некорректный ID задачи.", show_alert=True)
        return

    row = await get_owned_success_task(
        database,
        task_id=task_id,
        workspace_id=int(workspace_id),
        actor_user_id=int(callback.from_user.id),
    )
    if row is None:
        await callback.answer(
            "Готовая задача не найдена или принадлежит другому пользователю.",
            show_alert=True,
        )
        return

    try:
        runtime = active_media_delivery_runtime()
        await runtime.repository.backfill_task(task_id=task_id)
        await runtime.resolver.execute(task_id=task_id)
        await callback.answer("Повторяю доставку без новой генерации и списания.")
        summary = await runtime.redelivery.execute(
            task_id=task_id,
            chat_id=_callback_chat_id(callback),
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:  # p2-approved-boundary: report-redelivery-failure
        failure = classify_media_delivery_error(error, phase="redelivery")
        logger.error(
            "media_redelivery_failed task=%s code=%s fingerprint=%s",
            task_id,
            failure.code,
            failure.fingerprint,
        )
        raise_if_programming_error(error, phase="redelivery")
        await callback.answer(
            "Не удалось восстановить сохранённый результат. "
            "Новая генерация и новое списание не запускались.",
            show_alert=True,
        )
        return

    if summary is None:
        await callback.bot.send_message(
            _callback_chat_id(callback),
            "Сохранённое состояние результата не найдено. "
            "Новая генерация не запускалась.",
        )


def _callback_chat_id(callback: Any) -> int:
    message = getattr(callback, "message", None)
    chat = getattr(message, "chat", None)
    if chat is not None and getattr(chat, "id", None) is not None:
        return int(chat.id)
    return int(callback.from_user.id)


__all__ = (
    "KieProviderResultResolver",
    "MediaDeliveryRuntime",
    "active_media_delivery_runtime",
    "build_media_delivery_runtime",
    "configure_media_delivery_runtime",
    "ensure_media_delivery_runtime",
    "redeliver_owned_task",
)
