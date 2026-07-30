from __future__ import annotations

import importlib
from html import escape
from typing import Any

from aiogram import F
from aiogram.filters import Command, or_f
from aiogram.types import InlineKeyboardMarkup, Message

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import AITaskRequest
from velvet_bot.domains.auf_wallet import (
    AufPricingRepository,
    format_auf_units,
)
from velvet_bot.domains.media_generation import KIE_GENERATION_TASK_TYPE
from velvet_bot.presentation.telegram.routers import workspace_auf_photo as photo_router

from velvet_bot.presentation.telegram.routers.workspace_auf_legacy import MeowPhotoForm
from velvet_bot.presentation.telegram.routers.workspace_auf_photo_adjustments import (
    handle_photo_remove_last,
)

_INSTALLED = False


def _state_value(data, key: str):
    if key in data:
        return data[key]
    return data.get(key.replace("auf_", "meow_", 1))

def _copy_button(button, *, text: str):
    copy_method = getattr(button, "model_copy", None)
    if copy_method is None:
        copy_method = button.copy
    return copy_method(update={"text": text})


def _final_keyboard(*, workspace_id: int, model, quoted_units: int) -> InlineKeyboardMarkup:
    base = photo_router._final_keyboard(workspace_id, model)
    rows = [list(row) for row in base.inline_keyboard]
    if rows and rows[0]:
        rows[0][0] = _copy_button(
            rows[0][0],
            text=f"Да, создать · {format_auf_units(quoted_units)}",
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_auf_final(
    callback,
    state,
    *,
    database,
    wallet_service,
) -> None:
    data = await state.get_data()
    request = photo_router._request(data)
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    quote = await AufPricingRepository(database).quote(
        {
            "workspace_id": workspace_id,
            "request": request.to_task_payload(),
        }
    )
    await state.update_data(
        auf_expected_price_version=quote.version_key,
        auf_expected_quoted_units=quote.quoted_units,
    )
    overview = await wallet_service.overview(
        workspace_id=workspace_id,
        actor_user_id=callback.from_user.id,
        history_limit=1,
    )
    global_owner = wallet_service.is_global_owner(callback.from_user.id)
    available_units = overview.wallet.available_units
    enough = global_owner or available_units >= quote.quoted_units
    remaining_units = max(0, available_units - quote.quoted_units)
    ratio = "как у исходника" if request.aspect_ratio == "auto" else request.aspect_ratio

    if global_owner:
        wallet_line = (
            f"Учётная цена: <b>{format_auf_units(quote.quoted_units)}</b>\n"
            "Списание Стэл: <b>0 Ауф</b>"
        )
    elif enough:
        wallet_line = (
            f"Цена: <b>{format_auf_units(quote.quoted_units)}</b>\n"
            f"Доступно: <b>{format_auf_units(available_units)}</b>\n"
            f"Останется: <b>{format_auf_units(remaining_units)}</b>"
        )
    else:
        missing = quote.quoted_units - available_units
        wallet_line = (
            f"Цена: <b>{format_auf_units(quote.quoted_units)}</b>\n"
            f"Доступно: <b>{format_auf_units(available_units)}</b>\n"
            f"Не хватает: <b>{format_auf_units(missing)}</b>"
        )

    await state.set_state(photo_router.AufPhotoForm.confirming_generation)
    await photo_router._edit_or_answer(
        callback,
        text=(
            "<b>Проверьте перед созданием</b>\n\n"
            f"Модель: <b>{escape(request.model.display_name)}</b>\n"
            f"Фото: <b>{len(request.references)}</b> из "
            f"{request.model.max_photo_references}\n"
            f"Качество: <b>{escape(request.resolution)}</b>\n"
            f"Соотношение: <b>{escape(ratio)}</b>\n"
            "Результат: <b>1 изображение</b>\n"
            "Контент: <b>Mature</b>\n\n"
            f"<b>Стоимость в Ауф</b>\n{wallet_line}\n\n"
            f"<b>Текст</b>\n{escape(photo_router._truncate(request.prompt, 2200))}\n\n"
            "<i>Цена и версия тарифа фиксируются при подтверждении. "
            "Если тариф изменится до запуска, бот попросит подтвердить новую сумму.</i>"
        ),
        reply_markup=_final_keyboard(
            workspace_id=workspace_id,
            model=request.model,
            quoted_units=quote.quoted_units,
        ),
    )


async def _enqueue_auf_photo(
    callback,
    state,
    *,
    kie_settings,
    ai_usage_service,
    ai_task_queue_service,
    database,
) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    request = photo_router._request(data)
    expected_version = str(data.get("auf_expected_price_version") or "").strip()
    expected_units = int(data.get("auf_expected_quoted_units") or 0)
    if not expected_version or expected_units <= 0:
        await callback.answer(
            "Цена Ауф устарела. Вернитесь к настройкам и подтвердите её снова.",
            show_alert=True,
        )
        return

    rub = kie_settings.pricing.estimate_rub(
        request,
        usd_to_rub=kie_settings.usd_to_rub,
    )
    block_reason = photo_router._budget_block_reason(
        await ai_usage_service.status(),
        estimated_cost_rub=rub,
    )
    if block_reason is not None:
        await callback.answer(block_reason, show_alert=True)
        return

    chat_id = callback.message.chat.id if isinstance(callback.message, Message) else None
    result = await ai_task_queue_service.enqueue(
        AITaskRequest(
            scope=AIBudgetScope.VISION,
            task_type=KIE_GENERATION_TASK_TYPE,
            payload={
                "request": request.to_task_payload(),
                "chat_id": chat_id,
                "user_id": callback.from_user.id,
                "workspace_id": workspace_id,
                "auf_expected_price_version": expected_version,
                "auf_expected_quoted_units": expected_units,
            },
            priority=40,
            max_attempts=3,
            created_by=callback.from_user.id,
            estimated_cost_rub=rub,
        )
    )
    await state.clear()
    await photo_router._edit_or_answer(
        callback,
        text=(
            f"<b>Ауф · {escape(request.model.display_name)}</b>\n\n"
            "Фото и текст зафиксированы, задача поставлена в очередь.\n\n"
            f"Фото: <b>{len(request.references)}</b>\n"
            f"Качество: <b>{escape(request.resolution)}</b>\n"
            f"Зарезервировано: <b>{format_auf_units(expected_units)}</b>\n"
            f"Задача: <code>{result.task.id}</code>"
        ),
        reply_markup=photo_router.build_auf_root_keyboard(
            workspace_id=workspace_id,
            enabled=True,
        ),
    )


def install_auf_photo_ui() -> None:
    """Install the capability-aware photo flow over the historical callback protocol."""

    global _INSTALLED
    if _INSTALLED:
        return

    controller = importlib.import_module(
        "velvet_bot.presentation.telegram.workspace_home_controller"
    )
    original_action = controller.handle_scoped_auf_action
    original_register = controller.register_workspace_home

    async def handle_scoped_auf_photo_action(
        callback,
        callback_data,
        state,
        access_policy,
        kie_settings,
        database,
        ai_usage_service,
        ai_task_queue_service,
        auf_runtime_service,
        auf_wallet_service,
        auf_purchase_service,
    ) -> None:
        action = callback_data.action
        if action != "create" and not action.startswith("photo"):
            await original_action(
                callback,
                callback_data,
                state,
                access_policy,
                kie_settings,
                database,
                ai_usage_service,
                ai_task_queue_service,
                auf_runtime_service,
                auf_wallet_service,
                auf_purchase_service,
            )
            return
        if not await controller._require_auf_callback(
            callback,
            workspace_id=callback_data.workspace_id,
            service=auf_runtime_service,
        ):
            return
        if action == "photo_remove_last":
            await handle_photo_remove_last(callback, callback_data, state)
            return
        if action == "photo_ratio":
            model = photo_router._model((await state.get_data()).get("meow_model"))
            ratio = callback_data.value
            if model is None or ratio not in model.supported_aspect_ratios:
                await callback.answer("Недоступное соотношение сторон.", show_alert=True)
                return
            await state.update_data(auf_aspect_ratio=ratio)
            await _show_auf_final(
                callback,
                state,
                database=database,
                wallet_service=auf_wallet_service,
            )
            return
        if action == "photo_generate":
            await _enqueue_auf_photo(
                callback,
                state,
                kie_settings=kie_settings,
                ai_usage_service=ai_usage_service,
                ai_task_queue_service=ai_task_queue_service,
                database=database,
            )
            return
        await photo_router.handle_auf_photo_action(
            callback,
            callback_data,
            state,
            controller._AufScopedAccessPolicy(),
            kie_settings,
            database,
            ai_usage_service,
            ai_task_queue_service,
        )

    async def handle_scoped_auf_photo_input(
        message,
        state,
        access_policy,
        kie_settings,
        auf_runtime_service,
    ) -> None:
        if not await controller._require_auf_message(
            message,
            state,
            workspace_key="auf_workspace_id",
            service=auf_runtime_service,
        ):
            return
        await photo_router.handle_auf_photo_input(
            message,
            state,
            controller._AufScopedAccessPolicy(),
            kie_settings,
        )

    async def handle_scoped_auf_photo_command(
        message,
        state,
        access_policy,
        kie_settings,
        database,
        auf_runtime_service,
    ) -> None:
        if not await controller._require_auf_message(
            message,
            state,
            workspace_key="auf_workspace_id",
            service=auf_runtime_service,
        ):
            return
        await photo_router.handle_auf_photo_command(
            message,
            state,
            controller._AufScopedAccessPolicy(),
            kie_settings,
            database,
        )

    def register_workspace_home_with_photo(router) -> None:
        original_register(router)
        for photo_state in (
            or_f(
                photo_router.AufPhotoForm.collecting_input,
                MeowPhotoForm.collecting_input,
            ),
            or_f(
                photo_router.AufPhotoForm.reviewing_input,
                MeowPhotoForm.reviewing_input,
            ),
        ):
            router.message.register(
                handle_scoped_auf_photo_command,
                photo_state,
                Command("refs"),
            )
            router.message.register(
                handle_scoped_auf_photo_input,
                photo_state,
                F.photo | F.document | F.text,
            )

    controller.handle_scoped_auf_action = handle_scoped_auf_photo_action
    controller.register_workspace_home = register_workspace_home_with_photo
    _INSTALLED = True


__all__ = ("install_auf_photo_ui",)
