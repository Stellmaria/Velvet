from __future__ import annotations

import asyncio
import json
import logging
import os
from html import escape

import asyncpg
from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.application.storage_librarian import StorageLibrarianService
from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage.librarian_afk_repository import (
    StorageLibrarianAfkRepository,
)
from velvet_bot.domains.telegram_storage.librarian_models import (
    StorageLibrarianError,
    StorageLibrarianSettings,
    UnsupportedStorageContent,
)
from velvet_bot.domains.telegram_storage.librarian_repository import (
    StorageLibrarianRepository,
)
from velvet_bot.infrastructure.ai.storage_librarian_hermes import HermesRunsClient
from velvet_bot.infrastructure.ai.storage_librarian_ollama import (
    OllamaStorageAnalysisClient,
)
from velvet_bot.infrastructure.telegram.storage_librarian_files import (
    TelegramStorageObjectLoader,
)
from velvet_bot.infrastructure.telegram.storage_librarian_reports import (
    TelegramStorageLibrarianReportPublisher,
)

logger = logging.getLogger(__name__)
_scheduler_task: asyncio.Task[None] | None = None
_background_tasks: set[asyncio.Task[None]] = set()


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().casefold()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "да"}


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = os.getenv(name, "").strip()
    value = int(raw) if raw else int(default)
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} должен быть от {minimum} до {maximum}.")
    return value


def _auto_allowed_kinds(settings: StorageLibrarianSettings) -> tuple[str, ...]:
    raw = os.getenv(
        "STORAGE_LIBRARIAN_AUTO_ALLOWED_KINDS",
        "diagnostics,releases",
    )
    requested = tuple(
        dict.fromkeys(
            value.strip().casefold()
            for value in raw.split(",")
            if value.strip()
        )
    )
    return tuple(kind for kind in requested if kind in settings.allowed_kinds)


def _build_service(
    *,
    bot: Bot,
    database: Database,
    settings: StorageLibrarianSettings,
) -> StorageLibrarianService:
    publish_reports = _env_enabled("STORAGE_LIBRARIAN_PUBLISH_REPORTS", False)
    return StorageLibrarianService(
        database=database,
        settings=settings,
        object_loader=TelegramStorageObjectLoader(bot),
        analysis_client=OllamaStorageAnalysisClient(settings),
        answer_client=HermesRunsClient(settings),
        report_publisher=(
            TelegramStorageLibrarianReportPublisher(bot)
            if publish_reports
            else None
        ),
    )


def _short(value: str, limit: int = 700) -> str:
    text = value.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _jsonish_list(value: object) -> list[object]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            decoded: object = json.loads(value)
        except json.JSONDecodeError:
            return []
        return list(decoded) if isinstance(decoded, list) else []
    return []


async def _send_chunks(message: Message, text: str) -> None:
    remaining = text.strip() or "Результат пуст."
    while remaining:
        if len(remaining) <= 3900:
            chunk = remaining
            remaining = ""
        else:
            split_at = remaining.rfind("\n", 0, 3900)
            if split_at < 1000:
                split_at = 3900
            chunk = remaining[:split_at]
            remaining = remaining[split_at:].lstrip()
        await message.answer(chunk)


async def _librarian_scheduler_loop(
    *,
    bot: Bot,
    database: Database,
    settings: StorageLibrarianSettings,
    min_object_id: int,
    allowed_kinds: tuple[str, ...],
    batch_size: int,
) -> None:
    service = _build_service(
        bot=bot,
        database=database,
        settings=settings,
    )
    repository = StorageLibrarianAfkRepository(
        database,
        min_object_id=min_object_id,
    )
    service.repository = repository
    while True:
        try:
            queued = await repository.enqueue_newer_than(
                settings=settings,
                min_object_id=min_object_id,
                allowed_kinds=allowed_kinds,
                limit=batch_size,
            )
            processed = await service.process_once(auto_enqueue=False)
            if queued or processed:
                logger.info(
                    "Storage Librarian AFK cycle queued=%s processed=%s cutoff=%s kinds=%s",
                    queued,
                    processed,
                    min_object_id,
                    ",".join(allowed_kinds),
                )
        except asyncio.CancelledError:
            raise
        except (
            StorageLibrarianError,
            TelegramAPIError,
            asyncpg.PostgresError,
            OSError,
            ValueError,
        ) as error:
            logger.warning("Storage Librarian scheduler iteration failed: %s", error)
        await asyncio.sleep(settings.scan_interval_seconds)


