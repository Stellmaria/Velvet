from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Awaitable, Callable, Mapping
from html import escape
from typing import Any
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.application.media_tasks import task_payload_mapping, task_result_urls
from velvet_bot.application.workspace_tasks import get_owned_success_task
from velvet_bot.core.config.kie import load_kie_settings
from velvet_bot.domains.auf_wallet import format_auf_units
from velvet_bot.domains.media_generation.model_catalog import media_model_display_name
from velvet_bot.domains.media_generation.models import KieTaskState
from velvet_bot.infrastructure.ai import KieClient
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback
from velvet_bot.presentation.telegram.routers.workspace_auf_video import edit_or_answer

logger = logging.getLogger(__name__)
_INSTALLED = False
_Redeliver = Callable[..., Awaitable[None]]
_ORIGINAL_REDELIVER: _Redeliver | None = None
_DELIVERY_ERRORS = (RuntimeError, ValueError, OSError, TypeError, AttributeError)
_VIDEO_MODELS = frozenset(
    {
        "grok_imagine_video",
        "grok_imagine_video_15",
        "seedance_15_pro_video",
        "wan_26_image_to_video",
    }
)
_INPUT_MODE_NAMES = {
    "text": "Только текст",
    "photo_text": "Фото + текст",
}
_TASK_STATUS = {
    "queued": "⏳ в очереди",
    "running": "⚙️ выполняется",
    "success": "✅ готово",
    "error": "❌ ошибка",
    "cancelled": "🚫 отменено",
}
_CHARGE_STATUS = {
    "reserved": "зарезервировано",
    "captured": "списано",
    "refunded": "возвращено после ошибки",
    "released": "возвращено после отмены",
}


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


async def _load_provider_urls(provider_task_id_value: str) -> tuple[str, ...]:
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
    record = await client.get_task(provider_task_id_value)
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
    provider_task_id_value: str,
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
            provider_task_id_value,
            list(urls),
        )


