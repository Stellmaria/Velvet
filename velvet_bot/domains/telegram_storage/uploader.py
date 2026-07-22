from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import FSInputFile

from velvet_bot.domains.telegram_storage.files import (
    remove_paths,
    safe_token,
    sha256_file,
    split_file,
)
from velvet_bot.domains.telegram_storage.models import (
    StorageCandidate,
    StoredObject,
    StoredPart,
    TelegramStorageSettings,
)
from velvet_bot.domains.telegram_storage.repository import TelegramStorageRepository

logger = logging.getLogger(__name__)


class TelegramStorageUploader:
    _MIN_SEND_INTERVAL_SECONDS = 1.1
    _FLOOD_RETRY_CUSHION_SECONDS = 1.0
    _MAX_SEND_ATTEMPTS = 5
    _TRANSIENT_RETRY_BASE_SECONDS = 2.0
    _TRANSIENT_RETRY_MAX_SECONDS = 30.0

    def __init__(
        self,
        *,
        bot: Bot,
        repository: TelegramStorageRepository,
        settings: TelegramStorageSettings,
    ) -> None:
        self._bot = bot
        self._repository = repository
        self._settings = settings
        self._send_lock = asyncio.Lock()
        self._next_send_at = 0.0

    @staticmethod
    def _caption(
        candidate: StorageCandidate,
        *,
        sha256: str,
        size_bytes: int,
        part_number: int,
        part_count: int,
    ) -> str:
        encrypted = "да" if candidate.encrypted else "нет"
        lines = [
            (
                f"#velvet_storage #storage_{candidate.kind} "
                f"#sha_{sha256[:12]}"
            ),
            f"Ключ: {candidate.logical_key}",
            f"Файл: {candidate.original_name}",
            f"Размер: {size_bytes / 1024 / 1024:.2f} МБ",
            f"SHA256: {sha256}",
            f"Шифрование: {encrypted}",
        ]
        if part_count > 1:
            lines.append(f"Часть: {part_number}/{part_count}")
        return "\n".join(lines)[:1024]

    async def _wait_for_send_slot(self) -> None:
        delay = self._next_send_at - asyncio.get_running_loop().time()
        if delay > 0:
            await asyncio.sleep(delay)

    async def _send_document(self, **kwargs: Any) -> Any:
        async with self._send_lock:
            await self._wait_for_send_slot()
            loop = asyncio.get_running_loop()
            for attempt in range(1, self._MAX_SEND_ATTEMPTS + 1):
                try:
                    message = await self._bot.send_document(**kwargs)
                except TelegramRetryAfter as error:
                    if attempt >= self._MAX_SEND_ATTEMPTS:
                        raise
                    delay = max(float(error.retry_after), 0.0) + (
                        self._FLOOD_RETRY_CUSHION_SECONDS
                    )
                    self._next_send_at = max(self._next_send_at, loop.time() + delay)
                    logger.info(
                        "Telegram storage flood control chat=%s retry_after=%.1fs "
                        "attempt=%s/%s",
                        kwargs.get("chat_id"),
                        delay,
                        attempt,
                        self._MAX_SEND_ATTEMPTS,
                    )
                    await asyncio.sleep(delay)
                    continue
                except (TelegramNetworkError, TelegramServerError) as error:
                    if attempt >= self._MAX_SEND_ATTEMPTS:
                        raise
                    delay = min(
                        self._TRANSIENT_RETRY_BASE_SECONDS * (2 ** (attempt - 1)),
                        self._TRANSIENT_RETRY_MAX_SECONDS,
                    )
                    self._next_send_at = max(self._next_send_at, loop.time() + delay)
                    logger.info(
                        "Telegram storage transient send failure chat=%s delay=%.1fs "
                        "attempt=%s/%s error=%s",
                        kwargs.get("chat_id"),
                        delay,
                        attempt,
                        self._MAX_SEND_ATTEMPTS,
                        error,
                    )
                    await asyncio.sleep(delay)
                    continue
                self._next_send_at = loop.time() + self._MIN_SEND_INTERVAL_SECONDS
                return message
        raise RuntimeError("Telegram storage send retry loop exhausted unexpectedly.")

    async def upload(
        self,
        candidate: StorageCandidate,
        *,
        manifest: dict[str, Any] | None = None,
        encryption_version: str | None = None,
    ) -> tuple[StoredObject, int, int, bool]:
        path = candidate.path.resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = sha256_file(path)
        size_bytes = path.stat().st_size
        existing = await self._repository.get_existing(
            candidate.kind,
            candidate.logical_key,
            digest,
        )
        if existing is not None:
            deleted = freed = 0
            if self._settings.delete_after_upload and candidate.delete_paths:
                deleted, freed = remove_paths(candidate.delete_paths)
                if deleted:
                    await self._repository.mark_local_deleted(existing.object_id)
            return existing, deleted, freed, True

        thread_id = self._settings.threads.for_kind(candidate.kind)
        part_dir = self._settings.staging_dir / "parts" / (
            safe_token(candidate.logical_key) + "-" + digest[:12]
        )
        part_paths = split_file(path, part_dir, self._settings.max_part_bytes)
        sent_messages: list[tuple[int, int]] = []
        stored_parts: list[StoredPart] = []
        try:
            for index, part_path in enumerate(part_paths, start=1):
                part_digest = sha256_file(part_path)
                message = await self._send_document(
                    chat_id=self._settings.chat_id,
                    message_thread_id=thread_id,
                    document=FSInputFile(part_path, filename=part_path.name),
                    caption=self._caption(
                        candidate,
                        sha256=digest,
                        size_bytes=size_bytes,
                        part_number=index,
                        part_count=len(part_paths),
                    ),
                    disable_notification=True,
                )
                if message.document is None:
                    raise ValueError("Telegram не вернул document file_id.")
                sent_messages.append((self._settings.chat_id, message.message_id))
                stored_parts.append(
                    StoredPart(
                        part_number=index,
                        message_id=message.message_id,
                        telegram_file_id=message.document.file_id,
                        telegram_file_unique_id=message.document.file_unique_id,
                        size_bytes=int(message.document.file_size or part_path.stat().st_size),
                        sha256=part_digest,
                    )
                )

            payload = dict(manifest or {})
            payload.update(candidate.metadata)
            payload.update(
                {
                    "source_path": candidate.source_path,
                    "original_name": candidate.original_name,
                    "multipart": len(part_paths) > 1,
                    "part_count": len(part_paths),
                }
            )
            stored = await self._repository.create_object(
                candidate=candidate,
                sha256=digest,
                size_bytes=size_bytes,
                chat_id=self._settings.chat_id,
                thread_id=thread_id,
                parts=tuple(stored_parts),
                manifest=payload,
                encryption_version=encryption_version,
            )
        except Exception:  # p2-approved-boundary: isolate-telegram-storage-operation
            for chat_id, message_id in sent_messages:
                try:
                    await self._bot.delete_message(chat_id=chat_id, message_id=message_id)
                except TelegramAPIError:
                    logger.warning(
                        "Could not delete orphan storage message chat=%s message=%s",
                        chat_id,
                        message_id,
                    )
            raise
        finally:
            if len(part_paths) > 1:
                remove_paths(part_paths)
                try:
                    part_dir.rmdir()
                except OSError:
                    pass

        deleted = freed = 0
        if self._settings.delete_after_upload and candidate.delete_paths:
            deleted, freed = remove_paths(candidate.delete_paths)
            if deleted:
                await self._repository.mark_local_deleted(stored.object_id)
        return stored, deleted, freed, False


__all__ = ("TelegramStorageUploader",)
