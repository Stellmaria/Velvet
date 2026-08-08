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
TEXT_CONTEXT_RESERVED_TOKENS = 1024
TEXT_CHARS_PER_TOKEN = 2
TEXT_ANALYSIS_WRAPPER_RESERVED_CHARS = 2048
TEXT_CHUNK_WRAPPER_RESERVED_CHARS = 512
MIN_STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS = 720


class StorageLibrarianError(RuntimeError):
    """Retryable Storage Librarian failure by default."""


class TerminalStorageLibrarianError(StorageLibrarianError):
    """Deterministic failure that must not be retried unchanged."""


class UnsupportedStorageContent(TerminalStorageLibrarianError):
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


def storage_librarian_text_prompt_char_limit(
    *,
    context_length: int,
    max_output_tokens: int,
) -> int:
    """Return the conservative total prompt-character budget for local Ollama."""

    available_tokens = (
        context_length
        - max_output_tokens
        - TEXT_CONTEXT_RESERVED_TOKENS
    )
    if available_tokens < 512:
        raise ValueError(
            "Storage Librarian text context оставляет недостаточно места для входа."
        )
    return available_tokens * TEXT_CHARS_PER_TOKEN


def storage_librarian_text_source_char_limit(
    *,
    context_length: int,
    max_output_tokens: int,
) -> int:
    """Return the safe source-envelope budget after prompt wrapper reservation."""

    source_limit = (
        storage_librarian_text_prompt_char_limit(
            context_length=context_length,
            max_output_tokens=max_output_tokens,
        )
        - TEXT_ANALYSIS_WRAPPER_RESERVED_CHARS
    )
    if source_limit < 2000:
        raise ValueError(
            "Storage Librarian text context оставляет недостаточно места для source envelope."
        )
    return source_limit


def _chunk_limits(max_text_chars: int) -> tuple[int, int, int]:
    max_chunk_count = _int_env(
        "STORAGE_LIBRARIAN_MAX_CHUNKS",
        12,
        minimum=2,
        maximum=32,
    )
    theoretical_chunk_capacity = max(
        1,
        max_text_chars - TEXT_CHUNK_WRAPPER_RESERVED_CHARS,
    ) * max_chunk_count
    max_chunk_source_chars = min(
        _int_env(
            "STORAGE_LIBRARIAN_MAX_CHUNK_SOURCE_CHARS",
            220_000,
            minimum=4000,
            maximum=2_000_000,
        ),
        theoretical_chunk_capacity,
    )
    max_inference_calls = min(
        _int_env(
            "STORAGE_LIBRARIAN_MAX_INFERENCE_CALLS",
            max_chunk_count + 1,
            minimum=2,
            maximum=64,
        ),
        max_chunk_count + 1,
    )
    return max_chunk_count, max_chunk_source_chars, max_inference_calls


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
    ollama_base_url: str = "http://ollama-librarian:11434"
    text_model: str = "velvet-librarian-text:v1"
    vision_model: str = "velvet-librarian-vision:v1"
    text_context_length: int = 8192
    text_max_output_tokens: int = 384
    vision_context_length: int = 16384
    vision_max_output_tokens: int = 640
    ollama_keep_alive: str = "5m"
    max_chunk_count: int = 12
    max_chunk_source_chars: int = 220_000
    max_inference_calls: int = 13

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

        text_context_length = _int_env(
            "STORAGE_LIBRARIAN_TEXT_CONTEXT_LENGTH",
            8192,
            minimum=2048,
            maximum=65536,
        )
        text_max_output_tokens = _int_env(
            "STORAGE_LIBRARIAN_TEXT_MAX_OUTPUT_TOKENS",
            384,
            minimum=64,
            maximum=4096,
        )
        max_text_chars_limit = storage_librarian_text_source_char_limit(
            context_length=text_context_length,
            max_output_tokens=text_max_output_tokens,
        )
        max_text_chars = min(
            _int_env(
                "STORAGE_LIBRARIAN_MAX_TEXT_CHARS",
                max_text_chars_limit,
                minimum=2000,
                maximum=500_000,
            ),
            max_text_chars_limit,
        )
        max_chunk_count, max_chunk_source_chars, max_inference_calls = _chunk_limits(
            max_text_chars
        )
        run_timeout_seconds = max(
            MIN_STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS,
            _int_env(
                "STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS",
                MIN_STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS,
                minimum=30,
                maximum=1800,
            ),
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
            run_timeout_seconds=run_timeout_seconds,
            max_object_bytes=_int_env(
                "STORAGE_LIBRARIAN_MAX_OBJECT_BYTES",
                12 * 1024 * 1024,
                minimum=1024,
                maximum=48 * 1024 * 1024,
            ),
            max_text_chars=max_text_chars,
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
                    "velvet-librarian:qwen3-4b-text:v4",
                ).strip()
                or "velvet-librarian:qwen3-4b-text:v4"
            ),
            allowed_kinds=kinds,
            ollama_base_url=(
                os.getenv(
                    "STORAGE_LIBRARIAN_OLLAMA_BASE_URL",
                    "http://ollama-librarian:11434",
                ).strip().rstrip("/")
                or "http://ollama-librarian:11434"
            ),
            text_model=(
                os.getenv(
                    "STORAGE_LIBRARIAN_TEXT_MODEL",
                    "velvet-librarian-text:v1",
                ).strip()
                or "velvet-librarian-text:v1"
            ),
            vision_model=(
                os.getenv(
                    "STORAGE_LIBRARIAN_VISION_MODEL",
                    "velvet-librarian-vision:v1",
                ).strip()
                or "velvet-librarian-vision:v1"
            ),
            text_context_length=text_context_length,
            text_max_output_tokens=text_max_output_tokens,
            vision_context_length=_int_env(
                "STORAGE_LIBRARIAN_VISION_CONTEXT_LENGTH",
                16384,
                minimum=4096,
                maximum=65536,
            ),
            vision_max_output_tokens=_int_env(
                "STORAGE_LIBRARIAN_VISION_MAX_OUTPUT_TOKENS",
                640,
                minimum=64,
                maximum=4096,
            ),
            ollama_keep_alive=(
                os.getenv("STORAGE_LIBRARIAN_OLLAMA_KEEP_ALIVE", "5m").strip()
                or "5m"
            ),
            max_chunk_count=max_chunk_count,
            max_chunk_source_chars=max_chunk_source_chars,
            max_inference_calls=max_inference_calls,
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
    analyzer: str = "hermes"


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
    "MIN_STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS",
    "PROTECTED_KINDS",
    "StorageLibrarianError",
    "StorageLibrarianSettings",
    "TEXT_CHUNK_WRAPPER_RESERVED_CHARS",
    "TerminalStorageLibrarianError",
    "UnsupportedStorageContent",
    "storage_librarian_text_prompt_char_limit",
    "storage_librarian_text_source_char_limit",
)