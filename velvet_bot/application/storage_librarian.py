from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from typing import cast

from aiogram import Bot

from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage.librarian_content import (
    analysis_prompt,
    extract_storage_text,
    parse_librarian_analysis,
    redact_sensitive,
)
from velvet_bot.domains.telegram_storage.librarian_models import (
    JsonValue,
    StorageLibrarianError,
    StorageLibrarianSettings,
    UnsupportedStorageContent,
)
from velvet_bot.domains.telegram_storage.librarian_repository import (
    StorageLibrarianRepository,
)
from velvet_bot.infrastructure.ai.storage_librarian_hermes import HermesRunsClient
from velvet_bot.infrastructure.telegram.storage_librarian_files import (
    download_storage_object,
)


def _json_list(value: object) -> list[JsonValue]:
    if isinstance(value, list):
        return cast(list[JsonValue], value)
    if isinstance(value, str):
        try:
            decoded: object = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(decoded, list):
            return cast(list[JsonValue], decoded)
    return []


class StorageLibrarianService:
    def __init__(
        self,
        *,
        bot: Bot,
        database: Database,
        settings: StorageLibrarianSettings | None = None,
    ) -> None:
        self.bot = bot
        self.settings = settings or StorageLibrarianSettings.from_env()
        self.repository = StorageLibrarianRepository(database)
        self.client = HermesRunsClient(self.settings)
        self.worker_id = f"storage-librarian:{os.getpid()}"

    async def process_once(self, *, auto_enqueue: bool = True) -> int:
        if not self.settings.enabled:
            return 0
        if auto_enqueue:
            await self.repository.enqueue_pending(settings=self.settings)
        job = await self.repository.claim_next(self.worker_id)
        if job is None:
            return 0
        try:
            item = await self.repository.load_object(job.storage_object_id)
            if item is None:
                raise StorageLibrarianError("Storage object исчез до анализа.")
            if item.storage_kind not in self.settings.allowed_kinds:
                raise UnsupportedStorageContent(
                    f"Категория {item.storage_kind} запрещена для Librarian."
                )
            source = await download_storage_object(
                self.bot,
                item,
                max_bytes=self.settings.max_object_bytes,
            )
            source_text = extract_storage_text(
                item,
                source,
                settings=self.settings,
            )
            run = await self.client.run(
                prompt=analysis_prompt(item, source_text),
                session_id=(
                    f"velvet-storage-{item.object_id}-"
                    f"{self.settings.analyzer_version}"
                ),
                instructions=(
                    "Ты библиотекарь закрытого Telegram Storage Velvet. Анализируй "
                    "только предоставленный текст, не вызывай инструменты и возвращай "
                    "строгий JSON без Markdown."
                ),
            )
            analysis = parse_librarian_analysis(run.output)
            await self.repository.complete(
                job=job,
                settings=self.settings,
                analysis=analysis,
                source_excerpt=source_text[:12000],
                run=run,
            )
            return 1
        except UnsupportedStorageContent as error:
            await self.repository.skip(
                job=job,
                settings=self.settings,
                reason=str(error),
            )
            return 1
        except asyncio.CancelledError:
            raise
        except Exception as error:  # p2-approved-boundary: isolate-storage-librarian-job
            await self.repository.fail(job, error)
            return 1

    async def answer(self, question: str) -> str:
        if not self.settings.enabled:
            raise StorageLibrarianError("Storage Librarian выключен.")
        rows = await self.repository.search_analyses(question, limit=8)
        if not rows:
            return "В проанализированном архиве совпадений пока нет."
        context: list[dict[str, object]] = []
        for row in rows:
            context.append(
                {
                    "storage_object_id": int(row["storage_object_id"]),
                    "kind": str(row["storage_kind"]),
                    "logical_key": str(row["logical_key"]),
                    "original_name": str(row["original_name"]),
                    "summary": str(row["summary"]),
                    "tags": _json_list(row["tags"]),
                    "entities": _json_list(row["entities"]),
                    "action_items": _json_list(row["action_items"]),
                    "analyzed_at": str(row["analyzed_at"]),
                }
            )
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        question_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]
        run = await self.client.run(
            prompt=(
                "Ответь на вопрос владельца Velvet только по приведённым индексированным "
                "резюме. Не используй инструменты и не выдумывай отсутствующие факты. "
                "Для каждого важного утверждения укажи Storage ID.\n\n"
                f"Вопрос: {redact_sensitive(question)[:2000]}\n\n"
                "Контекст:\n"
                + json.dumps(context, ensure_ascii=False, indent=2)[:100000]
            ),
            session_id=f"velvet-storage-ask-{question_hash}-{stamp}",
            instructions=(
                "Ты поисковый слой Telegram Storage Velvet. Отвечай по-русски, кратко, "
                "с указанием Storage ID и без вызова инструментов."
            ),
        )
        return run.output[:12000]


__all__ = ("StorageLibrarianService",)
