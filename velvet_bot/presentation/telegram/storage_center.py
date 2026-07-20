from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage import (
    TelegramStorageMigrationService,
    TelegramStorageRepository,
    TelegramStorageSettings,
)
from velvet_bot.domains.telegram_storage.files import storage_message_link

logger = logging.getLogger(__name__)
_background_tasks: set[asyncio.Task] = set()


def _human_size(value: int | None) -> str:
    size = max(0, int(value or 0))
    amount = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if amount < 1024 or unit == "ТБ":
            return f"{amount:.0f} {unit}" if unit == "Б" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{size} Б"


def _summary_text(summary) -> str:
    lines = [
        f"<b>Telegram Storage Migration #{summary.run_id}</b>",
        "",
        f"Статус: <b>{escape(summary.status)}</b>",
        f"Найдено: <b>{summary.discovered_files}</b>",
        f"Загружено: <b>{summary.stored_files}</b>",
        f"Уже было: <b>{summary.skipped_files}</b>",
        f"Ошибок: <b>{summary.failed_files}</b>",
        f"Удалено локально: <b>{summary.deleted_files}</b>",
        f"Освобождено: <b>{_human_size(summary.freed_bytes)}</b>",
    ]
    if summary.errors:
        lines.extend(("", "<b>Последние ошибки</b>"))
        lines.extend(f"• {escape(value[:500])}" for value in summary.errors[-5:])
    return "\n".join(lines)


async def handle_storage_menu(
    message: Message,
    database: Database,
) -> None:
    settings = TelegramStorageSettings.from_env()
    rows = await TelegramStorageRepository(database).list_objects(limit=12)
    lines = [
        "<b>Telegram Storage Center</b>",
        "",
        f"Чат: <code>{settings.chat_id}</code>",
        (
            "Ветки: "
            f"watermarks={settings.threads.watermarks}, "
            f"backups={settings.threads.backups}, "
            f"diagnostics={settings.threads.diagnostics}, "
            f"exports={settings.threads.exports}, "
            f"codex={settings.threads.codex}, "
            f"releases={settings.threads.releases}, "
            f"rework={settings.threads.rework}"
        ),
        "",
        "<b>Последние объекты</b>",
    ]
    if not rows:
        lines.append("• хранилище пока пустое")
    for row in rows:
        first_message_id = row.get("first_message_id")
        link = (
            storage_message_link(int(row["chat_id"]), int(first_message_id))
            if first_message_id is not None
            else None
        )
        title = escape(str(row["logical_key"]))
        if link:
            title = f'<a href="{link}">{title}</a>'
        lines.append(
            f"• <b>#{row['id']}</b> {title}\n"
            f"  {escape(str(row['storage_kind']))} · {_human_size(row['size_bytes'])} · "
            f"частей {row['part_count']}"
        )
    lines.extend(
        (
            "",
            "<code>/storage_migrate force</code> — принудительно досканировать ПК",
            "<code>/storage_find запрос</code> — поиск по ключу, имени или SHA",
            "<code>/storage_download ID</code> — получить файл или его части",
        )
    )
    await message.answer("\n".join(lines))


async def _run_manual_migration(
    *,
    status_message: Message,
    bot: Bot,
    database: Database,
    requested_by: int,
) -> None:
    async def progress(text: str) -> None:
        try:
            await status_message.edit_text(
                "<b>Перенос файлов на Telegram</b>\n\n" + escape(text)
            )
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                logger.warning("Could not update storage progress: %s", error)

    try:
        service = TelegramStorageMigrationService(bot=bot, database=database)
        summary = await service.run(
            migration_kind="manual",
            requested_by=requested_by,
            progress=progress,
        )
        await status_message.edit_text(_summary_text(summary))
    except Exception as error:
        logger.exception("Manual Telegram storage migration failed")
        await status_message.edit_text(
            "<b>Перенос не выполнен</b>\n\n" + escape(str(error))
        )


