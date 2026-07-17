from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from velvet_bot.database import Database
from velvet_bot.reference_catalog import get_reference_page
from velvet_bot.reference_ui import ReferenceCallback

router = Router(name=__name__)


@router.callback_query(ReferenceCallback.filter(F.action == "compare_help"))
async def handle_reference_compare_help(
    callback: CallbackQuery,
    callback_data: ReferenceCallback,
    database: Database,
) -> None:
    page = await get_reference_page(
        database,
        callback_data.character_id,
        callback_data.offset,
    )
    if page is None or page.reference is None:
        await callback.answer("Референс больше недоступен.", show_alert=True)
        return

    command = f"/compare_ref {page.character.name} {page.offset + 1}"
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "<b>🔎 Сравнение результата с референсом</b>\n\n"
            "1. Отправьте готовое изображение в этот личный чат.\n"
            "2. Ответьте на него командой:\n"
            f"<code>{escape(command)}</code>\n\n"
            "Qwen сравнит лицо, волосы, телосложение и уникальные видимые признаки."
        )
        await callback.answer()
        return

    await callback.answer(
        f"В ЛС боту ответьте на результат командой {command}"[:190],
        show_alert=True,
    )


__all__ = ("router",)
