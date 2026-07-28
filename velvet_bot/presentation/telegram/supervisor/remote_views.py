from __future__ import annotations

from html import escape
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .contract import supervisor_callback


_COMMAND_TITLE_OVERRIDES = {
    "ollama-recovery-status": "Ollama: состояние набора моделей",
    "ollama-configure-qwen3-vl-4b": "Ollama: настроить набор моделей",
    "ollama-pull-qwen3-vl-4b": "Ollama: установить набор моделей",
    "ollama-show-qwen3-vl-4b": "Ollama: проверить набор моделей",
    "ollama-repair-qwen3-vl-4b": "Ollama: восстановить набор моделей",
}
_TITLE_TEXT_OVERRIDES = {
    "Ollama: состояние vision": "Ollama: состояние набора моделей",
    "Ollama: настроить vision qwen3-vl:4b": "Ollama: настроить набор моделей",
    "Ollama: скачать qwen3-vl:4b": "Ollama: установить набор моделей",
    "Ollama: проверить vision qwen3-vl:4b": "Ollama: проверить набор моделей",
    "Ollama: восстановить vision qwen3-vl:4b": "Ollama: восстановить набор моделей",
}

# The registry intentionally remains broader than the normal menu. Rare recovery
# commands are still resolvable by exact key/alias, but the main menu only shows
# commands that are useful during routine operation.
_VISIBLE_COMMAND_KEYS = {
    "git-status",
    "git-head",
    "git-log",
    "git-diff-names",
    "git-fetch",
    "git-sync-count",
    "git-incoming",
    "python-version",
    "pip-check",
    "compile",
    "tests",
    "ollama-list",
    "ollama-recovery-status",
    "ollama-start",
    "ollama-repair-qwen3-vl-4b",
    "python-processes",
}
_TELEGRAM_SAFE_TEXT_LIMIT = 3600
_HISTORY_ITEMS_LIMIT = 12
_HISTORY_NOTICE_RESERVE = 180


def _command_title(item: dict[str, Any], *, default: str = "Команда") -> str:
    key = str(item.get("key") or item.get("command_key") or "")
    raw = str(item.get("title", default))
    return _COMMAND_TITLE_OVERRIDES.get(key, _TITLE_TEXT_OVERRIDES.get(raw, raw))


def _visible_commands(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in commands if str(item.get("key", "")) in _VISIBLE_COMMAND_KEYS]


def console_text(commands: list[dict[str, Any]]) -> str:
    visible = _visible_commands(commands)
    hidden_count = max(0, len(commands) - len(visible))
    lines = [
        "<b>🖥 Безопасная консоль Supervisor</b>",
        "",
        "Команды запускаются без shell и только из фиксированного реестра. ",
        "Перед выполнением бот покажет точную команду и попросит подтверждение.",
        "",
        "<b>Основные команды</b>",
    ]
    current_category = ""
    for item in visible:
        category = str(item.get("category") or "Диагностика")
        if category != current_category:
            current_category = category
            lines.extend(["", f"<b>{escape(category)}</b>"])
        lines.append(
            f"• <b>{escape(_command_title(item))}</b>\n"
            f"  <code>{escape(str(item.get('command', '')))}</code>"
        )
    if hidden_count:
        lines.extend(
            [
                "",
                (
                    f"<i>Ещё {hidden_count} аварийных и узкоспециальных команд "
                    "остаются в безопасном allowlist, но скрыты из обычного меню. "
                    "Их можно вызвать через точный ввод команды.</i>"
                ),
            ]
        )
    return "\n".join(lines)


def console_keyboard(commands: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    preferred = {
        "git-status",
        "git-head",
        "git-fetch",
        "compile",
        "tests",
        "ollama-list",
        "ollama-recovery-status",
        "ollama-repair-qwen3-vl-4b",
    }
    for item in _visible_commands(commands):
        key = str(item.get("key", ""))
        if key not in preferred:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"▶️ {_command_title(item, default=key)[:42]}",
                    callback_data=supervisor_callback("console.quick", task_id=key),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="⌨️ Ввести команду",
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
        f"Название: <b>{escape(_command_title(request, default='—'))}</b>\n"
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

    shown = 0
    for item in operations[:_HISTORY_ITEMS_LIMIT]:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        status = str(item.get("status", "—"))
        message = " ".join(str(item.get("message", "")).split())[:180]
        entry = [
            "",
            (
                f"<code>{escape(str(item.get('id', '—')))}</code> · "
                f"<b>{escape(status)}</b> · "
                f"{escape(str(item.get('kind', '—')))}"
            ),
        ]
        if message:
            entry.append(escape(message))

        # Successful command output is already available on its own operation card
        # and, for long results, as a text attachment. History only keeps concise
        # diagnostics for failed operations.
        if status.casefold() == "error":
            output = " ".join(str(result.get("output", "")).split())[-220:]
            if output:
                entry.append(f"<code>{escape(output)}</code>")
            error = " ".join(str(item.get("error", "")).split())[-320:]
            if error:
                entry.append(f"<code>{escape(error)}</code>")

        candidate = "\n".join(lines + entry)
        if len(candidate) > _TELEGRAM_SAFE_TEXT_LIMIT - _HISTORY_NOTICE_RESERVE:
            break
        lines.extend(entry)
        shown += 1

    remaining = max(0, len(operations) - shown)
    if remaining:
        lines.extend(
            [
                "",
                f"<i>Не показано более старых операций: {remaining}. "
                "Подробный вывод остаётся в карточках операций и текстовых вложениях.</i>",
            ]
        )
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
                    text="♻️ Рестарт Supervisor",
                    callback_data=supervisor_callback("self.restart.ask"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬇️ Обновить + рестарт",
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
