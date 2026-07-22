from __future__ import annotations

import hashlib
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DependencySyncError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DependencySyncResult:
    source: str
    requirements_sha256: str
    installed: bool
    output_tail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "requirements_sha256": self.requirements_sha256,
            "installed": self.installed,
            "output_tail": self.output_tail,
        }


def _resolved_python(settings: Any) -> str:
    raw = str(settings.python_executable).strip()
    candidate = Path(raw)
    if candidate.is_absolute():
        return str(candidate)
    project_candidate = Path(settings.project_dir) / candidate
    if project_candidate.exists() or any(separator in raw for separator in ("\\", "/")):
        return str(project_candidate.resolve())
    return raw


def _fingerprint(requirements: str, python_executable: str) -> str:
    digest = hashlib.sha256()
    digest.update(python_executable.encode("utf-8", errors="replace"))
    digest.update(b"\0")
    digest.update(requirements.encode("utf-8"))
    return digest.hexdigest()


def _cache_path(settings: Any) -> Path:
    return Path(settings.runtime_dir) / "requirements-sync.sha256"


def _run(
    command: tuple[str, ...],
    *,
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(60, int(timeout_seconds)),
        shell=False,
        check=False,
        env={
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        },
    )


_TRANSIENT_GIT_NETWORK_MARKERS = (
    "couldn't connect to server",
    "failed to connect to github.com",
    "could not resolve host",
    "connection reset by peer",
    "connection timed out",
    "the requested url returned error: 502",
    "the requested url returned error: 503",
    "the requested url returned error: 504",
)


def _run_git_with_retries(
    command: tuple[str, ...],
    *,
    cwd: Path,
    timeout_seconds: int,
    attempts: int = 3,
) -> subprocess.CompletedProcess[str]:
    result: subprocess.CompletedProcess[str] | None = None
    for attempt in range(max(1, attempts)):
        result = _run(command, cwd=cwd, timeout_seconds=timeout_seconds)
        output = (result.stdout or "").casefold()
        transient = any(marker in output for marker in _TRANSIENT_GIT_NETWORK_MARKERS)
        if result.returncode == 0 or not transient or attempt + 1 >= attempts:
            return result
        time.sleep((1.0, 3.0)[min(attempt, 1)])
    assert result is not None
    return result


def _sync_text(
    settings: Any,
    requirements: str,
    *,
    source: str,
    force: bool = False,
) -> DependencySyncResult:
    cleaned = requirements.strip()
    if not cleaned:
        raise DependencySyncError(f"{source}: requirements.txt пустой.")

    project_dir = Path(settings.project_dir).resolve()
    runtime_dir = Path(settings.runtime_dir).resolve()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    python_executable = _resolved_python(settings)
    fingerprint = _fingerprint(cleaned + "\n", python_executable)
    cache_path = _cache_path(settings)
    try:
        cached = cache_path.read_text(encoding="utf-8").strip()
    except OSError:
        cached = ""
    if not force and cached == fingerprint:
        return DependencySyncResult(
            source=source,
            requirements_sha256=fingerprint,
            installed=False,
            output_tail="Зависимости уже синхронизированы.",
        )

    staged = runtime_dir / "requirements-sync.txt"
    temporary = staged.with_suffix(".tmp")
    temporary.write_text(cleaned + "\n", encoding="utf-8")
    temporary.replace(staged)
    command = (
        python_executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "-r",
        str(staged),
    )
    completed = _run(
        command,
        cwd=project_dir,
        timeout_seconds=max(int(settings.command_timeout_seconds), 900),
    )
    if completed.returncode:
        raise DependencySyncError(
            f"Не удалось синхронизировать зависимости из {source}.\n"
            + (completed.stdout or "")[-5000:]
        )

    cache_tmp = cache_path.with_suffix(".tmp")
    cache_tmp.write_text(fingerprint + "\n", encoding="utf-8")
    cache_tmp.replace(cache_path)
    return DependencySyncResult(
        source=source,
        requirements_sha256=fingerprint,
        installed=True,
        output_tail=(completed.stdout or "")[-4000:],
    )


def sync_current_requirements(
    settings: Any,
    *,
    force: bool = False,
) -> DependencySyncResult:
    requirements_path = Path(settings.project_dir).resolve() / "requirements.txt"
    try:
        requirements = requirements_path.read_text(encoding="utf-8")
    except OSError as error:
        raise DependencySyncError(
            f"Не удалось прочитать {requirements_path}: {error}"
        ) from error
    return _sync_text(
        settings,
        requirements,
        source=str(requirements_path),
        force=force,
    )


def sync_remote_requirements(settings: Any) -> DependencySyncResult:
    project_dir = Path(settings.project_dir).resolve()
    remote = str(settings.update_remote)
    branch = str(settings.update_branch)
    timeout = max(int(settings.command_timeout_seconds), 300)
    fetch = _run_git_with_retries(
        ("git", "fetch", "--prune", remote, branch),
        cwd=project_dir,
        timeout_seconds=timeout,
    )
    if fetch.returncode:
        raise DependencySyncError(
            "Не удалось получить удалённую ветку после трёх попыток перед синхронизацией зависимостей.\n"
            + (fetch.stdout or "")[-5000:]
        )
    ref = f"{remote}/{branch}:requirements.txt"
    show = _run(
        ("git", "show", ref),
        cwd=project_dir,
        timeout_seconds=60,
    )
    if show.returncode:
        raise DependencySyncError(
            f"Не удалось прочитать requirements.txt из {remote}/{branch}.\n"
            + (show.stdout or "")[-5000:]
        )
    return _sync_text(
        settings,
        show.stdout,
        source=f"{remote}/{branch}:requirements.txt",
    )


__all__ = (
    "DependencySyncError",
    "DependencySyncResult",
    "sync_current_requirements",
    "sync_remote_requirements",
)
