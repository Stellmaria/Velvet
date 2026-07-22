from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Any

from .config import SupervisorSettings
from .git_ops import GitRepository
from .models import CodexTask, JsonStateStore, utc_now
from .notifier import TelegramNotifier

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def summarize_codex_failure(error: BaseException) -> str:
    """Return a short actionable message instead of proxy HTML/CSS noise."""

    raw = str(error).strip()
    folded = raw.casefold()
    if "403 forbidden" in folded and (
        "backend-api/codex/responses" in folded or "cf-ray" in folded
    ):
        return (
            "Codex получил 403 Forbidden от ChatGPT до запуска работы с кодом.\n"
            "Вероятная причина: локальная авторизация Codex истекла либо запрос "
            "заблокирован сетью или Cloudflare.\n\n"
            "На компьютере Supervisor выполните `codex --login`, затем "
            "перезапустите Supervisor и повторите задачу. Если вход уже выполнен, "
            "проверьте доступ к chatgpt.com без проблемного VPN или прокси."
        )
    if "<html" in folded or "<!doctype html" in folded:
        return (
            "Codex вернул HTML-страницу вместо API-ответа. Это сетевой или "
            "авторизационный отказ, а не ошибка кода проекта. Повторите вход через "
            "`codex --login` и проверьте соединение."
        )
    compact = " ".join(_HTML_TAG_RE.sub(" ", raw).split())
    return (compact[-3000:] if compact else type(error).__name__)


