from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from velvet_bot.domains.workspaces.product_models import (
    GLOBAL_WORKSPACE_CREATOR_ID,
    WORKSPACE_MODULE_KEYS,
)
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService

router = Router(name=__name__)


def _parse_switch(value: str) -> bool | None:
    normalized = value.strip().casefold()
    if normalized in {"on", "true", "1", "да", "вкл", "enable"}:
        return True
    if normalized in {"off", "false", "0", "нет", "выкл", "disable"}:
        return False
    return None


@router.message(Command("workspace_module"))
async def handle_workspace_module_policy(
    message: Message,
    workspace_product_service: WorkspaceProductService,
) -> None:
    actor_user_id = message.from_user.id if message.from_user else 0
    if actor_user_id != GLOBAL_WORKSPACE_CREATOR_ID:
        await message.answer("Эта команда доступна только Стэл.")
        return
    parts = (message.text or "").split()
    if len(parts) != 4 or not parts[1].isdigit():
        await message.answer(
            "Формат: <code>/workspace_module WORKSPACE_ID MODULE on|off</code>\n"
            "Доступные модули: <code>"
            + ", ".join(WORKSPACE_MODULE_KEYS)
            + "</code>"
        )
        return
    module_key = parts[2].casefold()
    enabled = _parse_switch(parts[3])
    if module_key not in WORKSPACE_MODULE_KEYS or enabled is None:
        await message.answer("Неизвестный модуль или значение on/off.")
        return
    setting = await workspace_product_service.set_module_allowed(
        actor_user_id=actor_user_id,
        workspace_id=int(parts[1]),
        module_key=module_key,
        is_allowed=enabled,
    )
    await message.answer(
        f"Модуль <code>{setting.module_key}</code> "
        + ("разрешён." if setting.is_allowed else "запрещён и скрыт.")
    )


__all__ = ("router",)
