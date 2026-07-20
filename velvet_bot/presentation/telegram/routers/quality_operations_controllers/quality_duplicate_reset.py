from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.domains.media_quality.reset_repository import DuplicateResetRepository
from velvet_bot.presentation.telegram.routers.quality_operations_controllers.quality_duplicates import (
    show_duplicate_list,
)
from velvet_bot.quality_ui import QualityCallback, quality_callback
from velvet_bot.workers import WorkerManager


router = Router(name=__name__)


async def _safe_edit(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


@router.callback_query(QualityCallback.filter(F.action == "dupresetask"))
async def handle_duplicate_reset_confirmation(
    callback: CallbackQuery,
    callback_data: QualityCallback,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Сбросить и пересканировать",
                    callback_data=quality_callback("dupreset"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=quality_callback(
                        "duplicates",
                        section=callback_data.section or "pending",
                        page=callback_data.page,
                    ),
                )
            ],
        ]
    )
    await _safe_edit(
        callback.message,
        "<b>♻️ Полностью пересканировать дубли?</b>\n\n"
        "Будут удалены рассчитанные fingerprints и пары дублей для доступных "
        "изображений. Прежние решения «подтверждено» и «разные изображения» для "
        "этих пар тоже сбросятся.\n\n"
        "Изображения больше 20 МБ без сохранённого preview не попадут в заведомо "
        "неисполнимую очередь.",
        keyboard,
    )
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "dupreset"))
async def handle_duplicate_reset(
    callback: CallbackQuery,
    database: Database,
    worker_manager: WorkerManager,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return

    result = await DuplicateResetRepository(database).reset_all()
    worker_note = "Первый цикл проверки запущен."
    try:
        await worker_manager.run_now("media-quality")
    except (RuntimeError, ValueError) as error:
        worker_note = f"Очередь сброшена, но worker не запущен: {escape(str(error))[:300]}"

    await callback.answer(
        f"В очередь возвращено изображений: {result.media_reset}.",
        show_alert=True,
    )
    await show_duplicate_list(
        callback.message,
        database,
        status="pending",
        page_number=0,
    )
    await callback.message.answer(
        "<b>♻️ Пересканирование дублей запущено</b>\n\n"
        f"Изображений в очереди: <b>{result.media_reset}</b>\n"
        f"Удалено fingerprints: <b>{result.fingerprints_deleted}</b>\n"
        f"Удалено старых пар: <b>{result.candidates_deleted}</b>\n\n"
        f"{worker_note} Остальные файлы обработает периодический worker."
    )


__all__ = ("router",)