class CodexTaskManager:
    def __init__(
        self,
        *,
        settings: SupervisorSettings,
        repository: GitRepository,
        notifier: TelegramNotifier,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._notifier = notifier
        self._lock = threading.RLock()
        self._execution_lock = threading.Lock()
        self._store = JsonStateStore(settings.runtime_dir / "codex_tasks.json")
        self._tasks: dict[str, CodexTask] = {}
        self._load()

    def _load(self) -> None:
        payload = self._store.load()
        raw_tasks = payload.get("tasks", [])
        if not isinstance(raw_tasks, list):
            return
        for item in raw_tasks:
            if not isinstance(item, dict):
                continue
            try:
                task = CodexTask.from_dict(item)
            except (KeyError, TypeError, ValueError):
                continue
            if task.status in {"queued", "running", "testing"}:
                task.status = "error"
                task.error = "Supervisor был перезапущен во время выполнения задачи."
                task.finished_at = utc_now()
            self._tasks[task.id] = task
        self._persist()

    def _persist(self) -> None:
        self._store.save(
            {
                "tasks": [
                    task.to_dict(include_large_fields=True)
                    for task in sorted(
                        self._tasks.values(),
                        key=lambda value: value.created_at,
                    )[-100:]
                ]
            }
        )

    def list_tasks(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            tasks = sorted(
                self._tasks.values(),
                key=lambda value: value.created_at,
                reverse=True,
            )[: max(1, min(int(limit), 100))]
            return [task.to_dict() for task in tasks]

    def get(self, task_id: str) -> CodexTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def get_dict(self, task_id: str) -> dict[str, Any] | None:
        task = self.get(task_id)
        return task.to_dict() if task else None

    def create(self, prompt: str, requested_by: str) -> CodexTask:
        if not self._settings.codex_enabled:
            raise RuntimeError(
                "Codex отключён. Задайте CODEX_ENABLED=true после выполнения codex login."
            )
        cleaned = prompt.strip()
        if len(cleaned) < 10:
            raise ValueError("Задача Codex слишком короткая.")
        if len(cleaned) > 8000:
            raise ValueError("Задача Codex не должна превышать 8000 символов.")
        task = CodexTask.create(cleaned, requested_by)
        with self._lock:
            self._tasks[task.id] = task
            self._persist()
        thread = threading.Thread(
            target=self._execute,
            args=(task.id,),
            name=f"codex-task:{task.id}",
            daemon=True,
        )
        thread.start()
        return task

    def _update(self, task_id: str, **changes: Any) -> CodexTask:
        with self._lock:
            task = self._tasks[task_id]
            for name, value in changes.items():
                setattr(task, name, value)
            self._persist()
            return task

    def _execute(self, task_id: str) -> None:
        if not self._execution_lock.acquire(blocking=False):
            self._update(
                task_id,
                status="error",
                error="Уже выполняется другая задача Codex.",
                finished_at=utc_now(),
            )
            return
        try:
            self._execute_locked(task_id)
        finally:
            self._execution_lock.release()

    def _execute_locked(self, task_id: str) -> None:
        task = self.get(task_id)
        if task is None:
            return
        worktree = self._settings.codex_worktree_dir / task.id
        try:
            self._update(task_id, status="running", started_at=utc_now())
            base_sha, branch = self._repository.create_worktree(task.id, worktree)
            self._update(
                task_id,
                base_sha=base_sha,
                branch=branch,
                worktree=str(worktree),
            )

            prompt = _build_codex_prompt(task.prompt)
            result = self._repository.run(
                self._settings.codex_command,
                cwd=worktree,
                timeout_seconds=self._settings.codex_timeout_seconds,
                input_text=prompt,
                check=False,
            )
            self._update(task_id, codex_output=result.output[-100000:])
            if result.returncode:
                raise RuntimeError(
                    "Codex завершился с ошибкой.\n" + result.output[-5000:]
                )

            changed_files = self._repository.changed_files(cwd=worktree)
            if not changed_files:
                self._update(
                    task_id,
                    status="no_changes",
                    changed_files=[],
                    finished_at=utc_now(),
                )
                self._notifier.send(
                    "Codex не создал изменений",
                    f"Задача {task.id}: {task.prompt[:500]}",
                    level="WARNING",
                )
                return

            self._update(
                task_id,
                status="testing",
                changed_files=changed_files,
            )
            test_result = self._repository.run_tests(cwd=worktree)
            self._update(task_id, test_output=test_result.output[-100000:])
            if test_result.returncode:
                raise RuntimeError(
                    "Тесты Codex-ветки завершились с ошибкой.\n"
                    + test_result.output[-5000:]
                )

            message = "codex: " + " ".join(task.prompt.split())[:170]
            commit_sha = self._repository.commit_all(message, cwd=worktree)
            diff = self._repository.commit_diff(commit_sha, cwd=worktree)
            self._update(
                task_id,
                status="ready",
                commit_sha=commit_sha,
                diff=diff[-100000:],
                finished_at=utc_now(),
            )
            self._notifier.send(
                "Codex подготовил исправление",
                (
                    f"Задача: {task.id}\n"
                    f"Файлов: {len(changed_files)}\n"
                    f"Commit: {commit_sha}\n"
                    "Изменения ожидают подтверждения в Telegram."
                ),
                level="SUCCESS",
            )
        except Exception as error:
            logger.exception("Codex task failed id=%s", task_id)
            summary = summarize_codex_failure(error)
            self._update(
                task_id,
                status="error",
                error=summary[:10000],
                finished_at=utc_now(),
            )
            self._notifier.send(
                "Ошибка задачи Codex",
                f"Задача: {task_id}\n{summary}",
                level="ERROR",
            )

    def mark_applied(self, task_id: str) -> CodexTask:
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return self._update(
            task_id,
            status="applied",
            applied_at=utc_now(),
        )

    def mark_pushed(self, task_id: str) -> CodexTask:
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return self._update(task_id, pushed_at=utc_now())

    def reject(self, task_id: str) -> CodexTask:
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status in {"running", "testing", "queued"}:
            raise RuntimeError("Нельзя отклонить задачу, пока Codex её выполняет.")
        target = Path(task.worktree) if task.worktree else None
        if target is not None:
            self._repository.remove_worktree(target, task.branch)
        return self._update(
            task_id,
            status="rejected",
            finished_at=task.finished_at or utc_now(),
        )

    def cleanup_after_apply(self, task_id: str) -> None:
        task = self.get(task_id)
        if task is None:
            return
        if task.worktree:
            self._repository.remove_worktree(Path(task.worktree), task.branch)


def _build_codex_prompt(user_prompt: str) -> str:
    return f"""Работай только в текущем Git worktree проекта Velvet.

Задача пользователя:
{user_prompt}

Обязательные правила:
1. Изучи существующую архитектуру и внеси минимальные согласованные изменения.
2. Не читай, не изменяй и не добавляй .env, токены, ключи, дампы, backups, logs и runtime.
3. Не выполняй git push, git reset --hard, удаление веток и разрушительные операции с БД.
4. Не коммить изменения: Supervisor сам проверит файлы, запустит тесты и создаст commit.
5. Добавь или обнови тесты для изменённого поведения.
6. Не меняй рабочую базу данных. Интеграционные тесты используют только TEST_DATABASE_URL.
7. В конце кратко перечисли изменённые файлы, найденную причину и выполненные проверки.
"""


__all__ = ("CodexTaskManager", "summarize_codex_failure")
