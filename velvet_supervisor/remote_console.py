from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Iterable

from .config import SupervisorSettings

_FORBIDDEN_INPUT_RE = re.compile(r"[\x00-\x1f;&|><`]|\$\(")
_SECRET_RE = re.compile(
    r"(?i)(BOT_TOKEN|DATABASE_URL|PASSWORD|SECRET|API_KEY|SUPERVISOR_TOKEN)\s*[=:]\s*\S+"
)
_CONNECTION_RE = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|redis|mysql|mongodb(?:\+srv)?)://\S+"
)
_BOT_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
_TERMINAL_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_MAX_INPUT_LENGTH = 300
_MAX_OUTPUT_LENGTH = 20_000
_OLLAMA_BUNDLE_TIMEOUT_SECONDS = 7_200


@dataclass(frozen=True, slots=True)
class RemoteCommandSpec:
    key: str
    title: str
    command: tuple[str, ...]
    aliases: tuple[str, ...]
    timeout_seconds: int = 60
    category: str = "Диагностика"
    enforce_global_timeout: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "command": subprocess.list2cmdline(self.command),
            "aliases": list(self.aliases),
            "timeout_seconds": self.timeout_seconds,
            "category": self.category,
        }


class RemoteCommandRejected(ValueError):
    pass


class RemoteCommandFailed(RuntimeError):
    def __init__(self, message: str, result: dict[str, object]) -> None:
        super().__init__(message)
        self.result = result


