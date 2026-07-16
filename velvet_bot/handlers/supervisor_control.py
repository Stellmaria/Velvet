from __future__ import annotations

import re
from html import escape
from typing import Any

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.supervisor_client import SupervisorClient, SupervisorClientError

router = Router(name=__name__)

_OWNER_MENU_CALLBACK = "own:menu"
_INPUT_MARKER_RE = re.compile(r"SUPERVISOR_INPUT:(codex|task)")
_TASKS_PER_MENU = 8


class SupervisorCallback(CallbackData, prefix="sup"):
    action: str
    task_id: str = ""


class SupervisorReplyMarkerFilter(BaseFilter):
    async def __call__(self, message: Message) -> dict[str, str] | bool:
        reply = message.reply_to_message
        if reply is None:
            return False
        source = reply.text or reply.caption or ""
        match = _INPUT_MARKER_RE.search(source)
        if match is None:
            return False
        return {"supervisor_input_kind": match.group(1)}


def _cb(action: str, *, task_id: str = "") -> str:
    return SupervisorCallback(action=action, task_id=task_id).pack()


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
        if operation.get("message"):
            lines.append(escape(str(operation["message"])[:1000]))
        if operation.get("error"):
            lines.append(f"<code>{escape(str(operation['error'])[-1500:])}</code>")
    return "\n".join(lines)


def _bot_text(payload: dict[str, Any]) -> str:
    status = payload.get("status", {})
    bot = status.get("bot", {})
    running = bool(bot.get("running"))
    return (
        "<b>🤖 Управление Velvet Bot</b>\n\n"
        f"Состояние: <b>{'✅ работает' if running else '❌ остановлен'}</b>\n"
        f"PID: <code>{escape(str(bot.get('pid') or '—'))}</code>\n"
        f"Автоперезапуск: <b>{'включён' if bot.get('auto_restart') else 'выключен'}</b>\n"
        f"Crash-loop: <b>{'заблокирован' if bot.get('crash_loop_open') else 'норма'}</b>\n"
        f"Перезапусков в окне: <b>{bot.get('restart_count_in_window', 0)}/"
        f"{bot.get('restart_limit', 0)}</b>\n\n"
        "Перезапуск затрагивает только дочерний процесс бота. Supervisor остаётся "
        "работать и проверяет, что новая копия действительно запустилась."
    )


def _git_text(payload: dict[str, Any]) -> str:
    status = payload.get("status", {})
    git = status.get("git", {})
    operation = status.get("operation")
    lines = [
        "<b>🌿 Git и развёртывание</b>",
        "",
        f"Ветка: <code>{escape(str(git.get('branch', '—')))}</code>",
        f"Commit: <code>{escape(str(git.get('head_sha', '—'))[:16])}</code>",
        f"Рабочее дерево: <b>{'изменено' if git.get('dirty') else 'чистое'}</b>",
    ]
    if git.get("error"):
        lines.extend(["", f"<code>{escape(str(git['error'])[:1500])}</code>"])
    if operation:
        lines.extend(
            [
                "",
                "<b>Последняя операция</b>",
                f"Тип: <code>{escape(str(operation.get('kind', '—')))}</code>",
                f"Статус: <b>{escape(str(operation.get('status', '—')))}</b>",
            ]
        )
        if operation.get("message"):
            lines.append(escape(str(operation["message"])[:1200]))
        if operation.get("error"):
            lines.append(f"<code>{escape(str(operation['error'])[-1800:])}</code>")
    lines.extend(
        [
            "",
            "Обновление допускает только fast-forward, запускает полный набор "
            "тестов и автоматически возвращает прежний commit при неудачном запуске.",
        ]
    )
    return "\n".join(lines)


def _logs_text(lines: int, content: str) -> str:
    tail = content[-3400:] if content else "Логи пока пусты."
    return (
        "<b>📄 Журнал Velvet Bot</b>\n\n"
        f"Показаны последние <b>{lines}</b> строк.\n\n"
        f"<pre>{escape(tail)}</pre>"
    )


def _task_status_label(status: str) -> str:
    return {
        "queued": "⏳ очередь",
        "running": "⚙️ выполняется",
        "testing": "🧪 тесты",
        "ready": "✅ готово",
        "applied": "📦 применено",
        "rejected": "🚫 отклонено",
        "error": "❌ ошибка",
        "no_changes": "ℹ️ без изменений",
    }.get(status, status or "—")


