from __future__ import annotations

import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.character_management import create_workspace_character
from velvet_bot.domains.workspaces.character_topics import ensure_character_archive_topic
from velvet_bot.domains.workspaces.models import WorkspaceRole
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.routers.workspace_character_management import (
    WorkspaceForm,
)

router = Router(name=__name__)
_CREATE_PATTERN = re.compile(r"^\s*(?:создать|create)(?:\s+|$)", re.IGNORECASE)


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _characters_enabled(database: Database, *, workspace_id: int) -> bool:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT
              AND module_key = 'characters'
            """,
            int(workspace_id),
        )
    return bool(value)


async def handle_workspace_character_create_with_topic(
    message: Message,
    state: FSMContext,
    database: Database,
    workspace_service: WorkspaceService,
    bot: Bot,
) -> None:
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    user_id = message.from_user.id if message.from_user else 0
    if workspace_id <= 0:
        await state.clear()
        await message.answer("Сессия пространства устарела. Откройте раздел заново.")
        return

    raw = " ".join((message.text or "").split())
    _, _, character_name = raw.partition(" ")
    if not character_name.strip():
        await message.answer("После «создать» укажите имя персонажа.")
        return

    try:
        await workspace_service.require_role(
            workspace_id=workspace_id,
            user_id=user_id,
            minimum_role=WorkspaceRole.EDITOR,
            global_owner=_is_global_owner(user_id),
        )
        if not await _characters_enabled(database, workspace_id=workspace_id):
            raise WorkspaceAccessError(
                "Модуль персонажей выключен или не разрешён Стэл."
            )
    except WorkspaceAccessError as error:
        await state.clear()
        await message.answer(escape(str(error)))
        return

    try:
        character, created = await create_workspace_character(
            database,
            workspace_id=workspace_id,
            name=character_name,
            created_by=user_id,
            created_in_chat=message.chat.id,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return

    topic_result = await ensure_character_archive_topic(
        bot=bot,
        database=database,
        workspace_id=workspace_id,
        character=character,
    )
    lines = [
        ("<b>Персонаж создан</b>" if created else "<b>Персонаж уже существовал</b>"),
        f"Имя: <b>{escape(character.name)}</b>",
        f"ID: <code>#{character.id}</code>",
    ]
    if topic_result.topic is not None:
        action = "создана и назначена" if topic_result.created else "уже назначена"
        lines.extend(
            [
                "",
                f"Тема архива: <b>{action}</b>",
                f'<a href="{escape(topic_result.topic.url, quote=True)}">Открыть ветку персонажа</a>',
                "Новые сохранённые материалы будут копироваться в эту ветку.",
            ]
        )
    elif topic_result.error:
        lines.extend(
            [
                "",
                "<b>⚠️ Персональная ветка не создана</b>",
                escape(topic_result.error),
                "Персонаж сохранён в базе; настройку ветки можно повторить позже.",
            ]
        )
    await message.answer("\n".join(lines), disable_web_page_preview=True)


router.message.register(
    handle_workspace_character_create_with_topic,
    StateFilter(WorkspaceForm.waiting_character_command),
    F.text.regexp(_CREATE_PATTERN),
)


__all__ = ("router",)
