from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.config.kie import KieSettings
from velvet_bot.domains.auf_runtime import (
    AufRuntimeAccessError,
    AufRuntimeService,
)
from velvet_bot.presentation.telegram.routers import workspace_auf as workspace_auf_router
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback
from velvet_bot.workspace_ui import WorkspaceCallback


_ORIGINAL_BUILD_AUF_ROOT_KEYBOARD = workspace_auf_router.build_auf_root_keyboard
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


workspace_auf_router.build_auf_root_keyboard = build_auf_root_keyboard


def _build_root_keyboard(
    *,
    workspace_id: int,
    enabled: bool,
    grs_enabled: bool,
    global_owner: bool,
    module_visible: bool,
) -> InlineKeyboardMarkup:
    # Provider-specific balance callbacks remain registered for compatibility with
    # already-sent owner keyboards, but are deliberately absent from the product UI.
    del grs_enabled, global_owner
    base = build_auf_root_keyboard(workspace_id=workspace_id, enabled=enabled)
    rows = list(base.inline_keyboard)
    back_row = rows.pop() if rows else []
    if enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="💳 Ауф · баланс",
                    callback_data=AufCallback(
                        action="wallet",
                        workspace_id=workspace_id,
                    ).pack(),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="⚙️ Параллельность",
                    callback_data=AufCallback(
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
                    callback_data=AufCallback(
                        action="visibility_toggle",
                        workspace_id=workspace_id,
                    ).pack(),
                )
            ]
        )
    if back_row:
        rows.append(back_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def build_auf_root_view(
    *,
    workspace_id: int,
    user_id: int,
    kie_settings: KieSettings,
    auf_runtime_service: AufRuntimeService,
) -> tuple[str, InlineKeyboardMarkup]:
    await auf_runtime_service.require_workspace_access(
        workspace_id=workspace_id,
        actor_user_id=user_id,
    )
    global_owner = auf_runtime_service.is_global_owner(user_id)
    module_visible = await auf_runtime_service.module_is_visible(
        workspace_id=workspace_id,
        actor_user_id=user_id,
    )
    if kie_settings.enabled:
        text = (
            "<b>Ауф</b>\n\n"
            "<b>Фото</b> — Nano Banana 2, Nano Banana Pro и Seedream 5 Pro. "
            "Используйте текст и референсы из базы или Telegram.\n\n"
            "<b>Видео</b> — Grok Imagine v1, Grok Imagine Video 1.5, "
            "Seedance 1.5 Pro и Wan 2.7. Добавьте фото и описание движения.\n\n"
            "Баланс, пакеты покупки и история операций доступны отдельной кнопкой."
        )
    else:
        text = (
            "<b>Ауф</b>\n\n"
            "Генерация сейчас недоступна. Обратитесь к владельцу пространства."
        )
    keyboard = _build_root_keyboard(
        workspace_id=workspace_id,
        enabled=kie_settings.enabled,
        grs_enabled=bool(kie_settings.grs_api_key),
        global_owner=global_owner,
        module_visible=module_visible,
    )
    return text, keyboard


async def handle_auf_root_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    kie_settings: KieSettings,
    auf_runtime_service: AufRuntimeService,
) -> None:
    workspace_id = callback_data.workspace_id
    user_id = callback.from_user.id
    try:
        text, keyboard = await build_auf_root_view(
            workspace_id=workspace_id,
            user_id=user_id,
            kie_settings=kie_settings,
            auf_runtime_service=auf_runtime_service,
        )
    except (AufRuntimeAccessError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return

    await state.clear()
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


__all__ = (
    "build_auf_root_keyboard",
    "build_auf_root_view",
    "handle_auf_root_entry",
)
