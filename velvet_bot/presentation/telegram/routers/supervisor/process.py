from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from velvet_bot.presentation.telegram.supervisor.contract import SupervisorCallback
from velvet_bot.presentation.telegram.supervisor.editing import edit_supervisor_message
from velvet_bot.presentation.telegram.supervisor.views import (
    _answer_error,
    _confirm_keyboard,
    _operation_accepted,
)
from velvet_bot.process_restart import process_restart_coordinator
from velvet_bot.supervisor_client import SupervisorClient, SupervisorClientError

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_RESTART_TEXT = (
    "<b>Перезапустить Velvet Bot?</b>\n\n"
    "Текущий процесс завершится, после чего Docker Compose или локальный "
    "Supervisor автоматически запустит новую копию. PostgreSQL и сохранённые "
    "данные не перезапускаются."
)
_RESTART_ACCEPTED_TEXT = (
    "<b>♻️ Перезапуск принят</b>\n\n"
    "Velvet Bot завершает текущий процесс. Новая копия будет поднята внешним "
    "контуром автоперезапуска. Обычно бот возвращается в течение нескольких секунд."
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


async def _accept_direct_process_restart(callback: CallbackQuery) -> None:
    scheduled = await process_restart_coordinator.request()
    if not scheduled:
        await callback.answer("Перезапуск уже запущен.", show_alert=True)
        return
    if isinstance(callback.message, Message):
        await edit_supervisor_message(
            callback.message,
            _RESTART_ACCEPTED_TEXT,
            None,
        )
    await callback.answer("Перезапуск принят.")


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

    if callback_data.action == "restart.ask":
        await edit_supervisor_message(
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

    if supervisor_client is None:
        await _accept_direct_process_restart(callback)
        return

    try:
        await _operation_accepted(callback, await supervisor_client.restart())
    except SupervisorClientError as error:
        # Restart is also a recovery action. If the optional desktop Supervisor
        # is stale or unavailable, fall back to the container-safe process exit
        # instead of leaving the owner with a dead control button.
        logger.warning("Supervisor restart failed; using process fallback: %s", error)
        try:
            await _accept_direct_process_restart(callback)
        except Exception as fallback_error:
            await _answer_error(callback, fallback_error)


__all__ = ("router",)
