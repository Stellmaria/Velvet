from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from velvet_bot.core.access import AccessPolicy
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import (
    GLOBAL_WORKSPACE_CREATOR_ID,
    WORKSPACE_MODULE_KEYS,
    WorkspaceModuleKey,
)
from velvet_bot.domains.workspaces.product_service import (
    WorkspaceCreationAccessError,
    WorkspaceModuleAccessError,
    WorkspaceProductService,
)
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.workspace_ui import (
    MODULE_HELP,
    MODULE_LABELS,
    WorkspaceCallback,
    WorkspaceForm,
    build_module_help_keyboard,
    build_modules_keyboard,
    build_public_workspaces_keyboard,
    build_selected_public_workspace_keyboard,
    build_taxonomy_keyboard,
    build_taxonomy_list_keyboard,
    build_workspace_home_keyboard,
    format_taxonomy,
    format_workspace_home,
)

router = Router(name=__name__)
_WORKSPACE_CALLBACK_ACTIONS = {
    "noop",
    "close",
    "publics",
    "publicselect",
    "create",
    "home",
    "visibility",
    "modules",
    "modtoggle",
    "modulehelp",
    "module",
    "taxonomy",
    "categories",
    "universes",
    "stories",
    "addcategory",
    "adduniverse",
    "addstory",
    "krimport",
}


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


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


async def _resolve_workspace(
    *,
    callback_data: WorkspaceCallback,
    user_id: int,
    workspace_service: WorkspaceService,
) -> Workspace:
    global_owner = _is_global_owner(user_id)
    if callback_data.workspace_id:
        return await workspace_service.set_active_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=user_id,
            global_owner=global_owner,
        )
    return await workspace_service.resolve_active_workspace(
        user_id=user_id,
        global_owner=global_owner,
    )


async def _show_home(
    callback: CallbackQuery,
    *,
    workspace: Workspace,
    user_id: int,
    workspace_product_service: WorkspaceProductService,
    workspace_service: WorkspaceService,
) -> None:
    global_owner = _is_global_owner(user_id)
    membership = await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=user_id,
        minimum_role="owner",
        global_owner=global_owner,
    )
    modules = await workspace_product_service.list_modules(
        workspace_id=workspace.id,
        actor_user_id=user_id,
        global_owner=global_owner,
    )
    settings = await workspace_product_service._workspaces.get_settings(workspace.id)
    if settings is None:
        await callback.answer("Настройки пространства не найдены.", show_alert=True)
        return
    allowed_modules = sum(item.is_allowed for item in modules)
    enabled_modules = sum(item.is_allowed and item.is_enabled for item in modules)
    role_label = "владелец" if membership.role == "owner" else membership.role
    text = format_workspace_home(
        workspace,
        public_enabled=settings.public_archive_enabled,
        enabled_modules=enabled_modules,
        allowed_modules=allowed_modules,
    ) + f"\nРоль: <b>{escape(role_label)}</b>"
    await _edit_or_answer(
        callback,
        text=text,
        reply_markup=build_workspace_home_keyboard(
            workspace,
            public_enabled=settings.public_archive_enabled,
            modules=modules,
        ),
    )


@router.message(Command("workspace_grant"))
async def handle_workspace_grant(
    message: Message,
    workspace_product_service: WorkspaceProductService,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not _is_global_owner(user_id):
        await message.answer("Эта команда доступна только Стэл.")
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "Формат: <code>/workspace_grant TELEGRAM_ID [modules]</code>\n"
            "Модули через запятую. Без списка выдаётся базовый набор."
        )
        return
    modules: tuple[WorkspaceModuleKey, ...] | None = None
    if len(parts) == 3:
        parsed = tuple(
            item.strip().casefold()
            for item in parts[2].split(",")
            if item.strip()
        )
        unknown = [item for item in parsed if item not in WORKSPACE_MODULE_KEYS]
        if unknown:
            await message.answer(
                "Неизвестные модули: " + ", ".join(escape(item) for item in unknown)
            )
            return
        modules = parsed
    kwargs = {}
    if modules is not None:
        kwargs["allowed_modules"] = modules
    grant = await workspace_product_service.grant_creation_access(
        actor_user_id=user_id,
        user_id=int(parts[1]),
        **kwargs,
    )
    await message.answer(
        "<b>Доступ выдан</b>\n\n"
        f"Telegram ID: <code>{grant.user_id}</code>\n"
        f"Модули: <code>{', '.join(grant.allowed_modules)}</code>\n"
        "На следующем /start пользователь увидит кнопку создания архива."
    )


