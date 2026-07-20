from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, Message

from velvet_bot.domains.watermark.archive_output import ArchiveWatermarkOutput
from velvet_bot.domains.watermark.models import WatermarkWorkItem
from velvet_bot.infrastructure.krita_bridge import KritaBridge

DEFAULT_WATERMARK_STORAGE_CHAT_ID = -1004459280894
DEFAULT_WATERMARK_STORAGE_THREAD_ID = 3


@dataclass(frozen=True, slots=True)
class WatermarkStorageSettings:
    chat_id: int
    thread_id: int | None

    @classmethod
    def from_env(cls) -> "WatermarkStorageSettings":
        chat_raw = os.getenv(
            "WATERMARK_STORAGE_CHAT_ID",
            str(DEFAULT_WATERMARK_STORAGE_CHAT_ID),
        ).strip()
        thread_raw = os.getenv(
            "WATERMARK_STORAGE_THREAD_ID",
            str(DEFAULT_WATERMARK_STORAGE_THREAD_ID),
        ).strip()
        try:
            chat_id = int(chat_raw)
        except ValueError as error:
            raise ValueError("WATERMARK_STORAGE_CHAT_ID должен быть числом.") from error
        try:
            thread_id = int(thread_raw) if thread_raw else None
        except ValueError as error:
            raise ValueError("WATERMARK_STORAGE_THREAD_ID должен быть числом.") from error
        return cls(chat_id=chat_id, thread_id=thread_id)


@dataclass(frozen=True, slots=True)
class StoredWatermark:
    message: Message
    sha256: str
    file_name: str
    file_size: int
    message_link: str


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def storage_message_link(chat_id: int, message_id: int) -> str:
    raw = str(abs(int(chat_id)))
    internal_id = raw[3:] if raw.startswith("100") else raw
    return f"https://t.me/c/{internal_id}/{int(message_id)}"


def storage_file_name(
    *,
    media_id: int,
    job_id: int,
    revision: int,
    sha256: str,
) -> str:
    return (
        f"velvet-wm-m{int(media_id)}-j{int(job_id)}-"
        f"r{int(revision)}-{sha256[:12]}.png"
    )


def storage_caption(
    *,
    media_id: int,
    job_id: int,
    revision: int,
    sha256: str,
    output: ArchiveWatermarkOutput,
    source_name: str,
    character_names: tuple[str, ...],
    item: WatermarkWorkItem,
) -> str:
    settings = item.revision.settings.normalized()
    characters = ", ".join(character_names) or "не привязан"
    return "\n".join(
        (
            f"#velvet_watermark #media_{media_id} #job_{job_id} #rev_{revision}",
            f"Media ID: {media_id}",
            f"Персонажи: {characters}",
            f"Исходник: {source_name}",
            f"SHA256: {sha256}",
            (
                f"Размер: {output.output_bytes / 1024 / 1024:.2f} МБ · "
                f"{output.width}×{output.height}"
            ),
            (
                "Шаблон: "
                f"{settings.position} / {settings.color.upper()} / "
                f"{settings.opacity}% / {settings.size:.1f}% / {settings.margin:.1f}%"
            ),
        )
    )[:1024]


async def store_archive_watermark(
    *,
    bot: Bot,
    item: WatermarkWorkItem,
    media_id: int,
    output: ArchiveWatermarkOutput,
    source_name: str,
    character_names: tuple[str, ...],
    settings: WatermarkStorageSettings | None = None,
) -> StoredWatermark:
    target = settings or WatermarkStorageSettings.from_env()
    digest = file_sha256(output.path)
    file_name = storage_file_name(
        media_id=media_id,
        job_id=item.job.id,
        revision=item.revision.revision,
        sha256=digest,
    )
    message = await bot.send_document(
        chat_id=target.chat_id,
        message_thread_id=target.thread_id,
        document=FSInputFile(output.path, filename=file_name),
        caption=storage_caption(
            media_id=media_id,
            job_id=item.job.id,
            revision=item.revision.revision,
            sha256=digest,
            output=output,
            source_name=source_name,
            character_names=character_names,
            item=item,
        ),
        disable_notification=True,
    )
    if message.document is None:
        raise ValueError("Telegram-хранилище не вернуло document file_id.")
    return StoredWatermark(
        message=message,
        sha256=digest,
        file_name=file_name,
        file_size=int(message.document.file_size or output.output_bytes),
        message_link=storage_message_link(target.chat_id, message.message_id),
    )


def cleanup_watermark_job_files(
    item: WatermarkWorkItem,
    bridge: KritaBridge,
) -> tuple[int, int]:
    candidates: set[Path] = set()
    source = bridge.paths.ensure_in(item.job.source_path, bridge.paths.sources)
    candidates.add(source)

    for directory in (
        bridge.paths.requests,
        bridge.paths.responses,
        bridge.paths.outputs,
        bridge.paths.previews,
    ):
        for path in directory.glob(f"job-{item.job.id}-r*"):
            candidates.add(bridge.paths.ensure_in(path, directory))

    deleted = 0
    freed = 0
    for path in candidates:
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError:
            continue
        deleted += 1
        freed += size
    return deleted, freed


__all__ = (
    "DEFAULT_WATERMARK_STORAGE_CHAT_ID",
    "DEFAULT_WATERMARK_STORAGE_THREAD_ID",
    "StoredWatermark",
    "WatermarkStorageSettings",
    "cleanup_watermark_job_files",
    "file_sha256",
    "storage_caption",
    "storage_file_name",
    "storage_message_link",
    "store_archive_watermark",
)
