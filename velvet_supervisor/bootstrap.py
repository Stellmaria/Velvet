from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence

from .config import SupervisorSettings
from .notifier import TelegramNotifier

_ALLOWED_ACTIONS = {"restart", "update"}


@dataclass(frozen=True, slots=True)
class BootstrapLaunch:
    operation_id: str
    action: str
    task_name: str
    command: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "action": self.action,
            "task_name": self.task_name,
            "command": subprocess.list2cmdline(self.command),
        }


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: int = 300,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    if check and completed.returncode:
        raise RuntimeError(
            f"Команда завершилась с кодом {completed.returncode}: "
            f"{subprocess.list2cmdline(command)}\n{completed.stdout[-5000:]}"
        )
    return completed


def _result_path(settings: SupervisorSettings) -> Path:
    return settings.runtime_dir / "bootstrap-result.json"


def _write_result(settings: SupervisorSettings, payload: dict[str, object]) -> None:
    path = _result_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_bootstrap_result(runtime_dir: Path) -> dict[str, object] | None:
    try:
        payload = json.loads((runtime_dir / "bootstrap-result.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _terminate_pid(pid: int | None, *, cwd: Path) -> None:
    if not pid or pid <= 0 or pid == os.getpid():
        return
    if os.name == "nt":
        _run(
            ("taskkill.exe", "/PID", str(pid), "/F"),
            cwd=cwd,
            timeout=30,
            check=False,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def _git_head(project_dir: Path) -> str:
    return _run(
        ("git", "rev-parse", "HEAD"),
        cwd=project_dir,
        timeout=30,
    ).stdout.strip()


def _update_project(settings: SupervisorSettings) -> tuple[str, str, str]:
    project_dir = settings.project_dir
    dirty = _run(
        ("git", "status", "--porcelain"),
        cwd=project_dir,
        timeout=30,
    ).stdout.strip()
    if dirty:
        raise RuntimeError(
            "Удалённое обновление Supervisor запрещено: рабочее дерево содержит изменения.\n"
            + dirty[:4000]
        )

    old_sha = _git_head(project_dir)
    _run(("git", "switch", settings.update_branch), cwd=project_dir, timeout=60)
    _run(
        ("git", "fetch", settings.update_remote),
        cwd=project_dir,
        timeout=settings.command_timeout_seconds,
    )
    remote_ref = f"{settings.update_remote}/{settings.update_branch}"
    ancestor = _run(
        ("git", "merge-base", "--is-ancestor", "HEAD", remote_ref),
        cwd=project_dir,
        timeout=30,
        check=False,
    )
    if ancestor.returncode:
        raise RuntimeError(
            "Локальная ветка разошлась с удалённой. Автоматический self-update остановлен."
        )
    _run(
        ("git", "pull", "--ff-only", settings.update_remote, settings.update_branch),
        cwd=project_dir,
        timeout=settings.command_timeout_seconds,
    )
    new_sha = _git_head(project_dir)
    if new_sha == old_sha:
        return old_sha, new_sha, "Изменений нет."

    tests = _run(
        settings.test_command,
        cwd=project_dir,
        timeout=settings.command_timeout_seconds,
        check=False,
    )
    if tests.returncode:
        _run(("git", "reset", "--hard", old_sha), cwd=project_dir, timeout=60)
        raise RuntimeError(
            "Тесты self-update не прошли; восстановлен предыдущий commit.\n"
            + tests.stdout[-5000:]
        )
    return old_sha, new_sha, tests.stdout[-4000:]


def _end_task(task_name: str, *, cwd: Path) -> None:
    if os.name != "nt":
        return
    _run(
        ("schtasks.exe", "/End", "/TN", task_name),
        cwd=cwd,
        timeout=30,
        check=False,
    )


def _run_task(task_name: str, *, cwd: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("Автозапуск Supervisor helper поддерживается только Windows Task Scheduler.")
    _run(
        ("schtasks.exe", "/Run", "/TN", task_name),
        cwd=cwd,
        timeout=30,
    )


def _delete_task(task_name: str, *, cwd: Path) -> None:
    if os.name != "nt":
        return
    _run(
        ("schtasks.exe", "/Delete", "/TN", task_name, "/F"),
        cwd=cwd,
        timeout=30,
        check=False,
    )


def launch_bootstrap(
    settings: SupervisorSettings,
    *,
    action: str,
    operation_id: str,
    supervisor_pid: int,
    bot_pid: int | None,
) -> BootstrapLaunch:
    if action not in _ALLOWED_ACTIONS:
        raise ValueError("Неизвестное действие bootstrap.")
    if os.name != "nt":
        raise RuntimeError("Удалённый перезапуск самого Supervisor доступен только на Windows.")

    main_task = os.getenv("SUPERVISOR_TASK_NAME", "VelvetSupervisor").strip() or "VelvetSupervisor"
    bootstrap_task = f"VelvetSupervisorBootstrap-{operation_id}"
    command = (
        settings.python_executable,
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
    action_text = subprocess.list2cmdline(command)
    start_at = datetime.now() + timedelta(minutes=2)
    create = (
        "schtasks.exe",
        "/Create",
        "/TN",
        bootstrap_task,
        "/TR",
        action_text,
        "/SC",
        "ONCE",
        "/ST",
        start_at.strftime("%H:%M"),
        "/RL",
        "LIMITED",
        "/F",
    )
    _run(create, cwd=settings.project_dir, timeout=30)
    try:
        _run(
            ("schtasks.exe", "/Run", "/TN", bootstrap_task),
            cwd=settings.project_dir,
            timeout=30,
        )
    except Exception:
        _delete_task(bootstrap_task, cwd=settings.project_dir)
        raise
    return BootstrapLaunch(operation_id, action, bootstrap_task, command)


def execute_bootstrap(
    settings: SupervisorSettings,
    *,
    action: str,
    operation_id: str,
    main_task: str,
    bootstrap_task: str,
    supervisor_pid: int,
    bot_pid: int | None,
) -> int:
    notifier = TelegramNotifier(
        settings.notification_bot_token,
        settings.notification_chat_id,
    )
    started_at = datetime.now().astimezone().isoformat()
    payload: dict[str, object] = {
        "operation_id": operation_id,
        "action": action,
        "status": "running",
        "started_at": started_at,
    }
    _write_result(settings, payload)
    time.sleep(3.0)

    try:
        _end_task(main_task, cwd=settings.project_dir)
        _terminate_pid(bot_pid, cwd=settings.project_dir)
        _terminate_pid(supervisor_pid, cwd=settings.project_dir)
        time.sleep(1.5)

        old_sha = _git_head(settings.project_dir)
        new_sha = old_sha
        test_tail = ""
        if action == "update":
            old_sha, new_sha, test_tail = _update_project(settings)

        _run_task(main_task, cwd=settings.project_dir)
        payload.update(
            {
                "status": "success",
                "finished_at": datetime.now().astimezone().isoformat(),
                "old_sha": old_sha,
                "new_sha": new_sha,
                "test_output_tail": test_tail,
            }
        )
        _write_result(settings, payload)
        notifier.send(
            "Velvet Supervisor перезапущен" if action == "restart" else "Velvet Supervisor обновлён и перезапущен",
            (
                f"Операция: {operation_id}\n"
                f"Commit: {old_sha[:12]} → {new_sha[:12]}\n"
                f"Задача: {main_task}"
            ),
            level="SUCCESS",
        )
        return 0
    except Exception as error:
        payload.update(
            {
                "status": "error",
                "finished_at": datetime.now().astimezone().isoformat(),
                "error": str(error)[-10_000:],
            }
        )
        _write_result(settings, payload)
        # Even after an update failure, try to bring the main task back from the
        # restored commit before reporting the incident.
        try:
            _run_task(main_task, cwd=settings.project_dir)
        except Exception as restart_error:
            payload["restart_error"] = str(restart_error)[-5000:]
            _write_result(settings, payload)
        notifier.send(
            "Ошибка удалённого перезапуска Supervisor",
            f"Операция: {operation_id}\nЭтап: {action}\n{str(error)[-3000:]}",
            level="ERROR",
        )
        return 1
    finally:
        _delete_task(bootstrap_task, cwd=settings.project_dir)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Velvet Supervisor bootstrap worker")
    parser.add_argument("--action", choices=sorted(_ALLOWED_ACTIONS), required=True)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--main-task", required=True)
    parser.add_argument("--bootstrap-task", required=True)
    parser.add_argument("--supervisor-pid", type=int, required=True)
    parser.add_argument("--bot-pid", type=int, default=0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project_dir = Path(args.project_dir).resolve()
    os.chdir(project_dir)
    os.environ["SUPERVISOR_PROJECT_DIR"] = str(project_dir)
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    settings = SupervisorSettings.load()
    return execute_bootstrap(
        settings,
        action=args.action,
        operation_id=args.operation_id,
        main_task=args.main_task,
        bootstrap_task=args.bootstrap_task,
        supervisor_pid=args.supervisor_pid,
        bot_pid=args.bot_pid or None,
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "BootstrapLaunch",
    "execute_bootstrap",
    "launch_bootstrap",
    "load_bootstrap_result",
    "main",
)
