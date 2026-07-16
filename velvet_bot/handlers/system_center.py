from __future__ import annotations

import json
from datetime import datetime
from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.services.system_health import SystemHealthReport, SystemHealthService
from velvet_bot.version import APP_VERSION
from velvet_bot.workers.manager import WorkerManager, WorkerSnapshot

router = Router(name=__name__)


class SystemCallback(CallbackData, prefix="sys"):
    action: str


def _format_bytes(value: int) -> str:
    amount = float(max(0, value))
    units = ("Б", "КБ", "МБ", "ГБ", "ТБ")
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "Б" else f"{int(amount)} Б"
        amount /= 1024
    return f"{amount:.1f} ТБ"


def _format_duration(seconds: int) -> str:
    days, remainder = divmod(max(0, seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} д.")
    if hours or days:
        parts.append(f"{hours} ч.")
    parts.append(f"{minutes} мин.")
    return " ".join(parts)


def _format_datetime(value: datetime | None) -> str:
    return value.astimezone().strftime("%d.%m.%Y %H:%M:%S") if value else "—"


def _yes_no(value: bool) -> str:
    return "✅" if value else "❌"


def _status_icon(status: str) -> str:
    return {"ok": "✅", "degraded": "⚠️", "failed": "❌"}.get(status, "ℹ️")


def _worker_icon(worker: WorkerSnapshot) -> str:
    if worker.state == "stopped":
        return "⏹"
    if worker.state == "failed":
        return "❌"
    if worker.consecutive_failures:
        return "⚠️"
    return "✅"


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚙️ Воркеры",
                    callback_data=SystemCallback(action="workers").pack(),
                ),
                InlineKeyboardButton(
                    text="🗄 База",
                    callback_data=SystemCallback(action="database").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📦 Очереди",
                    callback_data=SystemCallback(action="queues").pack(),
                ),
                InlineKeyboardButton(
                    text="💾 Бэкапы",
                    callback_data=SystemCallback(action="backups").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Версия",
                    callback_data=SystemCallback(action="version").pack(),
                ),
                InlineKeyboardButton(
                    text="📄 Отчёт",
                    callback_data=SystemCallback(action="export").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=SystemCallback(action="overview").pack(),
                )
            ],
        ]
    )


def _back_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ Система",
                    callback_data=SystemCallback(action="overview").pack(),
                ),
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=SystemCallback(action=action).pack(),
                ),
            ]
        ]
    )


def _workers_keyboard(report: SystemHealthReport) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{_worker_icon(item)} {item.description[:38]}",
                callback_data=SystemCallback(action=f"worker.{item.name}").pack(),
            )
        ]
        for item in report.workers
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Система",
                callback_data=SystemCallback(action="overview").pack(),
            ),
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=SystemCallback(action="workers").pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _worker_keyboard(name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ Запустить сейчас",
                    callback_data=SystemCallback(action=f"run.{name}").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="♻️ Перезапустить процесс",
                    callback_data=SystemCallback(action=f"restart.{name}").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Воркеры",
                    callback_data=SystemCallback(action="workers").pack(),
                ),
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=SystemCallback(action=f"worker.{name}").pack(),
                ),
            ],
        ]
    )


def _overview_text(report: SystemHealthReport) -> str:
    database = report.database
    workers_ok = sum(1 for item in report.workers if item.healthy)
    backup_status = database.latest_backup_status if database else None
    return (
        f"<b>{_status_icon(report.status)} Состояние Velvet Archive</b>\n\n"
        f"Версия: <code>{escape(report.app_version)}</code>\n"
        f"Процесс: <code>{report.process_id}</code>\n"
        f"Работает: <b>{_format_duration(report.uptime_seconds)}</b>\n"
        f"Проверено: <b>{_format_datetime(report.checked_at)}</b>\n\n"
        f"{_yes_no(report.telegram_ok)} Telegram: "
        f"<b>@{escape(report.bot_username or 'недоступен')}</b>\n"
        f"{_yes_no(report.database_ok)} PostgreSQL: "
        f"<b>{escape(database.database_name if database else 'недоступна')}</b>\n"
        f"{_yes_no(report.pg_dump_available)} pg_dump\n"
        f"{_yes_no(report.pg_restore_available)} pg_restore\n"
        f"💽 Свободно: <b>{_format_bytes(report.disk.free_bytes)}</b> "
        f"({report.disk.free_percent:.1f}%)\n"
        f"⚙️ Воркеры: <b>{workers_ok}/{len(report.workers)}</b> без ошибок\n"
        f"💾 Последняя копия: <b>{escape(backup_status or 'ещё нет')}</b>"
    )


