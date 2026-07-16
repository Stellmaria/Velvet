from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class CommandError(RuntimeError):
    def __init__(
        self,
        command: tuple[str, ...],
        returncode: int,
        output: str,
    ) -> None:
        self.command = command
        self.returncode = returncode
        self.output = output
        super().__init__(
            f"Команда завершилась с кодом {returncode}: "
            f"{subprocess.list2cmdline(command)}\n{output[-4000:]}"
        )


@dataclass(frozen=True, slots=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    output: str


class GitRepository:
    def __init__(
        self,
        project_dir: Path,
        *,
        timeout_seconds: int,
        test_command: tuple[str, ...],
    ) -> None:
        self.project_dir = project_dir
        self.timeout_seconds = timeout_seconds
        self.test_command = test_command

    def run(
        self,
        command: Iterable[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        args = tuple(str(value) for value in command)
        completed = subprocess.run(
            args,
            cwd=str(cwd or self.project_dir),
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds or self.timeout_seconds,
            check=False,
            env=env,
        )
        result = CommandResult(
            command=args,
            returncode=int(completed.returncode),
            output=completed.stdout or "",
        )
        if check and result.returncode:
            raise CommandError(args, result.returncode, result.output)
        return result

    def git(
        self,
        *args: str,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        check: bool = True,
    ) -> CommandResult:
        return self.run(
            ("git", *args),
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            check=check,
        )

    def head_sha(self, *, cwd: Path | None = None) -> str:
        return self.git("rev-parse", "HEAD", cwd=cwd).output.strip()

    def branch_name(self, *, cwd: Path | None = None) -> str:
        return self.git("branch", "--show-current", cwd=cwd).output.strip()

    def status_porcelain(self, *, cwd: Path | None = None) -> str:
        return self.git("status", "--porcelain", cwd=cwd).output.strip()

    def ensure_clean(self, *, cwd: Path | None = None) -> None:
        status = self.status_porcelain(cwd=cwd)
        if status:
            raise RuntimeError(
                "Рабочее дерево содержит незакоммиченные изменения:\n"
                f"{status[:4000]}"
            )

    def fetch(self, remote: str, branch: str) -> str:
        return self.git("fetch", "--prune", remote, branch).output

    def fast_forward(self, remote: str, branch: str) -> str:
        current = self.branch_name()
        if current != branch:
            raise RuntimeError(
                f"Обновление разрешено только на ветке {branch!r}; "
                f"сейчас открыта {current!r}."
            )
        return self.git("merge", "--ff-only", f"{remote}/{branch}").output

    def hard_reset(self, sha: str, *, cwd: Path | None = None) -> str:
        if len(sha) < 7:
            raise ValueError("Некорректный commit SHA для отката.")
        return self.git("reset", "--hard", sha, cwd=cwd).output

    def run_tests(self, *, cwd: Path | None = None) -> CommandResult:
        return self.run(
            self.test_command,
            cwd=cwd,
            timeout_seconds=max(self.timeout_seconds, 1800),
            check=False,
        )

    def create_worktree(self, task_id: str, target: Path) -> tuple[str, str]:
        self.ensure_clean()
        base_sha = self.head_sha()
        branch = f"codex/{task_id}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise RuntimeError(f"Каталог worktree уже существует: {target}")
        self.git("worktree", "add", "-b", branch, str(target), base_sha)
        return base_sha, branch

    def remove_worktree(self, target: Path, branch: str | None) -> None:
        if target.exists():
            self.git("worktree", "remove", "--force", str(target), check=False)
        self.git("worktree", "prune", check=False)
        if branch:
            self.git("branch", "-D", branch, check=False)

    def changed_files(self, *, cwd: Path) -> list[str]:
        output = self.git("status", "--porcelain", cwd=cwd).output
        result: list[str] = []
        for line in output.splitlines():
            value = line[3:].strip() if len(line) > 3 else ""
            if " -> " in value:
                value = value.split(" -> ", 1)[1]
            if value:
                result.append(value)
        return sorted(set(result))

    def staged_files(self, *, cwd: Path) -> list[str]:
        output = self.git(
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMR",
            cwd=cwd,
        ).output
        return [line.strip() for line in output.splitlines() if line.strip()]

    def commit_all(self, message: str, *, cwd: Path) -> str:
        self.git("add", "-A", cwd=cwd)
        staged = self.staged_files(cwd=cwd)
        if not staged:
            raise RuntimeError("Codex не создал изменений для коммита.")
        forbidden = [
            name
            for name in staged
            if _is_forbidden_generated_path(name)
        ]
        if forbidden:
            self.git("reset", cwd=cwd, check=False)
            raise RuntimeError(
                "Codex попытался добавить запрещённые файлы: "
                + ", ".join(forbidden[:20])
            )
        self.git("commit", "-m", message[:200], cwd=cwd)
        return self.head_sha(cwd=cwd)

    def commit_diff(self, sha: str, *, cwd: Path) -> str:
        return self.git(
            "show",
            "--format=medium",
            "--stat",
            "--patch",
            "--unified=2",
            sha,
            cwd=cwd,
        ).output

    def merge_codex_commit(self, branch: str, base_sha: str) -> str:
        self.ensure_clean()
        current_sha = self.head_sha()
        if current_sha != base_sha:
            raise RuntimeError(
                "Рабочая ветка изменилась после запуска Codex. "
                "Задачу нужно запустить заново на свежей версии."
            )
        return self.git("merge", "--ff-only", branch).output

    def push(self, remote: str, branch: str) -> str:
        return self.git("push", remote, branch).output


def _is_forbidden_generated_path(name: str) -> bool:
    normalized = name.replace("\\", "/").strip("/").casefold()
    leaf = normalized.rsplit("/", 1)[-1]
    if leaf == ".env" or leaf.startswith(".env."):
        return True
    if normalized.startswith(("logs/", "runtime/", "backups/", ".git/")):
        return True
    return leaf.endswith((".pem", ".key", ".p12", ".pfx"))


__all__ = (
    "CommandError",
    "CommandResult",
    "GitRepository",
)