async def handle_storage_migrate(
    message: Message,
    command: CommandObject,
    bot: Bot,
    database: Database,
) -> None:
    force = (command.args or "").strip().casefold() in {"force", "принудительно", "full"}
    if not force:
        await message.answer(
            "Команда удаляет локальные копии только после подтверждённой загрузки. "
            "Для запуска используйте <code>/storage_migrate force</code>."
        )
        return
    status_message = await message.answer(
        "<b>Перенос файлов на Telegram</b>\n\nНачинаю инвентаризацию…"
    )
    task = asyncio.create_task(
        _run_manual_migration(
            status_message=status_message,
            bot=bot,
            database=database,
            requested_by=message.from_user.id,
        ),
        name="telegram-storage-manual-migration",
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def handle_storage_find(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    query = (command.args or "").strip()
    if not query:
        await message.answer(
            "Укажите ID, часть ключа, имя файла или SHA: "
            "<code>/storage_find backup</code>"
        )
        return
    object_id = int(query) if query.isdigit() else None
    pattern = f"%{query}%"
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT o.id, o.storage_kind, o.logical_key, o.original_name,
                   o.size_bytes, o.sha256, o.encrypted, o.chat_id,
                   o.thread_id, o.part_count, o.migrated_at,
                   MIN(p.message_id) AS first_message_id
            FROM telegram_storage_objects AS o
            LEFT JOIN telegram_storage_parts AS p
              ON p.storage_object_id = o.id
            WHERE ($1::BIGINT IS NOT NULL AND o.id = $1::BIGINT)
               OR o.logical_key ILIKE $2::TEXT
               OR o.original_name ILIKE $2::TEXT
               OR o.sha256 ILIKE $2::TEXT
            GROUP BY o.id
            ORDER BY o.migrated_at DESC, o.id DESC
            LIMIT 20
            """,
            object_id,
            pattern,
        )
    if not rows:
        await message.answer("Совпадений в Telegram Storage не найдено.")
        return
    lines = [f"<b>Результаты поиска: {escape(query)}</b>", ""]
    for row in rows:
        message_id = row["first_message_id"]
        link = (
            storage_message_link(int(row["chat_id"]), int(message_id))
            if message_id is not None
            else ""
        )
        title = escape(str(row["logical_key"]))
        if link:
            title = f'<a href="{link}">{title}</a>'
        lines.append(
            f"• <b>#{row['id']}</b> {title}\n"
            f"  {escape(str(row['storage_kind']))} · {_human_size(row['size_bytes'])} · "
            f"SHA <code>{str(row['sha256'])[:12]}</code>"
        )
    await message.answer("\n".join(lines))


async def handle_storage_download(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    raw = (command.args or "").strip()
    if not raw.isdigit():
        await message.answer("Использование: <code>/storage_download ID</code>")
        return
    object_id = int(raw)
    async with database.acquire() as connection:
        object_row = await connection.fetchrow(
            """
            SELECT id, storage_kind, logical_key, original_name,
                   sha256, encrypted, part_count
            FROM telegram_storage_objects
            WHERE id = $1::BIGINT
            """,
            object_id,
        )
        parts = await connection.fetch(
            """
            SELECT part_number, telegram_file_id, sha256
            FROM telegram_storage_parts
            WHERE storage_object_id = $1::BIGINT
            ORDER BY part_number
            """,
            object_id,
        )
    if object_row is None or not parts:
        await message.answer("Объект Telegram Storage не найден.")
        return
    for part in parts:
        await message.answer_document(
            document=str(part["telegram_file_id"]),
            caption=(
                f"<b>Storage #{object_id}</b> · "
                f"часть {part['part_number']}/{object_row['part_count']}\n"
                f"{escape(str(object_row['logical_key']))}\n"
                f"SHA объекта: <code>{object_row['sha256']}</code>"
            ),
        )


async def handle_storage_startup(
    bot: Bot,
    database: Database,
) -> None:
    try:
        settings = TelegramStorageSettings.from_env()
    except ValueError as error:
        logger.error("Telegram storage startup configuration invalid: %s", error)
        return
    if not settings.migrate_on_start:
        return

    async def runner() -> None:
        try:
            service = TelegramStorageMigrationService(
                bot=bot,
                database=database,
                settings=settings,
            )
            summary = await service.run_initial_if_needed()
            if summary is not None:
                logger.info(
                    "Initial Telegram storage migration finished run=%s status=%s "
                    "stored=%s deleted=%s freed=%s",
                    summary.run_id,
                    summary.status,
                    summary.stored_files,
                    summary.deleted_files,
                    summary.freed_bytes,
                )
        except Exception:
            logger.exception("Initial Telegram storage migration failed")

    task = asyncio.create_task(runner(), name="telegram-storage-initial-migration")
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def register_storage_center(router: Router) -> None:
    router.message.register(handle_storage_menu, Command("storage", "storage_center"))
    router.message.register(handle_storage_migrate, Command("storage_migrate"))
    router.message.register(handle_storage_find, Command("storage_find"))
    router.message.register(handle_storage_download, Command("storage_download"))
    router.startup.register(handle_storage_startup)


__all__ = ("register_storage_center",)
