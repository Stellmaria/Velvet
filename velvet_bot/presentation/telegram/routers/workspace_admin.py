from __future__ import annotations

from html import escape
from typing import cast

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from velvet_bot.domains.workspaces.character_management import WorkspaceCharacterService
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID, WorkspaceRole
from velvet_bot.domains.workspaces.product_models import (
    GLOBAL_WORKSPACE_CREATOR_ID,
    WORKSPACE_MODULE_KEYS,
    WorkspaceModuleKey,
)
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.workspace_ui import (
    WorkspaceCallback,
    build_module_help_keyboard,
    build_modules_keyboard,
)

router = Router(name=__name__)


class WorkspaceForm(StatesGroup):
    """Additional workspace form state sharing the middleware-approved group name."""

    waiting_character_command = State()


def _parse_switch(value: str) -> bool | None:
    normalized = value.strip().casefold()
    if normalized in {"on", "true", "1", "да", "вкл", "enable"}:
        return True
    if normalized in {"off", "false", "0", "нет", "выкл", "disable"}:
        return False
    return None


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _require_character_access(
    *,
    workspace_product_service: WorkspaceProductService,
    workspace_service: WorkspaceService,
    workspace_id: int,
    user_id: int,
    minimum_role: str,
) -> None:
    await workspace_service.require_role(
        workspace_id=int(workspace_id),
        user_id=int(user_id),
        minimum_role=cast(WorkspaceRole, minimum_role),
        global_owner=_is_global_owner(user_id),
    )
    if not await workspace_product_service.is_module_enabled(
        workspace_id=workspace_id,
        module_key="characters",
    ):
        raise WorkspaceAccessError("Модуль персонажей выключен или не разрешён Стэл.")


def _story_text(value: str) -> str:
    story_id, primary, short_label, title = value.split("|", maxsplit=3)
    marker = "⭐" if primary == "1" else "📖"
    return (
        f"{marker} <code>{escape(story_id)}</code> "
        f"{escape(short_label)} · {escape(title)}"
    )


def _classification_text(row) -> str:
    category = escape(str(row.category)) if row.category else "не выбрана"
    universe = escape(str(row.universe)) if row.universe else "не выбрана"
    return f"{category} / {universe}"


async def _format_character_panel(
    workspace_characters: WorkspaceCharacterService,
    *,
    workspace_id: int,
    workspace_name: str,
) -> str:
    rows = await workspace_characters.list(workspace_id=workspace_id)
    lines = [
        f"<b>👥 Персонажи · {escape(workspace_name)}</b>",
        "",
    ]
    if rows:
        for row in rows[:25]:
            stories = row.stories
            story_mark = f" · 📖 {len(stories)}" if stories else ""
            lines.append(
                f"• <code>#{row.id}</code> <b>{escape(row.name)}</b>"
                f" · {_classification_text(row)}{story_mark}"
            )
        if len(rows) > 25:
            lines.append(f"…и ещё {len(rows) - 25}.")
    else:
        lines.append("Персонажей пока нет.")

    lines.extend(
        [
            "",
            "<b>Управление в этом разделе</b>",
            "<code>создать Имя персонажа</code>",
            "<code>карточка ID</code>",
            "<code>категория ID key</code>",
            "<code>вселенная ID key</code>",
            "<code>история ID story_id</code> — добавить или убрать",
            "<code>структура</code> — доступные значения и ID историй",
            "<code>список</code> — обновить",
            "<code>выход</code> — закончить настройку",
            "",
            "Категории, вселенные и истории берутся только из структуры этого архива.",
        ]
    )
    return "\n".join(lines)


