from __future__ import annotations

import hashlib
import mimetypes
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from aiogram import Bot
from aiogram.types import ExternalReplyInfo, Message

_INVALID_FILE_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

MediaSource: TypeAlias = Message | ExternalReplyInfo


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
    return normalized or "media"


def build_storage_file_name(
    original_file_name: str | None,
    telegram_file_unique_id: str,
    *,
    default_extension: str,
    default_stem: str = "photo",
) -> str:
    """Build a deterministic name so one Telegram file always has one archive name."""
    digest = hashlib.sha256(
        telegram_file_unique_id.encode("utf-8")
    ).hexdigest()[:24]

    if original_file_name:
        safe_original = sanitize_file_name(original_file_name)
        suffix = Path(safe_original).suffix.lower()
        stem = Path(safe_original).stem.strip(" .") or default_stem
    else:
        suffix = default_extension
        stem = default_stem

    if not suffix:
        suffix = default_extension
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"

    return f"{stem}__{digest}{suffix.lower()}"


def extract_media(source: MediaSource) -> MediaDescriptor | None:
    """Extract supported media from a normal or external Telegram reply."""
    if source.photo:
        photo = source.photo[-1]
        return MediaDescriptor(
            telegram_file_id=photo.file_id,
            telegram_file_unique_id=photo.file_unique_id,
            original_file_name=None,
            storage_file_name=build_storage_file_name(
                None,
                photo.file_unique_id,
                default_extension=".jpg",
                default_stem="photo",
            ),
            media_type="photo",
            mime_type="image/jpeg",
            file_size=photo.file_size,
        )

    if source.video:
        video = source.video
        original_name = video.file_name
        return MediaDescriptor(
            telegram_file_id=video.file_id,
            telegram_file_unique_id=video.file_unique_id,
            original_file_name=original_name,
            storage_file_name=build_storage_file_name(
                original_name,
                video.file_unique_id,
                default_extension=".mp4",
                default_stem="video",
            ),
            media_type="video",
            mime_type=video.mime_type or "video/mp4",
            file_size=video.file_size,
        )

    if source.animation:
        animation = source.animation
        original_name = animation.file_name
        guessed_extension = (
            mimetypes.guess_extension(animation.mime_type or "") or ".mp4"
        )
        return MediaDescriptor(
            telegram_file_id=animation.file_id,
            telegram_file_unique_id=animation.file_unique_id,
            original_file_name=original_name,
            storage_file_name=build_storage_file_name(
                original_name,
                animation.file_unique_id,
                default_extension=guessed_extension,
                default_stem="animation",
            ),
            media_type="animation",
            mime_type=animation.mime_type,
            file_size=animation.file_size,
        )

    document = source.document
    mime_type = document.mime_type if document else None
    if document and (
        (mime_type or "").startswith("image/")
        or (mime_type or "").startswith("video/")
    ):
        guessed_extension = mimetypes.guess_extension(mime_type or "") or ".bin"
        default_stem = (
            "video" if (mime_type or "").startswith("video/") else "image"
        )
        return MediaDescriptor(
            telegram_file_id=document.file_id,
            telegram_file_unique_id=document.file_unique_id,
            original_file_name=document.file_name,
            storage_file_name=build_storage_file_name(
                document.file_name,
                document.file_unique_id,
                default_extension=guessed_extension,
                default_stem=default_stem,
            ),
            media_type="document",
            mime_type=mime_type,
            file_size=document.file_size,
        )

    return None


extract_image = extract_media


async def send_media_to_topic(
    bot: Bot,
    media: MediaDescriptor,
    *,
    chat_id: int,
    thread_id: int,
    caption: str | None = None,
    is_spoiler: bool = False,
) -> Message:
    """Place only the media itself in a topic, without captions or service text."""
    del caption
    common = {
        "chat_id": chat_id,
        "message_thread_id": thread_id,
    }

    if media.media_type == "photo":
        return await bot.send_photo(
            photo=media.telegram_file_id,
            has_spoiler=is_spoiler,
            **common,
        )
    if media.media_type == "video":
        return await bot.send_video(
            video=media.telegram_file_id,
            has_spoiler=is_spoiler,
            **common,
        )
    if media.media_type == "animation":
        return await bot.send_animation(
            animation=media.telegram_file_id,
            has_spoiler=is_spoiler,
            **common,
        )
    return await bot.send_document(document=media.telegram_file_id, **common)
