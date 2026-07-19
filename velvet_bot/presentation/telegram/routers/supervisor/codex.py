from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, ForceReply, Message

from velvet_bot.application.supervisor import (
    create_supervisor_task,
    load_supervisor_task,
    load_supervisor_tasks,
)
from velvet_bot.presentation.telegram.routers.supervisor.status import (
    show_supervisor_menu,
)
from velvet_bot.presentation.telegram.supervisor.contract import (
    SupervisorCallback,
    SupervisorReplyMarkerFilter,
)
from velvet_bot.presentation.telegram.supervisor.views import (
    _answer_error,
    _codex_keyboard,
    _confirm_keyboard,
    _main_keyboard,
    _operation_accepted,
    _safe_edit,
    _task_keyboard,
    _task_text,
    _tasks_text,
    _unavailable_text,
)
from velvet_bot.supervisor_client import SupervisorClient, SupervisorClientError

router = Router(name=__name__)


def _requested_by(message: Message) -> str:
    if message.from_user is None:
        return "telegram"
    return f"{message.from_user.id}:@{message.from_user.username or 'без_username'}"


async def _create_codex_task(
    message: Message,
    supervisor_client: SupervisorClient,
    prompt: str,
) -> None:
    try:
        task = await create_supervisor_task(
            supervisor_client,
            prompt=prompt,
            requested_by=_requested_by(message),
        )
    except (SupervisorClientError, ValueError) as error:
        await _answer_error(message, error)
        return
    await message.answer(_task_text(task), reply_markup=_task_keyboard(task))


async def _show_task(
    message: Message,
    supervisor_client: SupervisorClient,
    task_id: str,
) -> None:
    try:
        task = await load_supervisor_task(supervisor_client, task_id)
    except ValueError as error:
        await message.answer(str(error), reply_markup=_main_keyboard())
        return
    except SupervisorClientError as error:
        await _answer_error(message, error)
        return
    await message.answer(_task_text(task), reply_markup=_task_keyboard(task))


@router.message(Command("codex"))
async def handle_codex_command(
    message: Message,
    supervisor_client: SupervisorClient | None,
) -> None:
    if supervisor_client is None:
        await message.answer(_unavailable_text())
        return
    prompt = (message.text or "").partition(" ")[2].strip()
    if not prompt:
        await message.answer(
            "<b>Опишите задачу Codex ответом на это сообщение.</b>\n\n"
            "Укажите ожидаемое поведение, найденную ошибку и нужные проверки.\n\n"
            "<code>SUPERVISOR_INPUT:codex</code>",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="Например: исправь меню и добавь тесты",
            ),
        )
        return
    await _create_codex_task(message, supervisor_client, prompt)


@router.message(Command("codex_status"))
async def handle_codex_status_command(
    message: Message,
    supervisor_client: SupervisorClient | None,
) -> None:
    if supervisor_client is None:
        await message.answer(_unavailable_text())
        return
    task_id = (message.text or "").partition(" ")[2].strip()
    if task_id:
        await _show_task(message, supervisor_client, task_id)
        return
    try:
        result = await load_supervisor_tasks(supervisor_client)
    except SupervisorClientError as error:
        await _answer_error(message, error)
        return
    tasks = list(result.tasks)
    await message.answer(
        _tasks_text(tasks, enabled=result.enabled),
        reply_markup=_codex_keyboard(tasks),
    )


@router.message(SupervisorReplyMarkerFilter())
async def handle_supervisor_input_reply(
    message: Message,
    supervisor_input_kind: str,
    supervisor_client: SupervisorClient | None,
) -> None:
    if supervisor_client is None:
        await message.answer(_unavailable_text())
        return
    value = (message.text or message.caption or "").strip()
    if value.casefold() in {"отмена", "cancel", "/cancel"}:
        await show_supervisor_menu(message, supervisor_client)
        return
    if supervisor_input_kind == "codex":
        await _create_codex_task(message, supervisor_client, value)
        return
    if supervisor_input_kind == "task":
        await _show_task(message, supervisor_client, value)
        return
    await message.answer("Неизвестный тип формы.", reply_markup=_main_keyboard())


@router.callback_query(
    SupervisorCallback.filter(
        (F.action == "task.input") | F.action.startswith("codex.")
    )
)
async def handle_supervisor_codex_callback(
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
    task_id = callback_data.task_id
    try:
        if action == "codex.menu":
            result = await load_supervisor_tasks(supervisor_client)
            tasks = list(result.tasks)
            await _safe_edit(
                callback.message,
                _tasks_text(tasks, enabled=result.enabled),
                _codex_keyboard(tasks),
            )
            await callback.answer()
            return

        if action == "codex.input":
            await callback.message.answer(
                "<b>Опишите задачу Codex ответом на это сообщение.</b>\n\n"
                "Формулируйте задачу так, чтобы результат можно было проверить тестами.\n\n"
                "<code>SUPERVISOR_INPUT:codex</code>",
                reply_markup=ForceReply(
                    selective=True,
                    input_field_placeholder="Опишите изменение или ошибку",
                ),
            )
            await callback.answer("Ожидаю описание задачи.")
            return

        if action == "task.input":
            await callback.message.answer(
                "<b>Отправьте ID задачи Codex ответом на это сообщение.</b>\n\n"
                "<code>SUPERVISOR_INPUT:task</code>",
                reply_markup=ForceReply(
                    selective=True,
                    input_field_placeholder="Например: a1b2c3d4e5f6",
                ),
            )
            await callback.answer("Ожидаю ID задачи.")
            return

        if action in {"codex.open", "codex.status"}:
            task = await load_supervisor_task(supervisor_client, task_id)
            await _safe_edit(
                callback.message,
                _task_text(task),
                _task_keyboard(task),
            )
            await callback.answer()
            return

        confirmations = {
            "codex.apply.ask": (
                "Применить изменения Codex и перезапустить?",
                "codex.apply",
                "✅ Применить",
            ),
            "codex.reject.ask": (
                "Удалить worktree и отклонить изменения?",
                "codex.reject",
                "🚫 Отклонить",
            ),
            "codex.push.ask": (
                "Отправить применённый commit в main?",
                "codex.push",
                "⬆️ Push",
            ),
        }
        if action in confirmations:
            title, confirmed_action, label = confirmations[action]
            await _safe_edit(
                callback.message,
                f"<b>{title}</b>",
                _confirm_keyboard(
                    confirmed_action,
                    label,
                    cancel_action="codex.open",
                    task_id=task_id,
                ),
            )
            await callback.answer()
            return

        if action == "codex.apply.do":
            await _operation_accepted(
                callback,
                await supervisor_client.apply_codex_task(task_id),
            )
            return
        if action == "codex.reject.do":
            payload = await supervisor_client.reject_codex_task(task_id)
            task = payload.get("task", {})
            await _safe_edit(
                callback.message,
                _task_text(task),
                _task_keyboard(task),
            )
            await callback.answer("Задача отклонена.")
            return
        if action == "codex.push.do":
            await _operation_accepted(
                callback,
                await supervisor_client.push_codex_task(task_id),
            )
            return

        await callback.answer("Неизвестное действие.", show_alert=True)
    except (SupervisorClientError, ValueError) as error:
        await _answer_error(callback, error)


__all__ = ("router",)
