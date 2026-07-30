from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.core.access import AccessPolicy
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import AITaskQueueService, AIUsageService
from velvet_bot.domains.media_generation import KieModelAlias
from velvet_bot.presentation.telegram.routers.workspace_auf import (
    AufCallback,
    AufForm,
    _callback,
    _edit_or_answer,
    _quality_selection_text,
    build_quality_keyboard,
    handle_auf_action as _handle_base_auf_action,
)


def build_model_keyboard(
    *,
    workspace_id: int,
    grs_enabled: bool = True,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if grs_enabled:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="Nano Banana 2",
                        callback_data=_callback(
                            "model",
                            workspace_id=workspace_id,
                            value=KieModelAlias.NANO_BANANA_2.value,
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Nano Banana Pro",
                        callback_data=_callback(
                            "model",
                            workspace_id=workspace_id,
                            value=KieModelAlias.NANO_BANANA_PRO.value,
                        ),
                    )
                ],
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="Seedream 5 Pro",
                    callback_data=_callback(
                        "model",
                        workspace_id=workspace_id,
                        value=KieModelAlias.SEEDREAM_5_PRO.value,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К проверке",
                    callback_data=_callback("review", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=_callback("cancel", workspace_id=workspace_id),
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def model_selection_text(*, grs_enabled: bool = True) -> str:
    if not grs_enabled:
        return (
            "<b>Выберите модель</b>\n\n"
            "Сейчас доступен Seedream 5 Pro. Остальные фото-модели временно "
            "недоступны."
        )
    return (
        "<b>Выберите модель</b>\n\n"
        "Выберите подходящую фото-модель. Доступные варианты качества появятся "
        "на следующем шаге."
    )


async def handle_auf_action(
    callback: CallbackQuery,
    callback_data: AufCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
    database: Database,
    ai_usage_service: AIUsageService,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    action = callback_data.action
    workspace_id = callback_data.workspace_id
    if action == "request_confirm":
        if not access_policy.allows_user(callback.from_user):
            await callback.answer("Ауф доступен только владельцу бота.", show_alert=True)
            return
        if not kie_settings.enabled:
            await callback.answer("Генерация сейчас недоступна.", show_alert=True)
            return
        grs_enabled = bool(kie_settings.grs_api_key)
        await state.set_state(AufForm.choosing_model)
        await _edit_or_answer(
            callback,
            text=model_selection_text(grs_enabled=grs_enabled),
            reply_markup=build_model_keyboard(
                workspace_id=workspace_id,
                grs_enabled=grs_enabled,
            ),
        )
        return
    if action == "model" and callback_data.value in {
        KieModelAlias.NANO_BANANA_2.value,
        KieModelAlias.NANO_BANANA_PRO.value,
    }:
        if not access_policy.allows_user(callback.from_user):
            await callback.answer("Ауф доступен только владельцу бота.", show_alert=True)
            return
        if not kie_settings.enabled:
            await callback.answer("Генерация сейчас недоступна.", show_alert=True)
            return
        if not kie_settings.grs_api_key:
            await callback.answer(
                "Эта модель сейчас недоступна. Выберите другую или повторите позже.",
                show_alert=True,
            )
            return
        model = KieModelAlias(str(callback_data.value))
        try:
            kie_settings.models.provider_model(model)
        except ValueError:
            await callback.answer(
                "Модель временно недоступна из-за ошибки настройки.",
                show_alert=True,
            )
            return
        await state.update_data(auf_model=model.value)
        await state.set_state(AufForm.choosing_quality)
        await _edit_or_answer(
            callback,
            text=_quality_selection_text(model),
            reply_markup=build_quality_keyboard(
                workspace_id=workspace_id,
                model=model,
            ),
        )
        return
    await _handle_base_auf_action(
        callback,
        callback_data,
        state,
        access_policy,
        kie_settings,
        database,
        ai_usage_service,
        ai_task_queue_service,
    )


__all__ = (
    "build_model_keyboard",
    "handle_auf_action",
    "model_selection_text",
)
