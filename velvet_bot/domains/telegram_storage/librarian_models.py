from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

DEFAULT_ALLOWED_KINDS = (
    "diagnostics",
    "exports",
    "codex",
    "releases",
    "rework",
    "inbox",
)
PROTECTED_KINDS = frozenset({"backups", "analysis", "watermarks"})


class StorageLibrarianError(RuntimeError):
    pass


class UnsupportedStorageContent(StorageLibrarianError):
    pass


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().casefold()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on", "да"}:
        return True
    if raw in {"0", "false", "no", "off", "нет"}:
        return False
    raise ValueError(f"{name} должен быть true/false.")


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    value = int(raw) if raw else default
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} должен быть от {minimum} до {maximum}.")
    return value


@dataclass(frozen=True, slots=True)
class StorageLibrarianSettings:
    enabled: bool
    hermes_base_url: str
    hermes_api_key: str | None
    scan_interval_seconds: int
    poll_interval_seconds: int
    run_timeout_seconds: int
    max_object_bytes: int
    max_text_chars: int
    max_zip_entries: int
    max_attempts: int
    analyzer_version: str
    allowed_kinds: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "StorageLibrarianSettings":
        raw_kinds = os.getenv(
            "STORAGE_LIBRARIAN_ALLOWED_KINDS",
            ",".join(DEFAULT_ALLOWED_KINDS),
        )
        kinds = tuple(
            dict.fromkeys(
                value.strip().casefold()
                for value in raw_kinds.split(",")
                if value.strip()
            )
        )
        forbidden = PROTECTED_KINDS.intersection(kinds)
        if forbidden:
            raise ValueError(
                "Storage Librarian не может анализировать защищённые категории: "
                + ", ".join(sorted(forbidden))
            )
        enabled = _bool_env("STORAGE_LIBRARIAN_ENABLED", False)
        base_url = os.getenv(
            "STORAGE_LIBRARIAN_HERMES_BASE_URL",
            os.getenv("HERMES_BASE_URL", "http://hermes:8642"),
        ).strip().rstrip("/")
        api_key = (
            os.getenv(
                "STORAGE_LIBRARIAN_HERMES_API_KEY",
                os.getenv("HERMES_API_KEY", ""),
            ).strip()
            or None
        )
        if enabled and not base_url:
            raise ValueError(
                "STORAGE_LIBRARIAN_HERMES_BASE_URL обязателен для Storage Librarian."
            )
        if enabled and (api_key is None or len(api_key) < 8):
            raise ValueError(
                "STORAGE_LIBRARIAN_HERMES_API_KEY должен содержать минимум 8 символов."
            )
        return cls(
            enabled=enabled,
            hermes_base_url=base_url,
            hermes_api_key=api_key,
            scan_interval_seconds=_int_env(
                "STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS",
                300,
                minimum=60,
                maximum=86400,
            ),
            poll_interval_seconds=_int_env(
                "STORAGE_LIBRARIAN_POLL_INTERVAL_SECONDS",
                2,
                minimum=1,
                maximum=30,
            ),
            run_timeout_seconds=_int_env(
                "STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS",
                900,
                minimum=30,
                maximum=1800,
            ),
            max_object_bytes=_int_env(
                "STORAGE_LIBRARIAN_MAX_OBJECT_BYTES",
                12 * 1024 * 1024,
                minimum=1024,
                maximum=48 * 1024 * 1024,
            ),
            max_text_chars=_int_env(
                "STORAGE_LIBRARIAN_MAX_TEXT_CHARS",
                120_000,
                minimum=2000,
                maximum=500_000,
            ),
            max_zip_entries=_int_env(
                "STORAGE_LIBRARIAN_MAX_ZIP_ENTRIES",
                40,
                minimum=1,
                maximum=200,
            ),
            max_attempts=_int_env(
                "STORAGE_LIBRARIAN_MAX_ATTEMPTS",
                3,
                minimum=1,
                maximum=10,
            ),
            analyzer_version=(
                os.getenv(
                    "STORAGE_LIBRARIAN_ANALYZER_VERSION",
                    "velvet-librarian:qwen3.5-9b-local:v3",
                ).strip()
                or "velvet-librarian:qwen3.5-9b-local:v3"
            ),
            allowed_kinds=kinds,
        )


@dataclass(frozen=True, slots=True)
class LibrarianPart:
    part_number: int
    telegram_file_id: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class LibrarianObject:
    object_id: int
    storage_kind: str
    logical_key: str
    original_name: str
    mime_type: str | None
    size_bytes: int
    sha256: str
    encrypted: bool
    manifest: JsonObject
    parts: tuple[LibrarianPart, ...]


@dataclass(frozen=True, slots=True)
class LibrarianJob:
    job_id: int
    storage_object_id: int
    attempts: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class HermesRunResult:
    run_id: str
    output: str
    usage: JsonObject


@dataclass(frozen=True, slots=True)
class LibrarianAnalysis:
    summary: str
    tags: tuple[str, ...]
    entities: tuple[dict[str, str], ...]
    action_items: tuple[dict[str, str], ...]
    sensitivity: str
    confidence: int | None
    raw: JsonObject


__all__ = (
    "DEFAULT_ALLOWED_KINDS",
    "HermesRunResult",
    "JsonObject",
    "JsonValue",
    "LibrarianAnalysis",
    "LibrarianJob",
    "LibrarianObject",
    "LibrarianPart",
    "PROTECTED_KINDS",
    "StorageLibrarianError",
    "StorageLibrarianSettings",
    "UnsupportedStorageContent",
)
