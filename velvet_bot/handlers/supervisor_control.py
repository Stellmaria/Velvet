from __future__ import annotations

from html import escape
from typing import Any

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.supervisor_client import SupervisorClient, SupervisorClientError

router = Router(name=__name__)


class SupervisorCallback(CallbackData, prefix="sup"):
    action: str
    task_id: str = ""


def _unavailable_text() -> str:
    return (
        "<b>🛡 Velvet Supervisor не подключён</b>\n\n"
        "Включите SUPERVISOR_ENABLED=true в .env, задайте общий "
        "SUPERVISOR_TOKEN и запускайте проект через:\n"
        "<code>python -m velvet_supervisor</code>"
    )


def _status_text(payload: dict[str, Any]) -> str:
    status = payload.get("status", {})
    supervisor = status.get("supervisor", {})
    bot = status.get("bot", {})
    git = status.get("git", {})
    operation = status.get("operation")
    codex = status.get("codex", {})
    running = bool(bot.get("running"))
    lines = [
        "<b>🛡 Velvet Supervisor</b>",
        "",
        f"Supervisor PID: <code>{escape(str(supervisor.get('pid', '—')))}</code>",
        (
            f"Бот: {'✅ работает' if running else '❌ остановлен'}"
            f" · PID <code>{escape(str(bot.get('pid') or '—'))}</code>"
        ),
        (
            "Автоперезапуск: "
            f"<b>{'включён' if bot.get('auto_restart') else 'выключен'}</b>"
        ),
        (
            "Crash-loop: "
            f"<b>{'заблокирован' if bot.get('crash_loop_open') else 'норма'}</b>"
            f" · {bot.get('restart_count_in_window', 0)}/"
            f"{bot.get('restart_limit', 0)}"
        ),
        "",
        f"Git-ветка: <code>{escape(str(git.get('branch', '—')))}</code>",
        f"Commit: <code>{escape(str(git.get('head_sha', '—'))[:16])}</code>",
        f"Рабочее дерево: <b>{'изменено' if git.get('dirty') else 'чистое'}</b>",
        (
            "Codex: "
            f"<b>{'включён' if codex.get('enabled') else 'выключен'}</b>"
        ),
    ]
    if git.get("error"):
        lines.append(f"Git ошибка: <code>{escape(str(git['error'])[:1000])}</code>")
    if operation:
        lines.extend(
            [
                "",
                "<b>Последняя операция</b>",
                (
                    f"<code>{escape(str(operation.get('kind', '—')))}</code> · "
                    f"<b>{escape(str(operation.get('status', '—')))}</b>"
                ),
            ]
        )
        if operation.get("error"):
            lines.append(
                f"<code>{escape(str(operation['error'])[-1500:])}</code>"
            )
    return "\n".join(lines)


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Обновить статус",
                    callback_data=SupervisorCallback(action="status").pack(),
                ),
                InlineKeyboardButton(
                    text="📄 Логи",
                    callback_data=SupervisorCallback(action="logs").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="♻️ Перезапустить",
                    callback_data=SupervisorCallback(action="restart.ask").pack(),
                ),
                InlineKeyboardButton(
                    text="⬇️ Git update",
                    callback_data=SupervisorCallback(action="update.ask").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Откатить",
                    callback_data=SupervisorCallback(action="rollback.ask").pack(),
                )
            ],
        ]
    )


def _confirm_keyboard(action: str, label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=SupervisorCallback(action=f"{action}.do").pack(),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=SupervisorCallback(action="status").pack(),
                ),
            ]
        ]
    )


