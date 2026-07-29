from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.access import AccessPolicy
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.presentation.telegram.routers.workspace_meow import (
    MeowCallback,
    build_meow_root_keyboard,
)
from velvet_bot.workspace_ui import WorkspaceCallback


def _build_root_keyboard(
    *,
    workspace_id: int,
    enabled: bool,
    grs_enabled: bool,
) -> InlineKeyboardMarkup:
    base = build_meow_root_keyboard(workspace_id=workspace_id, enabled=enabled)
    if not enabled:
        return base
    rows = list(base.inline_keyboard)
    back_row = rows.pop() if rows else []
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


async def handle_meow_root_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
) -> None:
    if not access_policy.allows_user(callback.from_user):
        await callback.answer("Мяу доступен только владельцу бота.", show_alert=True)
        return
    await state.clear()
    if kie_settings.enabled:
        grs_line = (
            "Nano Banana 2 и Nano Banana Pro через GRS AI"
            if kie_settings.grs_api_key
            else "Nano Banana 2/Pro скрыты до настройки GRS_API_KEY"
        )
        text = (
            "<b>Мяу</b>\n\n"
            f"<b>Создать</b> — {grs_line}; Seedream 5 Pro через Kie.ai. "
            "Можно использовать текст и референсы из базы или Telegram.\n\n"
            "<b>Оживить</b> — фото и описание движения превращаются в видео через "
            "Grok Imagine v1, Seedance 1.5 Pro или Wan 2.6.\n\n"
            f"Параллельных генераций: <b>до {kie_settings.max_concurrent_generations}</b>. "
            f"Автоповторов на задачу: <b>{kie_settings.generation_max_attempts}</b>.\n\n"
            "Баланс Kie и баланс GRS AI вынесены в отдельные экраны. "
            "GRS больше не проверяется автоматически перед генерацией."
        )
    else:
        text = (
            "<b>Мяу</b>\n\n"
            "Интерфейс установлен, но AI-генерация выключена. Заполните KIE_API_KEY, "
            "GRS_API_KEY, KIE_USD_TO_RUB и model id, затем включите KIE_ENABLED=true."
        )
    keyboard = _build_root_keyboard(
        workspace_id=callback_data.workspace_id,
        enabled=kie_settings.enabled,
        grs_enabled=bool(kie_settings.grs_api_key),
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


__all__ = ("handle_meow_root_entry",)