async def start_storage_librarian(bot: Bot, database: Database) -> None:
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    try:
        settings = StorageLibrarianSettings.from_env()
    except ValueError as error:
        logger.error("Storage Librarian configuration invalid: %s", error)
        return
    if not settings.enabled:
        logger.info("Storage Librarian is disabled")
        return
    if not _env_enabled("STORAGE_LIBRARIAN_AUTO_ENQUEUE", False):
        logger.info("Storage Librarian is manual-only; background queue is disabled")
        return
    try:
        min_object_id = _env_int(
            "STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID",
            0,
            minimum=0,
            maximum=9_223_372_036_854_775_807,
        )
        batch_size = _env_int(
            "STORAGE_LIBRARIAN_AUTO_BATCH_SIZE",
            1,
            minimum=1,
            maximum=10,
        )
        allowed_kinds = _auto_allowed_kinds(settings)
        if min_object_id <= 0:
            raise ValueError(
                "AFK-режим требует STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID > 0. "
                "Используйте deploy/hermes-librarian/enable_afk.sh."
            )
        if not allowed_kinds:
            raise ValueError(
                "STORAGE_LIBRARIAN_AUTO_ALLOWED_KINDS не содержит разрешённых категорий."
            )
    except ValueError as error:
        logger.error("Storage Librarian AFK configuration invalid: %s", error)
        return
    _scheduler_task = asyncio.create_task(
        _librarian_scheduler_loop(
            bot=bot,
            database=database,
            settings=settings,
            min_object_id=min_object_id,
            allowed_kinds=allowed_kinds,
            batch_size=batch_size,
        ),
        name="telegram-storage-librarian",
    )


async def stop_storage_librarian() -> None:
    global _scheduler_task
    task = _scheduler_task
    _scheduler_task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def handle_storage_librarian_status(
    message: Message,
    database: Database,
) -> None:
    try:
        settings = StorageLibrarianSettings.from_env()
        counts = await StorageLibrarianRepository(database).counts()
        auto_min_object_id = _env_int(
            "STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID",
            0,
            minimum=0,
            maximum=9_223_372_036_854_775_807,
        )
        auto_batch_size = _env_int(
            "STORAGE_LIBRARIAN_AUTO_BATCH_SIZE",
            1,
            minimum=1,
            maximum=10,
        )
        auto_kinds = _auto_allowed_kinds(settings)
    except (ValueError, asyncpg.PostgresError) as error:
        await message.answer(
            "<b>Storage Librarian недоступен</b>\n\n" + escape(str(error))
        )
        return
    auto_enqueue = _env_enabled("STORAGE_LIBRARIAN_AUTO_ENQUEUE", False)
    publish_reports = _env_enabled("STORAGE_LIBRARIAN_PUBLISH_REPORTS", False)
    lines = [
        "<b>Storage Librarian</b>",
        "",
        f"Состояние: <b>{'включён' if settings.enabled else 'выключен'}</b>",
        f"Фоновая очередь: <b>{'включена' if auto_enqueue else 'выключена'}</b>",
        f"Публикация отчётов: <b>{'включена' if publish_reports else 'выключена'}</b>",
        f"Версия: <code>{escape(settings.analyzer_version)}</code>",
        "Категории ручного режима: <code>"
        + escape(", ".join(settings.allowed_kinds))
        + "</code>",
        "",
        f"В очереди: <b>{counts['queued']}</b>",
        f"В работе: <b>{counts['running']}</b>",
        f"Готово: <b>{counts['completed']}</b>",
        f"Пропущено: <b>{counts['skipped']}</b>",
        f"Ошибок: <b>{counts['failed']}</b>",
        "",
        "<code>/storage_analyze ID</code> — поставить объект в приоритетную очередь",
        "<code>/storage_digest 7</code> — сводка за дни",
        "<code>/storage_ask вопрос</code> — поиск и ответ по индексу",
    ]
    if settings.enabled and not auto_enqueue:
        lines.extend(
            (
                "",
                "Режим manual-first активен: старый архив не анализируется массово и "
                "не расходует токены без ручной команды.",
            )
        )
    elif settings.enabled:
        lines.extend(
            (
                "",
                "AFK new-only: <b>активен</b>",
                f"Только Storage ID &gt; <code>{auto_min_object_id}</code>",
                "Категории AFK: <code>" + escape(", ".join(auto_kinds)) + "</code>",
                f"За цикл: <b>{auto_batch_size}</b>; интервал: "
                f"<b>{settings.scan_interval_seconds} сек.</b>",
                "Старый архив и объекты до cutoff автоматически не ставятся в очередь.",
            )
        )
    await message.answer("\n".join(lines))