def _task_keyboard(task: dict[str, Any]) -> InlineKeyboardMarkup:
    task_id = str(task.get("id", ""))
    status = str(task.get("status", ""))
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=SupervisorCallback(
                    action="codex.status",
                    task_id=task_id,
                ).pack(),
            )
        ]
    ]
    if status == "ready":
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Применить и перезапустить",
                    callback_data=SupervisorCallback(
                        action="codex.apply.ask",
                        task_id=task_id,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="🚫 Отклонить",
                    callback_data=SupervisorCallback(
                        action="codex.reject.ask",
                        task_id=task_id,
                    ).pack(),
                ),
            ]
        )
    if status == "applied" and not task.get("pushed_at"):
        rows.append(
            [
                InlineKeyboardButton(
                    text="⬆️ Push в main",
                    callback_data=SupervisorCallback(
                        action="codex.push.ask",
                        task_id=task_id,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🛡 Supervisor",
                callback_data=SupervisorCallback(action="status").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _task_text(task: dict[str, Any]) -> str:
    changed = task.get("changed_files") or []
    error = task.get("error")
    diff = str(task.get("diff", ""))
    lines = [
        "<b>🤖 Задача Codex</b>",
        "",
        f"ID: <code>{escape(str(task.get('id', '—')))}</code>",
        f"Статус: <b>{escape(str(task.get('status', '—')))}</b>",
        f"Запросил: <code>{escape(str(task.get('requested_by', '—')))}</code>",
        f"Base: <code>{escape(str(task.get('base_sha') or '—')[:16])}</code>",
        f"Commit: <code>{escape(str(task.get('commit_sha') or '—')[:16])}</code>",
        f"Изменено файлов: <b>{len(changed)}</b>",
    ]
    if changed:
        lines.append(
            "<code>" + escape("\n".join(str(value) for value in changed[:30])) + "</code>"
        )
    if error:
        lines.extend(["", "<b>Ошибка</b>", f"<code>{escape(str(error)[-2500:])}</code>"])
    elif diff:
        lines.extend(
            [
                "",
                "<b>Фрагмент diff</b>",
                f"<pre>{escape(diff[:2500])}</pre>",
            ]
        )
    return "\n".join(lines)


async def _answer_error(target: Message | CallbackQuery, error: Exception) -> None:
    text = f"<b>Операция не выполнена</b>\n\n<code>{escape(str(error))}</code>"
    if isinstance(target, CallbackQuery):
        if isinstance(target.message, Message):
            await target.message.answer(text)
        await target.answer("Ошибка Supervisor", show_alert=True)
    else:
        await target.answer(text)


@router.message(Command("supervisor", "status"))
async def handle_supervisor_status(
    message: Message,
    supervisor_client: SupervisorClient | None,
) -> None:
    if supervisor_client is None:
        await message.answer(_unavailable_text())
        return
    try:
        payload = await supervisor_client.status()
    except SupervisorClientError as error:
        await _answer_error(message, error)
        return
    await message.answer(_status_text(payload), reply_markup=_main_keyboard())


@router.message(Command("logs"))
async def handle_supervisor_logs(
    message: Message,
    supervisor_client: SupervisorClient | None,
) -> None:
    if supervisor_client is None:
        await message.answer(_unavailable_text())
        return
    raw = (message.text or "").partition(" ")[2].strip()
    try:
        lines = int(raw) if raw else 150
    except ValueError:
        lines = 150
    try:
        payload = await supervisor_client.logs(lines=lines)
    except SupervisorClientError as error:
        await _answer_error(message, error)
        return
    content = "\n".join(str(value) for value in payload.get("lines", []))
    if not content:
        await message.answer("<b>Логи пока пусты.</b>")
        return
    if len(content) <= 3500:
        await message.answer(f"<pre>{escape(content)}</pre>")
        return
    await message.answer_document(
        BufferedInputFile(content.encode("utf-8"), filename="velvet.log.txt"),
        caption=f"Последние {lines} строк журнала Velvet Bot.",
    )


@router.message(Command("restart"))
async def handle_restart_command(message: Message) -> None:
    await message.answer(
        "<b>Перезапустить Velvet Bot?</b>\n\n"
        "Supervisor сначала примет запрос, затем завершит дочерний процесс и запустит его заново.",
        reply_markup=_confirm_keyboard("restart", "♻️ Перезапустить"),
    )


@router.message(Command("update"))
async def handle_update_command(message: Message) -> None:
    await message.answer(
        "<b>Выполнить безопасное обновление?</b>\n\n"
        "Будут выполнены fetch, fast-forward, тесты и перезапуск. "
        "При ошибке тестов или запуска Supervisor вернёт предыдущий commit.",
        reply_markup=_confirm_keyboard("update", "⬇️ Обновить"),
    )


@router.message(Command("rollback"))
async def handle_rollback_command(message: Message) -> None:
    await message.answer(
        "<b>Откатить последнее развёртывание?</b>\n\n"
        "Будет восстановлен предыдущий сохранённый commit и перезапущен бот.",
        reply_markup=_confirm_keyboard("rollback", "↩️ Откатить"),
    )


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
            "<b>Формат</b>\n"
            "<code>/codex Исправь ошибку и добавь тесты</code>"
        )
        return
    requested_by = (
        f"{message.from_user.id}:@{message.from_user.username or 'без_username'}"
        if message.from_user
        else "telegram"
    )
    try:
        payload = await supervisor_client.create_codex_task(
            prompt=prompt,
            requested_by=requested_by,
        )
    except SupervisorClientError as error:
        await _answer_error(message, error)
        return
    task = payload.get("task", {})
    await message.answer(_task_text(task), reply_markup=_task_keyboard(task))


@router.message(Command("codex_status"))
async def handle_codex_status_command(
    message: Message,
    supervisor_client: SupervisorClient | None,
) -> None:
    if supervisor_client is None:
        await message.answer(_unavailable_text())
        return
    task_id = (message.text or "").partition(" ")[2].strip()
    if not task_id:
        await message.answer("<code>/codex_status TASK_ID</code>")
        return
    try:
        payload = await supervisor_client.codex_task(task_id)
    except SupervisorClientError as error:
        await _answer_error(message, error)
        return
    task = payload.get("task", {})
    await message.answer(_task_text(task), reply_markup=_task_keyboard(task))


@router.callback_query(SupervisorCallback.filter())
async def handle_supervisor_callback(
    callback: CallbackQuery,
    callback_data: SupervisorCallback,
    supervisor_client: SupervisorClient | None,
) -> None:
    if supervisor_client is None:
        await callback.answer("Supervisor не подключён.", show_alert=True)
        return
    action = callback_data.action
    task_id = callback_data.task_id
    try:
        if action == "status":
            payload = await supervisor_client.status()
            if isinstance(callback.message, Message):
                await callback.message.edit_text(
                    _status_text(payload),
                    reply_markup=_main_keyboard(),
                )
            await callback.answer()
            return
        if action == "logs":
            payload = await supervisor_client.logs(lines=120)
            content = "\n".join(str(value) for value in payload.get("lines", []))
            if isinstance(callback.message, Message):
                await callback.message.answer(
                    f"<pre>{escape(content[-3500:] or 'Логи пусты.')}</pre>"
                )
            await callback.answer()
            return
        if action.endswith(".ask"):
            labels = {
                "restart.ask": ("Перезапустить Velvet Bot?", "restart", "♻️ Перезапустить"),
                "update.ask": ("Обновить код из Git и перезапустить?", "update", "⬇️ Обновить"),
                "rollback.ask": ("Откатить последнее развёртывание?", "rollback", "↩️ Откатить"),
                "codex.apply.ask": ("Применить изменения Codex и перезапустить?", "codex.apply", "✅ Применить"),
                "codex.reject.ask": ("Удалить worktree и отклонить изменения?", "codex.reject", "🚫 Отклонить"),
                "codex.push.ask": ("Отправить применённый commit в main?", "codex.push", "⬆️ Push"),
            }
            title, confirmed_action, label = labels[action]
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=label,
                            callback_data=SupervisorCallback(
                                action=f"{confirmed_action}.do",
                                task_id=task_id,
                            ).pack(),
                        ),
                        InlineKeyboardButton(
                            text="Отмена",
                            callback_data=SupervisorCallback(
                                action="codex.status" if task_id else "status",
                                task_id=task_id,
                            ).pack(),
                        ),
                    ]
                ]
            )
            if isinstance(callback.message, Message):
                await callback.message.edit_text(f"<b>{escape(title)}</b>", reply_markup=keyboard)
            await callback.answer()
            return
        if action == "restart.do":
            await _operation_accepted(callback, await supervisor_client.restart())
            return
        if action == "update.do":
            await _operation_accepted(callback, await supervisor_client.update())
            return
        if action == "rollback.do":
            await _operation_accepted(callback, await supervisor_client.rollback())
            return
        if action == "codex.status":
            payload = await supervisor_client.codex_task(task_id)
            task = payload.get("task", {})
            if isinstance(callback.message, Message):
                await callback.message.edit_text(
                    _task_text(task),
                    reply_markup=_task_keyboard(task),
                )
            await callback.answer()
            return
        if action == "codex.apply.do":
            await _operation_accepted(callback, await supervisor_client.apply_codex_task(task_id))
            return
        if action == "codex.reject.do":
            payload = await supervisor_client.reject_codex_task(task_id)
            task = payload.get("task", {})
            if isinstance(callback.message, Message):
                await callback.message.edit_text(
                    _task_text(task),
                    reply_markup=_task_keyboard(task),
                )
            await callback.answer("Задача отклонена.")
            return
        if action == "codex.push.do":
            await _operation_accepted(callback, await supervisor_client.push_codex_task(task_id))
            return
        await callback.answer("Неизвестное действие.", show_alert=True)
    except SupervisorClientError as error:
        await _answer_error(callback, error)


async def _operation_accepted(
    callback: CallbackQuery,
    payload: dict[str, Any],
) -> None:
    operation = payload.get("operation", {})
    text = (
        "<b>Операция принята Supervisor</b>\n\n"
        f"ID: <code>{escape(str(operation.get('id', '—')))}</code>\n"
        f"Тип: <code>{escape(str(operation.get('kind', '—')))}</code>\n"
        "Результат появится в <code>/supervisor</code> и служебном лог-чате."
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text)
    await callback.answer("Операция принята.")


__all__ = ("SupervisorCallback", "router")