async def _format_taxonomy(
    workspace_product_service: WorkspaceProductService,
    *,
    workspace_id: int,
) -> str:
    categories = tuple(
        item
        for item in await workspace_product_service.list_categories(workspace_id)
        if item.is_enabled
    )
    universes = tuple(
        item
        for item in await workspace_product_service.list_universes(workspace_id)
        if item.is_enabled
    )
    stories = tuple(
        item
        for item in await workspace_product_service.list_stories(
            workspace_id=workspace_id
        )
        if item.is_enabled
    )
    lines = ["<b>🗂 Структура архива</b>", "", "<b>Категории</b>"]
    lines.extend(
        f"{escape(row.emoji)} <code>{escape(row.key)}</code> · {escape(row.label)}"
        for row in categories
    )
    lines.extend(["", "<b>Вселенные</b>"])
    lines.extend(
        f"{escape(row.emoji)} <code>{escape(row.key)}</code> · {escape(row.label)}"
        + (" · история обязательна" if row.requires_story else "")
        for row in universes
    )
    lines.extend(["", "<b>Истории</b>"])
    lines.extend(
        f"📖 <code>{row.id}</code> · {escape(row.universe_key)} · "
        f"{escape(row.short_label)} · {escape(row.title)}"
        for row in stories[:60]
    )
    if len(stories) > 60:
        lines.append(f"…и ещё {len(stories) - 60}.")
    if not stories:
        lines.append("Историй пока нет.")
    return "\n".join(lines)


async def _format_character_card(
    workspace_characters: WorkspaceCharacterService,
    *,
    workspace_id: int,
    character_id: int,
) -> str:
    row = await workspace_characters.load(
        workspace_id=workspace_id,
        character_id=character_id,
    )
    if row is None:
        raise ValueError("Персонаж не найден в этом архиве.")
    lines = [
        "<b>Карточка персонажа</b>",
        "",
        f"Имя: <b>{escape(row.name)}</b>",
        f"ID: <code>{row.id}</code>",
        f"Категория / вселенная: {_classification_text(row)}",
        "",
        "<b>Истории</b>",
    ]
    stories = row.stories
    lines.extend(
        f"{'⭐' if story.is_primary else '📖'} <code>{story.id}</code> "
        f"{escape(story.short_label)} · {escape(story.title)}"
        for story in stories
    )
    if not stories:
        lines.append("Не назначены.")
    return "\n".join(lines)


async def handle_workspace_character_module(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    workspace_characters: WorkspaceCharacterService,
    workspace_product_service: WorkspaceProductService,
    workspace_service: WorkspaceService,
) -> None:
    user_id = callback.from_user.id
    try:
        workspace = await workspace_service.set_active_workspace(
            workspace_id=int(callback_data.workspace_id),
            user_id=user_id,
            global_owner=_is_global_owner(user_id),
        )
        if workspace.is_system:
            await callback.answer(
                "Системный Velvet использует существующий раздел персонажей.",
                show_alert=True,
            )
            return
        await _require_character_access(
            workspace_product_service=workspace_product_service,
            workspace_service=workspace_service,
            workspace_id=workspace.id,
            user_id=user_id,
            minimum_role="owner",
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    await state.set_state(WorkspaceForm.waiting_character_command)
    await state.update_data(
        workspace_id=workspace.id,
        workspace_name=workspace.name,
    )
    text = await _format_character_panel(
        workspace_characters,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
    )
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                text,
                reply_markup=build_module_help_keyboard(workspace.id),
            )
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                await callback.message.answer(
                    text,
                    reply_markup=build_module_help_keyboard(workspace.id),
                )
    await callback.answer()


async def handle_workspace_character_back(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    workspace_product_service: WorkspaceProductService,
    workspace_service: WorkspaceService,
) -> None:
    user_id = callback.from_user.id
    try:
        workspace = await workspace_service.set_active_workspace(
            workspace_id=int(callback_data.workspace_id),
            user_id=user_id,
            global_owner=_is_global_owner(user_id),
        )
        modules = await workspace_product_service.list_modules(
            workspace_id=workspace.id,
            actor_user_id=user_id,
            global_owner=_is_global_owner(user_id),
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await state.clear()
    text = (
        f"<b>🧩 Модули · {escape(workspace.name)}</b>\n\n"
        "✅ включён, ➖ выключен владельцем, ⛔ не разрешён Стэл. "
        "Кнопка ℹ️ объясняет назначение каждого модуля."
    )
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                text,
                reply_markup=build_modules_keyboard(workspace.id, modules),
            )
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                await callback.message.answer(
                    text,
                    reply_markup=build_modules_keyboard(workspace.id, modules),
                )
    await callback.answer()