async def _process_manual_once(
    *,
    status_message: Message,
    bot: Bot,
    database: Database,
    settings: StorageLibrarianSettings,
) -> None:
    try:
        processed = await _build_service(
            bot=bot,
            database=database,
            settings=settings,
        ).process_once(auto_enqueue=False)
        text = (
            "<b>Storage Librarian</b>\n\n"
            + ("Задача обработана." if processed else "Очередь пока пуста.")
        )
    except (
        StorageLibrarianError,
        TelegramAPIError,
        asyncpg.PostgresError,
        OSError,
        ValueError,
    ) as error:
        logger.exception("Manual Storage Librarian iteration failed")
        text = "<b>Анализ не выполнен</b>\n\n" + escape(str(error))
    try:
        await status_message.edit_text(text)
    except TelegramBadRequest:
        pass


async def handle_storage_analyze(
    message: Message,
    command: CommandObject,
    bot: Bot,
    database: Database,
) -> None:
    raw = (command.args or "").strip()
    if not raw.isdigit():
        await message.answer("Использование: <code>/storage_analyze ID</code>")
        return
    try:
        settings = StorageLibrarianSettings.from_env()
        if not settings.enabled:
            raise StorageLibrarianError(
                "Сначала включите STORAGE_LIBRARIAN_ENABLED после проверки Hermes."
            )
        queued = await StorageLibrarianRepository(database).enqueue_object(
            int(raw),
            settings=settings,
        )
        if not queued:
            await message.answer("Storage object с таким ID не найден.")
            return
    except (
        StorageLibrarianError,
        UnsupportedStorageContent,
        asyncpg.PostgresError,
        ValueError,
    ) as error:
        await message.answer("<b>Не поставлено в очередь</b>\n\n" + escape(str(error)))
        return

    status_message = await message.answer(
        f"<b>Storage #{int(raw)}</b> поставлен в приоритетную очередь.\n\n"
        "Запускаю одну итерацию Librarian."
    )
    task = asyncio.create_task(
        _process_manual_once(
            status_message=status_message,
            bot=bot,
            database=database,
            settings=settings,
        ),
        name=f"storage-librarian-manual:{int(raw)}",
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def handle_storage_digest(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    raw = (command.args or "1").strip()
    try:
        days = max(1, min(int(raw), 365))
    except ValueError:
        await message.answer("Использование: <code>/storage_digest 7</code>")
        return
    try:
        rows = await StorageLibrarianRepository(database).recent_analyses(
            days=days,
            limit=15,
        )
    except asyncpg.PostgresError as error:
        await message.answer("Не удалось прочитать индекс: " + escape(str(error)))
        return
    if not rows:
        await message.answer(
            f"За последние {days} дн. проанализированных объектов пока нет."
        )
        return
    lines = [f"<b>Storage digest · {days} дн.</b>", ""]
    for row in rows:
        tags = ", ".join(str(value) for value in _jsonish_list(row["tags"])[:6])
        lines.append(
            f"<b>#{int(row['storage_object_id'])}</b> · "
            f"<code>{escape(str(row['storage_kind']))}</code>\n"
            f"{escape(_short(str(row['summary']), 650))}"
            + (f"\nТеги: {escape(tags)}" if tags else "")
        )
    await _send_chunks(message, "\n\n".join(lines))


async def handle_storage_ask(
    message: Message,
    command: CommandObject,
    bot: Bot,
    database: Database,
) -> None:
    question = (command.args or "").strip()
    if not question:
        await message.answer(
            "Использование: <code>/storage_ask что повторялось в диагностике?</code>"
        )
        return
    status = await message.answer("<b>Ищу по индексу Telegram Storage…</b>")
    try:
        settings = StorageLibrarianSettings.from_env()
        answer = await _build_service(
            bot=bot,
            database=database,
            settings=settings,
        ).answer(question)
    except (
        StorageLibrarianError,
        TelegramAPIError,
        asyncpg.PostgresError,
        OSError,
        ValueError,
    ) as error:
        logger.exception("Storage Librarian answer failed")
        answer = "Запрос не выполнен: " + str(error)
    try:
        await status.delete()
    except TelegramBadRequest:
        pass
    await _send_chunks(message, answer)


def register_storage_librarian(router: Router) -> None:
    router.message.register(
        handle_storage_librarian_status,
        Command("storage_librarian"),
    )
    router.message.register(handle_storage_analyze, Command("storage_analyze"))
    router.message.register(handle_storage_digest, Command("storage_digest"))
    router.message.register(handle_storage_ask, Command("storage_ask"))
    router.startup.register(start_storage_librarian)
    router.shutdown.register(stop_storage_librarian)


__all__ = (
    "register_storage_librarian",
    "start_storage_librarian",
    "stop_storage_librarian",
)