def _tasks_text(tasks: list[dict[str, Any]], *, enabled: bool = True) -> str:
    lines = [
        "<b>🧠 Codex</b>",
        "",
        f"Интеграция: <b>{'включена' if enabled else 'выключена'}</b>",
        "Новая задача вводится обычным ответом на сообщение формы, без slash-команды.",
    ]
    if not tasks:
        lines.extend(["", "Задач пока нет."])
        return "\n".join(lines)
    lines.extend(["", "<b>Последние задачи</b>"])
    for task in tasks[:_TASKS_PER_MENU]:
        prompt = " ".join(str(task.get("prompt", "")).split())
        if len(prompt) > 58:
            prompt = prompt[:57].rstrip() + "…"
        lines.append(
            f"<code>{escape(str(task.get('id', '—')))}</code> · "
            f"{escape(_task_status_label(str(task.get('status', ''))))}\n"
            f"{escape(prompt or 'Без описания')}"
        )
    return "\n\n".join(lines)


def _task_text(task: dict[str, Any]) -> str:
    changed = task.get("changed_files") or []
    error = task.get("error")
    diff = str(task.get("diff", ""))
    prompt = str(task.get("prompt", ""))
    lines = [
        "<b>🧠 Задача Codex</b>",
        "",
        f"ID: <code>{escape(str(task.get('id', '—')))}</code>",
        f"Статус: <b>{escape(_task_status_label(str(task.get('status', '—'))))}</b>",
        f"Запросил: <code>{escape(str(task.get('requested_by', '—')))}</code>",
        f"Base: <code>{escape(str(task.get('base_sha') or '—')[:16])}</code>",
        f"Commit: <code>{escape(str(task.get('commit_sha') or '—')[:16])}</code>",
        f"Изменено файлов: <b>{len(changed)}</b>",
    ]
    if prompt:
        lines.extend(["", "<b>Задача</b>", escape(prompt[:1800])])
    if changed:
        lines.extend(
            [
                "",
                "<b>Файлы</b>",
                "<code>" + escape("\n".join(str(value) for value in changed[:30])) + "</code>",
            ]
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


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 Бот", callback_data=_cb("bot.menu")),
                InlineKeyboardButton(text="🌿 Git", callback_data=_cb("git.menu")),
            ],
            [
                InlineKeyboardButton(text="📄 Логи", callback_data=_cb("logs.menu")),
                InlineKeyboardButton(text="🧠 Codex", callback_data=_cb("codex.menu")),
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data=_cb("status")),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data=_OWNER_MENU_CALLBACK),
            ],
            [InlineKeyboardButton(text="✖ Закрыть", callback_data=_cb("close"))],
        ]
    )


def _bot_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="♻️ Перезапустить бот",
                    callback_data=_cb("restart.ask"),
                )
            ],
            [
                InlineKeyboardButton(text="📄 Открыть логи", callback_data=_cb("logs.menu")),
                InlineKeyboardButton(text="🔄 Обновить", callback_data=_cb("bot.menu")),
            ],
            [InlineKeyboardButton(text="↩️ Supervisor", callback_data=_cb("status"))],
        ]
    )


def _git_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬇️ Обновить main",
                    callback_data=_cb("update.ask"),
                ),
                InlineKeyboardButton(
                    text="↩️ Откатить",
                    callback_data=_cb("rollback.ask"),
                ),
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data=_cb("git.menu")),
                InlineKeyboardButton(text="↩️ Supervisor", callback_data=_cb("status")),
            ],
        ]
    )


def _logs_keyboard(selected_lines: int = 150) -> InlineKeyboardMarkup:
    def label(value: int) -> str:
        return ("● " if value == selected_lines else "") + str(value)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=label(50), callback_data=_cb("logs.50")),
                InlineKeyboardButton(text=label(150), callback_data=_cb("logs.150")),
                InlineKeyboardButton(text=label(500), callback_data=_cb("logs.500")),
                InlineKeyboardButton(text=label(2000), callback_data=_cb("logs.2000")),
            ],
            [
                InlineKeyboardButton(
                    text="📎 Скачать файлом",
                    callback_data=_cb("logs.file"),
                )
            ],
            [
                InlineKeyboardButton(text="↩️ Supervisor", callback_data=_cb("status")),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data=_OWNER_MENU_CALLBACK),
            ],
        ]
    )


