from __future__ import annotations

from html import escape
from typing import cast

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.character_management import (
    WorkspaceCharacterRecord,
    add_workspace_character_alias,
    create_workspace_character,
    delete_workspace_character,
    delete_workspace_character_alias,
    list_workspace_characters,
    load_workspace_character,
    rename_workspace_character,
    set_workspace_character_category,
    set_workspace_character_prompt_url,
    set_workspace_character_topic,
    set_workspace_character_universe,
    toggle_workspace_character_story,
)
from velvet_bot.domains.workspaces.models import WorkspaceRole
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.services.telegram_topics import validate_topic_access
from velvet_bot.topics import parse_private_topic_link
from velvet_bot.workspace_ui import (
    WorkspaceCallback,
    build_module_help_keyboard,
    build_modules_keyboard,
)


router = Router(name=__name__)


class WorkspaceForm(StatesGroup):
    waiting_character_command = State()


def _is_global_owner(user_id: int) -> bool:
    from velvet_bot.domains.workspaces.product_models import (
        GLOBAL_WORKSPACE_CREATOR_ID,
    )

    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _module_enabled(
    database: Database,
    *,
    workspace_id: int,
    module_key: str,
) -> bool:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT
              AND module_key = $2::VARCHAR
            """,
            int(workspace_id),
            module_key,
        )
    return bool(value)


async def _require_access(
    *,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_id: int,
    user_id: int,
    minimum_role: str = "editor",
) -> None:
    await workspace_service.require_role(
        workspace_id=int(workspace_id),
        user_id=int(user_id),
        minimum_role=cast(WorkspaceRole, minimum_role),
        global_owner=_is_global_owner(user_id),
    )
    if not await _module_enabled(
        database,
        workspace_id=workspace_id,
        module_key="characters",
    ):
        raise WorkspaceAccessError("Модуль персонажей выключен или не разрешён Стэл.")


def _classification_text(item: WorkspaceCharacterRecord) -> str:
    category = escape(item.category) if item.category else "не выбрана"
    universe = escape(item.universe) if item.universe else "не выбрана"
    return f"{category} / {universe}"


def _topic_text(item: WorkspaceCharacterRecord) -> str:
    if not item.archive_topic_url:
        return "Тема Telegram: <b>не назначена</b>"
    return (
        "Тема Telegram: "
        f'<a href="{escape(item.archive_topic_url, quote=True)}">открыть</a>'
    )


def _prompt_text(item: WorkspaceCharacterRecord) -> str:
    if not item.prompt_post_url:
        return "Промт: <b>не назначен</b>"
    return (
        "Промт: "
        f'<a href="{escape(item.prompt_post_url, quote=True)}">открыть пост</a>'
    )


async def _format_panel(
    database: Database,
    *,
    workspace_id: int,
    workspace_name: str,
) -> str:
    items = await list_workspace_characters(
        database,
        workspace_id=workspace_id,
        limit=100,
    )
    lines = [f"<b>👥 Персонажи · {escape(workspace_name)}</b>", ""]
    if items:
        for item in items[:25]:
            story_mark = f" · 📖 {len(item.stories)}" if item.stories else ""
            lines.append(
                f"• <code>#{item.id}</code> <b>{escape(item.name)}</b>"
                f" · {_classification_text(item)}{story_mark}"
            )
        if len(items) > 25:
            lines.append(f"…и ещё {len(items) - 25}.")
    else:
        lines.append("Персонажей пока нет.")

    lines.extend(
        [
            "",
            "<b>Основное</b>",
            "<code>создать Имя персонажа</code>",
            "<code>карточка ID</code>",
            "<code>переименовать ID Новое имя</code>",
            "<code>удалить ID</code> — потребуется подтверждение",
            "",
            "<b>Классификация</b>",
            "<code>категория ID key</code>",
            "<code>вселенная ID key</code>",
            "<code>история ID story_id</code> — добавить или убрать",
            "<code>структура</code> — категории, вселенные и ID историй",
            "",
            "<b>Связи</b>",
            "<code>алиас ID Значение</code>",
            "<code>убрать_алиас ID Значение</code>",
            "<code>промт ID ссылка</code> или <code>промт ID off</code>",
            "<code>тема ID ссылка</code> или <code>тема ID off</code>",
            "",
            "<code>список</code> — обновить · <code>выход</code> — закрыть",
        ]
    )
    return "\n".join(lines)


async def _format_taxonomy(
    database: Database,
    *,
    workspace_id: int,
) -> str:
    async with database.acquire() as connection:
        categories = await connection.fetch(
            """
            SELECT key, label, emoji
            FROM workspace_categories
            WHERE workspace_id = $1::BIGINT AND is_enabled
            ORDER BY sort_order, label, id
            """,
            int(workspace_id),
        )
        universes = await connection.fetch(
            """
            SELECT key, label, emoji, requires_story
            FROM workspace_universes
            WHERE workspace_id = $1::BIGINT AND is_enabled
            ORDER BY sort_order, label, id
            """,
            int(workspace_id),
        )
        stories = await connection.fetch(
            """
            SELECT id, universe_key, short_label, title
            FROM workspace_stories
            WHERE workspace_id = $1::BIGINT AND is_enabled
            ORDER BY universe_key, sort_order, title, id
            """,
            int(workspace_id),
        )

    lines = ["<b>🗂 Структура архива</b>", "", "<b>Категории</b>"]
    lines.extend(
        f"{escape(str(row['emoji']))} <code>{escape(str(row['key']))}</code> · "
        f"{escape(str(row['label']))}"
        for row in categories
    )
    if not categories:
        lines.append("Категорий пока нет.")

    lines.extend(["", "<b>Вселенные</b>"])
    lines.extend(
        f"{escape(str(row['emoji']))} <code>{escape(str(row['key']))}</code> · "
        f"{escape(str(row['label']))}"
        + (" · история обязательна" if row["requires_story"] else "")
        for row in universes
    )
    if not universes:
        lines.append("Вселенных пока нет.")

    lines.extend(["", "<b>Истории</b>"])
    lines.extend(
        f"📖 <code>{int(row['id'])}</code> · "
        f"{escape(str(row['universe_key']))} · "
        f"{escape(str(row['short_label']))} · {escape(str(row['title']))}"
        for row in stories[:60]
    )
    if len(stories) > 60:
        lines.append(f"…и ещё {len(stories) - 60}.")
    if not stories:
        lines.append("Историй пока нет.")
    return "\n".join(lines)


async def _format_card(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
) -> str:
    item = await load_workspace_character(
        database,
        workspace_id=workspace_id,
        character_id=character_id,
    )
    if item is None:
        raise ValueError("Персонаж не найден в этом архиве.")

    lines = [
        "<b>Карточка персонажа</b>",
        "",
        f"Имя: <b>{escape(item.name)}</b>",
        f"ID: <code>{item.id}</code>",
        f"Категория / вселенная: {_classification_text(item)}",
        _prompt_text(item),
        _topic_text(item),
        "",
        "<b>Алиасы</b>",
    ]
    manual_aliases = [alias for alias in item.aliases if alias.source != "name"]
    lines.extend(f"• <code>{escape(alias.alias)}</code>" for alias in manual_aliases)
    if not manual_aliases:
        lines.append("Не добавлены.")

    lines.extend(["", "<b>Истории</b>"])
    for story in item.stories:
        marker = "⭐" if story.is_primary else "📖"
        lines.append(
            f"{marker} <code>{story.id}</code> "
            f"{escape(story.short_label)} · {escape(story.title)}"
        )
    if not item.stories:
        lines.append("Не назначены.")
    return "\n".join(lines)


async def _edit_or_answer(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup,
) -> None:
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                await callback.message.answer(text, reply_markup=reply_markup)
    await callback.answer()


async def handle_workspace_character_module(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    database: Database,
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
        await _require_access(
            database=database,
            workspace_service=workspace_service,
            workspace_id=workspace.id,
            user_id=user_id,
            minimum_role="editor",
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    await state.set_state(WorkspaceForm.waiting_character_command)
    await state.update_data(
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        pending_delete_id=None,
    )
    await _edit_or_answer(
        callback,
        text=await _format_panel(
            database,
            workspace_id=workspace.id,
            workspace_name=workspace.name,
        ),
        reply_markup=build_module_help_keyboard(workspace.id),
    )


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
    await _edit_or_answer(
        callback,
        text=(
            f"<b>🧩 Модули · {escape(workspace.name)}</b>\n\n"
            "✅ включён, ➖ выключен владельцем, ⛔ не разрешён Стэл. "
            "Кнопка ℹ️ объясняет назначение каждого модуля."
        ),
        reply_markup=build_modules_keyboard(workspace.id, modules),
    )


def _parse_id_and_value(
    tail: str,
    *,
    usage: str,
) -> tuple[int, str]:
    parts = tail.split(maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].strip():
        raise ValueError(f"Формат: <code>{usage}</code>")
    return int(parts[0]), parts[1].strip()


async def handle_workspace_character_message(
    message: Message,
    state: FSMContext,
    database: Database,
    workspace_service: WorkspaceService,
    bot: Bot,
) -> None:
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    workspace_name = str(data.get("workspace_name") or "Личный архив")
    user_id = message.from_user.id if message.from_user else 0
    if workspace_id <= 0:
        await state.clear()
        await message.answer("Сессия пространства устарела. Откройте раздел заново.")
        return

    raw = " ".join((message.text or "").split())
    command, _, tail = raw.partition(" ")
    action = command.casefold()

    minimum_role = "admin" if action in {"удалить", "delete", "подтвердить", "confirm"} else "editor"
    try:
        await _require_access(
            database=database,
            workspace_service=workspace_service,
            workspace_id=workspace_id,
            user_id=user_id,
            minimum_role=minimum_role,
        )
    except WorkspaceAccessError as error:
        await state.clear()
        await message.answer(escape(str(error)))
        return

    try:
        if action in {"выход", "закрыть", "exit"}:
            await state.clear()
            await message.answer("Настройка персонажей завершена.")
            return

        if action in {"список", "list"}:
            await message.answer(
                await _format_panel(
                    database,
                    workspace_id=workspace_id,
                    workspace_name=workspace_name,
                )
            )
            return

        if action in {"структура", "taxonomy"}:
            await message.answer(
                await _format_taxonomy(database, workspace_id=workspace_id)
            )
            return

        if action in {"создать", "create"}:
            if not tail:
                raise ValueError("После «создать» укажите имя персонажа.")
            item, created = await create_workspace_character(
                database,
                workspace_id=workspace_id,
                name=tail,
                created_by=user_id,
                created_in_chat=message.chat.id,
            )
            await message.answer(
                ("Персонаж создан: " if created else "Персонаж уже существовал: ")
                + f"<b>{escape(item.name)}</b> <code>#{item.id}</code>."
            )
            return

        if action in {"карточка", "profile"}:
            if not tail.isdigit():
                raise ValueError("Формат: <code>карточка ID</code>")
            await message.answer(
                await _format_card(
                    database,
                    workspace_id=workspace_id,
                    character_id=int(tail),
                )
            )
            return

        if action in {"переименовать", "rename"}:
            character_id, new_name = _parse_id_and_value(
                tail,
                usage="переименовать ID Новое имя",
            )
            item = await rename_workspace_character(
                database,
                workspace_id=workspace_id,
                character_id=character_id,
                new_name=new_name,
            )
            await message.answer(
                f"Персонаж переименован: <b>{escape(item.name)}</b> "
                f"<code>#{item.id}</code>."
            )
            return

        if action in {"удалить", "delete"}:
            if not tail.isdigit():
                raise ValueError("Формат: <code>удалить ID</code>")
            item = await load_workspace_character(
                database,
                workspace_id=workspace_id,
                character_id=int(tail),
            )
            if item is None:
                raise ValueError("Персонаж не найден в этом архиве.")
            await state.update_data(pending_delete_id=item.id)
            await message.answer(
                "<b>Подтвердите удаление</b>\n\n"
                f"Персонаж: <b>{escape(item.name)}</b> <code>#{item.id}</code>\n"
                "Будут удалены его связи с медиа, историями, алиасами и темой.\n\n"
                f"Для подтверждения: <code>подтвердить {item.id}</code>\n"
                "Для отмены: <code>отмена</code>"
            )
            return

        if action in {"отмена", "cancel"}:
            await state.update_data(pending_delete_id=None)
            await message.answer("Удаление отменено.")
            return

        if action in {"подтвердить", "confirm"}:
            if not tail.isdigit():
                raise ValueError("Формат: <code>подтвердить ID</code>")
            pending_id = int((await state.get_data()).get("pending_delete_id") or 0)
            character_id = int(tail)
            if pending_id <= 0 or pending_id != character_id:
                raise ValueError(
                    "Нет совпадающего запроса на удаление. Сначала используйте "
                    "<code>удалить ID</code>."
                )
            deleted = await delete_workspace_character(
                database,
                workspace_id=workspace_id,
                character_id=character_id,
            )
            await state.update_data(pending_delete_id=None)
            await message.answer(
                f"Персонаж <b>{escape(deleted.name)}</b> удалён.\n"
                f"Связей с медиа: <b>{deleted.media_links}</b> · "
                f"историй: <b>{deleted.story_links}</b> · "
                f"алиасов: <b>{deleted.aliases}</b>."
            )
            return

        if action in {"категория", "category"}:
            character_id, raw_key = _parse_id_and_value(
                tail,
                usage="категория ID key",
            )
            key = None if raw_key.casefold() in {"-", "нет", "off"} else raw_key.casefold()
            await set_workspace_character_category(
                database,
                workspace_id=workspace_id,
                character_id=character_id,
                category_key=key,
            )
            await message.answer("Категория персонажа обновлена.")
            return

        if action in {"вселенная", "universe"}:
            character_id, raw_key = _parse_id_and_value(
                tail,
                usage="вселенная ID key",
            )
            key = None if raw_key.casefold() in {"-", "нет", "off"} else raw_key.casefold()
            await set_workspace_character_universe(
                database,
                workspace_id=workspace_id,
                character_id=character_id,
                universe_key=key,
            )
            await message.answer(
                "Вселенная обновлена. Старые привязки историй очищены."
            )
            return

        if action in {"история", "story"}:
            character_id, raw_story_id = _parse_id_and_value(
                tail,
                usage="история ID story_id",
            )
            if not raw_story_id.isdigit():
                raise ValueError("Формат: <code>история ID story_id</code>")
            assigned = await toggle_workspace_character_story(
                database,
                workspace_id=workspace_id,
                character_id=character_id,
                story_id=int(raw_story_id),
                assigned_by_user_id=user_id,
            )
            await message.answer(
                "История добавлена персонажу."
                if assigned
                else "История удалена у персонажа."
            )
            return

        if action in {"алиас", "alias"}:
            character_id, alias = _parse_id_and_value(
                tail,
                usage="алиас ID Значение",
            )
            saved = await add_workspace_character_alias(
                database,
                workspace_id=workspace_id,
                character_id=character_id,
                alias=alias,
                created_by=user_id,
            )
            await message.answer(
                f"Алиас сохранён: <code>{escape(saved.alias)}</code>."
            )
            return

        if action in {"убрать_алиас", "aliasdel"}:
            character_id, alias = _parse_id_and_value(
                tail,
                usage="убрать_алиас ID Значение",
            )
            removed = await delete_workspace_character_alias(
                database,
                workspace_id=workspace_id,
                character_id=character_id,
                alias=alias,
            )
            await message.answer(
                "Алиас удалён."
                if removed
                else "Ручной алиас не найден. Имя персонажа удалить как алиас нельзя."
            )
            return

        if action in {"промт", "prompt"}:
            character_id, value = _parse_id_and_value(
                tail,
                usage="промт ID ссылка|off",
            )
            prompt_url = None if value.casefold() in {"off", "нет", "-", "удалить"} else value
            await set_workspace_character_prompt_url(
                database,
                workspace_id=workspace_id,
                character_id=character_id,
                prompt_post_url=prompt_url,
            )
            await message.answer(
                "Ссылка на промт удалена."
                if prompt_url is None
                else "Ссылка на промт сохранена."
            )
            return

        if action in {"тема", "topic"}:
            character_id, value = _parse_id_and_value(
                tail,
                usage="тема ID ссылка|off",
            )
            if value.casefold() in {"off", "нет", "-", "удалить"}:
                topic = None
            else:
                topic = parse_private_topic_link(value)
                await validate_topic_access(bot, topic)
            await set_workspace_character_topic(
                database,
                workspace_id=workspace_id,
                character_id=character_id,
                topic=topic,
            )
            await message.answer(
                "Тема Telegram удалена."
                if topic is None
                else "Тема Telegram проверена и назначена."
            )
            return

        raise ValueError(
            "Неизвестное действие. Используйте: создать, карточка, переименовать, "
            "удалить, категория, вселенная, история, алиас, убрать_алиас, промт, "
            "тема, структура, список или выход."
        )
    except ValueError as error:
        await message.answer(escape(str(error)))


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


__all__ = ("router",)
