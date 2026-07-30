from __future__ import annotations

from velvet_bot.application.media_tasks import task_result_urls

from velvet_bot.application.workspace_tasks import get_owned_success_task

from velvet_bot.application.media_tasks import task_payload_mapping
from velvet_bot.domains.media_generation.model_catalog import (
    media_model_display_name,
)

import asyncio
import importlib
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from uuid import UUID

from aiogram.types import InlineKeyboardButton

from velvet_bot.core.config.kie import load_kie_settings
from velvet_bot.domains.media_generation.models import KieTaskState
from velvet_bot.infrastructure.ai import KieClient

logger = logging.getLogger(__name__)
_INSTALLED = False
_Redeliver = Callable[..., Awaitable[None]]
_ORIGINAL_REDELIVER: _Redeliver | None = None
_DELIVERY_ERRORS = (RuntimeError, ValueError, OSError, TypeError, AttributeError)


def provider_task_id(
    result: Mapping[str, object],
    payload: Mapping[str, object],
) -> str | None:
    runtime = task_payload_mapping(payload.get("kie_campaign"))
    for container in (result, payload, runtime):
        for key in (
            "provider_task_id",
            "last_provider_task_id",
            "active_provider_task_id",
        ):
            value = str(container.get(key) or "").strip()
            if value:
                return value
    return None


async def _load_provider_urls(provider_task_id: str) -> tuple[str, ...]:
    settings = load_kie_settings()
    if not settings.enabled or settings.api_key is None:
        raise RuntimeError("Провайдер генерации выключен на сервере.")
    client = KieClient(
        api_key=settings.api_key,
        grs_api_key=settings.grs_api_key,
        models=settings.models,
        base_url=settings.base_url,
        file_upload_base_url=settings.file_upload_base_url,
        grs_base_url=settings.grs_base_url,
        timeout_seconds=settings.timeout_seconds,
        poll_interval_seconds=settings.poll_interval_seconds,
        task_timeout_seconds=settings.task_timeout_seconds,
    )
    record = await client.get_task(provider_task_id)
    if record.state is not KieTaskState.SUCCESS:
        raise RuntimeError(
            "Провайдер пока не подтверждает готовый результат: "
            f"{record.state.value}."
        )
    return tuple(str(url).strip() for url in record.result_urls if str(url).strip())


async def _persist_provider_urls(
    database: Any,
    *,
    task_id: UUID,
    provider_task_id: str,
    urls: tuple[str, ...],
) -> None:
    async with database.acquire() as connection:
        await connection.execute(
            """
            UPDATE ai_tasks
            SET result = COALESCE(result, '{}'::JSONB)
                         || jsonb_build_object(
                                'provider_task_id', $2::TEXT,
                                'result_urls', to_jsonb($3::TEXT[])
                            ),
                updated_at = NOW()
            WHERE id = $1::UUID
            """,
            task_id,
            provider_task_id,
            list(urls),
        )


def delivery_buttons_for_all_success(
    *,
    portal: Any,
    page: Any,
    results: Any,
    workspace_id: int,
) -> list[list[InlineKeyboardButton]]:
    del results
    recovery = importlib.import_module(
        "velvet_bot.app.auf_result_delivery_recovery"
    )
    rows: list[list[InlineKeyboardButton]] = []
    for row in page:
        if str(row["status"]) != "success":
            continue
        request = task_payload_mapping(task_payload_mapping(row["payload"]).get("request"))
        model_alias = str(request.get("model") or "").strip()
        model = media_model_display_name(model_alias, fallback="Результат")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📤 Доставить · {model}"[:60],
                    callback_data=recovery.delivery_callback(
                        workspace_id=workspace_id,
                        task_id=row["id"],
                    ),
                )
            ]
        )
    return rows


def _original_redeliver() -> _Redeliver:
    original = _ORIGINAL_REDELIVER
    if original is None:
        raise RuntimeError("Повторная доставка Ауф не была установлена.")
    return original


async def _redeliver_with_provider_recovery(
    callback: Any,
    *,
    database: Any,
    workspace_id: int,
    task_id_text: str,
) -> None:
    try:
        task_id = UUID(task_id_text)
    except (TypeError, ValueError):
        await callback.answer("Некорректный ID задачи.", show_alert=True)
        return

    row = await get_owned_success_task(
        database,
        task_id=task_id,
        workspace_id=workspace_id,
        actor_user_id=callback.from_user.id,
    )
    if row is None:
        await callback.answer(
            "Готовая задача не найдена или принадлежит другому пользователю.",
            show_alert=True,
        )
        return

    result = task_payload_mapping(row["result"])
    if task_result_urls(result):
        await _original_redeliver()(
            callback,
            database=database,
            workspace_id=workspace_id,
            task_id_text=task_id_text,
        )
        return

    payload = task_payload_mapping(row["payload"])
    resolved_provider_task_id = provider_task_id(result, payload)
    if resolved_provider_task_id is None:
        await callback.answer(
            "У задачи не сохранился ID провайдера. Повторная генерация не запускалась.",
            show_alert=True,
        )
        return

    try:
        urls = await _load_provider_urls(resolved_provider_task_id)
        if not urls:
            raise RuntimeError("Провайдер вернул готовую задачу без URL результата.")
        await _persist_provider_urls(
            database,
            task_id=task_id,
            provider_task_id=resolved_provider_task_id,
            urls=urls,
        )
    except asyncio.CancelledError:
        raise
    except _DELIVERY_ERRORS as error:
        logger.exception(
            "Could not recover completed provider result task=%s provider_task=%s",
            task_id,
            resolved_provider_task_id,
        )
        await callback.answer(
            "Не удалось получить сохранённый результат у провайдера: "
            f"{str(error)[:250]}",
            show_alert=True,
        )
        return

    await _original_redeliver()(
        callback,
        database=database,
        workspace_id=workspace_id,
        task_id_text=task_id_text,
    )


def install_auf_active_delivery_fix() -> None:
    global _INSTALLED, _ORIGINAL_REDELIVER
    if _INSTALLED:
        return

    recovery = importlib.import_module(
        "velvet_bot.app.auf_result_delivery_recovery"
    )
    workers = importlib.import_module("velvet_bot.app.workers")

    _ORIGINAL_REDELIVER = recovery.get_redelivery_handler()
    recovery.install_redelivery_handler(_redeliver_with_provider_recovery)
    recovery.install_task_delivery_buttons(delivery_buttons_for_all_success)

    active_worker = workers.KieGenerationWorker
    active_worker.install_delivery_handler(recovery.deliver_record_with_recovery)
    logger.info(
        "Installed Auf delivery fix on active worker class=%s",
        active_worker.__name__,
    )
    _INSTALLED = True


__all__ = (
    "delivery_buttons_for_all_success",
    "install_auf_active_delivery_fix",
    "provider_task_id",
)