@router.message(Command("workspace_revoke"))
async def handle_workspace_revoke(
    message: Message,
    workspace_product_service: WorkspaceProductService,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not _is_global_owner(user_id):
        await message.answer("Эта команда доступна только Стэл.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Формат: <code>/workspace_revoke TELEGRAM_ID</code>")
        return
    changed = await workspace_product_service.revoke_creation_access(
        actor_user_id=user_id,
        user_id=int(parts[1]),
    )
    await message.answer(
        "Право создания архива отозвано."
        if changed
        else "Активное разрешение не найдено."
    )


@router.callback_query(
    WorkspaceCallback.filter(F.action.in_(_WORKSPACE_CALLBACK_ACTIONS))
)
async def handle_workspace_callback(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    workspace_product_service: WorkspaceProductService,
    workspace_service: WorkspaceService,
) -> None:
    action = callback_data.action
    user_id = callback.from_user.id
    if action == "noop":
        await callback.answer()
        return
    if action == "close":
        await state.clear()
        if isinstance(callback.message, Message):
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
        await callback.answer()
        return
    if action == "publics":
        public_workspaces = await workspace_product_service.list_public_workspaces()
        await _edit_or_answer(
            callback,
            text=(
                "<b>Публичные архивы</b>\n\n"
                "Здесь показываются только пространства, владельцы которых включили "
                "публичный режим read-only."
            ),
            reply_markup=build_public_workspaces_keyboard(public_workspaces),
        )
        return
    if action == "publicselect":
        selected = await workspace_product_service.select_public_workspace(
            user_id=user_id,
            workspace_id=callback_data.workspace_id,
        )
        if not selected:
            await callback.answer("Архив больше не является публичным.", show_alert=True)
            return
        public_workspaces = await workspace_product_service.list_public_workspaces()
        workspace = next(
            (item for item in public_workspaces if item.id == callback_data.workspace_id),
            None,
        )
        await _edit_or_answer(
            callback,
            text=(
                f"<b>{escape(workspace.name if workspace else 'Публичный архив')}</b>\n\n"
                "Открыт режим просмотра. Изменение персонажей и материалов недоступно."
            ),
            reply_markup=build_selected_public_workspace_keyboard(),
        )
        return
    if action == "create":
        if not await workspace_product_service.can_create_workspace(user_id):
            await callback.answer(
                "Право на создание архива не выдано или уже использовано.",
                show_alert=True,
            )
            return
        await state.set_state(WorkspaceForm.waiting_workspace_name)
        await state.update_data(workspace_owner_user_id=user_id)
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "<b>Название личного архива</b>\n\n"
                "Отправьте название одним сообщением. Новый архив будет приватным."
            )
        await callback.answer()
        return

    try:
        workspace = await _resolve_workspace(
            callback_data=callback_data,
            user_id=user_id,
            workspace_service=workspace_service,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    if action == "home":
        try:
            await _show_home(
                callback,
                workspace=workspace,
                user_id=user_id,
                workspace_product_service=workspace_product_service,
                workspace_service=workspace_service,
            )
        except WorkspaceAccessError as error:
            await callback.answer(str(error), show_alert=True)
        return
    if action == "visibility":
        settings = await workspace_product_service._workspaces.get_settings(workspace.id)
        if settings is None:
            await callback.answer("Настройки не найдены.", show_alert=True)
            return
        try:
            await workspace_product_service.set_public_archive_enabled(
                workspace_id=workspace.id,
                actor_user_id=user_id,
                enabled=not settings.public_archive_enabled,
                global_owner=_is_global_owner(user_id),
            )
        except (WorkspaceAccessError, WorkspaceModuleAccessError) as error:
            await callback.answer(str(error), show_alert=True)
            return
        await _show_home(
            callback,
            workspace=workspace,
            user_id=user_id,
            workspace_product_service=workspace_product_service,
            workspace_service=workspace_service,
        )
        return
    if action == "modules":
        try:
            modules = await workspace_product_service.list_modules(
                workspace_id=workspace.id,
                actor_user_id=user_id,
                global_owner=_is_global_owner(user_id),
            )
        except WorkspaceAccessError as error:
            await callback.answer(str(error), show_alert=True)
            return
        await _edit_or_answer(
            callback,
            text=(
                f"<b>🧩 Модули · {escape(workspace.name)}</b>\n\n"
                "✅ включён, ➖ выключен владельцем, ⛔ не разрешён Стэл. "
                "Кнопка ℹ️ объясняет назначение каждого модуля."
            ),
            reply_markup=build_modules_keyboard(workspace.id, modules),
        )
        return
    if action == "modtoggle":
        module_key = callback_data.module_key
        if module_key not in WORKSPACE_MODULE_KEYS:
            await callback.answer("Неизвестный модуль.", show_alert=True)
            return
        modules = await workspace_product_service.list_modules(
            workspace_id=workspace.id,
            actor_user_id=user_id,
            global_owner=_is_global_owner(user_id),
        )
        current = next((item for item in modules if item.module_key == module_key), None)
        if current is None or not current.is_allowed:
            await callback.answer("Этот модуль не разрешён Стэл.", show_alert=True)
            return
        try:
            await workspace_product_service.set_module_enabled(
                workspace_id=workspace.id,
                actor_user_id=user_id,
                module_key=module_key,
                is_enabled=not current.is_enabled,
                global_owner=_is_global_owner(user_id),
            )
        except (WorkspaceAccessError, WorkspaceModuleAccessError) as error:
            await callback.answer(str(error), show_alert=True)
            return
        modules = await workspace_product_service.list_modules(
            workspace_id=workspace.id,
            actor_user_id=user_id,
            global_owner=_is_global_owner(user_id),
        )
        await _edit_or_answer(
            callback,
            text=f"<b>🧩 Модули · {escape(workspace.name)}</b>",
            reply_markup=build_modules_keyboard(workspace.id, modules),
        )
        return
    if action in {"modulehelp", "module"}:
        module_key = callback_data.module_key
        if module_key not in WORKSPACE_MODULE_KEYS:
            await callback.answer("Неизвестный модуль.", show_alert=True)
            return
        text = (
            f"<b>{MODULE_LABELS[module_key]}</b>\n\n"
            f"{escape(MODULE_HELP[module_key])}\n\n"
            "Показываемые кнопки зависят от разрешения Стэл и выбора владельца архива."
        )
        await _edit_or_answer(
            callback,
            text=text,
            reply_markup=build_module_help_keyboard(workspace.id),
        )
        return
    if action == "taxonomy":
        categories = await workspace_product_service.list_categories(workspace.id)
        universes = await workspace_product_service.list_universes(workspace.id)
        stories = await workspace_product_service.list_stories(workspace_id=workspace.id)
        await _edit_or_answer(
            callback,
            text=format_taxonomy(
                workspace,
                categories=categories,
                universes=universes,
                stories=stories,
            ),
            reply_markup=build_taxonomy_keyboard(workspace.id),
        )
        return
    if action in {"categories", "universes", "stories"}:
        if action == "categories":
            items = await workspace_product_service.list_categories(workspace.id)
            body = "\n".join(
                f"{item.emoji} <code>{escape(item.key)}</code> · {escape(item.label)}"
                for item in items
            ) or "Категорий пока нет."
            title = "Категории"
        elif action == "universes":
            items = await workspace_product_service.list_universes(workspace.id)
            body = "\n".join(
                f"{item.emoji} <code>{escape(item.key)}</code> · {escape(item.label)}"
                for item in items
            ) or "Вселенных пока нет."
            title = "Вселенные"
        else:
            items = await workspace_product_service.list_stories(workspace_id=workspace.id)
            body = "\n".join(
                f"📖 <code>{escape(item.universe_key)}/{escape(item.key)}</code> · "
                f"{escape(item.short_label)} · {escape(item.title)}"
                for item in items
            ) or "Историй пока нет."
            title = "Истории"
        await _edit_or_answer(
            callback,
            text=f"<b>{title} · {escape(workspace.name)}</b>\n\n{body}",
            reply_markup=build_taxonomy_list_keyboard(workspace.id),
        )
        return
    if action in {"addcategory", "adduniverse", "addstory"}:
        state_map = {
            "addcategory": WorkspaceForm.waiting_category,
            "adduniverse": WorkspaceForm.waiting_universe,
            "addstory": WorkspaceForm.waiting_story,
        }
        prompts = {
            "addcategory": "Отправьте: <code>key | Название | emoji</code>",
            "adduniverse": (
                "Отправьте: <code>key | Название | emoji | да/нет</code>\n"
                "Последнее значение означает, обязательны ли истории."
            ),
            "addstory": (
                "Отправьте: <code>universe_key | story_key | КРАТКО | Название</code>"
            ),
        }
        await state.set_state(state_map[action])
        await state.update_data(workspace_id=workspace.id)
        if isinstance(callback.message, Message):
            await callback.message.answer(prompts[action])
        await callback.answer()
        return
    if action == "krimport":
        try:
            _, copied = await workspace_product_service.import_kr_template(
                workspace_id=workspace.id,
                actor_user_id=user_id,
                global_owner=_is_global_owner(user_id),
            )
        except (ValueError, WorkspaceAccessError, WorkspaceModuleAccessError) as error:
            await callback.answer(str(error), show_alert=True)
            return
        await callback.answer(
            f"Вселенная КР добавлена. Историй скопировано: {copied}.",
            show_alert=True,
        )
        return


@router.message(WorkspaceForm.waiting_workspace_name)
async def handle_workspace_name(
    message: Message,
    state: FSMContext,
    workspace_product_service: WorkspaceProductService,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    name = (message.text or "").strip()
    try:
        workspace = await workspace_product_service.create_personal_workspace(
            owner_user_id=user_id,
            name=name,
        )
    except (ValueError, WorkspaceCreationAccessError) as error:
        await message.answer(str(error))
        return
    await state.clear()
    await message.answer(
        f"<b>{escape(workspace.name)}</b> создан.\n\n"
        "Архив приватный. Публичный read-only режим можно включить в разделе "
        "«Моё пространство»."
    )


async def _form_workspace_id(state: FSMContext) -> int:
    data = await state.get_data()
    value = int(data.get("workspace_id") or 0)
    if value <= 0:
        raise ValueError("Сессия настройки устарела. Откройте «Моё пространство» заново.")
    return value


@router.message(WorkspaceForm.waiting_category)
async def handle_category_form(
    message: Message,
    state: FSMContext,
    workspace_product_service: WorkspaceProductService,
) -> None:
    parts = [item.strip() for item in (message.text or "").split("|")]
    if len(parts) not in {2, 3}:
        await message.answer("Формат: <code>key | Название | emoji</code>")
        return
    try:
        item = await workspace_product_service.create_category(
            workspace_id=await _form_workspace_id(state),
            actor_user_id=message.from_user.id if message.from_user else 0,
            key=parts[0],
            label=parts[1],
            emoji=parts[2] if len(parts) == 3 else None,
        )
    except (ValueError, WorkspaceAccessError, WorkspaceModuleAccessError) as error:
        await message.answer(str(error))
        return
    await state.clear()
    await message.answer(f"Категория сохранена: {item.emoji} <b>{escape(item.label)}</b>.")


@router.message(WorkspaceForm.waiting_universe)
async def handle_universe_form(
    message: Message,
    state: FSMContext,
    workspace_product_service: WorkspaceProductService,
) -> None:
    parts = [item.strip() for item in (message.text or "").split("|")]
    if len(parts) != 4:
        await message.answer("Формат: <code>key | Название | emoji | да/нет</code>")
        return
    requires_story = parts[3].casefold() in {"да", "yes", "true", "1"}
    try:
        item = await workspace_product_service.create_universe(
            workspace_id=await _form_workspace_id(state),
            actor_user_id=message.from_user.id if message.from_user else 0,
            key=parts[0],
            label=parts[1],
            emoji=parts[2],
            requires_story=requires_story,
        )
    except (ValueError, WorkspaceAccessError, WorkspaceModuleAccessError) as error:
        await message.answer(str(error))
        return
    await state.clear()
    await message.answer(f"Вселенная сохранена: {item.emoji} <b>{escape(item.label)}</b>.")


@router.message(WorkspaceForm.waiting_story)
async def handle_story_form(
    message: Message,
    state: FSMContext,
    workspace_product_service: WorkspaceProductService,
) -> None:
    parts = [item.strip() for item in (message.text or "").split("|")]
    if len(parts) != 4:
        await message.answer(
            "Формат: <code>universe_key | story_key | КРАТКО | Название</code>"
        )
        return
    try:
        item = await workspace_product_service.create_story(
            workspace_id=await _form_workspace_id(state),
            actor_user_id=message.from_user.id if message.from_user else 0,
            universe_key=parts[0],
            key=parts[1],
            short_label=parts[2],
            title=parts[3],
        )
    except (ValueError, WorkspaceAccessError, WorkspaceModuleAccessError) as error:
        await message.answer(str(error))
        return
    await state.clear()
    await message.answer(
        f"История сохранена: <b>{escape(item.short_label)} · {escape(item.title)}</b>."
    )


__all__ = ("router",)
