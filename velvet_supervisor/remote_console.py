from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
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
_MAX_INPUT_LENGTH = 300
_MAX_OUTPUT_LENGTH = 20_000


@dataclass(frozen=True, slots=True)
class RemoteCommandSpec:
    key: str
    title: str
    command: tuple[str, ...]
    aliases: tuple[str, ...]
    timeout_seconds: int = 60
    category: str = "Диагностика"

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


def _redact(value: str, secret_values: Iterable[str] = ()) -> str:
    result = value
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

    No user text is ever passed to a shell. A user message only resolves to one
    predefined argv tuple. This keeps a stolen Telegram session from becoming
    an unrestricted Windows terminal.
    """

    def __init__(self, settings: SupervisorSettings) -> None:
        self._settings = settings
        task_name = os.getenv("SUPERVISOR_TASK_NAME", "VelvetSupervisor").strip()
        python = settings.python_executable
        specs = (
            RemoteCommandSpec(
                key="git-status",
                title="Git: локальные изменения",
                command=("git", "status", "--short"),
                aliases=("git status", "git status --short", "статус git"),
                category="Git",
            ),
            RemoteCommandSpec(
                key="git-head",
                title="Git: текущий commit",
                command=("git", "rev-parse", "--short", "HEAD"),
                aliases=("git rev-parse --short head", "git head", "текущий commit"),
                category="Git",
            ),
            RemoteCommandSpec(
                key="git-log",
                title="Git: последние пять commit",
                command=("git", "log", "-5", "--oneline"),
                aliases=("git log -5 --oneline", "git log", "последние коммиты"),
                category="Git",
            ),
            RemoteCommandSpec(
                key="git-fetch",
                title="Git: получить origin",
                command=("git", "fetch", "origin"),
                aliases=("git fetch", "git fetch origin"),
                timeout_seconds=180,
                category="Git",
            ),
            RemoteCommandSpec(
                key="python-version",
                title="Версия Python",
                command=(python, "--version"),
                aliases=("python --version", "python -v", "версия python"),
            ),
            RemoteCommandSpec(
                key="compile",
                title="Проверить синтаксис проекта",
                command=(
                    python,
                    "-m",
                    "compileall",
                    "-q",
                    "velvet_bot",
                    "velvet_supervisor",
                ),
                aliases=(
                    "python -m compileall -q velvet_bot velvet_supervisor",
                    "compileall",
                    "проверить синтаксис",
                ),
                timeout_seconds=180,
                category="Проверки",
            ),
            RemoteCommandSpec(
                key="tests",
                title="Запустить тесты проекта",
                command=settings.test_command,
                aliases=("tests", "pytest", "unittest", "запустить тесты"),
                timeout_seconds=settings.command_timeout_seconds,
                category="Проверки",
            ),
            RemoteCommandSpec(
                key="ollama-list",
                title="Список моделей Ollama",
                command=("ollama", "list"),
                aliases=("ollama list", "модели ollama"),
                timeout_seconds=60,
                category="AI",
            ),
            RemoteCommandSpec(
                key="task-status",
                title="Состояние задачи VelvetSupervisor",
                command=(
                    "schtasks.exe",
                    "/Query",
                    "/TN",
                    task_name or "VelvetSupervisor",
                    "/V",
                    "/FO",
                    "LIST",
                ),
                aliases=(
                    "schtasks /query /tn velvetsupervisor /v /fo list",
                    "task status",
                    "статус задачи supervisor",
                ),
                category="Supervisor",
            ),
            RemoteCommandSpec(
                key="python-processes",
                title="Процессы Python",
                command=(
                    "tasklist.exe",
                    "/FI",
                    "IMAGENAME eq python.exe",
                    "/FO",
                    "LIST",
                ),
                aliases=("tasklist python", "python processes", "процессы python"),
                category="Supervisor",
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
                timeout=max(5, min(spec.timeout_seconds, self._settings.command_timeout_seconds)),
                shell=False,
                check=False,
            )
            output = completed.stdout or ""
            returncode = int(completed.returncode)
        except FileNotFoundError as error:
            output = f"Исполняемый файл не найден: {error.filename or spec.command[0]}"
            returncode = 127
        except subprocess.TimeoutExpired as error:
            raw = error.stdout or ""
            output = f"Команда превысила таймаут {spec.timeout_seconds} сек.\n{raw}"
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
