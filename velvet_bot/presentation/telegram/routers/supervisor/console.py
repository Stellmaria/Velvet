from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import BaseFilter, Command
from aiogram.types import BufferedInputFile, CallbackQuery, ForceReply, Message

from velvet_bot.presentation.telegram.supervisor.console_results import (
    console_operation_dm_text,
    console_operation_finished,
    console_operation_keyboard,
    console_operation_missing_text,
    console_operation_output_attachment,
    console_operation_text,
    console_operation_watch_timeout_text,
)
from velvet_bot.presentation.telegram.supervisor.contract import SupervisorCallback
from velvet_bot.presentation.telegram.supervisor.remote_views import (
    console_keyboard,
    console_preview_keyboard,
    console_preview_text,
    console_text,
    operation_history_text,
)
from velvet_bot.presentation.telegram.supervisor.views import (
    _answer_error,
    _main_keyboard,
    _safe_edit,
    _unavailable_text,
)
from velvet_bot.supervisor_client import SupervisorClient, SupervisorClientError

router = Router(name=__name__)
logger = logging.getLogger(__name__)
_CONSOLE_MARKER_RE = re.compile(r"SUPERVISOR_INPUT:console")
_CONSOLE_WATCH_INTERVAL_SECONDS = 1.0
_CONSOLE_WATCH_TIMEOUT_SECONDS = 60 * 60
_CONSOLE_WATCHERS: set[asyncio.Task[None]] = set()


class ConsoleReplyMarkerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        reply = message.reply_to_message
        if reply is None:
            return False
        source = reply.text or reply.caption or ""
        return _CONSOLE_MARKER_RE.search(source) is not None


def _requested_by(message: Message) -> str:
    if message.from_user is None:
        return "telegram"
    return f"{message.from_user.id}:@{message.from_user.username or 'без_username'}"


async def _catalog(client: SupervisorClient) -> list[dict[str, object]]:
    payload = await client.console_commands()
    raw = payload.get("commands", [])
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


async def _operation(
    client: SupervisorClient,
    operation_id: str,
) -> dict[str, Any] | None:
    payload = await client.operations(limit=100)
    raw = payload.get("operations", [])
    if not isinstance(raw, list):
        return None
    for item in raw:
        if isinstance(item, dict) and str(item.get("id", "")) == operation_id:
            return item
    return None


async def _render_operation(
    message: Message,
    operation: dict[str, Any],
) -> None:
    operation_id = str(operation.get("id", ""))
    finished = console_operation_finished(operation)
    await _safe_edit(
        message,
        console_operation_text(operation),
        console_operation_keyboard(operation_id, finished=finished),
    )


async def _notify_console_result(
    bot: Bot,
    recipient_id: int,
    operation: dict[str, Any],
) -> None:
    if not console_operation_finished(operation):
        return

    operation_id = str(operation.get("id", ""))
    try:
        await bot.send_message(
            chat_id=recipient_id,
            text=console_operation_dm_text(operation),
            reply_markup=console_operation_keyboard(operation_id, finished=True),
        )
        attachment = console_operation_output_attachment(operation)
        if attachment is not None:
            filename, payload = attachment
            await bot.send_document(
                chat_id=recipient_id,
                document=BufferedInputFile(payload, filename=filename),
                caption=(
                    "📎 Полный вывод команды Supervisor\n"
                    f"Операция: <code>{operation_id}</code>"
                ),
            )
    except TelegramAPIError as error:
        logger.warning(
            "Could not deliver Supervisor console result in DM operation=%s recipient=%s: %s",
            operation_id,
            recipient_id,
            error,
        )