def _workers_text(report: SystemHealthReport) -> str:
    lines = ["<b>⚙️ Фоновые процессы</b>", ""]
    for item in report.workers:
        lines.append(
            f"{_worker_icon(item)} <b>{escape(item.description)}</b> · "
            f"<code>{escape(item.state)}</code> · ошибок {item.failed_runs}"
        )
    lines.extend(["", "Выберите процесс для подробностей и безопасного управления."])
    return "\n".join(lines)


def _worker_text(item: WorkerSnapshot) -> str:
    text = (
        f"<b>{_worker_icon(item)} {escape(item.description)}</b>\n\n"
        f"Имя: <code>{escape(item.name)}</code>\n"
        f"Состояние: <code>{escape(item.state)}</code>\n"
        f"Интервал: <b>{item.interval_seconds:g} сек.</b>\n"
        f"Успешных запусков: <b>{item.successful_runs}</b>\n"
        f"Ошибок: <b>{item.failed_runs}</b>\n"
        f"Ошибок подряд: <b>{item.consecutive_failures}</b>\n"
        f"Последний запуск: <b>{_format_datetime(item.last_started_at)}</b>\n"
        f"Последний успех: <b>{_format_datetime(item.last_success_at)}</b>\n"
        f"Последняя ошибка: <b>{_format_datetime(item.last_error_at)}</b>\n"
        f"Следующий запуск: <b>{_format_datetime(item.next_run_at)}</b>"
    )
    if item.last_error:
        text += f"\n\n<code>{escape(item.last_error[:1000])}</code>"
    return text


def _database_text(report: SystemHealthReport) -> str:
    item = report.database
    if item is None:
        return (
            "<b>❌ PostgreSQL недоступна</b>\n\n"
            f"<code>{escape(report.database_error or 'неизвестная ошибка')}</code>"
        )
    return (
        "<b>🗄 PostgreSQL</b>\n\n"
        f"База: <code>{escape(item.database_name)}</code>\n"
        f"PostgreSQL: <code>{escape(item.postgres_version)}</code>\n"
        f"Размер: <b>{_format_bytes(item.database_size_bytes)}</b>\n"
        f"Схема: <code>{escape(item.schema_version or 'нет')}</code>\n"
        f"Миграций: <b>{item.migration_count}</b>\n\n"
        f"Персонажей: <b>{item.character_count}</b>\n"
        f"Материалов: <b>{item.media_count}</b>\n"
        f"Каналов аналитики: <b>{item.tracked_channel_count}</b>\n"
        f"Чатов обсуждений: <b>{item.tracked_discussion_count}</b>"
    )


def _queues_text(report: SystemHealthReport) -> str:
    item = report.database
    if item is None:
        return "<b>📦 Очереди</b>\n\nPostgreSQL недоступна."
    return (
        "<b>📦 Очереди и незавершённая работа</b>\n\n"
        f"Запланировано публикаций: <b>{item.scheduled_publications}</b>\n"
        f"Сейчас публикуется: <b>{item.publishing_publications}</b>\n"
        f"Ошибок публикации: <b>{item.publication_errors}</b>\n"
        f"Ожидают визуального анализа: <b>{item.pending_visual_scans}</b>\n"
        f"Ожидают проверки file_id: <b>{item.unknown_file_checks}</b>"
    )


def _backups_text(report: SystemHealthReport) -> str:
    item = report.database
    if item is None:
        return "<b>💾 Резервные копии</b>\n\nPostgreSQL недоступна."
    return (
        "<b>💾 Резервные копии</b>\n\n"
        f"pg_dump: {_yes_no(report.pg_dump_available)}\n"
        f"pg_restore: {_yes_no(report.pg_restore_available)}\n"
        f"Каталог: <code>{escape(report.disk.path)}</code>\n"
        f"Свободно: <b>{_format_bytes(report.disk.free_bytes)}</b> "
        f"({report.disk.free_percent:.1f}%)\n\n"
        f"Последний статус: <b>{escape(item.latest_backup_status or 'копий нет')}</b>\n"
        f"Файл: <code>{escape(item.latest_backup_file_name or '—')}</code>\n"
        f"Создана: <b>{_format_datetime(item.latest_backup_at)}</b>\n\n"
        "Управление копиями: <code>/backup</code>"
    )


