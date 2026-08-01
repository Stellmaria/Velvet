from __future__ import annotations

import asyncio
import hashlib
import io

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)

from velvet_bot.domains.telegram_storage.librarian_models import (
    LibrarianObject,
    LibrarianPart,
    StorageLibrarianError,
    UnsupportedStorageContent,
)


async def _download_part(bot: Bot, part: LibrarianPart) -> bytes:
    destination = io.BytesIO()
    try:
        await bot.download(
            part.telegram_file_id,
            destination=destination,
            timeout=90,
            seek=True,
        )
    except asyncio.CancelledError:
        raise
    except (
        TelegramBadRequest,
        TelegramNetworkError,
        TelegramAPIError,
        TimeoutError,
        OSError,
    ) as error:
        raise StorageLibrarianError(
            f"Не удалось скачать storage part {part.part_number}: {error}"
        ) from error
    value = destination.getvalue()
    if not value:
        raise StorageLibrarianError(
            f"Telegram вернул пустую storage part {part.part_number}."
        )
    if len(value) != part.size_bytes:
        raise StorageLibrarianError(
            f"Размер storage part {part.part_number} не совпадает: "
            f"{len(value)} != {part.size_bytes}."
        )
    if hashlib.sha256(value).hexdigest() != part.sha256:
        raise StorageLibrarianError(
            f"SHA256 storage part {part.part_number} не совпадает."
        )
    return value


async def download_storage_object(
    bot: Bot,
    item: LibrarianObject,
    *,
    max_bytes: int,
) -> bytes:
    if item.encrypted or item.storage_kind == "backups":
        raise UnsupportedStorageContent(
            "Encrypted backup никогда не передаётся Hermes."
        )
    if item.size_bytes > max_bytes:
        raise UnsupportedStorageContent(
            f"Объект больше лимита Librarian: {item.size_bytes} > {max_bytes}."
        )
    if not item.parts:
        raise StorageLibrarianError("У storage object отсутствуют Telegram parts.")

    chunks: list[bytes] = []
    total = 0
    for part in item.parts:
        value = await _download_part(bot, part)
        total += len(value)
        if total > max_bytes:
            raise UnsupportedStorageContent(
                "Multipart-объект превысил лимит Librarian."
            )
        chunks.append(value)

    result = b"".join(chunks)
    if len(result) != item.size_bytes:
        raise StorageLibrarianError(
            f"Размер собранного storage object не совпадает: "
            f"{len(result)} != {item.size_bytes}."
        )
    if hashlib.sha256(result).hexdigest() != item.sha256:
        raise StorageLibrarianError(
            "SHA256 собранного storage object не совпадает."
        )
    return result


__all__ = ("download_storage_object",)
