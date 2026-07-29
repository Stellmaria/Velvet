from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.core.access import AccessPolicy
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import AITaskQueueService, AIUsageService
from velvet_bot.domains.media_generation import KieModelAlias
from velvet_bot.presentation.telegram.routers.workspace_meow import (
    MeowCallback,
    MeowForm,
    _callback,
    _edit_or_answer,
    _quality_selection_text,
    build_quality_keyboard,
    handle_meow_action as handle_legacy_meow_action,
)


def build_model_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
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


def model_selection_text() -> str:
    return (
        "<b>Выберите модель</b>\n\n"
        "Nano Banana 2 и Nano Banana Pro отправляются через GRS AI. "
        "Seedream 5 Pro остаётся на Kie.ai.\n"
        "Для обеих Banana доступны 1K, 2K и 4K по единому документированному "
        "GRS API-контракту."
    )


async def handle_meow_action(
    callback: CallbackQuery,
    callback_data: MeowCallback,
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
            await callback.answer("Мяу доступен только владельцу бота.", show_alert=True)
            return
        if not kie_settings.enabled:
            await callback.answer("AI-генерация выключена на сервере.", show_alert=True)
            return
        await state.set_state(MeowForm.choosing_model)
        await _edit_or_answer(
            callback,
            text=model_selection_text(),
            reply_markup=build_model_keyboard(workspace_id=workspace_id),
        )
        return
    if action == "model" and callback_data.value == KieModelAlias.NANO_BANANA_2.value:
        if not access_policy.allows_user(callback.from_user):
            await callback.answer("Мяу доступен только владельцу бота.", show_alert=True)
            return
        if not kie_settings.enabled:
            await callback.answer("AI-генерация выключена на сервере.", show_alert=True)
            return
        model = KieModelAlias.NANO_BANANA_2
        try:
            kie_settings.models.provider_model(model)
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        await state.update_data(meow_model=model.value)
        await state.set_state(MeowForm.choosing_quality)
        await _edit_or_answer(
            callback,
            text=_quality_selection_text(model),
            reply_markup=build_quality_keyboard(
                workspace_id=workspace_id,
                model=model,
            ),
        )
        return
    await handle_legacy_meow_action(
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
    "handle_meow_action",
    "model_selection_text",
)
