from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

_MAGIC_V1 = b"VELVET-AESGCM1\n"
_MAGIC_V2 = b"VELVET-AESGCM2\n"
_SALT_BYTES = 16
_NONCE_BYTES = 12
_TAG_BYTES = 16
_CHUNK_BYTES = 1024 * 1024
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class StorageEncryptionUnavailable(RuntimeError):
    pass


class UnknownStorageEncryptionKey(ValueError):
    def __init__(self, key_id: str | None) -> None:
        label = key_id or "<legacy-v1>"
        super().__init__(
            f"Ключ расшифровки backup недоступен: key_id={label}. "
            "Добавьте его в STORAGE_ENCRYPTION_KEYRING до restore."
        )
        self.key_id = key_id


@dataclass(frozen=True, slots=True)
class EncryptedFileHeader:
    version: int
    key_id: str | None
    header_bytes: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class StorageEncryptionKeyring:
    active_key_id: str
    keys: Mapping[str, str] = field(repr=False)
    legacy_key_id: str | None = None

    def __post_init__(self) -> None:
        normalized = dict(self.keys)
        _validate_key_id(self.active_key_id)
        if self.active_key_id not in normalized:
            raise ValueError(
                "STORAGE_ENCRYPTION_ACTIVE_KEY_ID отсутствует в keyring."
            )
        if self.legacy_key_id is not None:
            _validate_key_id(self.legacy_key_id)
            if self.legacy_key_id not in normalized:
                raise ValueError(
                    "STORAGE_ENCRYPTION_LEGACY_KEY_ID отсутствует в keyring."
                )
        for key_id, secret in normalized.items():
            _validate_key_id(key_id)
            if len(secret) < 24:
                raise ValueError(
                    f"Ключ backup {key_id} должен содержать не менее 24 символов."
                )
        object.__setattr__(self, "keys", normalized)

    @property
    def active_secret(self) -> str:
        return self.keys[self.active_key_id]

    @property
    def key_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.keys))

    def has_key(self, key_id: str | None) -> bool:
        selected = self.legacy_key_id if key_id is None else key_id
        return selected is not None and selected in self.keys

    def secret_for(self, key_id: str | None) -> str:
        selected = self.legacy_key_id if key_id is None else key_id
        if selected is None or selected not in self.keys:
            raise UnknownStorageEncryptionKey(key_id)
        return self.keys[selected]

    def public_status(self) -> dict[str, object]:
        return {
            "active_key_id": self.active_key_id,
            "available_key_ids": list(self.key_ids),
            "legacy_v1_key_id": self.legacy_key_id,
        }


def _validate_key_id(key_id: str) -> None:
    if not _KEY_ID_RE.fullmatch(key_id):
        raise ValueError(
            "Storage encryption key ID должен состоять из 1–64 символов "
            "A-Z, a-z, 0-9, '.', '_' или '-'."
        )


def keyring_from_env(values: Mapping[str, str] | None = None) -> StorageEncryptionKeyring:
    env = os.environ if values is None else values
    active_key_id = (
        str(env.get("STORAGE_ENCRYPTION_ACTIVE_KEY_ID", "")).strip()
        or "primary-v1"
    )
    active_secret = str(env.get("STORAGE_ENCRYPTION_SECRET", "")).strip()
    if len(active_secret) < 24:
        raise ValueError(
            "Для шифрования backup задайте отдельный STORAGE_ENCRYPTION_SECRET "
            "минимум из 24 символов."
        )

    raw_keyring = str(env.get("STORAGE_ENCRYPTION_KEYRING", "")).strip()
    historical: dict[str, str] = {}
    if raw_keyring:
        try:
            payload = json.loads(raw_keyring)
        except json.JSONDecodeError as error:
            raise ValueError(
                "STORAGE_ENCRYPTION_KEYRING должен быть JSON-объектом key_id:secret."
            ) from error
        if not isinstance(payload, dict):
            raise ValueError(
                "STORAGE_ENCRYPTION_KEYRING должен быть JSON-объектом key_id:secret."
            )
        for raw_id, raw_secret in payload.items():
            if not isinstance(raw_id, str) or not isinstance(raw_secret, str):
                raise ValueError(
                    "STORAGE_ENCRYPTION_KEYRING принимает только строковые key ID и secrets."
                )
            historical[raw_id.strip()] = raw_secret.strip()

    conflicting = historical.get(active_key_id)
    if conflicting is not None and conflicting != active_secret:
        raise ValueError(
            "Активный key ID задан в STORAGE_ENCRYPTION_KEYRING с другим secret."
        )
    historical[active_key_id] = active_secret
    legacy_key_id = (
        str(env.get("STORAGE_ENCRYPTION_LEGACY_KEY_ID", "")).strip() or None
    )
    return StorageEncryptionKeyring(
        active_key_id=active_key_id,
        keys=historical,
        legacy_key_id=legacy_key_id,
    )


