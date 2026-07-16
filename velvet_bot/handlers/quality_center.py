from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message

from velvet_bot.analytics_dashboard import AnalyticsCallback
from velvet_bot.archive_ui import ArchiveMediaCallback
from velvet_bot.database import Database
from velvet_bot.handlers.admin_directory import AdminDirectoryCallback
from velvet_bot.media_quality import reset_failed_scans
from velvet_bot.quality_audit import (
    get_quality_summary,
    list_character_issues,
    list_media_issues,
    list_unresolved_hashtags,
    reset_broken_file_checks,
)
from velvet_bot.quality_ui import (
    QualityCallback,
    build_quality_dashboard,
    build_quality_page,
)

router = Router(name=__name__)

_SECTION_TITLES = {
    "missing_category": "Персонажи без категории",
    "missing_universe": "Персонажи без вселенной",
    "missing_story": "Персонажи без истории",
    "empty_characters": "Персонажи без материалов",
    "media_without_prompt": "Материалы без привязанного поста",
    "broken_files": "Недоступные Telegram-файлы",
    "scan_errors": "Ошибки визуального сканирования",
    "unresolved_hashtags": "Нераспознанные хэштеги",
}


async def _safe_edit(message: Message, text: str, reply_markup) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


async def _show_dashboard(message: Message, database: Database) -> None:
    summary = await get_quality_summary(database)
    text, keyboard = build_quality_dashboard(summary)
    await _safe_edit(message, text, keyboard)


@router.message(Command("quality", "auditarchive"))
async def handle_quality_command(message: Message, database: Database) -> None:
    summary = await get_quality_summary(database)
    text, keyboard = build_quality_dashboard(summary)
    await message.answer(text, reply_markup=keyboard)


async def _show_section(
    message: Message,
    database: Database,
    *,
    section: str,
    page_number: int,
) -> None:
    if section in {
        "missing_category",
        "missing_universe",
        "missing_story",
        "empty_characters",
    }:
        page = await list_character_issues(database, section, page=page_number)
    elif section in {"media_without_prompt", "broken_files", "scan_errors"}:
        page = await list_media_issues(database, section, page=page_number)
    elif section == "unresolved_hashtags":
        page = await list_unresolved_hashtags(database, page=page_number)
    else:
        raise ValueError("Неизвестный раздел аудита.")

    item_rows: list[list[InlineKeyboardButton]] = []
    for item in page.items:
        if item.character_id is not None and item.media_id is None:
            item_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"👤 {item.label}"[:60],
                        callback_data=AdminDirectoryCallback(
                            action="profile",
                            category=item.category or "uncategorized",
                            page=0,
                            character_id=item.character_id,
                        ).pack(),
                    )
                ]
            )
        elif item.character_id is not None and item.media_id is not None:
            item_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🖼 {item.label}"[:60],
                        callback_data=ArchiveMediaCallback(
                            action="open",
                            character_id=item.character_id,
                            offset=item.media_offset or 0,
                            media_id=item.media_id,
                        ).pack(),
                    )
                ]
            )

    extra_rows: list[list[InlineKeyboardButton]] = []
    if section == "unresolved_hashtags":
        extra_rows.append(
            [
                InlineKeyboardButton(
                    text="🔤 Назначить алиасы",
                    callback_data=AnalyticsCallback(
                        action="unresolved",
                        period="all",
                        page=page.page,
                        source_id=0,
                    ).pack(),
                )
            ]
        )
    if section == "broken_files" and page.total_items:
        extra_rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Проверить заново",
                    callback_data=QualityCallback(action="retry_broken").pack(),
                )
            ]
        )
    if section == "scan_errors" and page.total_items:
        extra_rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Повторить сканирование",
                    callback_data=QualityCallback(action="retry_scans").pack(),
                )
            ]
        )

    text, keyboard = build_quality_page(
        page,
        section=section,
        title=_SECTION_TITLES[section],
        item_rows=item_rows,
        extra_rows=extra_rows,
    )
    await _safe_edit(message, text, keyboard)


@router.callback_query(QualityCallback.filter(F.action == "noop"))
async def handle_quality_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "close"))
async def handle_quality_close(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "menu"))
async def handle_quality_menu(
    callback: CallbackQuery,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await _show_dashboard(callback.message, database)
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "section"))
async def handle_quality_section(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await _show_section(
        callback.message,
        database,
        section=callback_data.section,
        page_number=callback_data.page,
    )
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "retry_scans"))
async def handle_retry_scans(
    callback: CallbackQuery,
    database: Database,
) -> None:
    count = await reset_failed_scans(database)
    if isinstance(callback.message, Message):
        await _show_section(
            callback.message,
            database,
            section="scan_errors",
            page_number=0,
        )
    await callback.answer(f"Возвращено в очередь: {count}.", show_alert=True)


@router.callback_query(QualityCallback.filter(F.action == "retry_broken"))
async def handle_retry_broken(
    callback: CallbackQuery,
    database: Database,
) -> None:
    count = await reset_broken_file_checks(database)
    if isinstance(callback.message, Message):
        await _show_section(
            callback.message,
            database,
            section="broken_files",
            page_number=0,
        )
    await callback.answer(f"На повторную проверку: {count}.", show_alert=True)


@router.callback_query(QualityCallback.filter(F.action == "orphan_info"))
async def handle_orphan_info(
    callback: CallbackQuery,
    database: Database,
) -> None:
    summary = await get_quality_summary(database)
    await callback.answer(
        (
            f"Сиротских записей: {summary.orphan_media}. "
            "Они не связаны ни с одним персонажем. Автоматическое удаление отключено."
        ),
        show_alert=True,
    )
