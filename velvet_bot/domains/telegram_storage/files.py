from __future__ import annotations

import json
import os
import re
import zipfile
from pathlib import Path
from typing import Iterable

from velvet_bot.domains.telegram_storage.deletion import (
    DeletionPolicy,
    DeletionResult,
    delete_paths,
    temporary_deletion_policy,
)
from velvet_bot.domains.telegram_storage.encryption import (
    StorageEncryptionUnavailable,
    decrypt_file,
    encrypt_file,
    sha256_file,
)

_CHUNK_BYTES = 1024 * 1024






def safe_token(value: str, *, fallback: str = "artifact", limit: int = 80) -> str:
    cleaned = re.sub(r"[^0-9A-Za-zА-Яа-я._-]+", "-", value.strip())
    cleaned = cleaned.strip("-._") or fallback
    return cleaned[:limit]


def storage_message_link(chat_id: int, message_id: int) -> str:
    raw = str(abs(int(chat_id)))
    internal_id = raw[3:] if raw.startswith("100") else raw
    return f"https://t.me/c/{internal_id}/{int(message_id)}"


def build_zip(
    destination: Path,
    *,
    files: dict[str, Path],
    text_entries: dict[str, str] | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as archive:
        for archive_name, path in sorted(files.items()):
            if path.is_file():
                archive.write(path, arcname=archive_name)
        for archive_name, content in sorted((text_entries or {}).items()):
            archive.writestr(archive_name, content)
    return destination


def zip_directory(source: Path, destination: Path) -> Path:
    files: dict[str, Path] = {}
    for path in sorted(source.rglob("*")):
        if path.is_file():
            files[path.relative_to(source).as_posix()] = path
    return build_zip(destination, files=files)



def split_file(source: Path, directory: Path, max_part_bytes: int) -> tuple[Path, ...]:
    if source.stat().st_size <= max_part_bytes:
        return (source,)
    directory.mkdir(parents=True, exist_ok=True)
    total = (source.stat().st_size + max_part_bytes - 1) // max_part_bytes
    parts: list[Path] = []
    with source.open("rb") as stream:
        for index in range(1, total + 1):
            part = directory / f"{source.name}.part{index:03d}-of-{total:03d}"
            part.unlink(missing_ok=True)
            with part.open("wb") as output:
                remaining = max_part_bytes
                while remaining > 0:
                    block = stream.read(min(_CHUNK_BYTES, remaining))
                    if not block:
                        break
                    output.write(block)
                    remaining -= len(block)
            parts.append(part)
    return tuple(parts)


def remove_paths(
    paths: Iterable[Path],
    *,
    policy: DeletionPolicy | None = None,
    dry_run: bool = False,
) -> DeletionResult:
    selected_policy = policy or temporary_deletion_policy()
    return delete_paths(paths, policy=selected_policy, dry_run=dry_run)


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


__all__ = (
    "DeletionPolicy",
    "DeletionResult",
    "StorageEncryptionUnavailable",
    "build_zip",
    "decrypt_file",
    "encrypt_file",
    "remove_paths",
    "safe_token",
    "sha256_file",
    "split_file",
    "storage_message_link",
    "write_json",
    "zip_directory",
)
