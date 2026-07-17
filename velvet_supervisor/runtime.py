from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable

from .codex import CodexTaskManager
from .config import SupervisorSettings
from .git_ops import GitRepository
from .models import JsonStateStore, OperationState, iso_or_none, utc_now
from .notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class OperationConflict(RuntimeError):
    pass


class VelvetSupervisor:
    def __init__(self, settings: SupervisorSettings) -> None:
        self.settings = settings
        self.settings.logs_dir.mkdir(parents=True, exist_ok=True)
        self.settings.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._monitor_thread: threading.Thread | None = None
        self._desired_running = True
        self._started_at = utc_now()
        self._child_started_at: datetime | None = None
        self._last_exit_at: datetime | None = None
        self._last_exit_code: int | None = None
        self._restart_times: deque[float] = deque()
        self._crash_loop_open = False
        self._tail: deque[str] = deque(maxlen=settings.max_log_lines)
        self._last_error_notice: dict[str, float] = {}
        self._last_operation: OperationState | None = None
        self._state_store = JsonStateStore(settings.runtime_dir / "state.json")
        self._state = self._state_store.load()
        self._child_logger = _build_child_logger(settings.logs_dir)
        self._notifier = TelegramNotifier(
            settings.notification_bot_token,
            settings.notification_chat_id,
        )
        self._repository = GitRepository(
            settings.project_dir,
            timeout_seconds=settings.command_timeout_seconds,
            test_command=settings.test_command,
        )
        self.codex = CodexTaskManager(
            settings=settings,
            repository=self._repository,
            notifier=self._notifier,
        )

    def start(self) -> None:
        with self._lock:
            self._start_child_locked(reason="supervisor-start")
            if self._monitor_thread is None:
                self._monitor_thread = threading.Thread(
                    target=self._monitor_loop,
                    name="velvet-supervisor-monitor",
                    daemon=True,
                )
                self._monitor_thread.start()
        self._notifier.send(
            "Velvet Supervisor запущен",
            (
                f"PID Supervisor: {os.getpid()}\n"
                f"Проект: {self.settings.project_dir}\n"
                f"API: {self.settings.host}:{self.settings.port}"
            ),
            level="SUCCESS",
        )

    def shutdown(self) -> None:
        self._stop_event.set()
        self._desired_running = False
        self._stop_child()
        self._notifier.send(
            "Velvet Supervisor остановлен",
            f"PID Supervisor: {os.getpid()}",
            level="WARNING",
        )

    def _start_child_locked(self, *, reason: str) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        command = self.settings.bot_command
        self._child_logger.info(
            "Starting Velvet Bot reason=%s command=%s",
            reason,
            subprocess.list2cmdline(command),
        )
        process = subprocess.Popen(
            command,
            cwd=str(self.settings.project_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=_child_environment(),
        )
        self._process = process
        self._child_started_at = utc_now()
        self._last_exit_code = None
        self._reader_thread = threading.Thread(
            target=self._read_child_output,
            args=(process,),
            name=f"velvet-log-reader:{process.pid}",
            daemon=True,
        )
        self._reader_thread.start()

    def _read_child_output(self, process: subprocess.Popen[str]) -> None:
        stream = process.stdout
        if stream is None:
            return
        for raw_line in iter(stream.readline, ""):
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            with self._lock:
                self._tail.append(line)
            self._child_logger.info("%s", line)
            if _looks_like_error(line):
                self._schedule_error_notice(line)
        stream.close()

    def _schedule_error_notice(self, seed: str) -> None:
        key = seed[-300:].casefold()
        now = time.monotonic()
        with self._lock:
            previous = self._last_error_notice.get(key, 0.0)
            if now - previous < 600:
                return
            self._last_error_notice[key] = now
        timer = threading.Timer(1.0, self._send_error_tail, args=(seed,))
        timer.daemon = True
        timer.start()

    def _send_error_tail(self, seed: str) -> None:
        body = "\n".join(self.log_tail(35))
        self._notifier.send(
            "Ошибка в логах Velvet Bot",
            body or seed,
            level="ERROR",
        )

    def _monitor_loop(self) -> None:
        while not self._stop_event.wait(1.0):
            restart_delay: float | None = None
            exit_code: int | None = None
            with self._lock:
                process = self._process
                if process is None:
                    continue
                exit_code = process.poll()
                if exit_code is None:
                    continue
                self._process = None
                self._last_exit_code = int(exit_code)
                self._last_exit_at = utc_now()
                self._child_logger.error(
                    "Velvet Bot exited code=%s desired_running=%s",
                    exit_code,
                    self._desired_running,
                )
                if self._desired_running and self.settings.auto_restart:
                    restart_delay = self._register_crash_locked()
            tail = "\n".join(self.log_tail(50))
            self._notifier.send(
                "Velvet Bot остановлен",
                (
                    f"Код завершения: {exit_code}\n"
                    f"Автоперезапуск: "
                    f"{'ожидается' if restart_delay is not None else 'остановлен'}\n\n"
                    f"{tail[-2800:]}"
                ),
                level="ERROR",
            )
            if restart_delay is not None:
                if self._stop_event.wait(restart_delay):
                    return
                with self._lock:
                    if self._desired_running and self._process is None:
                        self._start_child_locked(reason="automatic-restart")
                        pid = self._process.pid if self._process else None
                    else:
                        pid = None
                if pid:
                    self._notifier.send(
                        "Velvet Bot перезапущен",
                        f"Новый PID: {pid}",
                        level="SUCCESS",
                    )

    def _register_crash_locked(self) -> float | None:
        now = time.monotonic()
        window_start = now - self.settings.restart_window_seconds
        while self._restart_times and self._restart_times[0] < window_start:
            self._restart_times.popleft()
        if len(self._restart_times) >= self.settings.max_restarts:
            self._crash_loop_open = True
            return None
        self._restart_times.append(now)
        self._crash_loop_open = False
        return min(30.0, 2.0 * len(self._restart_times))

    def _stop_child(self, *, timeout: float = 20.0) -> None:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                self._process = None
                return
            process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        with self._lock:
            if self._process is process:
                self._process = None
            self._last_exit_code = process.returncode
            self._last_exit_at = utc_now()

    def log_tail(self, lines: int = 200) -> list[str]:
        safe_lines = max(1, min(int(lines), self.settings.max_log_lines))
        with self._lock:
            return list(self._tail)[-safe_lines:]

    def status(self) -> dict[str, Any]:
        with self._lock:
            process = self._process
            running = bool(process is not None and process.poll() is None)
            pid = process.pid if running and process is not None else None
            operation = self._last_operation.to_dict() if self._last_operation else None
            child_started_at = self._child_started_at
            last_exit_at = self._last_exit_at
            crash_count = len(self._restart_times)
        try:
            git_payload: dict[str, Any] = {
                "branch": self._repository.branch_name(),
                "head_sha": self._repository.head_sha(),
                "dirty": bool(self._repository.status_porcelain()),
            }
        except Exception as error:
            git_payload = {"error": str(error)}
        return {
            "supervisor": {
                "pid": os.getpid(),
                "started_at": iso_or_none(self._started_at),
                "host": self.settings.host,
                "port": self.settings.port,
            },
            "bot": {
                "running": running,
                "pid": pid,
                "started_at": iso_or_none(child_started_at),
                "last_exit_at": iso_or_none(last_exit_at),
                "last_exit_code": self._last_exit_code,
                "desired_running": self._desired_running,
                "auto_restart": self.settings.auto_restart,
                "crash_loop_open": self._crash_loop_open,
                "restart_count_in_window": crash_count,
                "restart_limit": self.settings.max_restarts,
                "restart_window_seconds": self.settings.restart_window_seconds,
            },
            "git": git_payload,
            "operation": operation,
            "codex": {
                "enabled": self.settings.codex_enabled,
                "recent_tasks": self.codex.list_tasks(limit=5),
            },
        }

    def _schedule(
        self,
        kind: str,
        runner: Callable[[OperationState], dict[str, Any] | None],
        *,
        message: str = "",
    ) -> OperationState:
        if not self._operation_lock.acquire(blocking=False):
            raise OperationConflict("Уже выполняется другая системная операция.")
        operation = OperationState.create(kind, message)
        with self._lock:
            self._last_operation = operation

        def execute() -> None:
            try:
                operation.status = "running"
                operation.started_at = utc_now()
                result = runner(operation) or {}
                operation.result = result
                operation.status = "success"
                operation.message = operation.message or "Операция завершена."
            except Exception as error:
                logger.exception("Supervisor operation failed kind=%s", kind)
                operation.status = "error"
                operation.error = str(error)[:10000]
                self._notifier.send(
                    f"Ошибка операции Supervisor: {kind}",
                    str(error)[-3000:],
                    level="ERROR",
                )
            finally:
                operation.finished_at = utc_now()
                self._operation_lock.release()
                self._persist_operation(operation)

        thread = threading.Thread(
            target=execute,
            name=f"supervisor-operation:{kind}:{operation.id}",
            daemon=True,
        )
        thread.start()
        return operation

    def _persist_operation(self, operation: OperationState) -> None:
        with self._lock:
            history = self._state.get("operation_history", [])
            if not isinstance(history, list):
                history = []
            history.append(operation.to_dict())
            self._state["operation_history"] = history[-50:]
            self._state_store.save(self._state)

    def schedule_restart(self) -> OperationState:
        return self._schedule(
            "restart",
            lambda operation: self._restart_operation(operation),
            message="Перезапуск принят.",
        )

    def _restart_operation(self, operation: OperationState) -> dict[str, Any]:
        time.sleep(0.75)
        self._desired_running = False
        self._stop_child()
        with self._lock:
            self._restart_times.clear()
            self._crash_loop_open = False
            self._desired_running = True
            self._start_child_locked(reason="manual-restart")
            pid = self._process.pid if self._process else None
        self._wait_for_stable_child()
        self._notifier.send(
            "Velvet Bot перезапущен вручную",
            f"PID: {pid}\nОперация: {operation.id}",
            level="SUCCESS",
        )
        return {"pid": pid}

    def schedule_update(self) -> OperationState:
        return self._schedule(
            "update",
            lambda operation: self._update_operation(operation),
            message="Обновление принято.",
        )

    def _update_operation(self, operation: OperationState) -> dict[str, Any]:
        self._repository.ensure_clean()
        old_sha = self._repository.head_sha()
        self._repository.fetch(
            self.settings.update_remote,
            self.settings.update_branch,
        )
        self._repository.fast_forward(
            self.settings.update_remote,
            self.settings.update_branch,
        )
        new_sha = self._repository.head_sha()
        if new_sha == old_sha:
            return {"old_sha": old_sha, "new_sha": new_sha, "changed": False}

        test_result = self._repository.run_tests()
        if test_result.returncode:
            self._repository.hard_reset(old_sha)
            raise RuntimeError(
                "Тесты после git update не прошли; код возвращён на предыдущий commit.\n"
                + test_result.output[-5000:]
            )

        self._desired_running = False
        self._stop_child()
        with self._lock:
            self._desired_running = True
            self._start_child_locked(reason="git-update")
        try:
            self._wait_for_stable_child()
        except Exception:
            self._desired_running = False
            self._stop_child()
            self._repository.hard_reset(old_sha)
            with self._lock:
                self._desired_running = True
                self._start_child_locked(reason="automatic-update-rollback")
            self._wait_for_stable_child()
            raise

        self._record_deployment(old_sha=old_sha, new_sha=new_sha, source="update")
        self._notifier.send(
            "Velvet Bot обновлён",
            f"{old_sha[:12]} → {new_sha[:12]}\nОперация: {operation.id}",
            level="SUCCESS",
        )
        return {
            "old_sha": old_sha,
            "new_sha": new_sha,
            "changed": True,
            "test_output_tail": test_result.output[-4000:],
        }

    def schedule_rollback(self, target_sha: str | None = None) -> OperationState:
        return self._schedule(
            "rollback",
            lambda operation: self._rollback_operation(operation, target_sha),
            message="Откат принят.",
        )

    def _rollback_operation(
        self,
        operation: OperationState,
        target_sha: str | None,
    ) -> dict[str, Any]:
        self._repository.ensure_clean()
        current_sha = self._repository.head_sha()
        resolved_target = target_sha or self._last_previous_sha()
        if not resolved_target:
            raise RuntimeError("Нет сохранённого commit для отката.")
        if resolved_target == current_sha:
            return {"old_sha": current_sha, "new_sha": resolved_target, "changed": False}

        self._desired_running = False
        self._stop_child()
        self._repository.hard_reset(resolved_target)
        with self._lock:
            self._desired_running = True
            self._start_child_locked(reason="manual-rollback")
        try:
            self._wait_for_stable_child()
        except Exception:
            self._desired_running = False
            self._stop_child()
            self._repository.hard_reset(current_sha)
            with self._lock:
                self._desired_running = True
                self._start_child_locked(reason="rollback-recovery")
            self._wait_for_stable_child()
            raise
        self._record_deployment(
            old_sha=current_sha,
            new_sha=resolved_target,
            source="rollback",
        )
        self._notifier.send(
            "Velvet Bot откатан",
            f"{current_sha[:12]} → {resolved_target[:12]}\nОперация: {operation.id}",
            level="WARNING",
        )
        return {
            "old_sha": current_sha,
            "new_sha": resolved_target,
            "changed": True,
        }

    def schedule_codex_apply(self, task_id: str) -> OperationState:
        return self._schedule(
            "codex-apply",
            lambda operation: self._codex_apply_operation(operation, task_id),
            message=f"Применение задачи {task_id} принято.",
        )

    def _codex_apply_operation(
        self,
        operation: OperationState,
        task_id: str,
    ) -> dict[str, Any]:
        task = self.codex.get(task_id)
        if task is None:
            raise RuntimeError("Задача Codex не найдена.")
        if task.status != "ready" or not task.branch or not task.base_sha:
            raise RuntimeError("Задача Codex ещё не готова к применению.")
        old_sha = self._repository.head_sha()
        self._repository.merge_codex_commit(task.branch, task.base_sha)
        new_sha = self._repository.head_sha()
        test_result = self._repository.run_tests()
        if test_result.returncode:
            self._repository.hard_reset(old_sha)
            raise RuntimeError(
                "Тесты после применения Codex не прошли; commit отменён.\n"
                + test_result.output[-5000:]
            )

        self._desired_running = False
        self._stop_child()
        with self._lock:
            self._desired_running = True
            self._start_child_locked(reason=f"codex-apply:{task_id}")
        try:
            self._wait_for_stable_child()
        except Exception:
            self._desired_running = False
            self._stop_child()
            self._repository.hard_reset(old_sha)
            with self._lock:
                self._desired_running = True
                self._start_child_locked(reason="codex-apply-rollback")
            self._wait_for_stable_child()
            raise

        self.codex.mark_applied(task_id)
        self.codex.cleanup_after_apply(task_id)
        self._record_deployment(old_sha=old_sha, new_sha=new_sha, source="codex")
        self._notifier.send(
            "Изменения Codex применены",
            f"Задача: {task_id}\nCommit: {new_sha}\nОперация: {operation.id}",
            level="SUCCESS",
        )
        return {
            "task_id": task_id,
            "old_sha": old_sha,
            "new_sha": new_sha,
            "test_output_tail": test_result.output[-4000:],
        }

    def reject_codex_task(self, task_id: str) -> dict[str, Any]:
        task = self.codex.reject(task_id)
        return task.to_dict()

    def schedule_codex_push(self, task_id: str) -> OperationState:
        return self._schedule(
            "codex-push",
            lambda operation: self._codex_push_operation(operation, task_id),
            message=f"Push задачи {task_id} принят.",
        )

    def _codex_push_operation(
        self,
        operation: OperationState,
        task_id: str,
    ) -> dict[str, Any]:
        task = self.codex.get(task_id)
        if task is None:
            raise RuntimeError("Задача Codex не найдена.")
        if task.status != "applied":
            raise RuntimeError("Push разрешён только после применения задачи.")
        output = self._repository.push(
            self.settings.codex_push_remote,
            self.settings.update_branch,
        )
        self.codex.mark_pushed(task_id)
        self._notifier.send(
            "Изменения Codex отправлены в Git",
            f"Задача: {task_id}\nВетка: {self.settings.update_branch}",
            level="SUCCESS",
        )
        return {"task_id": task_id, "output": output[-4000:]}

    def _wait_for_stable_child(self) -> None:
        deadline = time.monotonic() + self.settings.startup_grace_seconds
        while time.monotonic() < deadline:
            with self._lock:
                process = self._process
                if process is None:
                    raise RuntimeError("Процесс Velvet Bot не запущен.")
                code = process.poll()
            if code is not None:
                raise RuntimeError(
                    f"Velvet Bot завершился во время проверки запуска с кодом {code}.\n"
                    + "\n".join(self.log_tail(50))
                )
            time.sleep(0.5)

    def _record_deployment(self, *, old_sha: str, new_sha: str, source: str) -> None:
        with self._lock:
            deployments = self._state.get("deployments", [])
            if not isinstance(deployments, list):
                deployments = []
            deployments.append(
                {
                    "old_sha": old_sha,
                    "new_sha": new_sha,
                    "source": source,
                    "created_at": utc_now().isoformat(),
                }
            )
            self._state["deployments"] = deployments[-30:]
            self._state_store.save(self._state)

    def _last_previous_sha(self) -> str | None:
        with self._lock:
            deployments = self._state.get("deployments", [])
            if not isinstance(deployments, list) or not deployments:
                return None
            value = deployments[-1].get("old_sha")
            return str(value) if value else None


def _child_environment() -> dict[str, str]:
    """Force one encoding contract between the Windows child and Supervisor."""
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def _is_recoverable_polling_disconnect(line: str) -> bool:
    lowered = line.casefold()
    return (
        "aiogram.dispatcher" in lowered
        and "failed to fetch updates" in lowered
        and "telegramnetworkerror" in lowered
        and (
            "serverdisconnectederror" in lowered
            or "server disconnected" in lowered
        )
    )


def _build_child_logger(logs_dir: Path) -> logging.Logger:
    child_logger = logging.getLogger("velvet_supervisor.child")
    child_logger.setLevel(logging.INFO)
    child_logger.propagate = False
    if not child_logger.handlers:
        handler = RotatingFileHandler(
            logs_dir / "velvet.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        )
        child_logger.addHandler(handler)
    return child_logger


def _looks_like_error(line: str) -> bool:
    if _is_recoverable_polling_disconnect(line):
        return False
    lowered = line.casefold()
    return any(
        marker in lowered
        for marker in (
            "traceback (most recent call last)",
            " | error | ",
            " | critical | ",
            "[error]",
            "[critical]",
            "unhandled bot error",
        )
    )


__all__ = (
    "OperationConflict",
    "VelvetSupervisor",
)
