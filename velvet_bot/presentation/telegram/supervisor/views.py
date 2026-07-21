from __future__ import annotations

from html import escape
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.presentation.telegram.supervisor.contract import supervisor_callback

_OWNER_MENU_CALLBACK = "own:menu"
_TASKS_PER_MENU = 8


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
        f"Codex: <b>{'включён' if codex.get('enabled') else 'выключен'}</b>",
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
        lines.extend(["", "<b>Фрагмент diff</b>", f"<pre>{escape(diff[:2500])}</pre>"])
    return "\n".join(lines)


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 Бот", callback_data=supervisor_callback("bot.menu")),
                InlineKeyboardButton(text="🌿 Git", callback_data=supervisor_callback("git.menu")),
            ],
            [
                InlineKeyboardButton(text="📄 Логи", callback_data=supervisor_callback("logs.menu")),
                InlineKeyboardButton(text="🧠 Codex", callback_data=supervisor_callback("codex.menu")),
            ],
            [
                InlineKeyboardButton(text="🖥 Консоль", callback_data=supervisor_callback("console.menu")),
                InlineKeyboardButton(text="🧩 Сам Supervisor", callback_data=supervisor_callback("self.menu")),
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data=supervisor_callback("status")),
                InlineKeyboardButton(text="🏠 Главная", callback_data=_OWNER_MENU_CALLBACK),
            ],
            [InlineKeyboardButton(text="✖ Закрыть", callback_data=supervisor_callback("close"))],
        ]
    )


def _bot_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="♻️ Перезапустить бот",
                    callback_data=supervisor_callback("restart.ask"),
                )
            ],
            [
                InlineKeyboardButton(text="📄 Открыть логи", callback_data=supervisor_callback("logs.menu")),
                InlineKeyboardButton(text="🔄 Обновить", callback_data=supervisor_callback("bot.menu")),
            ],
            [InlineKeyboardButton(text="↩️ Supervisor", callback_data=supervisor_callback("status"))],
        ]
    )


def _git_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬇️ Обновить main", callback_data=supervisor_callback("update.ask")),
                InlineKeyboardButton(text="↩️ Откатить", callback_data=supervisor_callback("rollback.ask")),
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data=supervisor_callback("git.menu")),
                InlineKeyboardButton(text="↩️ Supervisor", callback_data=supervisor_callback("status")),
            ],
        ]
    )


def _logs_keyboard(selected_lines: int = 150) -> InlineKeyboardMarkup:
    def label(value: int) -> str:
        return ("● " if value == selected_lines else "") + str(value)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=label(50), callback_data=supervisor_callback("logs.50")),
                InlineKeyboardButton(text=label(150), callback_data=supervisor_callback("logs.150")),
            ],
            [
                InlineKeyboardButton(text=label(500), callback_data=supervisor_callback("logs.500")),
                InlineKeyboardButton(text=label(2000), callback_data=supervisor_callback("logs.2000")),
            ],
            [
                InlineKeyboardButton(text="📎 Скачать файлом", callback_data=supervisor_callback("logs.file"))
            ],
            [
                InlineKeyboardButton(text="↩️ Supervisor", callback_data=supervisor_callback("status")),
                InlineKeyboardButton(text="🏠 Главная", callback_data=_OWNER_MENU_CALLBACK),
            ],
        ]
    )


def _codex_keyboard(tasks: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="➕ Новая задача", callback_data=supervisor_callback("codex.input")),
            InlineKeyboardButton(text="🔎 Найти по ID", callback_data=supervisor_callback("task.input")),
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
                    callback_data=supervisor_callback("codex.open", task_id=task_id),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data=supervisor_callback("codex.menu")),
            InlineKeyboardButton(text="↩️ Supervisor", callback_data=supervisor_callback("status")),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _task_keyboard(task: dict[str, Any]) -> InlineKeyboardMarkup:
    task_id = str(task.get("id", ""))
    status = str(task.get("status", ""))
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🔄 Обновить задачу", callback_data=supervisor_callback("codex.open", task_id=task_id))]
    ]
    if status == "ready":
        rows.append(
            [
                InlineKeyboardButton(text="✅ Применить + рестарт", callback_data=supervisor_callback("codex.apply.ask", task_id=task_id)),
                InlineKeyboardButton(text="🚫 Отклонить", callback_data=supervisor_callback("codex.reject.ask", task_id=task_id)),
            ]
        )
    if status == "applied" and not task.get("pushed_at"):
        rows.append(
            [InlineKeyboardButton(text="⬆️ Push в main", callback_data=supervisor_callback("codex.push.ask", task_id=task_id))]
        )
    rows.append(
        [
            InlineKeyboardButton(text="↩️ Список задач", callback_data=supervisor_callback("codex.menu")),
            InlineKeyboardButton(text="🛡 Supervisor", callback_data=supervisor_callback("status")),
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
                InlineKeyboardButton(text=label, callback_data=supervisor_callback(f"{confirmed_action}.do", task_id=task_id)),
                InlineKeyboardButton(text="✖ Отмена", callback_data=supervisor_callback(cancel_action, task_id=task_id)),
            ]
        ]
    )


def _accepted_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Проверить статус", callback_data=supervisor_callback("status")),
                InlineKeyboardButton(text="📄 Логи", callback_data=supervisor_callback("logs.menu")),
            ],
            [InlineKeyboardButton(text="🏠 Главная", callback_data=_OWNER_MENU_CALLBACK)],
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
    "_accepted_keyboard",
    "_answer_error",
    "_bot_keyboard",
    "_bot_text",
    "_codex_keyboard",
    "_confirm_keyboard",
    "_git_keyboard",
    "_git_text",
    "_logs_keyboard",
    "_logs_text",
    "_main_keyboard",
    "_operation_accepted",
    "_safe_edit",
    "_status_text",
    "_task_keyboard",
    "_task_status_label",
    "_task_text",
    "_tasks_text",
    "_unavailable_text",
)
