from __future__ import annotations

from html import escape
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .contract import supervisor_callback


def console_text(commands: list[dict[str, Any]]) -> str:
    lines = [
        "<b>🖥 Безопасная консоль Supervisor</b>",
        "",
        "Команды запускаются без shell и только из фиксированного реестра. ",
        "Перед выполнением бот покажет точную команду и попросит подтверждение.",
        "",
        "<b>Доступные команды</b>",
    ]
    for item in commands:
        lines.append(
            f"• <b>{escape(str(item.get('title', 'Команда')))}</b>\n"
            f"  <code>{escape(str(item.get('command', '')))}</code>"
        )
    return "\n".join(lines)


def console_keyboard(commands: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    preferred = {
        "git-status",
        "git-head",
        "compile",
        "tests",
        "ollama-list",
        "task-status",
    }
    for item in commands:
        key = str(item.get("key", ""))
        if key not in preferred:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"▶️ {str(item.get('title', key))[:42]}",
                    callback_data=supervisor_callback("console.quick", task_id=key),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="⌨️ Ввести разрешённую команду",
                    callback_data=supervisor_callback("console.input"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🕘 История операций",
                    callback_data=supervisor_callback("console.history"),
                ),
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=supervisor_callback("console.menu"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Supervisor",
                    callback_data=supervisor_callback("status"),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def console_preview_text(request: dict[str, Any]) -> str:
    return (
        "<b>Подтвердите удалённую команду</b>\n\n"
        f"ID: <code>{escape(str(request.get('id', '—')))}</code>\n"
        f"Название: <b>{escape(str(request.get('title', '—')))}</b>\n"
        f"Каталог: <code>{escape(str(request.get('project_dir', '—')))}</code>\n"
        f"Команда: <code>{escape(str(request.get('command', '—')))}</code>\n"
        f"Таймаут: <b>{escape(str(request.get('timeout_seconds', '—')))} сек.</b>\n"
        f"Инициатор: <code>{escape(str(request.get('requested_by', '—')))}</code>\n\n"
        "Параметры нельзя дописать после подтверждения: будет выполнена именно эта argv-команда."
    )


def console_preview_keyboard(request_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Выполнить",
                    callback_data=supervisor_callback("console.run", task_id=request_id),
                ),
                InlineKeyboardButton(
                    text="✖ Отмена",
                    callback_data=supervisor_callback("console.menu"),
                ),
            ]
        ]
    )


def operation_history_text(operations: list[dict[str, Any]]) -> str:
    lines = ["<b>🕘 История операций Supervisor</b>"]
    if not operations:
        return "\n\n".join(lines + ["Операций пока нет."])
    for item in operations[:15]:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        output = str(result.get("output", ""))
        if len(output) > 500:
            output = output[-500:]
        lines.extend(
            [
                "",
                (
                    f"<code>{escape(str(item.get('id', '—')))}</code> · "
                    f"<b>{escape(str(item.get('status', '—')))}</b> · "
                    f"{escape(str(item.get('kind', '—')))}"
                ),
                escape(str(item.get("message", ""))[:500]),
            ]
        )
        if output:
            lines.append(f"<pre>{escape(output)}</pre>")
        if item.get("error"):
            lines.append(f"<code>{escape(str(item['error'])[-700:])}</code>")
    return "\n".join(lines)


def self_control_text(status_payload: dict[str, Any]) -> str:
    status = status_payload.get("status", {})
    supervisor = status.get("supervisor", {})
    git = status.get("git", {})
    bootstrap = supervisor.get("bootstrap")
    lines = [
        "<b>🧩 Управление самим Supervisor</b>",
        "",
        f"PID: <code>{escape(str(supervisor.get('pid', '—')))}</code>",
        f"Commit: <code>{escape(str(git.get('head_sha', '—'))[:16])}</code>",
        "",
        "Перезапуск и self-update передаются отдельной одноразовой задаче Windows. "
        "Она переживает остановку текущего Supervisor и запускает основную задачу заново.",
    ]
    if isinstance(bootstrap, dict):
        lines.extend(
            [
                "",
                "<b>Последний bootstrap</b>",
                f"Операция: <code>{escape(str(bootstrap.get('operation_id', '—')))}</code>",
                f"Действие: <code>{escape(str(bootstrap.get('action', '—')))}</code>",
                f"Статус: <b>{escape(str(bootstrap.get('status', '—')))}</b>",
            ]
        )
        if bootstrap.get("error"):
            lines.append(f"<code>{escape(str(bootstrap['error'])[-1200:])}</code>")
    return "\n".join(lines)


def self_control_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="♻️ Перезапустить Supervisor",
                    callback_data=supervisor_callback("self.restart.ask"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬇️ Обновить и перезапустить",
                    callback_data=supervisor_callback("self.update.ask"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить статус",
                    callback_data=supervisor_callback("self.menu"),
                ),
                InlineKeyboardButton(
                    text="↩️ Назад",
                    callback_data=supervisor_callback("status"),
                ),
            ],
        ]
    )


__all__ = (
    "console_keyboard",
    "console_preview_keyboard",
    "console_preview_text",
    "console_text",
    "operation_history_text",
    "self_control_keyboard",
    "self_control_text",
)
