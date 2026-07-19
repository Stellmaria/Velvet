from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from velvet_bot.character_directory import list_category_summaries
from velvet_bot.database import Database
from velvet_bot.domains.characters.catalog import normalize_category
from velvet_bot.presentation.telegram.routers.characters.directory import (
    AdminDirectoryCallback,
    _category_keyboard,
    _category_text,
)

router = Router(name=__name__)


class InvalidDirectoryCategoryFilter(BaseFilter):
    async def __call__(
        self,
        callback: CallbackQuery,
        callback_data: AdminDirectoryCallback,
    ) -> bool:
        del callback
        try:
            normalize_category(
                callback_data.category,
                allow_uncategorized=True,
            )
        except ValueError:
            return True
        return False


@router.callback_query(
    AdminDirectoryCallback.filter(F.action == "menu"),
    InvalidDirectoryCategoryFilter(),
)
async def handle_invalid_directory_menu(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    del callback_data
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return

    summaries = await list_category_summaries(
        database,
        public_only=False,
        include_uncategorized=True,
    )
    await callback.message.edit_text(
        _category_text(sum(item.character_count for item in summaries)),
        reply_markup=_category_keyboard(summaries),
    )
    await callback.answer(
        "Категория в старой карточке устарела. Открыт список категорий.",
        show_alert=True,
    )


__all__ = ("InvalidDirectoryCategoryFilter", "router")
