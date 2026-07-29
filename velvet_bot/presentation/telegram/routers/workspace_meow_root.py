from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from velvet_bot.core.access import AccessPolicy
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.presentation.telegram.routers.workspace_meow import (
    build_meow_root_keyboard,
)
from velvet_bot.workspace_ui import WorkspaceCallback


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
        text = (
            "<b>Мяу</b>\n\n"
            "<b>Создать</b> — изображения через Nano Banana Pro и Seedream 5 Pro. "
            "Можно использовать текст и референсы из базы или Telegram.\n\n"
            "<b>Оживить</b> — одно фото и описание движения превращаются в видео "
            "через Grok Imagine v1. Перед платным запуском бот покажет параметры "
            "и расчётную себестоимость."
        )
    else:
        text = (
            "<b>Мяу</b>\n\n"
            "Интерфейс установлен, но Kie.ai выключен. Заполните KIE_API_KEY, "
            "KIE_USD_TO_RUB и model id, затем включите KIE_ENABLED=true."
        )
    keyboard = build_meow_root_keyboard(
        workspace_id=callback_data.workspace_id,
        enabled=kie_settings.enabled,
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
