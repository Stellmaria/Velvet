from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from velvet_bot.presentation.telegram.supervisor.contract import SupervisorCallback
from velvet_bot.presentation.telegram.supervisor.views import (
    _answer_error,
    _confirm_keyboard,
    _operation_accepted,
    _safe_edit,
)
from velvet_bot.supervisor_client import SupervisorClient, SupervisorClientError

router = Router(name=__name__)

_RESTART_TEXT = (
    "<b>Перезапустить Velvet Bot?</b>\n\n"
    "Supervisor завершит только дочерний процесс и запустит новую копию."
)


@router.message(Command("restart"))
async def handle_restart_command(message: Message) -> None:
    await message.answer(
        _RESTART_TEXT,
        reply_markup=_confirm_keyboard(
            "restart",
            "♻️ Перезапустить",
            cancel_action="bot.menu",
        ),
    )


@router.callback_query(
    SupervisorCallback.filter(F.action.in_({"restart.ask", "restart.do"}))
)
async def handle_supervisor_process_callback(
    callback: CallbackQuery,
    callback_data: SupervisorCallback,
    supervisor_client: SupervisorClient | None,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    if supervisor_client is None:
        await callback.answer("Supervisor не подключён.", show_alert=True)
        return

    try:
        if callback_data.action == "restart.ask":
            await _safe_edit(
                callback.message,
                _RESTART_TEXT,
                _confirm_keyboard(
                    "restart",
                    "♻️ Перезапустить",
                    cancel_action="bot.menu",
                ),
            )
            await callback.answer()
            return
        await _operation_accepted(callback, await supervisor_client.restart())
    except SupervisorClientError as error:
        await _answer_error(callback, error)


__all__ = ("router",)