def _crypto_components():
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ModuleNotFoundError as error:
        raise StorageEncryptionUnavailable(
            "Для шифрования резервных копий не установлен пакет cryptography."
        ) from error
    return Cipher, algorithms, modes, Scrypt


def _derive_key(secret: str, salt: bytes) -> bytes:
    _, _, _, scrypt = _crypto_components()
    return scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(
        secret.encode("utf-8")
    )


def inspect_encrypted_file(source: str | Path) -> EncryptedFileHeader:
    path = Path(source)
    with path.open("rb") as stream:
        magic = stream.read(len(_MAGIC_V2))
        if magic == _MAGIC_V2:
            raw_length = stream.read(2)
            if len(raw_length) != 2:
                raise ValueError("Повреждён заголовок encrypted backup.")
            key_id_length = struct.unpack(">H", raw_length)[0]
            if not 1 <= key_id_length <= 64:
                raise ValueError("Некорректная длина key ID encrypted backup.")
            raw_key_id = stream.read(key_id_length)
            if len(raw_key_id) != key_id_length:
                raise ValueError("Повреждён key ID encrypted backup.")
            try:
                key_id = raw_key_id.decode("ascii")
            except UnicodeDecodeError as error:
                raise ValueError("Key ID encrypted backup должен быть ASCII.") from error
            _validate_key_id(key_id)
            header = magic + raw_length + raw_key_id
            return EncryptedFileHeader(version=2, key_id=key_id, header_bytes=header)
        if magic == _MAGIC_V1:
            return EncryptedFileHeader(version=1, key_id=None, header_bytes=_MAGIC_V1)
    raise ValueError("Неизвестный формат зашифрованного архива.")


def _temporary_destination(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".partial",
        dir=destination.parent,
    )
    os.close(descriptor)
    return Path(name)


def encrypt_file(
    source: str | Path,
    destination: str | Path,
    keyring: StorageEncryptionKeyring | str,
    *,
    key_id: str | None = None,
) -> Path:
    source_path = Path(source)
    destination_path = Path(destination)
    if isinstance(keyring, str):
        selected_key_id = key_id or "primary-v1"
        selected = StorageEncryptionKeyring(
            active_key_id=selected_key_id,
            keys={selected_key_id: keyring},
        )
    else:
        selected = keyring
        selected_key_id = key_id or selected.active_key_id
    secret = selected.secret_for(selected_key_id)
    raw_key_id = selected_key_id.encode("ascii")
    salt = os.urandom(_SALT_BYTES)
    nonce = os.urandom(_NONCE_BYTES)
    header = _MAGIC_V2 + struct.pack(">H", len(raw_key_id)) + raw_key_id

    cipher, algorithms, modes, _ = _crypto_components()
    encryptor = cipher(
        algorithms.AES(_derive_key(secret, salt)),
        modes.GCM(nonce),
    ).encryptor()
    encryptor.authenticate_additional_data(header)

    temporary = _temporary_destination(destination_path)
    completed = False
    try:
        with source_path.open("rb") as input_stream, temporary.open("wb") as output_stream:
            output_stream.write(header)
            output_stream.write(salt)
            output_stream.write(nonce)
            for block in iter(lambda: input_stream.read(_CHUNK_BYTES), b""):
                output_stream.write(encryptor.update(block))
            output_stream.write(encryptor.finalize())
            output_stream.write(encryptor.tag)
        os.replace(temporary, destination_path)
        completed = True
    finally:
        if not completed:
            temporary.unlink(missing_ok=True)
    return destination_path


