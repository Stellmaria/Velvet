from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from velvet_bot.access import AccessPolicy
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.owner_menu import build_owner_main_keyboard, owner_menu_text
from velvet_bot.workspace_ui import build_start_keyboard

router = Router(name=__name__)


@router.message(CommandStart())
async def handle_start(
    message: Message,
    bot_username: str,
    access_policy: AccessPolicy,
    workspace_product_service: WorkspaceProductService,
) -> None:
    is_global_owner = access_policy.allows_user(message.from_user)
    if is_global_owner:
        first_name = message.from_user.first_name if message.from_user else ""
        await message.answer(
            owner_menu_text(first_name),
            reply_markup=build_owner_main_keyboard(),
        )
        return

    user_id = message.from_user.id if message.from_user else 0
    state = await workspace_product_service.get_start_state(user_id)
    extra = (
        "\n\nСтэл выдала вам право создать отдельный приватный архив."
        if state.can_create
        else ""
    )
    if state.owned_workspaces:
        extra += "\n\nУ вас есть личное пространство. Его настройки доступны отдельно."
    await message.answer(
        "<b>Velvet Archive</b>\n\n"
        "Можно просматривать только архивы, владельцы которых включили публичный "
        "режим read-only. Личные архивы создаются приватными и не пересекаются "
        "с персонажами, каналами и настройками других владельцев."
        + extra,
        reply_markup=build_start_keyboard(
            can_create=state.can_create,
            has_workspace=bool(state.owned_workspaces),
        ),
    )


__all__ = ("router",)
