from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from velvet_bot.database import Database
from velvet_bot.domains.media_rework import MediaReworkRepository
from velvet_bot.presentation.telegram.routers.quality_operations_controllers.quality_rework import (
    _list_keyboard,
    register_quality_rework_handlers,
)


async def handle_rework_command(message: Message, database: Database) -> None:
    repository = MediaReworkRepository(database)
    page = await repository.list_active(page=0)
    summary = await repository.summary()
    text = "\n".join(
        [
            "<b>🛠 Единая очередь доработки</b>",
            "",
            f"Активно: <b>{summary.active}</b>",
            f"Нужно исправить: <b>{summary.needs_fix}</b> · "
            f"проверяется: <b>{summary.checking}</b> · "
            f"ждёт решения: <b>{summary.ready_for_review}</b>",
            f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>",
            "",
            "Критичные оценки Qwen и решения администратора собираются здесь автоматически.",
        ]
    )
    await message.answer(text, reply_markup=_list_keyboard(page))


def register_quality_rework_entry(router: Router) -> None:
    router.message.register(
        handle_rework_command,
        Command("rework", "reworks", "quality_rework"),
    )
    register_quality_rework_handlers(router)


__all__ = ("register_quality_rework_entry",)