def _integer(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def task_card_text(*, row: Any, offset: int) -> str:
    payload = task_payload_mapping(row["payload"])
    request = task_payload_mapping(payload.get("request"))
    model_alias = str(request.get("model") or "").strip()
    model = media_model_display_name(model_alias)
    status_raw = str(row["status"])
    status = _TASK_STATUS.get(status_raw, status_raw)
    media_type = "Видео" if model_alias in _VIDEO_MODELS else "Изображение"
    mode_raw = str(request.get("input_mode") or "").strip()
    mode = _INPUT_MODE_NAMES.get(mode_raw, mode_raw.replace("_", " ").title())
    resolution = str(request.get("resolution") or "").strip()
    created_at = row["created_at"].strftime("%d.%m %H:%M")
    task_id = str(row["id"])
    quoted_units = _integer(row["quoted_units"])
    charge_status_raw = str(row["charge_status"] or "")
    charge_status = _CHARGE_STATUS.get(
        charge_status_raw,
        charge_status_raw or "учтено",
    )

    lines = [
        "<b>🧾 Мои задачи Ауф</b>",
        (
            "<i>Последняя задача</i>"
            if offset == 0
            else f"<i>Задача {offset + 1} в истории</i>"
        ),
        "",
        f"<b>{escape(model)}</b>",
        f"Статус: {escape(status)}",
        f"Тип: <b>{media_type}</b>",
    ]
    if mode:
        lines.append(f"Режим: <b>{escape(mode)}</b>")
    if resolution:
        lines.append(f"Качество: <b>{escape(resolution)}</b>")
    lines.extend(
        [
            f"Создана: <b>{created_at}</b>",
            f"ID: <code>{escape(task_id[:8])}</code>",
            "",
        ]
    )
    if quoted_units > 0:
        lines.extend(
            [
                f"Стоимость: <b>{format_auf_units(quoted_units)}</b>",
                f"Расчёт: <b>{escape(charge_status)}</b>",
            ]
        )
    else:
        lines.extend(
            [
                "Тип учёта: <b>личная задача</b>",
                "Списаний Ауф: <b>нет</b>",
            ]
        )

    lines.append("")
    if status_raw == "success":
        lines.extend(
            [
                "Нажмите <b>«Получить результат»</b>, чтобы бот повторно "
                "отправил уже готовый файл.",
                "<i>Новая генерация и новое списание не запускаются.</i>",
            ]
        )
    elif status_raw in {"queued", "running"}:
        lines.append("Задача ещё выполняется. Нажмите «Обновить карточку» позже.")
    else:
        lines.append("Для этой задачи готового результата нет.")
    return "\n".join(lines)


def _task_history_callback(*, workspace_id: int, offset: int) -> str:
    return AufCallback(
        action="wallet_tasks",
        workspace_id=int(workspace_id),
        offset=max(0, int(offset)),
    ).pack()


def task_card_keyboard(
    *,
    row: Any | None,
    workspace_id: int,
    offset: int,
    has_older: bool,
) -> InlineKeyboardMarkup:
    recovery = importlib.import_module("velvet_bot.app.auf_result_delivery_recovery")
    rows: list[list[InlineKeyboardButton]] = []
    if row is not None and str(row["status"]) == "success":
        rows.append(
            [
                InlineKeyboardButton(
                    text="📥 Получить результат",
                    callback_data=recovery.delivery_callback(
                        workspace_id=workspace_id,
                        task_id=row["id"],
                    ),
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []
    if offset > 0:
        navigation.append(
            InlineKeyboardButton(
                text="← Новее",
                callback_data=_task_history_callback(
                    workspace_id=workspace_id,
                    offset=offset - 1,
                ),
            )
        )
    if has_older:
        navigation.append(
            InlineKeyboardButton(
                text="Старее →",
                callback_data=_task_history_callback(
                    workspace_id=workspace_id,
                    offset=offset + 1,
                ),
            )
        )
    if navigation:
        rows.append(navigation)

    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🔄 Обновить карточку",
                    callback_data=_task_history_callback(
                        workspace_id=workspace_id,
                        offset=offset,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Кошелёк",
                    callback_data=AufCallback(
                        action="wallet",
                        workspace_id=workspace_id,
                    ).pack(),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_user_task_card(
    callback: Any,
    *,
    state: Any,
    database: Any,
    workspace_id: int,
    offset: int,
) -> None:
    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")
    await state.clear()
    normalized_offset = max(0, int(offset))
    history = await portal.load_user_tasks(
        database,
        workspace_id=workspace_id,
        actor_user_id=callback.from_user.id,
        offset=normalized_offset,
    )
    row = history[0] if history else None
    has_older = len(history) > 1
    text = (
        task_card_text(row=row, offset=normalized_offset)
        if row is not None
        else "<b>🧾 Мои задачи Ауф</b>\n\nЗадач пока нет."
    )
    await edit_or_answer(
        callback,
        text=text,
        reply_markup=task_card_keyboard(
            row=row,
            workspace_id=workspace_id,
            offset=normalized_offset,
            has_older=has_older,
        ),
    )


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
            provider_task_id_value=resolved_provider_task_id,
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

    recovery = importlib.import_module("velvet_bot.app.auf_result_delivery_recovery")
    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")
    workers = importlib.import_module("velvet_bot.app.workers")

    _ORIGINAL_REDELIVER = recovery.get_redelivery_handler()
    recovery.install_redelivery_handler(_redeliver_with_provider_recovery)
    portal.install_user_tasks_renderer(render_user_task_card)

    active_worker = workers.KieGenerationWorker
    active_worker.install_delivery_handler(recovery.deliver_record_with_recovery)
    logger.info(
        "Installed Auf delivery fix on active worker class=%s",
        active_worker.__name__,
    )
    _INSTALLED = True


__all__ = (
    "install_auf_active_delivery_fix",
    "provider_task_id",
    "render_user_task_card",
    "task_card_keyboard",
    "task_card_text",
)
