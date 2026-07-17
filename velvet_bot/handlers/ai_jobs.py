from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from velvet_bot.ai_jobs import AIJobRepository
from velvet_bot.ai_jobs_ui import build_job_detail_text, build_job_keyboard, build_job_list
from velvet_bot.database import Database
from velvet_bot.quality_ui import QualityCallback


router = Router(name=__name__)


async def _safe_edit(message: Message, text: str, reply_markup) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


@router.callback_query(QualityCallback.filter(F.action == "aijobs"))
async def handle_ai_job_list(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    page = await AIJobRepository(database).list_recent(
        created_by=callback.from_user.id,
        page=callback_data.page,
    )
    text, keyboard = build_job_list(page)
    await _safe_edit(callback.message, text, keyboard)
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "aijob"))
async def handle_ai_job_detail(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    job = await AIJobRepository(database).get(
        callback_data.item_id,
        created_by=callback.from_user.id,
    )
    if job is None:
        await callback.answer("AI-задание не найдено.", show_alert=True)
        return
    await _safe_edit(
        callback.message,
        build_job_detail_text(job),
        build_job_keyboard(job, page=callback_data.page),
    )
    await callback.answer()


__all__ = ("router",)
