from __future__ import annotations

import io
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import Message

from velvet_bot.application.owner_analytics import ImportResult, import_export_payload
from velvet_bot.database import Database

BOT_DOWNLOAD_LIMIT = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class DownloadedExport:
    payload: bytes
    file_name: str


async def download_export_document(message: Message, bot: Bot) -> DownloadedExport:
    source = message if message.document is not None else message.reply_to_message
    document = source.document if source is not None else None
    if document is None:
        raise ValueError("Отправьте result.json или ZIP экспорта Telegram ответом на форму.")
    file_name = document.file_name or "result.json"
    if not file_name.casefold().endswith((".json", ".zip")):
        raise ValueError("Поддерживаются только result.json и ZIP экспорта Telegram.")
    if document.file_size and document.file_size > BOT_DOWNLOAD_LIMIT:
        raise ValueError(
            "Файл больше 20 МБ. Извлеките из ZIP только result.json либо "
            "используйте локальный скрипт импорта."
        )
    destination = io.BytesIO()
    await bot.download(document.file_id, destination=destination, seek=True)
    payload = destination.getvalue()
    if not payload:
        raise ValueError("Telegram вернул пустой файл.")
    return DownloadedExport(payload=payload, file_name=file_name)


async def import_export_from_message(
    database: Database,
    bot: Bot,
    message: Message,
    *,
    analytics_channel_ids: frozenset[int],
    source_kind: str,
    target_chat_value: str | None,
    imported_by: int | None,
) -> ImportResult:
    downloaded = await download_export_document(message, bot)
    return await import_export_payload(
        database,
        analytics_channel_ids,
        raw=downloaded.payload,
        file_name=downloaded.file_name,
        source_kind=source_kind,
        target_chat_value=target_chat_value,
        imported_by=imported_by,
    )


__all__ = (
    "BOT_DOWNLOAD_LIMIT",
    "DownloadedExport",
    "download_export_document",
    "import_export_from_message",
)
