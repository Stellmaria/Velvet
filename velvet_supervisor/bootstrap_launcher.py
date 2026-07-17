from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from .bootstrap import (
    BootstrapLaunch,
    _acquire_lock,
    _delete_task,
    _release_lock,
    _resolved_python,
    _run,
)
from .config import SupervisorSettings

_ALLOWED_ACTIONS = {"restart", "update"}


def launch_bootstrap_short(
    settings: SupervisorSettings,
    *,
    action: str,
    operation_id: str,
    supervisor_pid: int,
    bot_pid: int | None,
) -> BootstrapLaunch:
    """Launch bootstrap through a tiny .cmd action to avoid schtasks /TR limits."""

    if action not in _ALLOWED_ACTIONS:
        raise ValueError("Неизвестное действие bootstrap.")
    if os.name != "nt":
        raise RuntimeError("Удалённый перезапуск самого Supervisor доступен только на Windows.")

    main_task = os.getenv("SUPERVISOR_TASK_NAME", "VelvetSupervisor").strip() or "VelvetSupervisor"
    bootstrap_task = f"VelvetSupervisorBootstrap-{operation_id}"
    command = (
        _resolved_python(settings),
        "-m",
        "velvet_supervisor.bootstrap",
        "--action",
        action,
        "--project-dir",
        str(settings.project_dir),
        "--operation-id",
        operation_id,
        "--main-task",
        main_task,
        "--bootstrap-task",
        bootstrap_task,
        "--supervisor-pid",
        str(supervisor_pid),
        "--bot-pid",
        str(bot_pid or 0),
    )

    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    wrapper = settings.runtime_dir / f"bootstrap-{operation_id}.cmd"
    wrapper.write_text(
        "@echo off\r\n"
        f'cd /d "{settings.project_dir}"\r\n'
        f"{subprocess.list2cmdline(command)}\r\n"
        'set "VELVET_BOOTSTRAP_EXIT=%ERRORLEVEL%"\r\n'
        'del "%~f0" >nul 2>&1\r\n'
        'exit /b %VELVET_BOOTSTRAP_EXIT%\r\n',
        encoding="utf-8",
    )

    # Task Scheduler limits /TR to roughly 261 characters. It now receives only
    # `cmd.exe /c <short wrapper>`, while the long argument list lives in the file.
    task_action = subprocess.list2cmdline(
        ("cmd.exe", "/d", "/s", "/c", str(wrapper))
    )
    if len(task_action) > 240:
        wrapper.unlink(missing_ok=True)
        raise RuntimeError(
            "Путь runtime слишком длинный даже для короткого bootstrap wrapper."
        )

    start_at = datetime.now() + timedelta(minutes=2)
    create = (
        "schtasks.exe",
        "/Create",
        "/TN",
        bootstrap_task,
        "/TR",
        task_action,
        "/SC",
        "ONCE",
        "/ST",
        start_at.strftime("%H:%M"),
        "/RL",
        "LIMITED",
        "/F",
    )

    _acquire_lock(settings, operation_id)
    try:
        _run(create, cwd=settings.project_dir, timeout=30)
        _run(
            ("schtasks.exe", "/Run", "/TN", bootstrap_task),
            cwd=settings.project_dir,
            timeout=30,
        )
    except Exception:
        _delete_task(bootstrap_task, cwd=settings.project_dir)
        wrapper.unlink(missing_ok=True)
        _release_lock(settings)
        raise

    return BootstrapLaunch(
        operation_id=operation_id,
        action=action,
        task_name=bootstrap_task,
        command=command,
    )


__all__ = ("launch_bootstrap_short",)
