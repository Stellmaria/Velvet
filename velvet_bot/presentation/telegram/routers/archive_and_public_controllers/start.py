from html import escape

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from velvet_bot.access import AccessPolicy
from velvet_bot.owner_menu import build_owner_main_keyboard, owner_menu_text
from velvet_bot.public_ui import build_public_entry_keyboard

router = Router(name=__name__)


@router.message(CommandStart())
async def handle_start(
    message: Message,
    bot_username: str,
    access_policy: AccessPolicy,
) -> None:
    is_owner = access_policy.allows_user(message.from_user)
    if not is_owner:
        await message.answer(
            "<b>Velvet Archive</b>\n\n"
            "В открытом доступе находится архив персонажей. "
            "Выберите категорию, вселенную и историю, затем откройте карточку "
            "персонажа. Материалы можно листать, отмечать лайком и подписываться "
            "на новые публикации персонажа.",
            reply_markup=build_public_entry_keyboard(),
        )
        return

    first_name = message.from_user.first_name if message.from_user else ""
    await message.answer(
        owner_menu_text(first_name),
        reply_markup=build_owner_main_keyboard(),
    )


__all__ = ("router",)
