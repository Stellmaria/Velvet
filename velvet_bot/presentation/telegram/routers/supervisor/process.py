from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from velvet_bot.presentation.telegram.supervisor.contract import SupervisorCallback
from velvet_bot.presentation.telegram.supervisor.editing import edit_supervisor_message
from velvet_bot.presentation.telegram.supervisor.views import (
    _confirm_keyboard,
    _operation_accepted,
)
from velvet_bot.supervisor_client import SupervisorClient, SupervisorClientError

router = Router(name=__name__)
logger = logging.getLogger(__name__)

ProcessTerminator = Callable[[], None]


def terminate_current_process() -> None:
    """Finish the bot so its external runtime can start a fresh copy."""

    logger.warning("Process self-restart requested")
    raise SystemExit(75)


@dataclass(slots=True)
class ProcessRestartCoordinator:
    terminator: ProcessTerminator = terminate_current_process
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock | None = field(default=None, init=False, repr=False)

    def _active_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def request(self, *, delay_seconds: float = 1.5) -> bool:
        """Schedule one restart and reject duplicate taps while it is pending."""

        delay = max(0.1, min(float(delay_seconds), 30.0))
        async with self._active_lock():
            if self._task is not None and not self._task.done():
                return False
            self._task = asyncio.create_task(
                self._terminate_after_delay(delay),
                name="velvet-process-self-restart",
            )
            return True

    async def _terminate_after_delay(self, delay_seconds: float) -> None:
        await asyncio.sleep(delay_seconds)
        self.terminator()

    @property
    def pending(self) -> bool:
        return self._task is not None and not self._task.done()


process_restart_coordinator = ProcessRestartCoordinator()

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
        logger.warning("Supervisor restart failed; using process fallback: %s", error)
        await _accept_direct_process_restart(callback)


__all__ = (
    "ProcessRestartCoordinator",
    "process_restart_coordinator",
    "router",
    "terminate_current_process",
)
