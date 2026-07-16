from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.handlers.owner_actions import OwnerActionCallback
from velvet_bot.handlers.references import (
    handle_reference_upload_cancel,
    handle_reference_upload_done,
)
from velvet_bot.reference_uploads import ReferenceUploadSessions

router = Router(name=__name__)


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ Референсы",
                    callback_data=OwnerActionCallback(action="references").pack(),
                ),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="own:menu"),
            ]
        ]
    )


def _user_message(callback: CallbackQuery) -> Message | None:
    if not isinstance(callback.message, Message):
        return None
    return callback.message.model_copy(
        update={"from_user": callback.from_user},
        deep=False,
    )


@router.callback_query(
    OwnerActionCallback.filter(F.action.in_({"direct.refdone", "direct.refcancel"}))
)
async def handle_reference_session_callback(
    callback: CallbackQuery,
    callback_data: OwnerActionCallback,
    reference_uploads: ReferenceUploadSessions,
) -> None:
    message = _user_message(callback)
    if message is None:
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    if callback_data.action == "direct.refdone":
        await handle_reference_upload_done(message, reference_uploads)
    else:
        await handle_reference_upload_cancel(message, reference_uploads)
    await message.answer("Вернуться к управлению:", reply_markup=_back_keyboard())
    await callback.answer()


__all__ = ("router",)
