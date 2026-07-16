from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from velvet_bot.error_center import ErrorIncidentCenter

logger = logging.getLogger(__name__)
router = Router(name=__name__)


@router.message(Command("test_error_alert"))
async def test_error_alert_command(message: Message) -> None:
    owner_id = message.from_user.id if message.from_user is not None else 0
    logger.error("Manual error-center test requested by owner_id=%s", owner_id)
    await message.answer(
        "Тестовая ошибка записана. Проверьте лог-чат и личные сообщения владельца."
    )


@router.callback_query(F.data.startswith("err:ack:"))
async def acknowledge_error_callback(
    callback: CallbackQuery,
    error_center: ErrorIncidentCenter,
) -> None:
    raw_id = (callback.data or "").rsplit(":", maxsplit=1)[-1]
    try:
        incident_id = int(raw_id)
    except ValueError:
        await callback.answer("Некорректный номер ошибки.", show_alert=True)
        return

    acknowledged = await error_center.acknowledge_incident(
        incident_id,
        callback.from_user.id,
    )
    if acknowledged:
        await callback.answer("Ошибка отмечена просмотренной.")
    else:
        await callback.answer("Ошибка уже удалена или не найдена.", show_alert=True)


@router.callback_query(F.data == "err:ackall")
async def acknowledge_all_errors_callback(
    callback: CallbackQuery,
    error_center: ErrorIncidentCenter,
) -> None:
    count = await error_center.acknowledge_all(callback.from_user.id)
    await callback.answer(f"Просмотрено ошибок: {count}.")
    if callback.message is not None:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


__all__ = ("router",)
