from __future__ import annotations

import hashlib
import mimetypes
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from aiogram.types import Message

_INVALID_FILE_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True, slots=True)
class MediaDescriptor:
    telegram_file_id: str
    telegram_file_unique_id: str
    original_file_name: str | None
    storage_file_name: str
    media_type: str
    mime_type: str | None
    file_size: int | None


def sanitize_file_name(value: str) -> str:
    """Return a portable file name without changing the stored original name."""
    normalized = unicodedata.normalize("NFKC", Path(value).name)
    normalized = _INVALID_FILE_NAME_CHARS.sub("_", normalized)
    normalized = " ".join(normalized.split()).strip(" .")
    return normalized or "image"


def build_storage_file_name(
    original_file_name: str | None,
    telegram_file_unique_id: str,
    *,
    default_extension: str,
) -> str:
    """Build a deterministic name so one Telegram file always has one archive name."""
    digest = hashlib.sha256(
        telegram_file_unique_id.encode("utf-8")
    ).hexdigest()[:24]

    if original_file_name:
        safe_original = sanitize_file_name(original_file_name)
        suffix = Path(safe_original).suffix.lower()
        stem = Path(safe_original).stem.strip(" .") or "image"
    else:
        suffix = default_extension
        stem = "photo"

    if not suffix:
        suffix = default_extension
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"

    return f"{stem}__{digest}{suffix.lower()}"


def extract_image(message: Message) -> MediaDescriptor | None:
    """Extract a Telegram photo or an image sent as a document."""
    if message.photo:
        photo = message.photo[-1]
        return MediaDescriptor(
            telegram_file_id=photo.file_id,
            telegram_file_unique_id=photo.file_unique_id,
            original_file_name=None,
            storage_file_name=build_storage_file_name(
                None,
                photo.file_unique_id,
                default_extension=".jpg",
            ),
            media_type="photo",
            mime_type="image/jpeg",
            file_size=photo.file_size,
        )

    document = message.document
    if document and (document.mime_type or "").startswith("image/"):
        guessed_extension = (
            mimetypes.guess_extension(document.mime_type or "") or ".bin"
        )
        return MediaDescriptor(
            telegram_file_id=document.file_id,
            telegram_file_unique_id=document.file_unique_id,
            original_file_name=document.file_name,
            storage_file_name=build_storage_file_name(
                document.file_name,
                document.file_unique_id,
                default_extension=guessed_extension,
            ),
            media_type="document",
            mime_type=document.mime_type,
            file_size=document.file_size,
        )

    return None
