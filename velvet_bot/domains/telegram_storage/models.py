from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

StorageKind = Literal[
    "watermarks",
    "backups",
    "diagnostics",
    "exports",
    "codex",
    "releases",
    "rework",
]


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().casefold()
    if not value:
        return default
    if value in {"1", "true", "yes", "on", "да"}:
        return True
    if value in {"0", "false", "no", "off", "нет"}:
        return False
    raise ValueError(f"{name} должен быть true/false.")


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    value = int(raw) if raw else default
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} должен быть от {minimum} до {maximum}.")
    return value


def _path(value: str, project_dir: Path) -> Path:
    candidate = Path(value.strip() or ".").expanduser()
    if not candidate.is_absolute():
        candidate = project_dir / candidate
    return candidate.resolve()


def _paths_env(name: str, defaults: tuple[str, ...], project_dir: Path) -> tuple[Path, ...]:
    raw = os.getenv(name, "").strip()
    values = tuple(part.strip() for part in raw.split(";") if part.strip()) if raw else defaults
    result: list[Path] = []
    seen: set[Path] = set()
    for value in values:
        candidate = _path(value, project_dir)
        if candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class StorageThreadMap:
    watermarks: int = 3
    backups: int = 4
    diagnostics: int = 9
    exports: int = 11
    codex: int = 7
    releases: int = 13
    rework: int = 15

    def for_kind(self, kind: StorageKind) -> int:
        return int(getattr(self, kind))


@dataclass(frozen=True, slots=True)
class TelegramStorageSettings:
    chat_id: int
    threads: StorageThreadMap
    project_dir: Path
    backup_dir: Path
    logs_dir: Path
    runtime_dir: Path
    codex_worktree_dir: Path
    export_dirs: tuple[Path, ...]
    release_dirs: tuple[Path, ...]
    staging_dir: Path
    migrate_on_start: bool
    delete_after_upload: bool
    active_file_grace_seconds: int
    max_part_bytes: int
    encryption_secret: str = field(repr=False)

    @classmethod
    def from_env(cls) -> "TelegramStorageSettings":
        project_dir = _path(os.getenv("SUPERVISOR_PROJECT_DIR", "."), Path.cwd())
        runtime_dir = _path(
            os.getenv("SUPERVISOR_RUNTIME_DIR", "runtime/supervisor"),
            project_dir,
        )
        secret = (
            os.getenv("STORAGE_ENCRYPTION_SECRET", "").strip()
            or os.getenv("SUPERVISOR_TOKEN", "").strip()
            or os.getenv("BOT_TOKEN", "").strip()
        )
        if len(secret) < 24:
            raise ValueError(
                "Для шифрования backup задайте STORAGE_ENCRYPTION_SECRET минимум из 24 символов."
            )
        return cls(
            chat_id=_int_env(
                "TELEGRAM_STORAGE_CHAT_ID",
                -1004459280894,
                minimum=-10**16,
                maximum=-1,
            ),
            threads=StorageThreadMap(
                watermarks=_int_env("STORAGE_THREAD_WATERMARKS", 3, minimum=1, maximum=2**31 - 1),
                backups=_int_env("STORAGE_THREAD_BACKUPS", 4, minimum=1, maximum=2**31 - 1),
                diagnostics=_int_env("STORAGE_THREAD_DIAGNOSTICS", 9, minimum=1, maximum=2**31 - 1),
                exports=_int_env("STORAGE_THREAD_EXPORTS", 11, minimum=1, maximum=2**31 - 1),
                codex=_int_env("STORAGE_THREAD_CODEX", 7, minimum=1, maximum=2**31 - 1),
                releases=_int_env("STORAGE_THREAD_RELEASES", 13, minimum=1, maximum=2**31 - 1),
                rework=_int_env("STORAGE_THREAD_REWORK", 15, minimum=1, maximum=2**31 - 1),
            ),
            project_dir=project_dir,
            backup_dir=_path(os.getenv("BACKUP_DIR", "backups"), project_dir),
            logs_dir=_path(os.getenv("SUPERVISOR_LOG_DIR", "logs"), project_dir),
            runtime_dir=runtime_dir,
            codex_worktree_dir=_path(
                os.getenv("CODEX_WORKTREE_DIR", str(runtime_dir / "codex-worktrees")),
                project_dir,
            ),
            export_dirs=_paths_env(
                "STORAGE_EXPORT_DIRS",
                ("exports", "reports", "runtime/exports", "runtime/reports"),
                project_dir,
            ),
            release_dirs=_paths_env(
                "STORAGE_RELEASE_DIRS",
                ("releases", "dist", "runtime/releases"),
                project_dir,
            ),
            staging_dir=_path(
                os.getenv("STORAGE_STAGING_DIR", "runtime/telegram-storage"),
                project_dir,
            ),
            migrate_on_start=_bool_env("STORAGE_MIGRATE_ON_START", True),
            delete_after_upload=_bool_env("STORAGE_DELETE_AFTER_UPLOAD", True),
            active_file_grace_seconds=_int_env(
                "STORAGE_ACTIVE_FILE_GRACE_SECONDS",
                600,
                minimum=60,
                maximum=86400,
            ),
            max_part_bytes=_int_env(
                "STORAGE_MAX_PART_BYTES",
                45 * 1024 * 1024,
                minimum=5 * 1024 * 1024,
                maximum=49 * 1024 * 1024,
            ),
            encryption_secret=secret,
        )


@dataclass(frozen=True, slots=True)
class StorageCandidate:
    kind: StorageKind
    path: Path
    logical_key: str
    original_name: str
    source_path: str | None = None
    mime_type: str | None = None
    encrypted: bool = False
    delete_paths: tuple[Path, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StoredPart:
    part_number: int
    message_id: int
    telegram_file_id: str
    telegram_file_unique_id: str | None
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class StoredObject:
    object_id: int
    kind: StorageKind
    logical_key: str
    sha256: str
    size_bytes: int
    chat_id: int
    thread_id: int
    parts: tuple[StoredPart, ...]


@dataclass(slots=True)
class MigrationSummary:
    run_id: int
    migration_kind: str
    discovered_files: int = 0
    stored_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    deleted_files: int = 0
    freed_bytes: int = 0
    errors: list[str] = field(default_factory=list)
    by_kind: dict[str, dict[str, int]] = field(default_factory=dict)

    def bump(self, kind: StorageKind, field_name: str, amount: int = 1) -> None:
        bucket = self.by_kind.setdefault(
            kind,
            {"discovered": 0, "stored": 0, "skipped": 0, "failed": 0, "deleted": 0},
        )
        bucket[field_name] = bucket.get(field_name, 0) + int(amount)

    @property
    def status(self) -> str:
        if self.failed_files and not self.stored_files:
            return "failed"
        if self.failed_files:
            return "partial"
        return "completed"


__all__ = (
    "MigrationSummary",
    "StorageCandidate",
    "StoredObject",
    "StoredPart",
    "StorageKind",
    "StorageThreadMap",
    "TelegramStorageSettings",
)
