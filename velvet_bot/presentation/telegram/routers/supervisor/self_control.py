from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from velvet_bot.application.supervisor import load_supervisor_status
from velvet_bot.presentation.telegram.supervisor.contract import SupervisorCallback
from velvet_bot.presentation.telegram.supervisor.remote_views import (
    self_control_keyboard,
    self_control_text,
)
from velvet_bot.presentation.telegram.supervisor.views import (
    _answer_error,
    _confirm_keyboard,
    _operation_accepted,
    _safe_edit,
    _unavailable_text,
)
from velvet_bot.supervisor_client import SupervisorClient, SupervisorClientError

router = Router(name=__name__)


async def _show(message: Message, client: SupervisorClient, *, edit: bool) -> None:
    payload = await load_supervisor_status(client)
    if edit:
        await _safe_edit(message, self_control_text(payload), self_control_keyboard())
    else:
        await message.answer(self_control_text(payload), reply_markup=self_control_keyboard())


@router.message(Command("supervisor_self"))
async def handle_self_command(
    message: Message,
    supervisor_client: SupervisorClient | None,
) -> None:
    if supervisor_client is None:
        await message.answer(_unavailable_text())
        return
    try:
        await _show(message, supervisor_client, edit=False)
    except SupervisorClientError as error:
        await _answer_error(message, error)


@router.callback_query(SupervisorCallback.filter(F.action.startswith("self.")))
async def handle_self_callback(
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
    action = callback_data.action
    try:
        if action == "self.menu":
            await _show(callback.message, supervisor_client, edit=True)
            await callback.answer()
            return
        if action == "self.restart.ask":
            await _safe_edit(
                callback.message,
                "<b>Перезапустить сам Velvet Supervisor?</b>\n\n"
                "Операция будет передана независимой задаче Windows. "
                "Текущий бот и Supervisor временно остановятся, затем запустятся заново.",
                _confirm_keyboard(
                    "self.restart",
                    "♻️ Перезапустить Supervisor",
                    cancel_action="self.menu",
                ),
            )
            await callback.answer()
            return
        if action == "self.update.ask":
            await _safe_edit(
                callback.message,
                "<b>Обновить main и перезапустить сам Supervisor?</b>\n\n"
                "Helper проверит чистоту Git, выполнит только fast-forward, "
                "запустит тесты и вернёт прежний commit при ошибке.",
                _confirm_keyboard(
                    "self.update",
                    "⬇️ Обновить и перезапустить",
                    cancel_action="self.menu",
                ),
            )
            await callback.answer()
            return
        if action == "self.restart.do":
            await _operation_accepted(callback, await supervisor_client.restart_supervisor())
            return
        if action == "self.update.do":
            await _operation_accepted(callback, await supervisor_client.update_supervisor())
            return
        await callback.answer("Неизвестное действие Supervisor.", show_alert=True)
    except SupervisorClientError as error:
        await _answer_error(callback, error)


__all__ = ("router",)
