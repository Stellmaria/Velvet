from __future__ import annotations

from html import escape
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .contract import supervisor_callback

_TERMINAL_STATUSES = {"success", "error"}
_STATUS_LABELS = {
    "queued": "⏳ в очереди",
    "running": "⚙️ выполняется",
    "success": "✅ завершено",
    "error": "❌ ошибка",
}
_CONSOLE_OUTPUT_INLINE_LIMIT = 2600


def console_operation_finished(operation: dict[str, Any]) -> bool:
    return str(operation.get("status", "")).casefold() in _TERMINAL_STATUSES


def console_operation_text(operation: dict[str, Any]) -> str:
    status = str(operation.get("status", "queued")).casefold()
    result = operation.get("result") if isinstance(operation.get("result"), dict) else {}
    operation_id = str(operation.get("id", "—"))
    title = str(result.get("title") or operation.get("message") or "Команда Supervisor")
    command = str(result.get("command") or "")
    output = str(result.get("output") or "").strip()
    error = str(operation.get("error") or "").strip()
    returncode = result.get("returncode")
    duration = result.get("duration_seconds")

    lines = [
        "<b>🖥 Команда Supervisor</b>",
        "",
        f"ID: <code>{escape(operation_id)}</code>",
        f"Статус: <b>{escape(_STATUS_LABELS.get(status, status or '—'))}</b>",
        f"Операция: <b>{escape(title[:500])}</b>",
    ]

    if not console_operation_finished(operation):
        lines.extend(
            [
                "",
                "Команда выполняется. Эта карточка обновится автоматически после завершения.",
            ]
        )
        return "\n".join(lines)

    if command:
        lines.extend(["", "<b>Команда</b>", f"<code>{escape(command[:900])}</code>"])

    lines.append("")
    if returncode is not None:
        lines.append(f"Код возврата: <b>{escape(str(returncode))}</b>")
    if duration is not None:
        lines.append(f"Время выполнения: <b>{escape(str(duration))} сек.</b>")

    if output:
        shown = output[-_CONSOLE_OUTPUT_INLINE_LIMIT:]
        if len(output) > len(shown):
            lines.extend(["", "<i>Показан конец длинного вывода. Полный вывод приложен файлом в ЛС.</i>"])
        lines.extend(["", "<b>Вывод</b>", f"<pre>{escape(shown)}</pre>"])
    elif status == "success":
        lines.extend(
            [
                "",
                "Команда завершилась успешно без текстового вывода. Это нормальный результат для некоторых проверок.",
            ]
        )

    if error:
        lines.extend(["", "<b>Ошибка</b>", f"<code>{escape(error[-1200:])}</code>"])

    return "\n".join(lines)


def console_operation_dm_text(operation: dict[str, Any]) -> str:
    text = console_operation_text(operation)
    return text.replace(
        "<b>🖥 Команда Supervisor</b>",
        "<b>📬 Итог команды Supervisor</b>",
        1,
    )


def console_operation_output_attachment(
    operation: dict[str, Any],
) -> tuple[str, bytes] | None:
    result = operation.get("result") if isinstance(operation.get("result"), dict) else {}
    output = str(result.get("output") or "")
    if len(output) <= _CONSOLE_OUTPUT_INLINE_LIMIT:
        return None

    operation_id = str(operation.get("id", "result"))
    safe_id = "".join(
        character
        for character in operation_id
        if character.isascii() and (character.isalnum() or character in {"-", "_"})
    )[:48] or "result"
    title = str(result.get("title") or operation.get("message") or "Команда Supervisor")
    command = str(result.get("command") or "")
    returncode = result.get("returncode")
    duration = result.get("duration_seconds")
    error = str(operation.get("error") or "").strip()

    lines = [
        "Velvet Supervisor console result",
        f"Operation ID: {operation_id}",
        f"Title: {title}",
        f"Command: {command}",
        f"Return code: {returncode}",
        f"Duration seconds: {duration}",
    ]
    if error:
        lines.append(f"Error: {error}")
    lines.extend(["", "OUTPUT", "------", output])
    payload = "\n".join(lines).encode("utf-8")
    return f"supervisor-console-{safe_id}.txt", payload


def console_operation_keyboard(
    operation_id: str,
    *,
    finished: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not finished:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Обновить сейчас",
                    callback_data=supervisor_callback(
                        "console.operation",
                        task_id=operation_id,
                    ),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🕘 История",
                    callback_data=supervisor_callback("console.history"),
                ),
                InlineKeyboardButton(
                    text="🖥 Консоль",
                    callback_data=supervisor_callback("console.menu"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📄 Логи",
                    callback_data=supervisor_callback("logs.menu"),
                ),
                InlineKeyboardButton(
                    text="🛡 Supervisor",
                    callback_data=supervisor_callback("status"),
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def console_operation_missing_text(operation_id: str) -> str:
    return (
        "<b>Команда Supervisor</b>\n\n"
        f"Операция <code>{escape(operation_id)}</code> пока не найдена в истории. "
        "Нажмите обновление через несколько секунд."
    )


def console_operation_watch_timeout_text(operation_id: str) -> str:
    return (
        "<b>Команда всё ещё выполняется</b>\n\n"
        f"ID: <code>{escape(operation_id)}</code>\n"
        "Автоматическое ожидание остановлено, чтобы не держать фоновую задачу бесконечно. "
        "Результат остаётся в Supervisor и доступен через кнопку обновления или историю."
    )


__all__ = (
    "console_operation_dm_text",
    "console_operation_finished",
    "console_operation_keyboard",
    "console_operation_missing_text",
    "console_operation_output_attachment",
    "console_operation_text",
    "console_operation_watch_timeout_text",
)
