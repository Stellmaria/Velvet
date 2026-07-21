from __future__ import annotations

from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.services.diagnostic_bundle import DiagnosticBundleService
from velvet_bot.services.system_health import SystemHealthReport, SystemHealthService
from velvet_bot.workers import WorkerManager

router = Router(name=__name__)


class DiagnosticCallback(CallbackData, prefix="diag"):
    action: str


def _keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📦 ZIP за 1 час",
                    callback_data=DiagnosticCallback(action="export.1").pack(),
                ),
                InlineKeyboardButton(
                    text="📦 ZIP за 24 часа",
                    callback_data=DiagnosticCallback(action="export.24").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📦 ZIP за 3 дня",
                    callback_data=DiagnosticCallback(action="export.72").pack(),
                ),
                InlineKeyboardButton(
                    text="📦 ZIP за 7 дней",
                    callback_data=DiagnosticCallback(action="export.168").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить состояние",
                    callback_data=DiagnosticCallback(action="status").pack(),
                )
            ],
        ]
    )


def _status_text(report: SystemHealthReport) -> str:
    database = report.database
    healthy_workers = sum(1 for item in report.workers if item.healthy)
    failed_workers = [
        item.name
        for item in report.workers
        if item.state == "failed" or item.consecutive_failures >= 3
    ]
    queue_text = "—"
    backup_text = "—"
    schema_text = "—"
    if database is not None:
        queue_total = (
            database.scheduled_publications
            + database.publishing_publications
            + database.pending_visual_scans
            + database.unknown_file_checks
        )
        queue_text = str(queue_total)
        backup_text = database.latest_backup_status or "ещё нет"
        schema_text = database.schema_version or "нет"
    return (
        "<b>🩺 Диагностика Velvet</b>\n\n"
        f"Состояние: <code>{escape(report.status)}</code>\n"
        f"Telegram: {'✅' if report.telegram_ok else '❌'}\n"
        f"PostgreSQL: {'✅' if report.database_ok else '❌'}\n"
        f"Схема БД: <code>{escape(schema_text)}</code>\n"
        f"Воркеры: <b>{healthy_workers}/{len(report.workers)}</b> без ошибок\n"
        f"Проблемные workers: <code>{escape(', '.join(failed_workers) or 'нет')}</code>\n"
        f"Незавершённые очереди: <b>{queue_text}</b>\n"
        f"Последний backup: <code>{escape(backup_text)}</code>\n"
        f"Свободно на диске: <b>{report.disk.free_percent:.1f}%</b>\n\n"
        "Автопроверка выполняется каждые <b>5 минут</b>. ZIP автоматически "
        "приходит только при серьёзной проблеме. Одинаковая авария повторяется "
        "не чаще одного раза в 6 часов.\n\n"
        "Ручная команда: <code>/diag_export 24h</code>\n"
        "Периоды: <code>1h</code>, <code>6h</code>, <code>24h</code>, "
        "<code>3d</code>, <code>7d</code>."
    )


async def _build_report(
    *,
    bot: Bot,
    system_service: SystemHealthService,
    worker_manager: WorkerManager,
) -> SystemHealthReport:
    return await system_service.check(bot=bot, worker_manager=worker_manager)


async def _send_bundle(
    *,
    message: Message,
    bot: Bot,
    diagnostic_service: DiagnosticBundleService,
    system_service: SystemHealthService,
    worker_manager: WorkerManager,
    window_hours: int,
) -> None:
    bundle = await diagnostic_service.build_current_bundle(
        bot=bot,
        system_service=system_service,
        worker_manager=worker_manager,
        window_hours=window_hours,
        reason="manual-owner-export",
    )
    await message.answer_document(
        BufferedInputFile(bundle.payload, filename=bundle.filename),
        caption=bundle.caption,
    )


def _private_only(message: Message) -> bool:
    return message.chat.type == ChatType.PRIVATE


@router.message(Command("diag", "diagnostics"))
async def handle_diagnostics_command(
    message: Message,
    bot: Bot,
    diagnostic_service: DiagnosticBundleService,
    system_service: SystemHealthService,
    worker_manager: WorkerManager,
) -> None:
    if not _private_only(message):
        await message.answer("Диагностические архивы доступны только в личных сообщениях бота.")
        return
    report = await _build_report(
        bot=bot,
        system_service=system_service,
        worker_manager=worker_manager,
    )
    await message.answer(_status_text(report), reply_markup=_keyboard())


@router.message(Command("diag_export"))
async def handle_diagnostic_export_command(
    message: Message,
    bot: Bot,
    diagnostic_service: DiagnosticBundleService,
    system_service: SystemHealthService,
    worker_manager: WorkerManager,
) -> None:
    if not _private_only(message):
        await message.answer("Диагностические архивы доступны только в личных сообщениях бота.")
        return
    text = message.text or ""
    argument = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else "24h"
    try:
        hours = diagnostic_service.parse_window(argument)
    except ValueError as error:
        await message.answer(f"<b>Неверный период</b>\n\n{escape(str(error))}")
        return
    status = await message.answer("Собираю безопасный диагностический ZIP…")
    await _send_bundle(
        message=message,
        bot=bot,
        diagnostic_service=diagnostic_service,
        system_service=system_service,
        worker_manager=worker_manager,
        window_hours=hours,
    )
    await status.delete()


@router.callback_query(DiagnosticCallback.filter())
async def handle_diagnostic_callback(
    callback: CallbackQuery,
    callback_data: DiagnosticCallback,
    bot: Bot,
    diagnostic_service: DiagnosticBundleService,
    system_service: SystemHealthService,
    worker_manager: WorkerManager,
) -> None:
    if not isinstance(callback.message, Message) or not _private_only(callback.message):
        await callback.answer("Диагностика доступна только в ЛС бота.", show_alert=True)
        return
    action = callback_data.action
    if action == "status":
        report = await _build_report(
            bot=bot,
            system_service=system_service,
            worker_manager=worker_manager,
        )
        await callback.message.edit_text(_status_text(report), reply_markup=_keyboard())
        await callback.answer()
        return
    if action.startswith("export."):
        hours = int(action.removeprefix("export."))
        await callback.answer("Собираю ZIP…")
        await _send_bundle(
            message=callback.message,
            bot=bot,
            diagnostic_service=diagnostic_service,
            system_service=system_service,
            worker_manager=worker_manager,
            window_hours=hours,
        )
        return
    await callback.answer("Неизвестное диагностическое действие.", show_alert=True)


__all__ = ("DiagnosticCallback", "router")