async def handle_workspace_character_message(
    message: Message,
    state: FSMContext,
    workspace_characters: WorkspaceCharacterService,
    workspace_product_service: WorkspaceProductService,
    workspace_service: WorkspaceService,
) -> None:
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    workspace_name = str(data.get("workspace_name") or "Личный архив")
    user_id = message.from_user.id if message.from_user else 0
    if workspace_id <= 0:
        await state.clear()
        await message.answer("Сессия пространства устарела. Откройте раздел заново.")
        return
    try:
        await _require_character_access(
            workspace_product_service=workspace_product_service,
            workspace_service=workspace_service,
            workspace_id=workspace_id,
            user_id=user_id,
            minimum_role="owner",
        )
    except WorkspaceAccessError as error:
        await state.clear()
        await message.answer(escape(str(error)))
        return

    raw = " ".join((message.text or "").split())
    command, _, tail = raw.partition(" ")
    action = command.casefold()
    try:
        if action in {"выход", "закрыть", "exit"}:
            await state.clear()
            await message.answer("Настройка персонажей завершена.")
            return
        if action in {"список", "list"}:
            await message.answer(
                await _format_character_panel(
                    workspace_characters,
                    workspace_id=workspace_id,
                    workspace_name=workspace_name,
                )
            )
            return
        if action in {"структура", "taxonomy"}:
            await message.answer(
                await _format_taxonomy(
                    workspace_product_service,
                    workspace_id=workspace_id,
                )
            )
            return
        if action in {"создать", "create"}:
            if not tail:
                raise ValueError("После «создать» укажите имя персонажа.")
            character, created = await workspace_characters.create(
                name=tail,
                created_by=user_id,
                created_in_chat=message.chat.id,
                workspace_id=workspace_id,
            )
            await message.answer(
                (
                    "Персонаж создан: "
                    if created
                    else "Персонаж уже существовал: "
                )
                + f"<b>{escape(character.name)}</b> <code>#{character.id}</code>."
            )
            return

        parts = tail.split(maxsplit=1)
        if action in {"карточка", "profile"}:
            if not tail.isdigit():
                raise ValueError("Формат: <code>карточка ID</code>")
            await message.answer(
                await _format_character_card(
                    workspace_characters,
                    workspace_id=workspace_id,
                    character_id=int(tail),
                )
            )
            return
        if action in {"категория", "category"}:
            if len(parts) != 2 or not parts[0].isdigit():
                raise ValueError("Формат: <code>категория ID key</code>")
            key = None if parts[1] in {"-", "нет", "off"} else parts[1].casefold()
            await workspace_characters.set_category(
                workspace_id=workspace_id,
                character_id=int(parts[0]),
                category_key=key,
            )
            await message.answer("Категория персонажа обновлена.")
            return
        if action in {"вселенная", "universe"}:
            if len(parts) != 2 or not parts[0].isdigit():
                raise ValueError("Формат: <code>вселенная ID key</code>")
            key = None if parts[1] in {"-", "нет", "off"} else parts[1].casefold()
            await workspace_characters.set_universe(
                workspace_id=workspace_id,
                character_id=int(parts[0]),
                universe_key=key,
            )
            await message.answer(
                "Вселенная обновлена. Старые привязки историй очищены."
            )
            return
        if action in {"история", "story"}:
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                raise ValueError("Формат: <code>история ID story_id</code>")
            assigned = await workspace_characters.toggle_story(
                workspace_id=workspace_id,
                character_id=int(parts[0]),
                story_id=int(parts[1]),
                assigned_by_user_id=user_id,
            )
            await message.answer(
                "История добавлена персонажу."
                if assigned
                else "История удалена у персонажа."
            )
            return
        raise ValueError(
            "Неизвестное действие. Используйте: создать, карточка, категория, "
            "вселенная, история, структура, список или выход."
        )
    except ValueError as error:
        await message.answer(escape(str(error)))


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


router.message.register(
    handle_workspace_module_policy,
    Command("workspace_module"),
)
router.callback_query.register(
    handle_workspace_character_module,
    WorkspaceCallback.filter(
        (F.action == "module") & (F.module_key == "characters")
    ),
)
router.callback_query.register(
    handle_workspace_character_back,
    WorkspaceCallback.filter(F.action == "modules"),
    StateFilter(WorkspaceForm.waiting_character_command),
)
router.message.register(
    handle_workspace_character_message,
    StateFilter(WorkspaceForm.waiting_character_command),
)


__all__ = (
    "router",
)
