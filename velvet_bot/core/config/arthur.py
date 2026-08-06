from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} must be set.")
    return value


def _parse_ids(value: str) -> frozenset[int]:
    result: set[int] = set()
    for raw in value.replace(";", ",").split(","):
        item = raw.strip()
        if not item:
            continue
        parsed = int(item)
        if parsed <= 0:
            raise ValueError("Arthur user ids must be positive.")
        result.add(parsed)
    return frozenset(result)


def _parse_usernames(value: str) -> frozenset[str]:
    return frozenset(
        item.strip().lstrip("@").casefold()
        for item in value.replace(";", ",").split(",")
        if item.strip().lstrip("@")
    )


def _parse_optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    parsed = int(value)
    if parsed == 0:
        raise ValueError(f"{name} cannot be zero.")
    return parsed


@dataclass(frozen=True, slots=True)
class ArthurSettings:
    bot_token: str
    database_url: str
    allowed_user_ids: frozenset[int]
    allowed_usernames: frozenset[str]
    data_dir: Path
    storage_gateway_base_url: str
    storage_gateway_api_key: str
    report_chat_id: int | None
    report_thread_id: int | None
    heartbeat_path: Path

    @classmethod
    def from_env(cls) -> ArthurSettings:
        bot_token = _required("ARTHUR_BOT_TOKEN")
        velvet_token = os.getenv("BOT_TOKEN", "").strip()
        if velvet_token and bot_token == velvet_token:
            raise ValueError("ARTHUR_BOT_TOKEN must not reuse BOT_TOKEN.")

        allowed_user_ids = _parse_ids(os.getenv("ARTHUR_ALLOWED_USER_IDS", ""))
        allowed_usernames = _parse_usernames(
            os.getenv("ARTHUR_ALLOWED_USERNAMES", "")
        )
        if not allowed_user_ids and not allowed_usernames:
            raise ValueError("Arthur owner allowlist must not be empty.")

        api_key = _required("ARTHUR_STORAGE_GATEWAY_API_KEY")
        if len(api_key) < 24:
            raise ValueError(
                "ARTHUR_STORAGE_GATEWAY_API_KEY must contain at least 24 characters."
            )

        if os.getenv("STORAGE_LIBRARIAN_AUTO_ENQUEUE", "false").strip().casefold() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            raise ValueError("Arthur Phase 2 requires STORAGE_LIBRARIAN_AUTO_ENQUEUE=false.")

        data_dir = Path(
            os.getenv("ARTHUR_DATA_DIR", "/app/runtime/arthur")
        ).expanduser()
        heartbeat_path = Path(
            os.getenv("ARTHUR_HEARTBEAT_PATH", "/tmp/arthur-heartbeat")
        )
        return cls(
            bot_token=bot_token,
            database_url=_required("DATABASE_URL"),
            allowed_user_ids=allowed_user_ids,
            allowed_usernames=allowed_usernames,
            data_dir=data_dir,
            storage_gateway_base_url=os.getenv(
                "ARTHUR_STORAGE_GATEWAY_BASE_URL",
                "http://arthur-storage-gateway:8786",
            ).strip().rstrip("/"),
            storage_gateway_api_key=api_key,
            report_chat_id=_parse_optional_int("ARTHUR_REPORT_CHAT_ID"),
            report_thread_id=_parse_optional_int("ARTHUR_REPORT_THREAD_ID"),
            heartbeat_path=heartbeat_path,
        )


@dataclass(frozen=True, slots=True)
class ArthurStorageGatewaySettings:
    velvet_bot_token: str
    database_url: str
    api_key: str
    host: str
    port: int
    max_object_bytes: int

    @classmethod
    def from_env(cls) -> ArthurStorageGatewaySettings:
        api_key = _required("ARTHUR_STORAGE_GATEWAY_API_KEY")
        if len(api_key) < 24:
            raise ValueError(
                "ARTHUR_STORAGE_GATEWAY_API_KEY must contain at least 24 characters."
            )
        port = int(os.getenv("ARTHUR_STORAGE_GATEWAY_PORT", "8786"))
        if not 1 <= port <= 65535:
            raise ValueError("ARTHUR_STORAGE_GATEWAY_PORT is invalid.")
        max_object_bytes = int(
            os.getenv("STORAGE_LIBRARIAN_MAX_OBJECT_BYTES", str(16 * 1024 * 1024))
        )
        if max_object_bytes <= 0:
            raise ValueError("STORAGE_LIBRARIAN_MAX_OBJECT_BYTES must be positive.")
        return cls(
            velvet_bot_token=_required("BOT_TOKEN"),
            database_url=_required("DATABASE_URL"),
            api_key=api_key,
            host=os.getenv("ARTHUR_STORAGE_GATEWAY_HOST", "0.0.0.0").strip(),
            port=port,
            max_object_bytes=max_object_bytes,
        )


__all__ = ("ArthurSettings", "ArthurStorageGatewaySettings")
