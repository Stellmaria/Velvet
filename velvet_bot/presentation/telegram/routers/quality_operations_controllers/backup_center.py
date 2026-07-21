from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.backup_service import BackupError, BackupRecord, BackupService
from velvet_bot.database import Database

router = Router(name=__name__)

_KIND_LABELS = {
    "manual": "ручная",
    "daily": "ежедневная",
    "weekly": "еженедельная",
    "pre_migration": "перед миграцией",
}
_STATUS_LABELS = {
    "running": "⏳ создаётся",
    "valid": "✅ проверена",
    "invalid": "⚠️ не прошла проверку",
    "failed": "❌ ошибка",
}


class BackupCallback(CallbackData, prefix="bkp"):
    action: str
    page: int = 0
    backup_id: int = 0


def _cb(action: str, *, page: int = 0, backup_id: int = 0) -> str:
    return BackupCallback(
        action=action,
        page=max(0, int(page)),
        backup_id=max(0, int(backup_id)),
    ).pack()


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💾 Создать копию сейчас",
                    callback_data=_cb("create"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 История копий",
                    callback_data=_cb("history"),
                ),
                InlineKeyboardButton(
                    text="✅ Проверить последнюю",
                    callback_data=_cb("verify"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚙ Настройки",
                    callback_data=_cb("settings"),
                ),
                InlineKeyboardButton(
                    text="🧹 Очистить старые",
                    callback_data=_cb("cleanup"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=_cb("menu"),
                ),
                InlineKeyboardButton(text="✖ Закрыть", callback_data=_cb("close")),
            ],
        ]
    )


def _settings_keyboard(
    *,
    daily_enabled: bool,
    weekly_enabled: bool,
    retention_count: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "✅ Ежедневная включена"
                        if daily_enabled
                        else "⛔ Ежедневная выключена"
                    ),
                    callback_data=_cb("daily"),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "✅ Еженедельная включена"
                        if weekly_enabled
                        else "⛔ Еженедельная выключена"
                    ),
                    callback_data=_cb("weekly"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="➖ Меньше",
                    callback_data=_cb("retminus"),
                ),
                InlineKeyboardButton(
                    text="➕ Больше",
                    callback_data=_cb("retplus"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"📦 Хранить: {retention_count}",
                    callback_data=_cb("noop"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Центр копий",
                    callback_data=_cb("menu"),
                ),
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=_cb("settings"),
                ),
            ],
        ]
    )


def _human_size(value: int | None) -> str:
    size = max(0, int(value or 0))
    units = ("Б", "КБ", "МБ", "ГБ", "ТБ")
    amount = float(size)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.0f} {unit}" if unit == "Б" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{size} Б"


def _date(value) -> str:
    return value.astimezone().strftime("%d.%m.%Y %H:%M") if value else "—"


def _record_line(record: BackupRecord) -> str:
    kind = _KIND_LABELS.get(record.backup_kind, record.backup_kind)
    status = _STATUS_LABELS.get(record.status, record.status)
    file_state = record.file_name or "файл удалён ротацией"
    return (
        f"<b>#{record.id}</b> · {escape(kind)} · {status}\n"
        f"<code>{escape(file_state)}</code> · {_human_size(record.size_bytes)} · "
        f"{_date(record.started_at)}"
    )


