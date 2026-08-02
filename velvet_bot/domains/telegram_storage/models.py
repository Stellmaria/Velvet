from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from velvet_bot.domains.telegram_storage.deletion import (
    DeletionPolicy,
    build_storage_deletion_policy,
)
from velvet_bot.domains.telegram_storage.encryption import (
    StorageEncryptionKeyring,
    keyring_from_env,
)

StorageKind = Literal[
    "watermarks",
    "backups",
    "diagnostics",
    "exports",
    "codex",
    "releases",
    "rework",
    "inbox",
    "analysis",
]
_STORAGE_KINDS: tuple[StorageKind, ...] = (
    "watermarks",
    "backups",
    "diagnostics",
    "exports",
    "codex",
    "releases",
    "rework",
    "inbox",
    "analysis",
)


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


def _optional_int_env(
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} должен быть от {minimum} до {maximum}.")
    return value


def _path(value: str, project_dir: Path) -> Path:
    candidate = Path(value.strip() or ".").expanduser()
    if not candidate.is_absolute():
        candidate = project_dir / candidate
    # Keep lexical identity so DeletionPolicy can reject configured symlinks
    # instead of silently following them to an external target.
    return Path(os.path.abspath(os.path.normpath(candidate)))


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
    inbox: int | None = None
    analysis: int | None = None

    def for_kind(self, kind: StorageKind) -> int:
        value = getattr(self, kind)
        if value is None:
            env_name = (
                "STORAGE_THREAD_INBOX"
                if kind == "inbox"
                else "STORAGE_THREAD_ANALYSIS"
            )
            raise ValueError(
                f"Для storage kind {kind} не настроена ветка Telegram: {env_name}."
            )
        return int(value)


@dataclass(frozen=True, slots=True)
class TelegramStorageSettings:
    chat_id: int
    threads: StorageThreadMap
    project_dir: Path
    data_dir: Path | None
    backup_dir: Path
    logs_dir: Path
    runtime_dir: Path
    codex_worktree_dir: Path
    export_dirs: tuple[Path, ...]
    release_dirs: tuple[Path, ...]
    staging_dir: Path
    krita_bridge_dir: Path
    migrate_on_start: bool
    delete_after_upload: bool
    active_file_grace_seconds: int
    max_part_bytes: int
    encryption_keyring: StorageEncryptionKeyring = field(repr=False)

    @property
    def encryption_secret(self) -> str:
        return self.encryption_keyring.active_secret

    @property
    def encryption_key_id(self) -> str:
        return self.encryption_keyring.active_key_id

    @classmethod
    def from_env(cls) -> "TelegramStorageSettings":
        project_dir = _path(os.getenv("SUPERVISOR_PROJECT_DIR", "."), Path.cwd())
        runtime_dir = _path(
            os.getenv("SUPERVISOR_RUNTIME_DIR", "runtime/supervisor"),
            project_dir,
        )
        data_raw = os.getenv("VELVET_DATA_DIR", "").strip()
        data_dir = _path(data_raw, project_dir) if data_raw else None
        encryption_keyring = keyring_from_env()
        settings = cls(
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
                inbox=_optional_int_env(
                    "STORAGE_THREAD_INBOX",
                    minimum=1,
                    maximum=2**31 - 1,
                ),
                analysis=_optional_int_env(
                    "STORAGE_THREAD_ANALYSIS",
                    minimum=1,
                    maximum=2**31 - 1,
                ),
            ),
            project_dir=project_dir,
            data_dir=data_dir,
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
            krita_bridge_dir=_path(
                os.getenv(
                    "KRITA_BRIDGE_DIR",
                    str(Path.home() / "VelvetKritaBridge"),
                ),
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
            encryption_keyring=encryption_keyring,
        )
        if settings.delete_after_upload:
            # Fail before migration starts if any configured deletion scope is empty
            # or points at a protected root such as the checkout, home or data root.
            for kind in _STORAGE_KINDS:
                settings.deletion_policy_for(kind)
        return settings

    def deletion_policy_for(self, kind: StorageKind) -> DeletionPolicy:
        roots_by_kind: dict[StorageKind, tuple[Path, ...]] = {
            "watermarks": (self.krita_bridge_dir,),
            "backups": (self.backup_dir, self.staging_dir),
            "diagnostics": (
                self.logs_dir,
                self.project_dir / "diagnostics",
                self.runtime_dir / "incidents",
            ),
            "exports": self.export_dirs,
            "codex": (self.staging_dir,),
            "releases": self.release_dirs,
            "rework": (self.staging_dir,),
            "inbox": (self.staging_dir,),
            "analysis": (self.staging_dir,),
        }
        return build_storage_deletion_policy(
            name=f"telegram-storage-{kind}",
            roots=roots_by_kind[kind],
            project_dir=self.project_dir,
            data_dir=self.data_dir,
            allow_recursive_directories=False,
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