async def _watch_console_operation(
    message: Message,
    client: SupervisorClient,
    operation_id: str,
    *,
    bot: Bot,
    recipient_id: int,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _CONSOLE_WATCH_TIMEOUT_SECONDS
    last_rendered = ""

    try:
        while loop.time() < deadline:
            try:
                operation = await _operation(client, operation_id)
            except SupervisorClientError:
                await asyncio.sleep(2.0)
                continue

            if operation is not None:
                rendered = console_operation_text(operation)
                if rendered != last_rendered:
                    await _safe_edit(
                        message,
                        rendered,
                        console_operation_keyboard(
                            operation_id,
                            finished=console_operation_finished(operation),
                        ),
                    )
                    last_rendered = rendered
                if console_operation_finished(operation):
                    await _notify_console_result(bot, recipient_id, operation)
                    return

            await asyncio.sleep(_CONSOLE_WATCH_INTERVAL_SECONDS)

        await _safe_edit(
            message,
            console_operation_watch_timeout_text(operation_id),
            console_operation_keyboard(operation_id, finished=False),
        )
    except asyncio.CancelledError:
        raise
    except Exception:  # p2-approved-boundary: isolate-supervisor-console-watcher
        # The command continues inside Supervisor even if Telegram editing fails.
        logger.exception(
            "Supervisor console watcher failed operation=%s recipient=%s",
            operation_id,
            recipient_id,
        )


def _start_console_watcher(
    message: Message,
    client: SupervisorClient,
    operation_id: str,
    *,
    bot: Bot,
    recipient_id: int,
) -> None:
    task = asyncio.create_task(
        _watch_console_operation(
            message,
            client,
            operation_id,
            bot=bot,
            recipient_id=recipient_id,
        ),
        name=f"supervisor-console-watch:{operation_id}",
    )
    _CONSOLE_WATCHERS.add(task)
    task.add_done_callback(_CONSOLE_WATCHERS.discard)


async def _preview(
    message: Message,
    client: SupervisorClient,
    *,
    command: str = "",
    command_key: str = "",
) -> None:
    payload = await client.preview_console_command(
        command=command,
        command_key=command_key,
        requested_by=_requested_by(message),
    )
    request = payload.get("request", {})
    if not isinstance(request, dict):
        raise SupervisorClientError("Supervisor вернул некорректный preview команды.")
    await message.answer(
        console_preview_text(request),
        reply_markup=console_preview_keyboard(str(request.get("id", ""))),
    )


@router.message(Command("console", "supervisor_console"))
async def handle_console_command(
    message: Message,
    supervisor_client: SupervisorClient | None,
) -> None:
    if supervisor_client is None:
        await message.answer(_unavailable_text())
        return
    value = (message.text or "").partition(" ")[2].strip()
    try:
        if value:
            await _preview(message, supervisor_client, command=value)
            return
        commands = await _catalog(supervisor_client)
        await message.answer(console_text(commands), reply_markup=console_keyboard(commands))
    except SupervisorClientError as error:
        await _answer_error(message, error)


@router.message(ConsoleReplyMarkerFilter())
async def handle_console_reply(
    message: Message,
    supervisor_client: SupervisorClient | None,
) -> None:
    if supervisor_client is None:
        await message.answer(_unavailable_text())
        return
    value = (message.text or message.caption or "").strip()
    if value.casefold() in {"отмена", "cancel", "/cancel"}:
        commands = await _catalog(supervisor_client)
        await message.answer(console_text(commands), reply_markup=console_keyboard(commands))
        return
    try:
        await _preview(message, supervisor_client, command=value)
    except SupervisorClientError as error:
        await _answer_error(message, error)


@router.callback_query(SupervisorCallback.filter(F.action.startswith("console.")))
async def handle_console_callback(
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
        if action == "console.menu":
            commands = await _catalog(supervisor_client)
            await _safe_edit(callback.message, console_text(commands), console_keyboard(commands))
            await callback.answer()
            return
        if action == "console.input":
            await callback.message.answer(
                "<b>Введите разрешённую команду ответом на это сообщение.</b>\n\n"
                "Команда должна полностью совпасть с безопасным реестром. "
                "Пайпы, перенаправления и shell-конструкции не принимаются.\n\n"
                "<code>SUPERVISOR_INPUT:console</code>",
                reply_markup=ForceReply(
                    selective=True,
                    input_field_placeholder="Например: git status --short",
                ),
            )
            await callback.answer("Ожидаю команду.")
            return
        if action == "console.quick":
            payload = await supervisor_client.preview_console_command(
                command_key=callback_data.task_id,
                requested_by=(
                    f"{callback.from_user.id}:@"
                    f"{callback.from_user.username or 'без_username'}"
                ),
            )
            request = payload.get("request", {})
            if not isinstance(request, dict):
                raise SupervisorClientError("Некорректный preview команды.")
            await _safe_edit(
                callback.message,
                console_preview_text(request),
                console_preview_keyboard(str(request.get("id", ""))),
            )
            await callback.answer()
            return
        if action == "console.run":
            payload = await supervisor_client.run_console_command(callback_data.task_id)
            operation = payload.get("operation", {})
            if not isinstance(operation, dict):
                raise SupervisorClientError("Supervisor вернул некорректную операцию.")
            operation_id = str(operation.get("id", ""))
            if not operation_id:
                raise SupervisorClientError("Supervisor не вернул ID операции.")
            await _render_operation(callback.message, operation)
            await callback.answer("Команда запущена. Итог придёт в ЛС.")
            if console_operation_finished(operation):
                await _notify_console_result(callback.bot, callback.from_user.id, operation)
            else:
                _start_console_watcher(
                    callback.message,
                    supervisor_client,
                    operation_id,
                    bot=callback.bot,
                    recipient_id=callback.from_user.id,
                )
            return
        if action == "console.operation":
            operation_id = callback_data.task_id
            operation = await _operation(supervisor_client, operation_id)
            if operation is None:
                await _safe_edit(
                    callback.message,
                    console_operation_missing_text(operation_id),
                    console_operation_keyboard(operation_id, finished=False),
                )
                await callback.answer("Операция пока не найдена.")
                return
            await _render_operation(callback.message, operation)
            await callback.answer("Статус обновлён.")
            return
        if action == "console.history":
            payload = await supervisor_client.operations(limit=20)
            raw = payload.get("operations", [])
            operations = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
            await _safe_edit(
                callback.message,
                operation_history_text(operations),
                _main_keyboard(),
            )
            await callback.answer()
            return
        await callback.answer("Неизвестное действие консоли.", show_alert=True)
    except SupervisorClientError as error:
        await _answer_error(callback, error)


__all__ = ("router",)