async def _edit(
    callback: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


async def _menu_text(
    backup_service: BackupService,
    database: Database,
) -> str:
    history = await backup_service.list_history(database, limit=1)
    last = history[0] if history else None
    last_text = _record_line(last) if last else "• копий пока нет"
    return (
        "<b>Центр резервных копий Velvet</b>\n\n"
        "Резервируется вся PostgreSQL-база: персонажи, истории, медиа-связи, "
        "промты, file_id и превью, аналитика, очередь публикаций, решения по "
        "дублям, роли и настройки.\n\n"
        "<b>Последняя операция</b>\n"
        f"{last_text}\n\n"
        "Автоматического восстановления рабочей базы здесь нет. Для восстановления "
        "нужна отдельная команда администратора на сервере и проверка архива."
    )


async def _show_menu(
    callback: CallbackQuery,
    backup_service: BackupService,
    database: Database,
) -> None:
    await _edit(
        callback,
        await _menu_text(backup_service, database),
        _main_keyboard(),
    )


async def _show_settings(
    callback: CallbackQuery,
    backup_service: BackupService,
    database: Database,
) -> None:
    settings = await backup_service.get_settings(database)
    weekday = (
        "Пн",
        "Вт",
        "Ср",
        "Чт",
        "Пт",
        "Сб",
        "Вс",
    )[settings.weekly_weekday]
    text = (
        "<b>⚙ Настройки резервных копий</b>\n\n"
        f"Ежедневная: <b>{'включена' if settings.daily_enabled else 'выключена'}</b> "
        f"в <code>{settings.daily_hour:02d}:00</code>\n"
        f"Еженедельная полная: "
        f"<b>{'включена' if settings.weekly_enabled else 'выключена'}</b> "
        f"в <code>{weekday} {settings.weekly_hour:02d}:00</code>\n"
        f"Часовой пояс: <code>{escape(settings.timezone)}</code>\n"
        f"Хранить последних файлов: <b>{settings.retention_count}</b>\n\n"
        "Перед применением новых SQL-миграций бот отдельно создаёт и проверяет "
        "предмиграционную копию. Если проверка не проходит, запуск останавливается."
    )
    await _edit(
        callback,
        text,
        _settings_keyboard(
            daily_enabled=settings.daily_enabled,
            weekly_enabled=settings.weekly_enabled,
            retention_count=settings.retention_count,
        ),
    )


@router.message(Command("backup"))
async def handle_backup_menu(
    message: Message,
    backup_service: BackupService,
    database: Database,
) -> None:
    await message.answer(
        await _menu_text(backup_service, database),
        reply_markup=_main_keyboard(),
    )


@router.callback_query(BackupCallback.filter())
async def handle_backup_callback(
    callback: CallbackQuery,
    callback_data: BackupCallback,
    backup_service: BackupService,
    database: Database,
) -> None:
    action = callback_data.action
    if action == "noop":
        await callback.answer()
        return
    if action == "close":
        if isinstance(callback.message, Message):
            await callback.message.delete()
        await callback.answer()
        return

    try:
        if action == "menu":
            await _show_menu(callback, backup_service, database)
        elif action == "create":
            await _edit(
                callback,
                "<b>⏳ Создаю резервную копию</b>\n\n"
                "Запускаю pg_dump и затем проверяю архив через pg_restore.",
                InlineKeyboardMarkup(inline_keyboard=[]),
            )
            record = await backup_service.create_backup(
                database,
                backup_kind="manual",
                created_by=callback.from_user.id,
            )
            await _edit(
                callback,
                "<b>Резервная копия создана</b>\n\n"
                f"{_record_line(record)}\n"
                f"SHA-256: <code>{escape(record.sha256 or '—')}</code>\n"
                f"Схема: <code>{escape(record.schema_version or '—')}</code>\n\n"
                f"{escape(str(record.validation.get('message', 'Проверка завершена.')))}",
                _main_keyboard(),
            )
        elif action == "history":
            history = await backup_service.list_history(database, limit=12)
            text = (
                "<b>📋 История резервных копий</b>\n\n"
                + (
                    "\n\n".join(_record_line(record) for record in history)
                    if history
                    else "• операций пока нет"
                )
            )
            await _edit(
                callback,
                text,
                InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="↩️ Центр копий",
                                callback_data=_cb("menu"),
                            ),
                            InlineKeyboardButton(
                                text="🔄 Обновить",
                                callback_data=_cb("history"),
                            ),
                        ]
                    ]
                ),
            )
        elif action == "verify":
            await _edit(
                callback,
                "<b>⏳ Проверяю последнюю копию</b>\n\n"
                "Сверяю контрольную сумму, читаемость архива, таблицы и версию схемы.",
                InlineKeyboardMarkup(inline_keyboard=[]),
            )
            record = await backup_service.verify_latest(database)
            await _edit(
                callback,
                "<b>Проверка резервной копии завершена</b>\n\n"
                f"{_record_line(record)}\n"
                f"SHA-256: <code>{escape(record.sha256 or '—')}</code>\n\n"
                f"{escape(str(record.validation.get('message', 'Проверка завершена.')))}",
                _main_keyboard(),
            )
        elif action == "settings":
            await _show_settings(callback, backup_service, database)
        elif action in {"daily", "weekly", "retminus", "retplus"}:
            settings = await backup_service.get_settings(database)
            if action == "daily":
                await backup_service.update_settings(
                    database,
                    daily_enabled=not settings.daily_enabled,
                    updated_by=callback.from_user.id,
                )
            elif action == "weekly":
                await backup_service.update_settings(
                    database,
                    weekly_enabled=not settings.weekly_enabled,
                    updated_by=callback.from_user.id,
                )
            else:
                delta = -1 if action == "retminus" else 1
                await backup_service.update_settings(
                    database,
                    retention_count=settings.retention_count + delta,
                    updated_by=callback.from_user.id,
                )
            await _show_settings(callback, backup_service, database)
        elif action == "cleanup":
            result = await backup_service.cleanup_old_backups(database)
            await _edit(
                callback,
                "<b>🧹 Очистка завершена</b>\n\n"
                f"Удалено файлов: <b>{result.deleted_files}</b>\n"
                f"Освобождено: <b>{_human_size(result.freed_bytes)}</b>\n"
                f"Оставлено файлов: <b>{result.retained_files}</b>",
                _main_keyboard(),
            )
        else:
            await callback.answer("Неизвестное действие резервных копий.", show_alert=True)
            return
    except BackupError as error:
        await _edit(
            callback,
            "<b>Операция резервного копирования не выполнена</b>\n\n"
            f"{escape(str(error))}",
            _main_keyboard(),
        )
    except Exception as error:  # p2-approved-boundary: report-backup-callback-failure
        try:
            await _edit(
                callback,
                "<b>Операция завершилась ошибкой</b>\n\n"
                f"{escape(str(error))}",
                _main_keyboard(),
            )
        except TelegramBadRequest:
            pass
        raise

    await callback.answer()
