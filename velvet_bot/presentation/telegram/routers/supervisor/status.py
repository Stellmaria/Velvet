from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from velvet_bot.application.supervisor import load_supervisor_status
from velvet_bot.presentation.telegram.supervisor.contract import SupervisorCallback
from velvet_bot.presentation.telegram.supervisor.views import (
    _answer_error,
    _bot_keyboard,
    _bot_text,
    _main_keyboard,
    _safe_edit,
    _status_text,
    _unavailable_text,
)
from velvet_bot.supervisor_client import SupervisorClient, SupervisorClientError

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_STALE_CALLBACK_MARKERS = (
    "query is too old",
    "response timeout expired",
    "query id is invalid",
)


async def _acknowledge_callback(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> bool:
    """Answer before Supervisor I/O and tolerate an already expired query."""

    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as error:
        normalized = str(error).casefold()
        if any(marker in normalized for marker in _STALE_CALLBACK_MARKERS):
            logger.info("Supervisor status callback expired before acknowledgement: %s", error)
            return False
        raise
    return True


async def show_supervisor_menu(
    message: Message,
    supervisor_client: SupervisorClient | None,
    *,
    edit: bool = False,
) -> None:
    if supervisor_client is None:
        if edit:
            await _safe_edit(message, _unavailable_text(), _main_keyboard())
        else:
            await message.answer(_unavailable_text())
        return
    payload = await load_supervisor_status(supervisor_client)
    if edit:
        await _safe_edit(message, _status_text(payload), _main_keyboard())
    else:
        await message.answer(_status_text(payload), reply_markup=_main_keyboard())


@router.message(Command("supervisor", "status"))
async def handle_supervisor_status(
    message: Message,
    supervisor_client: SupervisorClient | None,
) -> None:
    try:
        await show_supervisor_menu(message, supervisor_client)
    except SupervisorClientError as error:
        await _answer_error(message, error)


@router.callback_query(
    SupervisorCallback.filter(F.action.in_({"close", "status", "bot.menu"}))
)
async def handle_supervisor_status_callback(
    callback: CallbackQuery,
    callback_data: SupervisorCallback,
    supervisor_client: SupervisorClient | None,
) -> None:
    if not isinstance(callback.message, Message):
        await _acknowledge_callback(
            callback,
            "Меню больше недоступно.",
            show_alert=True,
        )
        return
    if supervisor_client is None:
        await _acknowledge_callback(
            callback,
            "Supervisor не подключён.",
            show_alert=True,
        )
        return

    await _acknowledge_callback(callback)

    try:
        if callback_data.action == "close":
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                await callback.message.edit_reply_markup(reply_markup=None)
            return

        payload = await load_supervisor_status(supervisor_client)
        if callback_data.action == "bot.menu":
            await _safe_edit(callback.message, _bot_text(payload), _bot_keyboard())
        else:
            await _safe_edit(callback.message, _status_text(payload), _main_keyboard())
    except SupervisorClientError as error:
        await _answer_error(callback.message, error)


__all__ = ("router", "show_supervisor_menu")
