from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from velvet_bot.presentation.telegram.supervisor.contract import SupervisorCallback
from velvet_bot.presentation.telegram.supervisor.views import (
    _answer_error,
    _logs_keyboard,
    _logs_text,
    _safe_edit,
    _unavailable_text,
)
from velvet_bot.supervisor_client import SupervisorClient, SupervisorClientError

router = Router(name=__name__)
logger = logging.getLogger(__name__)


async def _load_log_content(
    supervisor_client: SupervisorClient,
    *,
    lines: int,
) -> str:
    payload = await supervisor_client.logs(lines=lines)
    return "\n".join(str(value) for value in payload.get("lines", []))


async def _acknowledge_callback(callback: CallbackQuery, text: str | None = None) -> None:
    """Answer before slow Supervisor I/O so Telegram does not expire the query."""
    try:
        await callback.answer(text)
    except TelegramBadRequest as error:
        message = str(error).casefold()
        if "query is too old" not in message and "query id is invalid" not in message:
            raise
        logger.info("Supervisor logs callback expired before acknowledgement: %s", error)


@router.message(Command("logs"))
async def handle_supervisor_logs(
    message: Message,
    supervisor_client: SupervisorClient | None,
) -> None:
    if supervisor_client is None:
        await message.answer(_unavailable_text())
        return
    try:
        content = await _load_log_content(supervisor_client, lines=150)
    except SupervisorClientError as error:
        await _answer_error(message, error)
        return
    await message.answer(_logs_text(150, content), reply_markup=_logs_keyboard(150))


@router.callback_query(SupervisorCallback.filter(F.action.startswith("logs.")))
async def handle_supervisor_logs_callback(
    callback: CallbackQuery,
    callback_data: SupervisorCallback,
    supervisor_client: SupervisorClient | None,
) -> None:
    if not isinstance(callback.message, Message):
        await _acknowledge_callback(callback, "Меню больше недоступно.")
        return
    if supervisor_client is None:
        await _acknowledge_callback(callback, "Supervisor не подключён.")
        return

    action = callback_data.action
    await _acknowledge_callback(
        callback,
        "Готовлю файл журнала…" if action == "logs.file" else None,
    )

    try:
        if action == "logs.file":
            content = await _load_log_content(supervisor_client, lines=2000)
            await callback.message.answer_document(
                BufferedInputFile(
                    content.encode("utf-8"),
                    filename="velvet.log.txt",
                ),
                caption="Последние 2000 строк журнала Velvet Bot.",
            )
            return

        raw_lines = action.partition(".")[2]
        lines = int(raw_lines) if raw_lines.isdigit() else 150
        content = await _load_log_content(supervisor_client, lines=lines)
        await _safe_edit(
            callback.message,
            _logs_text(lines, content),
            _logs_keyboard(lines),
        )
    except SupervisorClientError as error:
        # The callback has already been acknowledged. Report the later I/O error as
        # a normal message instead of attempting to answer the same query twice.
        await _answer_error(callback.message, error)


__all__ = ("router",)