def _normalize(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _strip_terminal_control(value: str) -> str:
    cleaned = _TERMINAL_ESCAPE_RE.sub("", value)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    return cleaned


def _redact(value: str, secret_values: Iterable[str] = ()) -> str:
    result = _strip_terminal_control(value)
    for secret in secret_values:
        cleaned = secret.strip()
        if len(cleaned) >= 6:
            result = result.replace(cleaned, "<redacted>")
    result = _CONNECTION_RE.sub("<redacted-connection-url>", result)
    result = _BOT_TOKEN_RE.sub("<redacted-bot-token>", result)
    result = _SECRET_RE.sub(r"\1=<redacted>", result)
    return result


def _child_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


class RemoteCommandRegistry:
    """Exact allowlist for commands accepted from Telegram.

    User text only resolves to predefined argv tuples. No command is executed
    through a shell.
    """

    def __init__(self, settings: SupervisorSettings) -> None:
        self._settings = settings
        task_name = os.getenv("SUPERVISOR_TASK_NAME", "VelvetSupervisor").strip()
        python = settings.python_executable
        specs = (
            RemoteCommandSpec(
                "git-status",
                "Git: локальные изменения",
                ("git", "status", "--short"),
                ("git status", "git status --short", "статус git"),
                category="Git: состояние",
            ),
            RemoteCommandSpec(
                "git-branch",
                "Git: текущая ветка",
                ("git", "branch", "--show-current"),
                ("git branch --show-current", "текущая ветка"),
                category="Git: состояние",
            ),
            RemoteCommandSpec(
                "git-head",
                "Git: текущий commit",
                ("git", "rev-parse", "--short", "HEAD"),
                ("git rev-parse --short head", "git head", "текущий commit"),
                category="Git: состояние",
            ),
            RemoteCommandSpec(
                "git-log",
                "Git: последние десять commit",
                ("git", "log", "-10", "--oneline", "--decorate"),
                ("git log -10 --oneline --decorate", "git log", "последние коммиты"),
                category="Git: состояние",
            ),
            RemoteCommandSpec(
                "git-diff-stat",
                "Git: сводка локальных изменений",
                ("git", "diff", "--stat"),
                ("git diff --stat", "сводка изменений"),
                category="Git: состояние",
            ),
            RemoteCommandSpec(
                "git-diff-names",
                "Git: изменённые файлы",
                ("git", "diff", "--name-status"),
                ("git diff --name-status", "измененные файлы", "изменённые файлы"),
                category="Git: состояние",
            ),
            RemoteCommandSpec(
                "git-fetch",
                "Git: получить origin",
                ("git", "fetch", "origin", "--prune"),
                ("git fetch", "git fetch origin", "git fetch origin --prune"),
                timeout_seconds=180,
                category="Git: синхронизация",
            ),
            RemoteCommandSpec(
                "git-sync-count",
                "Git: отставание и опережение main",
                ("git", "rev-list", "--left-right", "--count", "HEAD...origin/main"),
                (
                    "git rev-list --left-right --count head...origin/main",
                    "сравнить с origin main",
                ),
                category="Git: синхронизация",
            ),
            RemoteCommandSpec(
                "git-incoming",
                "Git: входящие commit из origin/main",
                ("git", "log", "--oneline", "HEAD..origin/main"),
                ("git log --oneline head..origin/main", "входящие коммиты"),
                category="Git: синхронизация",
            ),
            RemoteCommandSpec(
                "git-outgoing",
                "Git: локальные commit вне origin/main",
                ("git", "log", "--oneline", "origin/main..HEAD"),
                ("git log --oneline origin/main..head", "исходящие коммиты"),
                category="Git: синхронизация",
            ),
            RemoteCommandSpec(
                "git-origin-diff-stat",
                "Git: разница HEAD и origin/main",
                ("git", "diff", "--stat", "HEAD", "origin/main"),
                ("git diff --stat head origin/main", "разница с origin main"),
                category="Git: синхронизация",
            ),
            RemoteCommandSpec(
                "git-clean-preview",
                "Git: показать удаляемые неотслеживаемые файлы",
                ("git", "clean", "-nd"),
                ("git clean -nd", "предпросмотр очистки git"),
                category="Git: восстановление",
            ),
            RemoteCommandSpec(
                "git-stash-list",
                "Git: список сохранённых изменений",
                ("git", "stash", "list"),
                ("git stash list", "список stash"),
                category="Git: восстановление",
            ),
            RemoteCommandSpec(
                "git-stash-save-all",
                "Git: временно сохранить все локальные изменения",
                (
                    "git",
                    "stash",
                    "push",
                    "--include-untracked",
                    "-m",
                    "Supervisor emergency stash",
                ),
                (
                    'git stash push --include-untracked -m "supervisor emergency stash"',
                    "сохранить локальные изменения",
                    "аварийный stash",
                ),
                timeout_seconds=180,
                category="Git: восстановление",
            ),
            RemoteCommandSpec(
                "git-stash-show",
                "Git: содержимое последнего stash",
                ("git", "stash", "show", "--stat", "stash@{0}"),
                ("git stash show --stat stash@{0}", "показать последний stash"),
                category="Git: восстановление",
            ),
            RemoteCommandSpec(
                "git-stash-pop",
                "Git: вернуть последний stash",
                ("git", "stash", "pop"),
                ("git stash pop", "вернуть последний stash"),
                timeout_seconds=180,
                category="Git: восстановление",
            ),
            RemoteCommandSpec(
                "git-clean-krita-bridge",
                "Git: удалить локальный ZIP-мост Krita",
                (
                    "git",
                    "clean",
                    "-f",
                    "--",
                    "tools/krita/Velvet_Anatomy_Krita_Plugin_bridge.zip",
                ),
                (
                    "git clean -f -- tools/krita/Velvet_Anatomy_Krita_Plugin_bridge.zip",
                    "удалить локальный zip-мост krita",
                    "очистить zip krita",
                ),
                category="Git: восстановление",
            ),
            RemoteCommandSpec(
                "python-version",
                "Версия Python",
                (python, "--version"),
                ("python --version", "python -v", "версия python"),
                category="Проверки",
            ),
            RemoteCommandSpec(
                "pip-check",
                "Проверить зависимости Python",
                (python, "-m", "pip", "check"),
                ("python -m pip check", "pip check", "проверить зависимости"),
                timeout_seconds=180,
                category="Проверки",
            ),
            RemoteCommandSpec(
                "compile",
                "Проверить синтаксис проекта",
                (python, "-m", "compileall", "-q", "velvet_bot", "velvet_supervisor"),
                (
                    "python -m compileall -q velvet_bot velvet_supervisor",
                    "compileall",
                    "проверить синтаксис",
                ),
                timeout_seconds=180,
                category="Проверки",
            ),
            RemoteCommandSpec(
                "tests",
                "Запустить тесты проекта",
                settings.test_command,
                ("tests", "pytest", "unittest", "запустить тесты"),
                timeout_seconds=settings.command_timeout_seconds,
                category="Проверки",
            ),
            RemoteCommandSpec(
                "ollama-list",
                "Ollama: список моделей",
                ("ollama", "list"),
                ("ollama list", "модели ollama"),
                timeout_seconds=60,
                category="AI: Ollama",
            ),
            RemoteCommandSpec(
                "ollama-recovery-status",
                "Ollama: состояние набора моделей",
                (python, "-m", "velvet_supervisor.ollama_recovery", "status"),
                (
                    "ollama recovery status",
                    "состояние ollama vision",
                    "состояние набора ollama",
                ),
                timeout_seconds=30,
                category="AI: Ollama",
            ),
            RemoteCommandSpec(
                "ollama-start",
                "Ollama: запустить локальный сервер",
                (python, "-m", "velvet_supervisor.ollama_recovery", "start"),
                ("ollama start", "запустить ollama"),
                timeout_seconds=60,
                category="AI: Ollama",
            ),
            RemoteCommandSpec(
                "ollama-configure-qwen3-vl-4b",
                "Ollama: настроить набор моделей",
                (python, "-m", "velvet_supervisor.ollama_recovery", "configure"),
                (
                    "ollama configure qwen3-vl 4b",
                    "настроить qwen3 vl 4b",
                    "настроить набор ollama",
                ),
                timeout_seconds=30,
                category="AI: Ollama",
            ),
            RemoteCommandSpec(
                "ollama-pull-qwen3-vl-4b",
                "Ollama: установить набор моделей",
                (python, "-m", "velvet_supervisor.ollama_recovery", "pull"),
                (
                    "ollama pull qwen3-vl:4b",
                    "скачать qwen3 vl 4b",
                    "установить набор ollama",
                ),
                timeout_seconds=_OLLAMA_BUNDLE_TIMEOUT_SECONDS,
                category="AI: Ollama",
                enforce_global_timeout=False,
            ),
            RemoteCommandSpec(
                "ollama-show-qwen3-vl-4b",
                "Ollama: проверить набор моделей",
                (python, "-m", "velvet_supervisor.ollama_recovery", "show"),
                (
                    "ollama show qwen3-vl:4b",
                    "проверить qwen3 vl 4b",
                    "проверить набор ollama",
                ),
                timeout_seconds=120,
                category="AI: Ollama",
            ),
            RemoteCommandSpec(
                "ollama-repair-qwen3-vl-4b",
                "Ollama: восстановить набор моделей",
                (python, "-m", "velvet_supervisor.ollama_recovery", "repair"),
                (
                    "ollama repair qwen3-vl:4b",
                    "восстановить ollama vision",
                    "восстановить набор ollama",
                ),
                timeout_seconds=_OLLAMA_BUNDLE_TIMEOUT_SECONDS,
                category="AI: Ollama",
                enforce_global_timeout=False,
            ),
            RemoteCommandSpec(
                "task-status",
                "Состояние задачи VelvetSupervisor",
                (
                    "schtasks.exe",
                    "/Query",
                    "/TN",
                    task_name or "VelvetSupervisor",
                    "/V",
                    "/FO",
                    "LIST",
                ),
                (
                    "schtasks /query /tn velvetsupervisor /v /fo list",
                    "task status",
                    "статус задачи supervisor",
                ),
                category="Система",
            ),
            RemoteCommandSpec(
                "python-processes",
                "Процессы Python",
                ("tasklist.exe", "/FI", "IMAGENAME eq python.exe", "/FO", "LIST"),
                ("tasklist python", "python processes", "процессы python"),
                category="Система",
            ),
            RemoteCommandSpec(
                "hostname",
                "Имя компьютера",
                ("hostname.exe",),
                ("hostname", "имя компьютера"),
                category="Система",
            ),
            RemoteCommandSpec(
                "network-config",
                "Сетевые адреса компьютера",
                ("ipconfig.exe",),
                ("ipconfig", "сеть", "сетевые адреса"),
                category="Система",
            ),
            RemoteCommandSpec(
                "disk-volumes",
                "Свободное место на дисках",
                (
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Get-Volume",
                ),
                (
                    "powershell -noprofile -noninteractive -command get-volume",
                    "свободное место",
                ),
                category="Система",
            ),
        )
        self._by_key = {spec.key: spec for spec in specs}
        self._by_alias: dict[str, RemoteCommandSpec] = {}
        for spec in specs:
            self._by_alias[_normalize(spec.key)] = spec
            self._by_alias[_normalize(subprocess.list2cmdline(spec.command))] = spec
            for alias in spec.aliases:
                self._by_alias[_normalize(alias)] = spec

    def catalog(self) -> tuple[RemoteCommandSpec, ...]:
        return tuple(self._by_key.values())

    def resolve(self, value: str, *, by_key: bool = False) -> RemoteCommandSpec:
        cleaned = value.strip()
        if not cleaned:
            raise RemoteCommandRejected("Команда не указана.")
        if len(cleaned) > _MAX_INPUT_LENGTH:
            raise RemoteCommandRejected("Команда слишком длинная.")
        if _FORBIDDEN_INPUT_RE.search(cleaned):
            raise RemoteCommandRejected(
                "Конвейеры, перенаправления, разделители и подстановка команд запрещены."
            )
        spec = self._by_key.get(cleaned) if by_key else self._by_alias.get(_normalize(cleaned))
        if spec is None:
            raise RemoteCommandRejected(
                "Команда отсутствует в безопасном реестре Supervisor. "
                "Используйте кнопки списка команд."
            )
        return spec

    def execute(self, key: str) -> dict[str, object]:
        spec = self.resolve(key, by_key=True)
        started = time.monotonic()
        effective_timeout = max(5, spec.timeout_seconds)
        if spec.enforce_global_timeout:
            effective_timeout = min(
                effective_timeout,
                self._settings.command_timeout_seconds,
            )
        try:
            completed = subprocess.run(
                list(spec.command),
                cwd=str(self._settings.project_dir),
                env=_child_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=effective_timeout,
                shell=False,
                check=False,
            )
            output: str | bytes = completed.stdout or ""
            returncode = int(completed.returncode)
        except FileNotFoundError as error:
            output = f"Исполняемый файл не найден: {error.filename or spec.command[0]}"
            returncode = 127
        except subprocess.TimeoutExpired as error:
            raw = error.stdout or ""
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            output = f"Команда превысила таймаут {effective_timeout} сек.\n{raw}"
            returncode = 124

        secrets = (
            self._settings.api_token,
            self._settings.notification_bot_token or "",
            os.getenv("BOT_TOKEN", ""),
            os.getenv("DATABASE_URL", ""),
        )
        safe_output = _redact(str(output), secrets)[-_MAX_OUTPUT_LENGTH:]
        result: dict[str, object] = {
            "command_key": spec.key,
            "title": spec.title,
            "command": subprocess.list2cmdline(spec.command),
            "returncode": returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "output": safe_output,
        }
        if returncode:
            raise RemoteCommandFailed(
                f"Команда завершилась с кодом {returncode}.",
                result,
            )
        return result


__all__ = (
    "RemoteCommandFailed",
    "RemoteCommandRegistry",
    "RemoteCommandRejected",
    "RemoteCommandSpec",
)
