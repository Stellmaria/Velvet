from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.config.kie import KieSettings
from velvet_bot.domains.auf_runtime import (
    AufRuntimeAccessError,
    AufRuntimeService,
)
from velvet_bot.presentation.telegram.routers import workspace_meow as workspace_meow_router
from velvet_bot.presentation.telegram.routers.workspace_meow import MeowCallback
from velvet_bot.workspace_ui import WorkspaceCallback


_ORIGINAL_BUILD_AUF_ROOT_KEYBOARD = workspace_meow_router.build_meow_root_keyboard
_ROOT_BUTTON_LABELS = {
    "Создать": "Фото",
    "Оживить": "Видео",
}


def build_auf_root_keyboard(
    *,
    workspace_id: int,
    enabled: bool,
) -> InlineKeyboardMarkup:
    base = _ORIGINAL_BUILD_AUF_ROOT_KEYBOARD(
        workspace_id=workspace_id,
        enabled=enabled,
    )
    rows: list[list[InlineKeyboardButton]] = []
    for row in base.inline_keyboard:
        updated_row: list[InlineKeyboardButton] = []
        for button in row:
            label = _ROOT_BUTTON_LABELS.get(button.text)
            if label is None:
                updated_row.append(button)
                continue
            copy_method = getattr(button, "model_copy", None)
            if copy_method is None:
                copy_method = button.copy
            updated_row.append(copy_method(update={"text": label}))
        rows.append(updated_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


# Compatibility boundary for the pre-Auf router module. New code should import
# build_auf_root_keyboard from this module.
build_meow_root_keyboard = build_auf_root_keyboard
workspace_meow_router.build_meow_root_keyboard = build_auf_root_keyboard


def _build_root_keyboard(
    *,
    workspace_id: int,
    enabled: bool,
    grs_enabled: bool,
    global_owner: bool,
    module_visible: bool,
) -> InlineKeyboardMarkup:
    base = build_auf_root_keyboard(workspace_id=workspace_id, enabled=enabled)
    rows = list(base.inline_keyboard)
    back_row = rows.pop() if rows else []
    if enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⚙️ Параллельность",
                    callback_data=MeowCallback(
                        action="runtime",
                        workspace_id=workspace_id,
                    ).pack(),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        "🙈 Скрыть Ауф в моём меню"
                        if module_visible
                        else "👁 Показать Ауф в моём меню"
                    ),
                    callback_data=MeowCallback(
                        action="visibility_toggle",
                        workspace_id=workspace_id,
                    ).pack(),
                )
            ]
        )
        if global_owner:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="Баланс Kie · очередь",
                        callback_data=MeowCallback(
                            action="balance",
                            workspace_id=workspace_id,
                        ).pack(),
                    )
                ]
            )
            if grs_enabled:
                rows.append(
                    [
                        InlineKeyboardButton(
                            text="Баланс GRS AI",
                            callback_data=MeowCallback(
                                action="grs_balance",
                                workspace_id=workspace_id,
                            ).pack(),
                        )
                    ]
                )
    if back_row:
        rows.append(back_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def handle_auf_root_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    kie_settings: KieSettings,
    meow_runtime_service: AufRuntimeService,
) -> None:
    workspace_id = callback_data.workspace_id
    user_id = callback.from_user.id
    try:
        await meow_runtime_service.require_workspace_access(
            workspace_id=workspace_id,
            actor_user_id=user_id,
        )
        workspace_settings = await meow_runtime_service.workspace_settings(
            workspace_id=workspace_id,
            actor_user_id=user_id,
        )
    except (AufRuntimeAccessError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return

    global_owner = meow_runtime_service.is_global_owner(user_id)
    module_visible = await meow_runtime_service.module_is_visible(
        workspace_id=workspace_id,
        actor_user_id=user_id,
    )
    await state.clear()
    if kie_settings.enabled:
        grs_line = (
            "Nano Banana 2 и Nano Banana Pro через GRS AI"
            if kie_settings.grs_api_key
            else "Nano Banana 2/Pro скрыты до настройки GRS_API_KEY"
        )
        if global_owner:
            runtime = await meow_runtime_service.runtime_settings(actor_user_id=user_id)
            concurrency = (
                f"Kie до <b>{runtime.kie_concurrency_limit}</b>, "
                f"GRS до <b>{runtime.grs_concurrency_limit}</b>"
            )
        else:
            concurrency = (
                f"до <b>{workspace_settings.concurrency_limit}</b> одновременно "
                "для этого пространства"
            )
        text = (
            "<b>Ауф</b>\n\n"
            f"<b>Фото</b> — {grs_line}; Seedream 5 Pro через Kie.ai. "
            "Можно использовать текст и референсы из базы или Telegram.\n\n"
            "<b>Видео</b> — фото и описание движения превращаются в видео через "
            "Grok Imagine v1, Grok Imagine 1.5, Seedance 1.5 Pro или Wan 2.7.\n\n"
            f"Параллельность: {concurrency}.\n"
            f"Автоповторов на задачу: <b>{kie_settings.generation_max_attempts}</b>.\n\n"
            "Настройки применяются из PostgreSQL без перезапуска бота."
        )
    else:
        text = (
            "<b>Ауф</b>\n\n"
            "Интерфейс установлен, но AI-генерация выключена. Заполните KIE_API_KEY, "
            "GRS_API_KEY, KIE_USD_TO_RUB и model id, затем включите KIE_ENABLED=true."
        )
    keyboard = _build_root_keyboard(
        workspace_id=workspace_id,
        enabled=kie_settings.enabled,
        grs_enabled=bool(kie_settings.grs_api_key),
        global_owner=global_owner,
        module_visible=module_visible,
    )
    if isinstance(callback.message, Message):
        if callback.message.photo or callback.message.video or callback.message.document:
            await callback.message.answer(text, reply_markup=keyboard)
        else:
            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
            except TelegramBadRequest as error:
                if "message is not modified" not in str(error).casefold():
                    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


# Existing router registration imports the historical name. Keep it as an alias
# until the callback/router stack is migrated in one coordinated change.
handle_meow_root_entry = handle_auf_root_entry


__all__ = (
    "build_auf_root_keyboard",
    "build_meow_root_keyboard",
    "handle_auf_root_entry",
    "handle_meow_root_entry",
)
