from __future__ import annotations

from html import escape
from typing import cast

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.administration import (
    WorkspaceAdminSummary,
    WorkspaceAdministrationAccessError,
    WorkspaceAdministrationService,
    WorkspaceGrantAdminSummary,
)
from velvet_bot.domains.workspaces.product_models import (
    GLOBAL_WORKSPACE_CREATOR_ID,
    WORKSPACE_MODULE_KEYS,
    WorkspaceModuleKey,
    WorkspaceModuleSetting,
)
from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_admin_ui import (
    WorkspaceAdminCallback,
    build_grant_card_keyboard,
    build_grant_modules_keyboard,
    build_grants_keyboard,
    build_new_grant_prompt_keyboard,
    build_workspace_admin_home_keyboard,
    build_workspace_card_keyboard,
    build_workspace_modules_keyboard,
    build_workspaces_keyboard,
)
from velvet_bot.workspace_ui import MODULE_LABELS


router = Router(name=__name__)
_PAGE_SIZE = 8


class WorkspaceAdminForm(StatesGroup):
    waiting_user_id = State()


def _is_stel(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


def _service(database: Database) -> WorkspaceAdministrationService:
    return WorkspaceAdministrationService(database)


async def _edit_or_answer(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup,
) -> None:
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
            return
        except TelegramBadRequest as error:
            if "message is not modified" in str(error).casefold():
                return
            await callback.message.answer(text, reply_markup=reply_markup)


async def _send_error(callback: CallbackQuery, error: Exception) -> None:
    text = f"<b>Не удалось выполнить действие</b>\n\n{escape(str(error))}"
    if isinstance(callback.message, Message):
        await callback.message.answer(text)


def _format_home(*, grants: int, workspaces: int) -> str:
    return (
        "<b>🏛 Управление личными пространствами</b>\n\n"
        f"Разрешений: <b>{grants}</b>\n"
        f"Созданных архивов: <b>{workspaces}</b>\n\n"
        "Здесь Стэл выдаёт право создать архив, выбирает модули будущего "
        "пространства и отдельно управляет доступностью модулей уже созданных архивов."
    )


def _format_grants(items: tuple[WorkspaceGrantAdminSummary, ...], *, total: int) -> str:
    active = sum(item.is_active for item in items)
    return (
        "<b>👤 Разрешения пользователей</b>\n\n"
        f"Всего: <b>{total}</b>. На этой странице активных: <b>{active}</b>.\n\n"
        "🟢 разрешение активно, ⚪ создание новых архивов отозвано. "
        "Числа справа показывают созданные архивы и установленный лимит."
    )


def _format_grant(grant: WorkspaceGrantAdminSummary) -> str:
    status = "активно" if grant.is_active else "отозвано"
    modules = ", ".join(MODULE_LABELS[item] for item in grant.allowed_modules)
    return (
        "<b>👤 Доступ пользователя</b>\n\n"
        f"Telegram ID: <code>{grant.user_id}</code>\n"
        f"Создание архивов: <b>{status}</b>\n"
        f"Создано: <b>{grant.owned_workspace_count}</b> из "
        f"<b>{grant.max_workspaces}</b>\n"
        f"Модули нового архива: <b>{escape(modules)}</b>\n\n"
        "Отзыв разрешения запрещает создавать новые пространства, но не удаляет "
        "существующий архив и его данные. Его модули управляются в карточке пространства."
    )


def _format_grant_modules(grant: WorkspaceGrantAdminSummary) -> str:
    return (
        "<b>🧩 Модули будущего архива</b>\n\n"
        f"Telegram ID: <code>{grant.user_id}</code>\n\n"
        "✅ модуль будет доступен при создании нового пространства.\n"
        "⛔ модуль не будет выдан.\n\n"
        "Изменения не переписывают политику уже созданных архивов. Для них есть "
        "отдельная карточка модулей."
    )


def _format_workspaces(
    items: tuple[WorkspaceAdminSummary, ...],
    *,
    total: int,
) -> str:
    public_count = sum(item.public_archive_enabled for item in items)
    return (
        "<b>🗄 Созданные личные архивы</b>\n\n"
        f"Всего: <b>{total}</b>. Публичных на этой странице: "
        f"<b>{public_count}</b>.\n\n"
        "🌐 публичный архив, 🔒 приватный. Нажмите на пространство, чтобы изменить "
        "разрешённые Стэл модули."
    )


def _format_workspace(workspace: WorkspaceAdminSummary) -> str:
    visibility = "публичный" if workspace.public_archive_enabled else "приватный"
    return (
        f"<b>🗄 {escape(workspace.name)}</b>\n\n"
        f"Workspace ID: <code>{workspace.workspace_id}</code>\n"
        f"Владелец: <code>{workspace.owner_user_id}</code>\n"
        f"Slug: <code>{escape(workspace.slug)}</code>\n"
        f"Режим: <b>{visibility}</b>\n"
        f"Персонажей: <b>{workspace.character_count}</b>\n\n"
        "Стэл управляет разрешением модулей. Владелец пространства может только "
        "включать или выключать уже разрешённые ему возможности."
    )


def _format_workspace_modules(
    workspace: WorkspaceAdminSummary,
    modules: tuple[WorkspaceModuleSetting, ...],
) -> str:
    allowed = sum(item.is_allowed for item in modules)
    enabled = sum(item.is_allowed and item.is_enabled for item in modules)
    return (
        f"<b>🧩 Модули · {escape(workspace.name)}</b>\n\n"
        f"Разрешено Стэл: <b>{allowed}</b>\n"
        f"Фактически включено владельцем: <b>{enabled}</b>\n\n"
        "✅ разрешён и включён владельцем.\n"
        "➖ разрешён, но выключен владельцем.\n"
        "⛔ запрещён Стэл и скрыт.\n\n"
        "Нажатие меняет именно разрешение Стэл."
    )


async def _render_home(
    callback: CallbackQuery,
    *,
    service: WorkspaceAdministrationService,
) -> None:
    actor = callback.from_user.id
    grants = await service.count_creation_grants(actor_user_id=actor)
    workspaces = await service.count_personal_workspaces(actor_user_id=actor)
    await _edit_or_answer(
        callback,
        text=_format_home(grants=grants, workspaces=workspaces),
        reply_markup=build_workspace_admin_home_keyboard(
            grant_count=grants,
            workspace_count=workspaces,
        ),
    )


async def _render_grants(
    callback: CallbackQuery,
    *,
    service: WorkspaceAdministrationService,
    page: int,
) -> None:
    actor = callback.from_user.id
    total = await service.count_creation_grants(actor_user_id=actor)
    safe_page = min(max(0, page), max(0, (total - 1) // _PAGE_SIZE))
    items = await service.list_creation_grants(
        actor_user_id=actor,
        limit=_PAGE_SIZE,
        offset=safe_page * _PAGE_SIZE,
    )
    await _edit_or_answer(
        callback,
        text=_format_grants(items, total=total),
        reply_markup=build_grants_keyboard(
            items,
            page=safe_page,
            total=total,
            page_size=_PAGE_SIZE,
        ),
    )


async def _render_grant(
    callback: CallbackQuery,
    *,
    service: WorkspaceAdministrationService,
    user_id: int,
    page: int,
) -> None:
    actor = callback.from_user.id
    grant = await service.get_creation_grant(
        actor_user_id=actor,
        user_id=user_id,
    )
    if grant is None:
        raise ValueError("Разрешение этого пользователя больше не найдено.")
    workspaces = await service.list_personal_workspaces(
        actor_user_id=actor,
        owner_user_id=user_id,
        limit=50,
    )
    await _edit_or_answer(
        callback,
        text=_format_grant(grant),
        reply_markup=build_grant_card_keyboard(grant, workspaces, page=page),
    )


async def _render_grant_modules(
    callback: CallbackQuery,
    *,
    service: WorkspaceAdministrationService,
    user_id: int,
    page: int,
) -> None:
    grant = await service.get_creation_grant(
        actor_user_id=callback.from_user.id,
        user_id=user_id,
    )
    if grant is None:
        raise ValueError("Разрешение этого пользователя больше не найдено.")
    await _edit_or_answer(
        callback,
        text=_format_grant_modules(grant),
        reply_markup=build_grant_modules_keyboard(grant, page=page),
    )


async def _render_workspaces(
    callback: CallbackQuery,
    *,
    service: WorkspaceAdministrationService,
    page: int,
) -> None:
    actor = callback.from_user.id
    total = await service.count_personal_workspaces(actor_user_id=actor)
    safe_page = min(max(0, page), max(0, (total - 1) // _PAGE_SIZE))
    items = await service.list_personal_workspaces(
        actor_user_id=actor,
        limit=_PAGE_SIZE,
        offset=safe_page * _PAGE_SIZE,
    )
    await _edit_or_answer(
        callback,
        text=_format_workspaces(items, total=total),
        reply_markup=build_workspaces_keyboard(
            items,
            page=safe_page,
            total=total,
            page_size=_PAGE_SIZE,
        ),
    )


async def _render_workspace(
    callback: CallbackQuery,
    *,
    service: WorkspaceAdministrationService,
    workspace_id: int,
    page: int,
) -> None:
    workspace = await service.get_personal_workspace(
        actor_user_id=callback.from_user.id,
        workspace_id=workspace_id,
    )
    if workspace is None:
        raise ValueError("Личное пространство больше не найдено.")
    await _edit_or_answer(
        callback,
        text=_format_workspace(workspace),
        reply_markup=build_workspace_card_keyboard(workspace, page=page),
    )


async def _render_workspace_modules(
    callback: CallbackQuery,
    *,
    service: WorkspaceAdministrationService,
    workspace_id: int,
    page: int,
) -> None:
    actor = callback.from_user.id
    workspace = await service.get_personal_workspace(
        actor_user_id=actor,
        workspace_id=workspace_id,
    )
    if workspace is None:
        raise ValueError("Личное пространство больше не найдено.")
    modules = await service.list_workspace_modules(
        actor_user_id=actor,
        workspace_id=workspace_id,
    )
    await _edit_or_answer(
        callback,
        text=_format_workspace_modules(workspace, modules),
        reply_markup=build_workspace_modules_keyboard(
            workspace,
            modules,
            page=page,
        ),
    )


@router.callback_query(WorkspaceAdminCallback.filter())
async def handle_workspace_admin_callback(
    callback: CallbackQuery,
    callback_data: WorkspaceAdminCallback,
    state: FSMContext,
    database: Database,
) -> None:
    if not _is_stel(callback.from_user.id):
        await callback.answer("Эта панель доступна только Стэл.", show_alert=True)
        return
    if callback_data.action == "noop":
        await callback.answer()
        return

    await callback.answer()
    service = _service(database)
    action = callback_data.action
    try:
        if action == "home":
            await state.clear()
            await _render_home(callback, service=service)
            return
        if action == "new":
            await state.set_state(WorkspaceAdminForm.waiting_user_id)
            await _edit_or_answer(
                callback,
                text=(
                    "<b>➕ Выдать право создать архив</b>\n\n"
                    "Отправьте Telegram ID пользователя одним сообщением. "
                    "Базовые модули можно изменить кнопками сразу после выдачи."
                ),
                reply_markup=build_new_grant_prompt_keyboard(),
            )
            return
        if action == "users":
            await state.clear()
            await _render_grants(callback, service=service, page=callback_data.page)
            return
        if action == "user":
            await state.clear()
            await _render_grant(
                callback,
                service=service,
                user_id=callback_data.user_id,
                page=callback_data.page,
            )
            return
        if action == "gmods":
            await _render_grant_modules(
                callback,
                service=service,
                user_id=callback_data.user_id,
                page=callback_data.page,
            )
            return
        if action == "gmt":
            if callback_data.module_key not in WORKSPACE_MODULE_KEYS:
                raise ValueError("Неизвестный модуль.")
            await service.toggle_creation_grant_module(
                actor_user_id=callback.from_user.id,
                user_id=callback_data.user_id,
                module_key=cast(WorkspaceModuleKey, callback_data.module_key),
            )
            await _render_grant_modules(
                callback,
                service=service,
                user_id=callback_data.user_id,
                page=callback_data.page,
            )
            return
        if action in {"goff", "gon"}:
            await service.set_creation_grant_active(
                actor_user_id=callback.from_user.id,
                user_id=callback_data.user_id,
                is_active=action == "gon",
            )
            await _render_grant(
                callback,
                service=service,
                user_id=callback_data.user_id,
                page=callback_data.page,
            )
            return
        if action == "spaces":
            await state.clear()
            await _render_workspaces(callback, service=service, page=callback_data.page)
            return
        if action == "space":
            await state.clear()
            await _render_workspace(
                callback,
                service=service,
                workspace_id=callback_data.workspace_id,
                page=callback_data.page,
            )
            return
        if action == "wmods":
            await _render_workspace_modules(
                callback,
                service=service,
                workspace_id=callback_data.workspace_id,
                page=callback_data.page,
            )
            return
        if action == "wmt":
            if callback_data.module_key not in WORKSPACE_MODULE_KEYS:
                raise ValueError("Неизвестный модуль.")
            await service.toggle_workspace_module(
                actor_user_id=callback.from_user.id,
                workspace_id=callback_data.workspace_id,
                module_key=cast(WorkspaceModuleKey, callback_data.module_key),
            )
            await _render_workspace_modules(
                callback,
                service=service,
                workspace_id=callback_data.workspace_id,
                page=callback_data.page,
            )
            return
        raise ValueError("Неизвестное действие панели пространств.")
    except (ValueError, RuntimeError, WorkspaceAdministrationAccessError) as error:
        await _send_error(callback, error)


@router.message(StateFilter(WorkspaceAdminForm.waiting_user_id))
async def handle_workspace_admin_user_id(
    message: Message,
    state: FSMContext,
    database: Database,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not _is_stel(user_id):
        await state.clear()
        await message.answer("Эта форма доступна только Стэл.")
        return
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("Выдача доступа выполняется только в личных сообщениях с ботом.")
        return
    raw = "".join((message.text or "").split())
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(
            "Нужен положительный Telegram ID без @username. Например: "
            "<code>8179531132</code>."
        )
        return

    service = _service(database)
    try:
        grant = await service.ensure_creation_grant(
            actor_user_id=user_id,
            user_id=int(raw),
        )
        workspaces = await service.list_personal_workspaces(
            actor_user_id=user_id,
            owner_user_id=grant.user_id,
            limit=50,
        )
    except (ValueError, RuntimeError, WorkspaceAdministrationAccessError) as error:
        await message.answer(
            f"<b>Не удалось выдать доступ</b>\n\n{escape(str(error))}"
        )
        return

    await state.clear()
    await message.answer(
        _format_grant(grant),
        reply_markup=build_grant_card_keyboard(grant, workspaces),
    )


__all__ = ("router",)