def _codex_keyboard(tasks: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="➕ Новая задача",
                callback_data=_cb("codex.input"),
            ),
            InlineKeyboardButton(
                text="🔎 Найти по ID",
                callback_data=_cb("task.input"),
            ),
        ]
    ]
    for task in tasks[:_TASKS_PER_MENU]:
        task_id = str(task.get("id", ""))
        status = _task_status_label(str(task.get("status", "")))
        prompt = " ".join(str(task.get("prompt", "")).split()) or "Без описания"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} · {task_id} · {prompt[:26]}",
                    callback_data=_cb("codex.open", task_id=task_id),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data=_cb("codex.menu")),
            InlineKeyboardButton(text="↩️ Supervisor", callback_data=_cb("status")),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _task_keyboard(task: dict[str, Any]) -> InlineKeyboardMarkup:
    task_id = str(task.get("id", ""))
    status = str(task.get("status", ""))
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="🔄 Обновить задачу",
                callback_data=_cb("codex.open", task_id=task_id),
            )
        ]
    ]
    if status == "ready":
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Применить и перезапустить",
                    callback_data=_cb("codex.apply.ask", task_id=task_id),
                ),
                InlineKeyboardButton(
                    text="🚫 Отклонить",
                    callback_data=_cb("codex.reject.ask", task_id=task_id),
                ),
            ]
        )
    if status == "applied" and not task.get("pushed_at"):
        rows.append(
            [
                InlineKeyboardButton(
                    text="⬆️ Push в main",
                    callback_data=_cb("codex.push.ask", task_id=task_id),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="↩️ Список задач", callback_data=_cb("codex.menu")),
            InlineKeyboardButton(text="🛡 Supervisor", callback_data=_cb("status")),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_keyboard(
    confirmed_action: str,
    label: str,
    *,
    cancel_action: str,
    task_id: str = "",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=_cb(f"{confirmed_action}.do", task_id=task_id),
                ),
                InlineKeyboardButton(
                    text="✖ Отмена",
                    callback_data=_cb(cancel_action, task_id=task_id),
                ),
            ]
        ]
    )


def _accepted_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Проверить статус", callback_data=_cb("status")),
                InlineKeyboardButton(text="📄 Логи", callback_data=_cb("logs.menu")),
            ],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data=_OWNER_MENU_CALLBACK)],
        ]
    )


async def _safe_edit(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


async def _answer_error(target: Message | CallbackQuery, error: Exception) -> None:
    text = f"<b>Операция не выполнена</b>\n\n<code>{escape(str(error))}</code>"
    if isinstance(target, CallbackQuery):
        if isinstance(target.message, Message):
            await target.message.answer(text, reply_markup=_main_keyboard())
        await target.answer("Ошибка Supervisor", show_alert=True)
    else:
        await target.answer(text, reply_markup=_main_keyboard())


async def _load_status(client: SupervisorClient) -> dict[str, Any]:
    return await client.status()


async def _load_tasks(client: SupervisorClient) -> tuple[list[dict[str, Any]], bool]:
    payload = await client.codex_tasks(limit=20)
    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list):
        tasks = []
    try:
        status_payload = await client.status()
        enabled = bool(status_payload.get("status", {}).get("codex", {}).get("enabled"))
    except SupervisorClientError:
        enabled = True
    return [item for item in tasks if isinstance(item, dict)], enabled


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
    payload = await _load_status(supervisor_client)
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


@router.message(Command("logs"))
async def handle_supervisor_logs(
    message: Message,
    supervisor_client: SupervisorClient | None,
) -> None:
    if supervisor_client is None:
        await message.answer(_unavailable_text())
        return
    try:
        payload = await supervisor_client.logs(lines=150)
    except SupervisorClientError as error:
        await _answer_error(message, error)
        return
    content = "\n".join(str(value) for value in payload.get("lines", []))
    await message.answer(_logs_text(150, content), reply_markup=_logs_keyboard(150))


@router.message(Command("restart"))
async def handle_restart_command(message: Message) -> None:
    await message.answer(
        "<b>Перезапустить Velvet Bot?</b>\n\n"
        "Supervisor завершит только дочерний процесс и запустит новую копию.",
        reply_markup=_confirm_keyboard(
            "restart",
            "♻️ Перезапустить",
            cancel_action="bot.menu",
        ),
    )


@router.message(Command("update"))
async def handle_update_command(message: Message) -> None:
    await message.answer(
        "<b>Выполнить безопасное обновление?</b>\n\n"
        "Будут выполнены fetch, fast-forward, тесты и перезапуск. "
        "При ошибке Supervisor вернёт предыдущий commit.",
        reply_markup=_confirm_keyboard(
            "update",
            "⬇️ Обновить",
            cancel_action="git.menu",
        ),
    )


