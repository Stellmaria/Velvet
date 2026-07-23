from __future__ import annotations

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from velvet_bot.owner_menu import (
    OwnerMenuCallback,
    build_owner_back_keyboard,
    build_owner_main_keyboard,
    owner_help_text,
    owner_menu_text,
)
from velvet_bot.presentation.telegram.archive_watermark_storage import (
    register_archive_watermark_storage_handler,
)
from velvet_bot.presentation.telegram.storage_center import register_storage_center
from velvet_bot.presentation.telegram.storage_scheduler import register_storage_scheduler
from velvet_bot.presentation.telegram.routers.core_operations_controllers.watermark import (
    router as watermark_router,
)
from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_product_experience import (
    install_workspace_product_experience,
    router as workspace_product_experience_router,
)

install_workspace_product_experience()
router = Router(name=__name__)


async def show_owner_menu(message: Message, *, edit: bool = False) -> None:
    first_name = message.chat.first_name or ""
    text = owner_menu_text(first_name)
    keyboard = build_owner_main_keyboard()
    if edit:
        try:
            await message.edit_text(text, reply_markup=keyboard)
            return
        except TelegramBadRequest as error:
            if "message is not modified" in str(error).casefold():
                return
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("menu", "admin"))
async def handle_owner_menu_command(message: Message) -> None:
    await show_owner_menu(message)


@router.callback_query(OwnerMenuCallback.filter())
async def handle_owner_menu_callback(
    callback: CallbackQuery,
    callback_data: OwnerMenuCallback,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return

    if callback_data.action == "menu":
        await show_owner_menu(callback.message, edit=True)
        await callback.answer()
        return

    if callback_data.action == "help":
        try:
            await callback.message.edit_text(
                owner_help_text(),
                reply_markup=build_owner_back_keyboard(),
            )
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                raise
        await callback.answer()
        return

    if callback_data.action == "close":
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        return

    await callback.answer("Неизвестный раздел.", show_alert=True)


register_storage_center(router)
register_storage_scheduler(router)
register_archive_watermark_storage_handler(router)
router.include_router(workspace_product_experience_router)
router.include_router(watermark_router)

__all__ = ("router", "show_owner_menu")
