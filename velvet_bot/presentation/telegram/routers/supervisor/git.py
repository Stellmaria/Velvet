from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from velvet_bot.application.supervisor import load_supervisor_status
from velvet_bot.presentation.telegram.supervisor.contract import SupervisorCallback
from velvet_bot.presentation.telegram.supervisor.views import (
    _answer_error,
    _confirm_keyboard,
    _git_keyboard,
    _git_text,
    _operation_accepted,
    _safe_edit,
)
from velvet_bot.supervisor_client import SupervisorClient, SupervisorClientError

router = Router(name=__name__)

_UPDATE_TEXT = (
    "<b>Выполнить безопасное обновление?</b>\n\n"
    "Будут выполнены fetch, fast-forward, тесты и перезапуск. "
    "При ошибке Supervisor вернёт предыдущий commit."
)
_ROLLBACK_TEXT = (
    "<b>Откатить последнее развёртывание?</b>\n\n"
    "Будет восстановлен предыдущий сохранённый commit и перезапущен бот."
)


@router.message(Command("update"))
async def handle_update_command(message: Message) -> None:
    await message.answer(
        _UPDATE_TEXT,
        reply_markup=_confirm_keyboard(
            "update",
            "⬇️ Обновить",
            cancel_action="git.menu",
        ),
    )


@router.message(Command("rollback"))
async def handle_rollback_command(message: Message) -> None:
    await message.answer(
        _ROLLBACK_TEXT,
        reply_markup=_confirm_keyboard(
            "rollback",
            "↩️ Откатить",
            cancel_action="git.menu",
        ),
    )


@router.callback_query(
    SupervisorCallback.filter(
        F.action.in_(
            {
                "git.menu",
                "update.ask",
                "update.do",
                "rollback.ask",
                "rollback.do",
            }
        )
    )
)
async def handle_supervisor_git_callback(
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
        if action == "git.menu":
            payload = await load_supervisor_status(supervisor_client)
            await _safe_edit(callback.message, _git_text(payload), _git_keyboard())
            await callback.answer()
            return
        if action == "update.ask":
            await _safe_edit(
                callback.message,
                _UPDATE_TEXT,
                _confirm_keyboard(
                    "update",
                    "⬇️ Обновить",
                    cancel_action="git.menu",
                ),
            )
            await callback.answer()
            return
        if action == "rollback.ask":
            await _safe_edit(
                callback.message,
                _ROLLBACK_TEXT,
                _confirm_keyboard(
                    "rollback",
                    "↩️ Откатить",
                    cancel_action="git.menu",
                ),
            )
            await callback.answer()
            return
        if action == "update.do":
            await _operation_accepted(callback, await supervisor_client.update())
            return
        await _operation_accepted(callback, await supervisor_client.rollback())
    except SupervisorClientError as error:
        await _answer_error(callback, error)


__all__ = ("router",)
