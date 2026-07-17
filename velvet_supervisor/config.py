from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path

from dotenv import load_dotenv


def _parse_bool(value: str, *, name: str, default: bool) -> bool:
    cleaned = value.strip().casefold()
    if not cleaned:
        return default
    if cleaned in {"1", "true", "yes", "on", "да"}:
        return True
    if cleaned in {"0", "false", "no", "off", "нет"}:
        return False
    raise RuntimeError(f"{name} должен быть true/false, yes/no, on/off или 1/0.")


def _parse_int(
    value: str,
    *,
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    cleaned = value.strip()
    if not cleaned:
        return default
    try:
        result = int(cleaned)
    except ValueError as error:
        raise RuntimeError(f"{name} должен быть целым числом.") from error
    if not minimum <= result <= maximum:
        raise RuntimeError(f"{name} должен быть от {minimum} до {maximum}.")
    return result


def _split_command(value: str, *, name: str) -> tuple[str, ...]:
    cleaned = value.strip()
    if not cleaned:
        raise RuntimeError(f"{name} не может быть пустым.")
    try:
        result = tuple(shlex.split(cleaned, posix=True))
    except ValueError as error:
        raise RuntimeError(f"{name} содержит некорректные кавычки.") from error
    if not result:
        raise RuntimeError(f"{name} не может быть пустым.")
    return result


def _safe_path(value: str, *, base: Path) -> Path:
    result = Path(value.strip() or ".")
    if not result.is_absolute():
        result = base / result
    return result.resolve()


@dataclass(frozen=True, slots=True)
class SupervisorSettings:
    project_dir: Path
    host: str
    port: int
    api_token: str
    python_executable: str
    bot_command: tuple[str, ...]
    test_command: tuple[str, ...]
    logs_dir: Path
    runtime_dir: Path
    auto_restart: bool
    max_restarts: int
    restart_window_seconds: int
    startup_grace_seconds: int
    command_timeout_seconds: int
    update_remote: str
    update_branch: str
    notification_bot_token: str | None
    notification_chat_id: int | None
    codex_enabled: bool
    codex_command: tuple[str, ...]
    codex_timeout_seconds: int
    codex_worktree_dir: Path
    codex_push_remote: str
    max_log_lines: int
    codex_model: str | None = None

    @classmethod
    def load(cls) -> "SupervisorSettings":
        initial_dir = Path(os.getenv("SUPERVISOR_PROJECT_DIR", ".")).resolve()
        load_dotenv(initial_dir / ".env")
        project_dir = Path(os.getenv("SUPERVISOR_PROJECT_DIR", str(initial_dir))).resolve()
        load_dotenv(project_dir / ".env", override=False)

        host = os.getenv("SUPERVISOR_HOST", "127.0.0.1").strip() or "127.0.0.1"
        allow_remote = _parse_bool(
            os.getenv("SUPERVISOR_ALLOW_REMOTE", "false"),
            name="SUPERVISOR_ALLOW_REMOTE",
            default=False,
        )
        try:
            parsed_host = ip_address(host)
        except ValueError:
            parsed_host = None
        if not allow_remote and parsed_host is not None and not parsed_host.is_loopback:
            raise RuntimeError(
                "SUPERVISOR_HOST должен быть loopback-адресом. "
                "Для внешнего интерфейса явно задайте SUPERVISOR_ALLOW_REMOTE=true."
            )
        if not allow_remote and host.casefold() not in {"localhost"} and parsed_host is None:
            raise RuntimeError(
                "SUPERVISOR_HOST должен быть localhost или loopback IP, "
                "если SUPERVISOR_ALLOW_REMOTE=false."
            )

        api_token = os.getenv("SUPERVISOR_TOKEN", "").strip()
        if len(api_token) < 24:
            raise RuntimeError(
                "SUPERVISOR_TOKEN должен быть задан в .env и содержать минимум 24 символа."
            )

        python_executable = os.getenv(
            "SUPERVISOR_PYTHON",
            sys.executable,
        ).strip() or sys.executable
        default_bot_command = f'"{python_executable}" main.py'
        default_test_command = (
            f'"{python_executable}" -m unittest discover -s tests -v'
        )

        notification_chat_raw = os.getenv(
            "SUPERVISOR_NOTIFICATION_CHAT_ID",
            os.getenv("LOG_CHAT_ID", ""),
        ).strip()
        notification_chat_id: int | None
        if notification_chat_raw:
            try:
                notification_chat_id = int(notification_chat_raw)
            except ValueError as error:
                raise RuntimeError(
                    "SUPERVISOR_NOTIFICATION_CHAT_ID должен быть числовым Telegram chat ID."
                ) from error
        else:
            notification_chat_id = None

        runtime_dir = _safe_path(
            os.getenv("SUPERVISOR_RUNTIME_DIR", "runtime/supervisor"),
            base=project_dir,
        )

        return cls(
            project_dir=project_dir,
            host=host,
            port=_parse_int(
                os.getenv("SUPERVISOR_PORT", "8765"),
                name="SUPERVISOR_PORT",
                default=8765,
                minimum=1024,
                maximum=65535,
            ),
            api_token=api_token,
            python_executable=python_executable,
            bot_command=_split_command(
                os.getenv("SUPERVISOR_BOT_COMMAND", default_bot_command),
                name="SUPERVISOR_BOT_COMMAND",
            ),
            test_command=_split_command(
                os.getenv("SUPERVISOR_TEST_COMMAND", default_test_command),
                name="SUPERVISOR_TEST_COMMAND",
            ),
            logs_dir=_safe_path(
                os.getenv("SUPERVISOR_LOG_DIR", "logs"),
                base=project_dir,
            ),
            runtime_dir=runtime_dir,
            auto_restart=_parse_bool(
                os.getenv("SUPERVISOR_AUTO_RESTART", "true"),
                name="SUPERVISOR_AUTO_RESTART",
                default=True,
            ),
            max_restarts=_parse_int(
                os.getenv("SUPERVISOR_MAX_RESTARTS", "3"),
                name="SUPERVISOR_MAX_RESTARTS",
                default=3,
                minimum=1,
                maximum=20,
            ),
            restart_window_seconds=_parse_int(
                os.getenv("SUPERVISOR_RESTART_WINDOW_SECONDS", "600"),
                name="SUPERVISOR_RESTART_WINDOW_SECONDS",
                default=600,
                minimum=30,
                maximum=86400,
            ),
            startup_grace_seconds=_parse_int(
                os.getenv("SUPERVISOR_STARTUP_GRACE_SECONDS", "12"),
                name="SUPERVISOR_STARTUP_GRACE_SECONDS",
                default=12,
                minimum=2,
                maximum=300,
            ),
            command_timeout_seconds=_parse_int(
                os.getenv("SUPERVISOR_COMMAND_TIMEOUT_SECONDS", "900"),
                name="SUPERVISOR_COMMAND_TIMEOUT_SECONDS",
                default=900,
                minimum=30,
                maximum=7200,
            ),
            update_remote=os.getenv("SUPERVISOR_UPDATE_REMOTE", "origin").strip()
            or "origin",
            update_branch=os.getenv("SUPERVISOR_UPDATE_BRANCH", "main").strip()
            or "main",
            notification_bot_token=(
                os.getenv("SUPERVISOR_NOTIFICATION_BOT_TOKEN", "").strip()
                or os.getenv("BOT_TOKEN", "").strip()
                or None
            ),
            notification_chat_id=notification_chat_id,
            codex_enabled=_parse_bool(
                os.getenv("CODEX_ENABLED", "false"),
                name="CODEX_ENABLED",
                default=False,
            ),
            codex_command=_split_command(
                os.getenv(
                    "CODEX_COMMAND",
                    "codex exec --json --sandbox workspace-write -",
                ),
                name="CODEX_COMMAND",
            ),
            codex_timeout_seconds=_parse_int(
                os.getenv("CODEX_TIMEOUT_SECONDS", "1800"),
                name="CODEX_TIMEOUT_SECONDS",
                default=1800,
                minimum=60,
                maximum=14400,
            ),
            codex_worktree_dir=_safe_path(
                os.getenv(
                    "CODEX_WORKTREE_DIR",
                    str(runtime_dir / "codex-worktrees"),
                ),
                base=project_dir,
            ),
            codex_push_remote=os.getenv("CODEX_PUSH_REMOTE", "origin").strip()
            or "origin",
            max_log_lines=_parse_int(
                os.getenv("SUPERVISOR_MAX_LOG_LINES", "2000"),
                name="SUPERVISOR_MAX_LOG_LINES",
                default=2000,
                minimum=200,
                maximum=20000,
            ),
            codex_model=(
                os.getenv("CODEX_MODEL", "gpt-5.3-codex").strip() or None
            ),
        )


__all__ = ("SupervisorSettings",)
