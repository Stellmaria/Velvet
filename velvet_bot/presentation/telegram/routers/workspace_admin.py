from __future__ import annotations

from typing import cast

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import (
    GLOBAL_WORKSPACE_CREATOR_ID,
    WORKSPACE_MODULE_KEYS,
    WorkspaceModuleKey,
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
    workspace_id = int(parts[1])
    raw_module_key = parts[2].casefold()
    enabled = _parse_switch(parts[3])
    if raw_module_key not in WORKSPACE_MODULE_KEYS or enabled is None:
        await message.answer("Неизвестный модуль или значение on/off.")
        return
    module_key = cast(WorkspaceModuleKey, raw_module_key)
    if (
        workspace_id == DEFAULT_WORKSPACE_ID
        and module_key == "public_archive"
        and not enabled
    ):
        await message.answer("Системный Velvet Anatomy должен оставаться публичным.")
        return
    setting = await workspace_product_service.set_module_allowed(
        actor_user_id=actor_user_id,
        workspace_id=workspace_id,
        module_key=module_key,
        is_allowed=enabled,
    )
    if module_key == "public_archive" and not enabled:
        await workspace_product_service.set_public_archive_enabled(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            enabled=False,
            global_owner=True,
        )
    await message.answer(
        f"Модуль <code>{setting.module_key}</code> "
        + ("разрешён." if setting.is_allowed else "запрещён и скрыт.")
    )


__all__ = ("router",)
