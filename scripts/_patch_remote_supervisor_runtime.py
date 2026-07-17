from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "velvet_supervisor/runtime.py"
VIEWS = ROOT / "velvet_bot/presentation/telegram/supervisor/views.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: ожидалось одно совпадение, найдено {count}")
    return source.replace(old, new, 1)


def patch_runtime() -> None:
    source = RUNTIME.read_text(encoding="utf-8")
    source = replace_once(
        source,
        "from typing import Any, Callable\n",
        "from typing import Any, Callable\nfrom uuid import uuid4\n",
        "runtime uuid import",
    )
    source = replace_once(
        source,
        "from .codex import CodexTaskManager\n",
        "from .bootstrap import launch_bootstrap, load_bootstrap_result\n"
        "from .codex import CodexTaskManager\n",
        "runtime bootstrap import",
    )
    source = replace_once(
        source,
        "from .notifier import TelegramNotifier\n",
        "from .notifier import TelegramNotifier\n"
        "from .remote_console import RemoteCommandFailed, RemoteCommandRegistry\n",
        "runtime console import",
    )
    source = replace_once(
        source,
        "        self._repository = GitRepository(\n"
        "            settings.project_dir,\n"
        "            timeout_seconds=settings.command_timeout_seconds,\n"
        "            test_command=settings.test_command,\n"
        "        )\n"
        "        self.codex = CodexTaskManager(\n",
        "        self._repository = GitRepository(\n"
        "            settings.project_dir,\n"
        "            timeout_seconds=settings.command_timeout_seconds,\n"
        "            test_command=settings.test_command,\n"
        "        )\n"
        "        self._console = RemoteCommandRegistry(settings)\n"
        "        self.codex = CodexTaskManager(\n",
        "runtime registry init",
    )
    source = replace_once(
        source,
        "            \"supervisor\": {\n"
        "                \"pid\": os.getpid(),\n"
        "                \"started_at\": iso_or_none(self._started_at),\n"
        "                \"host\": self.settings.host,\n"
        "                \"port\": self.settings.port,\n"
        "            },\n",
        "            \"supervisor\": {\n"
        "                \"pid\": os.getpid(),\n"
        "                \"started_at\": iso_or_none(self._started_at),\n"
        "                \"host\": self.settings.host,\n"
        "                \"port\": self.settings.port,\n"
        "                \"bootstrap\": load_bootstrap_result(self.settings.runtime_dir),\n"
        "            },\n",
        "runtime bootstrap status",
    )

    marker = "    def schedule_restart(self) -> OperationState:\n"
    methods = r'''    def operation_history(self, limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 100))
        with self._lock:
            history = self._state.get("operation_history", [])
            rows = [item for item in history if isinstance(item, dict)] if isinstance(history, list) else []
            current = self._last_operation.to_dict() if self._last_operation else None
        if current and (not rows or rows[-1].get("id") != current.get("id")):
            rows.append(current)
        return list(reversed(rows[-safe_limit:]))

    def console_commands(self) -> list[dict[str, object]]:
        return [spec.to_dict() for spec in self._console.catalog()]

    def preview_console_command(
        self,
        *,
        command: str,
        command_key: str,
        requested_by: str,
    ) -> dict[str, object]:
        spec = (
            self._console.resolve(command_key, by_key=True)
            if command_key.strip()
            else self._console.resolve(command)
        )
        now = time.time()
        request = {
            "id": uuid4().hex[:12],
            "command_key": spec.key,
            "title": spec.title,
            "command": subprocess.list2cmdline(spec.command),
            "timeout_seconds": spec.timeout_seconds,
            "requested_by": requested_by.strip()[:200] or "telegram",
            "project_dir": str(self.settings.project_dir),
            "created_at": now,
            "expires_at": now + 600,
        }
        with self._lock:
            raw = self._state.get("console_requests", {})
            requests = dict(raw) if isinstance(raw, dict) else {}
            requests = {
                key: value
                for key, value in requests.items()
                if isinstance(value, dict)
                and float(value.get("expires_at", 0)) >= now
            }
            requests[str(request["id"])] = request
            self._state["console_requests"] = requests
            self._state_store.save(self._state)
        return dict(request)

    def _consume_console_request(self, request_id: str) -> dict[str, object]:
        cleaned = request_id.strip()
        if not cleaned:
            raise ValueError("ID команды не указан.")
        with self._lock:
            raw = self._state.get("console_requests", {})
            requests = dict(raw) if isinstance(raw, dict) else {}
            request = requests.pop(cleaned, None)
            self._state["console_requests"] = requests
            self._state_store.save(self._state)
        if not isinstance(request, dict):
            raise ValueError("Запрос команды не найден или уже был использован.")
        if float(request.get("expires_at", 0)) < time.time():
            raise ValueError("Подтверждение команды устарело. Создайте новый запрос.")
        return request

    def schedule_console_command(self, request_id: str) -> OperationState:
        request = self._consume_console_request(request_id)
        title = str(request.get("title", "Команда"))
        return self._schedule(
            "console-command",
            lambda operation: self._console_operation(operation, request),
            message=f"Команда принята: {title}",
        )

    def _console_operation(
        self,
        operation: OperationState,
        request: dict[str, object],
    ) -> dict[str, object]:
        key = str(request.get("command_key", ""))
        try:
            result = self._console.execute(key)
        except RemoteCommandFailed as error:
            operation.result = dict(error.result)
            raise RuntimeError(
                f"{error}\n{str(error.result.get('output', ''))[-5000:]}"
            ) from error
        result["requested_by"] = str(request.get("requested_by", "telegram"))
        output = str(result.get("output", ""))
        self._notifier.send(
            "Команда Supervisor завершена",
            (
                f"Операция: {operation.id}\n"
                f"Команда: {result.get('command')}\n"
                f"Код: {result.get('returncode')}\n\n"
                f"{output[-2500:]}"
            ),
            level="SUCCESS",
        )
        return result

    def schedule_supervisor_restart(self, *, update: bool) -> OperationState:
        if not self._operation_lock.acquire(blocking=False):
            raise OperationConflict("Уже выполняется другая системная операция.")
        kind = "supervisor-update" if update else "supervisor-restart"
        operation = OperationState.create(
            kind,
            "Self-update передан bootstrap-задаче."
            if update
            else "Перезапуск передан bootstrap-задаче.",
        )
        operation.status = "handed-off"
        operation.started_at = utc_now()
        with self._lock:
            process = self._process
            bot_pid = process.pid if process is not None and process.poll() is None else None
            self._last_operation = operation
        try:
            launch = launch_bootstrap(
                self.settings,
                action="update" if update else "restart",
                operation_id=operation.id,
                supervisor_pid=os.getpid(),
                bot_pid=bot_pid,
            )
            operation.result = launch.to_dict()
            self._persist_operation(operation)
            return operation
        except Exception:
            operation.status = "error"
            operation.finished_at = utc_now()
            self._persist_operation(operation)
            raise
        finally:
            self._operation_lock.release()

'''
    source = replace_once(source, marker, methods + marker, "runtime remote methods")
    ast.parse(source, filename=str(RUNTIME))
    RUNTIME.write_text(source, encoding="utf-8")


def patch_views() -> None:
    source = VIEWS.read_text(encoding="utf-8")
    old = r'''def _main_keyboard() -> InlineKeyboardMarkup:
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
                InlineKeyboardButton(text="🔄 Обновить", callback_data=supervisor_callback("status")),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data=_OWNER_MENU_CALLBACK),
            ],
            [InlineKeyboardButton(text="✖ Закрыть", callback_data=supervisor_callback("close"))],
        ]
    )
'''
    new = r'''def _main_keyboard() -> InlineKeyboardMarkup:
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
                InlineKeyboardButton(text="🏠 Главное меню", callback_data=_OWNER_MENU_CALLBACK),
            ],
            [InlineKeyboardButton(text="✖ Закрыть", callback_data=supervisor_callback("close"))],
        ]
    )
'''
    source = replace_once(source, old, new, "views main keyboard")
    ast.parse(source, filename=str(VIEWS))
    VIEWS.write_text(source, encoding="utf-8")


def main() -> None:
    patch_runtime()
    patch_views()


if __name__ == "__main__":
    main()
