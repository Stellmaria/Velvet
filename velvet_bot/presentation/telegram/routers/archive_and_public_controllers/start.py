from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from velvet_bot.access import AccessPolicy
from velvet_bot.app.save_sessions import SaveUploadSessions
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
    state: FSMContext,
    save_upload_sessions: SaveUploadSessions,
) -> None:
    # `/start` is the universal recovery route. It must never leave a stale
    # workspace form or pending upload active after a failed callback.
    await state.clear()
    if message.from_user is not None:
        save_upload_sessions.stop(
            chat_id=message.chat.id,
            user_id=message.from_user.id,
        )
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
    personal_count = len(state.owned_workspaces) + len(state.member_workspaces)
    if state.owned_workspaces:
        extra += "\n\nУ вас есть личный архив. Его настройки доступны отдельно."
    if state.member_workspaces:
        extra += "\n\nВам также доступны пространства команд, в которых вам выдали роль."
    await message.answer(
        "<b>Velvet Archive</b>\n\n"
        "Можно просматривать только архивы, владельцы которых включили публичный "
        "режим read-only. Личные архивы создаются приватными и не пересекаются "
        "с персонажами, каналами и настройками других владельцев."
        + extra,
        reply_markup=build_start_keyboard(
            can_create=state.can_create,
            has_workspace=bool(personal_count),
            workspace_count=personal_count,
            has_owned_workspace=bool(state.owned_workspaces),
        ),
    )


__all__ = ("router",)