def encrypt_legacy_v1_file(
    source: str | Path,
    destination: str | Path,
    secret: str,
) -> Path:
    if len(secret) < 24:
        raise ValueError("Legacy backup secret должен содержать не менее 24 символов.")
    source_path = Path(source)
    destination_path = Path(destination)
    salt = os.urandom(_SALT_BYTES)
    nonce = os.urandom(_NONCE_BYTES)
    cipher, algorithms, modes, _ = _crypto_components()
    encryptor = cipher(
        algorithms.AES(_derive_key(secret, salt)),
        modes.GCM(nonce),
    ).encryptor()
    temporary = _temporary_destination(destination_path)
    completed = False
    try:
        with source_path.open("rb") as input_stream, temporary.open("wb") as output_stream:
            output_stream.write(_MAGIC_V1)
            output_stream.write(salt)
            output_stream.write(nonce)
            for block in iter(lambda: input_stream.read(_CHUNK_BYTES), b""):
                output_stream.write(encryptor.update(block))
            output_stream.write(encryptor.finalize())
            output_stream.write(encryptor.tag)
        os.replace(temporary, destination_path)
        completed = True
    finally:
        if not completed:
            temporary.unlink(missing_ok=True)
    return destination_path


def decrypt_file(
    source: str | Path,
    destination: str | Path,
    keyring: StorageEncryptionKeyring | str,
) -> Path:
    source_path = Path(source)
    destination_path = Path(destination)
    header = inspect_encrypted_file(source_path)
    if isinstance(keyring, str):
        selected = StorageEncryptionKeyring(
            active_key_id="primary-v1",
            keys={"primary-v1": keyring},
            legacy_key_id="primary-v1",
        )
    else:
        selected = keyring
    secret = selected.secret_for(header.key_id)

    header_size = len(header.header_bytes) + _SALT_BYTES + _NONCE_BYTES
    size = source_path.stat().st_size
    if size <= header_size + _TAG_BYTES:
        raise ValueError("Зашифрованный файл слишком короткий.")

    cipher, algorithms, modes, _ = _crypto_components()
    temporary = _temporary_destination(destination_path)
    completed = False
    try:
        with source_path.open("rb") as input_stream:
            actual_header = input_stream.read(len(header.header_bytes))
            if actual_header != header.header_bytes:
                raise ValueError("Encrypted backup header изменился во время чтения.")
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
            if header.version == 2:
                decryptor.authenticate_additional_data(header.header_bytes)
            with temporary.open("wb") as output_stream:
                while remaining > 0:
                    block = input_stream.read(min(_CHUNK_BYTES, remaining))
                    if not block:
                        raise ValueError("Зашифрованный файл оборван.")
                    remaining -= len(block)
                    output_stream.write(decryptor.update(block))
                output_stream.write(decryptor.finalize())
        os.replace(temporary, destination_path)
        completed = True
    finally:
        if not completed:
            temporary.unlink(missing_ok=True)
    return destination_path


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(_CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def reencrypt_file(
    source: str | Path,
    destination: str | Path,
    keyring: StorageEncryptionKeyring,
) -> Path:
    source_path = Path(source)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="velvet-backup-reencrypt-",
        dir=destination_path.parent,
    ) as directory:
        root = Path(directory)
        plaintext = root / "payload.bin"
        candidate = root / "candidate.velvet.enc"
        verified = root / "verified.bin"
        decrypt_file(source_path, plaintext, keyring)
        expected = sha256_file(plaintext)
        encrypt_file(plaintext, candidate, keyring)
        decrypt_file(candidate, verified, keyring)
        if sha256_file(verified) != expected:
            raise ValueError("Re-encryption verification failed.")
        os.replace(candidate, destination_path)
    return destination_path


__all__ = (
    "EncryptedFileHeader",
    "StorageEncryptionKeyring",
    "StorageEncryptionUnavailable",
    "UnknownStorageEncryptionKey",
    "decrypt_file",
    "encrypt_file",
    "encrypt_legacy_v1_file",
    "inspect_encrypted_file",
    "keyring_from_env",
    "reencrypt_file",
    "sha256_file",
)
