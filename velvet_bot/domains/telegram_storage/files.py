from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Iterable

_MAGIC = b"VELVET-AESGCM1\n"
_SALT_BYTES = 16
_NONCE_BYTES = 12
_TAG_BYTES = 16
_CHUNK_BYTES = 1024 * 1024


class StorageEncryptionUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _crypto_components():
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ModuleNotFoundError as error:
        raise StorageEncryptionUnavailable(
            "Для шифрования резервных копий не установлен пакет cryptography. "
            "Supervisor должен синхронизировать requirements.txt перед запуском."
        ) from error
    return Cipher, algorithms, modes, Scrypt


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(_CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


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


def _derive_key(secret: str, salt: bytes) -> bytes:
    _, _, _, scrypt = _crypto_components()
    return scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(
        secret.encode("utf-8")
    )


def encrypt_file(source: Path, destination: Path, secret: str) -> Path:
    cipher, algorithms, modes, _ = _crypto_components()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    salt = os.urandom(_SALT_BYTES)
    nonce = os.urandom(_NONCE_BYTES)
    encryptor = cipher(
        algorithms.AES(_derive_key(secret, salt)),
        modes.GCM(nonce),
    ).encryptor()
    with source.open("rb") as input_stream, destination.open("wb") as output_stream:
        output_stream.write(_MAGIC)
        output_stream.write(salt)
        output_stream.write(nonce)
        for block in iter(lambda: input_stream.read(_CHUNK_BYTES), b""):
            output_stream.write(encryptor.update(block))
        output_stream.write(encryptor.finalize())
        output_stream.write(encryptor.tag)
    return destination


def decrypt_file(source: Path, destination: Path, secret: str) -> Path:
    cipher, algorithms, modes, _ = _crypto_components()
    size = source.stat().st_size
    header_size = len(_MAGIC) + _SALT_BYTES + _NONCE_BYTES
    if size <= header_size + _TAG_BYTES:
        raise ValueError("Зашифрованный файл слишком короткий.")
    with source.open("rb") as input_stream:
        if input_stream.read(len(_MAGIC)) != _MAGIC:
            raise ValueError("Неизвестный формат зашифрованного архива.")
        salt = input_stream.read(_SALT_BYTES)
        nonce = input_stream.read(_NONCE_BYTES)
        input_stream.seek(-_TAG_BYTES, os.SEEK_END)
        tag = input_stream.read(_TAG_BYTES)
        input_stream.seek(header_size)
        remaining = size - header_size - _TAG_BYTES
        decryptor = cipher(
            algorithms.AES(_derive_key(secret, salt)),
            modes.GCM(nonce, tag),
        ).decryptor()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.unlink(missing_ok=True)
        with destination.open("wb") as output_stream:
            while remaining > 0:
                block = input_stream.read(min(_CHUNK_BYTES, remaining))
                if not block:
                    raise ValueError("Зашифрованный файл оборван.")
                remaining -= len(block)
                output_stream.write(decryptor.update(block))
            output_stream.write(decryptor.finalize())
    return destination


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


def remove_paths(paths: Iterable[Path]) -> tuple[int, int]:
    deleted = 0
    freed = 0
    unique = sorted({path.resolve() for path in paths}, key=lambda value: len(value.parts), reverse=True)
    for path in unique:
        try:
            if path.is_file() or path.is_symlink():
                size = path.stat().st_size if path.exists() else 0
                path.unlink(missing_ok=True)
                deleted += 1
                freed += size
            elif path.is_dir():
                size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
                shutil.rmtree(path)
                deleted += 1
                freed += size
        except OSError:
            continue
    return deleted, freed


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


__all__ = (
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