def _version_text(report: SystemHealthReport) -> str:
    schema = report.database.schema_version if report.database else None
    return (
        "<b>ℹ️ Версия Velvet Archive</b>\n\n"
        f"Приложение: <code>{escape(report.app_version)}</code>\n"
        f"Схема БД: <code>{escape(schema or 'недоступна')}</code>\n"
        f"Запущено: <b>{_format_datetime(report.started_at)}</b>\n"
        f"Время работы: <b>{_format_duration(report.uptime_seconds)}</b>"
    )


async def _build_report(
    bot: Bot,
    system_service: SystemHealthService,
    worker_manager: WorkerManager,
) -> SystemHealthReport:
    return await system_service.check(bot=bot, worker_manager=worker_manager)


async def _safe_edit(
    callback: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Системное меню больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


async def _send_export(
    callback: CallbackQuery,
    report: SystemHealthReport,
    system_service: SystemHealthService,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Чат для отчёта недоступен.", show_alert=True)
        return
    payload = json.dumps(
        system_service.report_to_dict(report),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    stamp = report.checked_at.strftime("%Y%m%dT%H%M%SZ")
    await callback.message.answer_document(
        BufferedInputFile(payload, filename=f"velvet_system_report_{stamp}.json"),
        caption=(
            "<b>Диагностический отчёт Velvet Archive</b>\n\n"
            "Токены, пароли и DATABASE_URL в файл не включаются. "
            "Секреты хотя бы раз оставили за дверью, редкое достижение."
        ),
    )


@router.message(Command("system", "health"))
async def handle_system_command(
    message: Message,
    bot: Bot,
    system_service: SystemHealthService,
    worker_manager: WorkerManager,
) -> None:
    report = await _build_report(bot, system_service, worker_manager)
    await message.answer(_overview_text(report), reply_markup=_main_keyboard())


@router.message(Command("version"))
async def handle_version_command(
    message: Message,
    bot: Bot,
    system_service: SystemHealthService,
    worker_manager: WorkerManager,
) -> None:
    report = await _build_report(bot, system_service, worker_manager)
    await message.answer(_version_text(report))


@router.callback_query(SystemCallback.filter())
async def handle_system_callback(
    callback: CallbackQuery,
    callback_data: SystemCallback,
    bot: Bot,
    system_service: SystemHealthService,
    worker_manager: WorkerManager,
) -> None:
    action = callback_data.action

    if action.startswith("run."):
        name = action.removeprefix("run.")
        await callback.answer("Запускаю одну итерацию…")
        try:
            await worker_manager.run_now(name)
        except (ValueError, RuntimeError) as error:
            if isinstance(callback.message, Message):
                await callback.message.answer(f"<b>Запуск не выполнен</b>\n\n{escape(str(error))}")
            return
        report = await _build_report(bot, system_service, worker_manager)
        item = worker_manager.snapshot(name)
        if item is not None:
            await _safe_edit(callback, _worker_text(item), _worker_keyboard(name))
        return

    if action.startswith("restart."):
        name = action.removeprefix("restart.")
        await callback.answer("Перезапускаю процесс…")
        try:
            await worker_manager.restart(name)
        except (ValueError, RuntimeError) as error:
            if isinstance(callback.message, Message):
                await callback.message.answer(
                    f"<b>Перезапуск не выполнен</b>\n\n{escape(str(error))}"
                )
            return
        item = worker_manager.snapshot(name)
        if item is not None:
            await _safe_edit(callback, _worker_text(item), _worker_keyboard(name))
        return

    report = await _build_report(bot, system_service, worker_manager)
    if action == "export":
        await callback.answer("Готовлю отчёт…")
        await _send_export(callback, report, system_service)
        return
    if action.startswith("worker."):
        name = action.removeprefix("worker.")
        item = worker_manager.snapshot(name)
        if item is None:
            await callback.answer("Процесс не найден.", show_alert=True)
            return
        text, keyboard = _worker_text(item), _worker_keyboard(name)
    elif action == "workers":
        text, keyboard = _workers_text(report), _workers_keyboard(report)
    elif action == "database":
        text, keyboard = _database_text(report), _back_keyboard(action)
    elif action == "queues":
        text, keyboard = _queues_text(report), _back_keyboard(action)
    elif action == "backups":
        text, keyboard = _backups_text(report), _back_keyboard(action)
    elif action == "version":
        text, keyboard = _version_text(report), _back_keyboard(action)
    else:
        text, keyboard = _overview_text(report), _main_keyboard()
    await _safe_edit(callback, text, keyboard)
    await callback.answer()


__all__ = ("APP_VERSION", "SystemCallback", "router")
