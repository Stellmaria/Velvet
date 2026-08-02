from __future__ import annotations

import logging
from html import escape

from aiogram import Bot

from velvet_bot.domains.telegram_storage.librarian_content import redact_sensitive
from velvet_bot.domains.telegram_storage.librarian_models import (
    LibrarianAnalysis,
    LibrarianObject,
)
from velvet_bot.domains.telegram_storage.models import TelegramStorageSettings

logger = logging.getLogger(__name__)


def _short(value: str, limit: int) -> str:
    text = value.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_storage_librarian_report(
    item: LibrarianObject,
    analysis: LibrarianAnalysis,
) -> str:
    tags = ", ".join(analysis.tags[:8])
    lines = [
        "<b>Velvet Librarian · новый отчёт</b>",
        "",
        f"Storage ID: <code>{item.object_id}</code>",
        f"Категория: <code>{escape(item.storage_kind)}</code>",
        f"Файл: <code>{escape(_short(item.original_name, 180))}</code>",
        "",
        escape(_short(analysis.summary, 1800)),
    ]
    if tags:
        lines.extend(("", "Теги: " + escape(tags)))
    if analysis.action_items:
        lines.extend(("", "<b>Действия</b>"))
        for action in analysis.action_items[:5]:
            title = action.get("title") or action.get("text") or "Действие"
            priority = action.get("priority") or ""
            suffix = f" · {priority}" if priority else ""
            lines.append("• " + escape(_short(str(title), 300) + suffix))
    details: list[str] = []
    if analysis.confidence is not None:
        details.append(f"уверенность {analysis.confidence}%")
    details.append(f"чувствительность {analysis.sensitivity}")
    lines.extend(("", " · ".join(details)))
    lines.append(f"Команда: <code>/storage_download {item.object_id}</code>")
    return "\n".join(lines)[:4000]


def build_storage_librarian_failure_report(
    *,
    object_id: int,
    item: LibrarianObject | None,
    error: BaseException,
) -> str:
    safe_error = redact_sensitive(str(error))[:1200]
    lines = [
        "<b>Velvet Librarian · анализ не выполнен</b>",
        "",
        f"Storage ID: <code>{int(object_id)}</code>",
    ]
    if item is not None:
        lines.extend(
            (
                f"Категория: <code>{escape(item.storage_kind)}</code>",
                f"Файл: <code>{escape(_short(item.original_name, 180))}</code>",
            )
        )
    lines.extend(
        (
            "",
            escape(_short(safe_error or "Причина не указана.", 1200)),
            "",
            "Автоматический перезапуск, обновление или откат не выполнялись.",
            f"Проверка: <code>/storage_librarian</code>",
        )
    )
    return "\n".join(lines)[:4000]


class TelegramStorageLibrarianReportPublisher:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def publish(
        self,
        item: LibrarianObject,
        analysis: LibrarianAnalysis,
    ) -> None:
        settings = TelegramStorageSettings.from_env()
        thread_id = settings.threads.for_kind("analysis")
        await self._bot.send_message(
            chat_id=settings.chat_id,
            message_thread_id=thread_id,
            text=build_storage_librarian_report(item, analysis),
            disable_notification=True,
        )
        logger.info(
            "Storage Librarian report published object_id=%s chat_id=%s thread_id=%s",
            item.object_id,
            settings.chat_id,
            thread_id,
        )

    async def publish_failure(
        self,
        *,
        object_id: int,
        item: LibrarianObject | None,
        error: BaseException,
    ) -> None:
        settings = TelegramStorageSettings.from_env()
        thread_id = settings.threads.for_kind("analysis")
        await self._bot.send_message(
            chat_id=settings.chat_id,
            message_thread_id=thread_id,
            text=build_storage_librarian_failure_report(
                object_id=object_id,
                item=item,
                error=error,
            ),
            disable_notification=False,
        )
        logger.warning(
            "Storage Librarian terminal failure published object_id=%s chat_id=%s thread_id=%s",
            object_id,
            settings.chat_id,
            thread_id,
        )


__all__ = (
    "TelegramStorageLibrarianReportPublisher",
    "build_storage_librarian_failure_report",
    "build_storage_librarian_report",
)