@router.message(Command("rollback"))
async def handle_rollback_command(message: Message) -> None:
    await message.answer(
        "<b>Откатить последнее развёртывание?</b>\n\n"
        "Будет восстановлен предыдущий сохранённый commit и перезапущен бот.",
        reply_markup=_confirm_keyboard(
            "rollback",
            "↩️ Откатить",
            cancel_action="git.menu",
        ),
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
    if not task_id:
        try:
            tasks, enabled = await _load_tasks(supervisor_client)
        except SupervisorClientError as error:
            await _answer_error(message, error)
            return
        await message.answer(_tasks_text(tasks, enabled=enabled), reply_markup=_codex_keyboard(tasks))
        return
    await _show_task(message, supervisor_client, task_id)


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


async def _create_codex_task(
    message: Message,
    supervisor_client: SupervisorClient,
    prompt: str,
) -> None:
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


async def _show_task(
    message: Message,
    supervisor_client: SupervisorClient,
    task_id: str,
) -> None:
    cleaned = task_id.strip()
    if not cleaned:
        await message.answer("ID задачи не указан.", reply_markup=_main_keyboard())
        return
    try:
        payload = await supervisor_client.codex_task(cleaned)
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
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    if supervisor_client is None:
        await callback.answer("Supervisor не подключён.", show_alert=True)
        return

    action = callback_data.action
    task_id = callback_data.task_id
    try:
        if action == "close":
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                await callback.message.edit_reply_markup(reply_markup=None)
            await callback.answer()
            return

        if action == "status":
            payload = await _load_status(supervisor_client)
            await _safe_edit(callback.message, _status_text(payload), _main_keyboard())
            await callback.answer()
            return

        if action == "bot.menu":
            payload = await _load_status(supervisor_client)
            await _safe_edit(callback.message, _bot_text(payload), _bot_keyboard())
            await callback.answer()
            return

        if action == "git.menu":
            payload = await _load_status(supervisor_client)
            await _safe_edit(callback.message, _git_text(payload), _git_keyboard())
            await callback.answer()
            return

        if action == "logs.menu" or action.startswith("logs."):
            if action == "logs.file":
                payload = await supervisor_client.logs(lines=2000)
                content = "\n".join(str(value) for value in payload.get("lines", []))
                await callback.message.answer_document(
                    BufferedInputFile(
                        content.encode("utf-8"),
                        filename="velvet.log.txt",
                    ),
                    caption="Последние 2000 строк журнала Velvet Bot.",
                )
                await callback.answer("Лог отправлен файлом.")
                return
            raw_lines = action.partition(".")[2]
            lines = int(raw_lines) if raw_lines.isdigit() else 150
            payload = await supervisor_client.logs(lines=lines)
            content = "\n".join(str(value) for value in payload.get("lines", []))
            await _safe_edit(
                callback.message,
                _logs_text(lines, content),
                _logs_keyboard(lines),
            )
            await callback.answer()
            return

        if action == "codex.menu":
            tasks, enabled = await _load_tasks(supervisor_client)
            await _safe_edit(
                callback.message,
                _tasks_text(tasks, enabled=enabled),
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
            payload = await supervisor_client.codex_task(task_id)
            task = payload.get("task", {})
            await _safe_edit(
                callback.message,
                _task_text(task),
                _task_keyboard(task),
            )
            await callback.answer()
            return

        if action.endswith(".ask"):
            labels = {
                "restart.ask": (
                    "Перезапустить Velvet Bot?",
                    "restart",
                    "♻️ Перезапустить",
                    "bot.menu",
                ),
                "update.ask": (
                    "Обновить main, запустить тесты и перезапустить?",
                    "update",
                    "⬇️ Обновить",
                    "git.menu",
                ),
                "rollback.ask": (
                    "Откатить последнее развёртывание и перезапустить?",
                    "rollback",
                    "↩️ Откатить",
                    "git.menu",
                ),
                "codex.apply.ask": (
                    "Применить изменения Codex и перезапустить?",
                    "codex.apply",
                    "✅ Применить",
                    "codex.open",
                ),
                "codex.reject.ask": (
                    "Удалить worktree и отклонить изменения?",
                    "codex.reject",
                    "🚫 Отклонить",
                    "codex.open",
                ),
                "codex.push.ask": (
                    "Отправить применённый commit в main?",
                    "codex.push",
                    "⬆️ Push",
                    "codex.open",
                ),
            }
            title, confirmed_action, label, cancel_action = labels[action]
            await _safe_edit(
                callback.message,
                f"<b>{escape(title)}</b>",
                _confirm_keyboard(
                    confirmed_action,
                    label,
                    cancel_action=cancel_action,
                    task_id=task_id,
                ),
            )
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
        "Статус и результат доступны через кнопки ниже и в служебном лог-чате."
    )
    if isinstance(callback.message, Message):
        await _safe_edit(callback.message, text, _accepted_keyboard())
    await callback.answer("Операция принята.")


__all__ = (
    "SupervisorCallback",
    "SupervisorReplyMarkerFilter",
    "router",
    "show_supervisor_menu",
)
