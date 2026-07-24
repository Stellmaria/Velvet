from __future__ import annotations

import logging
from contextvars import ContextVar
from html import escape
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot import watermark_ui
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID, Workspace
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.krita_supervisor import wake_krita
from velvet_bot.presentation.telegram.routers import workspace_owner_controls
from velvet_bot.presentation.telegram.routers.core_operations_controllers import (
    watermark as core_watermark,
)
from velvet_bot.watermark_ui import WatermarkCallback
from velvet_bot.workspace_ui import WorkspaceCallback, format_workspace_home, workspace_callback

logger = logging.getLogger(__name__)
router = Router(name=__name__)

_ROLE_RANK = {"viewer": 10, "reviewer": 20, "editor": 30, "admin": 40, "owner": 50}
_DRAFT_ACTIONS = frozenset(
    {
        "position",
        "color",
        "opacity",
        "size",
        "margin",
        "undo",
        "remove",
        "generate",
        "draft_noop",
        "start",
        "help",
    }
)
_SHOW_BUTTON_HINTS: ContextVar[bool] = ContextVar(
    "workspace_show_button_hints",
    default=True,
)
_INSTALLED = False

_ORIGINAL_HOME_KEYBOARD = workspace_owner_controls._workspace_home_keyboard
_ORIGINAL_RENDER_HOME = workspace_owner_controls._render_home
_ORIGINAL_RENDER_MEMBER_HOME = workspace_owner_controls._render_member_home


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


def _command_name(message: Message) -> str:
    text = (message.text or message.caption or "").strip()
    if not text.startswith("/"):
        return ""
    token = text.split(maxsplit=1)[0][1:]
    return token.split("@", maxsplit=1)[0].casefold()


def _workspace_commands(role: str) -> tuple[BotCommand, ...]:
    commands = [
        BotCommand(command="start", description="Открыть пространство"),
        BotCommand(command="archive", description="Архив этого пространства"),
        BotCommand(command="refs", description="Референсы персонажа"),
        BotCommand(command="compare_ref", description="Сравнить с референсом"),
    ]
    if _ROLE_RANK.get(role, 0) >= _ROLE_RANK["editor"]:
        commands.extend(
            [
                BotCommand(command="save", description="Сохранить материалы персонажу"),
                BotCommand(command="savecancel", description="Завершить пакетное сохранение"),
                BotCommand(command="refadd", description="Добавить референс"),
                BotCommand(command="refdel", description="Удалить референс"),
                BotCommand(command="watermark", description="Подготовить watermark"),
            ]
        )
    return tuple(commands)


async def _set_chat_commands(bot: Bot, chat_id: int, role: str) -> None:
    try:
        await bot.set_my_commands(
            list(_workspace_commands(role)),
            scope=BotCommandScopeChat(chat_id=int(chat_id)),
        )
    except TelegramAPIError as error:
        logger.warning(
            "Could not install workspace command menu for chat %s: %s",
            chat_id,
            error,
        )


async def _install_scoped_commands(callback: CallbackQuery, *, role: str) -> None:
    chat_id = (
        callback.message.chat.id
        if isinstance(callback.message, Message)
        else callback.from_user.id
    )
    await _set_chat_commands(callback.bot, chat_id, role)


def _home_keyboard_with_hint_toggle(
    workspace: Workspace,
    *,
    public_enabled: bool,
    modules,
) -> InlineKeyboardMarkup:
    keyboard = _ORIGINAL_HOME_KEYBOARD(
        workspace,
        public_enabled=public_enabled,
        modules=modules,
    )
    show_hints = _SHOW_BUTTON_HINTS.get()
    rows: list[list[InlineKeyboardButton]] = []
    for row in keyboard.inline_keyboard:
        filtered = [
            button
            for button in row
            if not (
                button.text in {"🙈 Скрыть все подсказки", "ℹ️ Показать подсказки"}
                or (not show_hints and button.text == "ℹ️")
            )
        ]
        if filtered:
            rows.append(filtered)

    toggle = InlineKeyboardButton(
        text="🙈 Скрыть все подсказки" if show_hints else "ℹ️ Показать подсказки",
        callback_data=workspace_callback(
            "helptoggle",
            workspace_id=workspace.id,
        ),
    )
    insert_at = len(rows)
    if rows and any(button.text == "✖ Закрыть" for button in rows[-1]):
        insert_at -= 1
    rows.insert(max(0, insert_at), [toggle])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_home_with_preferences(
    callback: CallbackQuery,
    *,
    workspace: Workspace,
    user_id: int,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    token = _SHOW_BUTTON_HINTS.set(
        await workspace_product_service.get_button_hints(workspace.id)
    )
    try:
        await _ORIGINAL_RENDER_HOME(
            callback,
            workspace=workspace,
            user_id=user_id,
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
        )
    finally:
        _SHOW_BUTTON_HINTS.reset(token)
    membership = await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=user_id,
        minimum_role="owner",
        global_owner=_is_global_owner(user_id),
    )
    await _install_scoped_commands(callback, role=membership.role)


async def _render_member_home_with_commands(
    callback: CallbackQuery,
    *,
    workspace: Workspace,
    user_id: int,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    await _ORIGINAL_RENDER_MEMBER_HOME(
        callback,
        workspace=workspace,
        user_id=user_id,
        workspace_service=workspace_service,
        workspace_product_service=workspace_product_service,
    )
    membership = await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=user_id,
        minimum_role="viewer",
        global_owner=_is_global_owner(user_id),
    )
    await _install_scoped_commands(callback, role=membership.role)


class PersonalArchiveCommandFilter(BaseFilter):
    async def __call__(
        self,
        message: Message,
        workspace_service: WorkspaceService,
        workspace_product_service: WorkspaceProductService,
    ) -> dict[str, Any] | bool:
        if _command_name(message) != "archive":
            return False
        user = message.from_user or message.guest_bot_caller_user
        if user is None:
            return False
        try:
            workspace = await workspace_service.resolve_active_workspace(
                user_id=user.id,
                global_owner=_is_global_owner(user.id),
            )
            if workspace.is_system:
                return False
            membership = await workspace_service.require_role(
                workspace_id=workspace.id,
                user_id=user.id,
                minimum_role="viewer",
                global_owner=_is_global_owner(user.id),
            )
            enabled = await workspace_product_service.is_module_enabled(
                workspace_id=workspace.id,
                module_key="archive",
            )
        except (WorkspaceAccessError, ValueError):
            return False
        if not enabled:
            return False
        return {
            "personal_workspace": workspace,
            "workspace_role": membership.role,
        }


class WatermarkCommandFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return _command_name(message) == "watermark"


@router.message(PersonalArchiveCommandFilter())
async def handle_personal_archive_command(
    message: Message,
    database: Database,
    personal_workspace: Workspace,
    workspace_role: str,
) -> None:
    rows = await workspace_owner_controls._load_archive_characters(
        database,
        workspace_id=personal_workspace.id,
    )
    await message.answer(
        (
            f"<b>🖼 Архив · {escape(personal_workspace.name)}</b>\n\n"
            f"Персонажей: <b>{len(rows)}</b>\n\n"
            "Здесь показаны материалы только активного пользовательского "
            "пространства."
        ),
        reply_markup=workspace_owner_controls._archive_dashboard_keyboard(
            workspace_id=personal_workspace.id,
            rows=rows,
        ),
    )
    await _set_chat_commands(message.bot, message.chat.id, workspace_role)


@router.callback_query(WorkspaceCallback.filter(F.action == "helptoggle"))
async def handle_workspace_help_toggle(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    user_id = callback.from_user.id
    try:
        workspace = await workspace_service.set_active_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=user_id,
            global_owner=_is_global_owner(user_id),
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    await callback.answer()
    if workspace.is_system:
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "Системная панель использует отдельные настройки."
            )
        return
    try:
        membership = await workspace_service.require_role(
            workspace_id=workspace.id,
            user_id=user_id,
            minimum_role="owner",
            global_owner=_is_global_owner(user_id),
        )
    except WorkspaceAccessError as error:
        if isinstance(callback.message, Message):
            await callback.message.answer(f"❌ {escape(str(error))}")
        return

    try:
        show_button_hints = await workspace_product_service.toggle_button_hints(
            workspace.id
        )
        settings = await workspace_product_service.get_settings(workspace.id)
    except ValueError as error:
        if isinstance(callback.message, Message):
            await callback.message.answer(str(error))
        return

    modules = await workspace_product_service.list_modules(
        workspace_id=workspace.id,
        actor_user_id=user_id,
        global_owner=_is_global_owner(user_id),
    )
    if not isinstance(callback.message, Message):
        return
    allowed_modules = sum(item.is_allowed for item in modules)
    enabled_modules = sum(item.is_allowed and item.is_enabled for item in modules)
    text = (
        format_workspace_home(
            workspace,
            public_enabled=settings.public_archive_enabled,
            enabled_modules=enabled_modules,
            allowed_modules=allowed_modules,
        )
        + "\nРоль: <b>владелец</b>"
    )
    token = _SHOW_BUTTON_HINTS.set(show_button_hints)
    try:
        keyboard = _home_keyboard_with_hint_toggle(
            workspace,
            public_enabled=settings.public_archive_enabled,
            modules=modules,
        )
    finally:
        _SHOW_BUTTON_HINTS.reset(token)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
    await _set_chat_commands(callback.bot, callback.message.chat.id, membership.role)


@router.message(WatermarkCommandFilter())
async def handle_deferred_watermark_command(
    message: Message,
    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if not core_watermark._watermark_enabled():
        await message.answer(
            "Krita bridge выключен. Включите KRITA_WATERMARK_ENABLED=true."
        )
        return
    source = message.reply_to_message
    if source is None:
        await message.answer(
            "Ответьте командой <code>/watermark</code> на изображение или "
            "отправьте изображение ответом на эту форму. Сначала откроется "
            "черновик настроек. Krita запустится только после кнопки "
            "«Сгенерировать preview».\n\n"
            f"<code>{core_watermark._INPUT_MARKER}</code>",
            reply_markup=watermark_ui.build_watermark_start_keyboard(),
        )
        return
    await core_watermark._create_job_from_message(
        message=message,
        source_message=source,
        bot=bot,
        database=database,
        workspace_service=workspace_service,
        watermark_service=core_watermark._build_service(bot, database),
    )


async def _callback_error(callback: CallbackQuery, error: Exception) -> None:
    if isinstance(callback.message, Message):
        await callback.message.answer(f"❌ {escape(str(error))}")


@router.callback_query(WatermarkCallback.filter(F.action.in_(_DRAFT_ACTIONS)))
async def handle_watermark_draft_callback(
    callback: CallbackQuery,
    callback_data: WatermarkCallback,
    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService | None = None,
) -> None:
    action = callback_data.action
    if action in {"start", "help"}:
        if not core_watermark._watermark_enabled():
            await callback.answer("Krita bridge выключен.", show_alert=True)
            return
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "<b>Водяной знак Velvet Anatomy</b>\n\n"
                "Ответьте изображением на это сообщение. Можно подряд менять "
                "положение, цвет, прозрачность, размер и отступ. Krita "
                "запустится только после кнопки генерации.\n\n"
                f"<code>{core_watermark._INPUT_MARKER}</code>",
                reply_markup=watermark_ui.build_watermark_start_keyboard(),
            )
        await callback.answer()
        return
    if action == "draft_noop":
        await callback.answer("Дождитесь готового preview.")
        return
    if not core_watermark._watermark_enabled():
        await callback.answer("Krita bridge выключен.", show_alert=True)
        return

    await callback.answer(
        "Запускаю генерацию." if action == "generate" else "Настройка сохранена."
    )
    service = core_watermark._build_service(bot, database)
    owner_user_id = callback.from_user.id
    job_id = callback_data.job_id
    try:
        current = await service.get_current(job_id, owner_user_id=owner_user_id)
        await core_watermark._require_job_workspace(
            database,
            workspace_service,
            user_id=owner_user_id,
            workspace_id=getattr(
                current.job,
                "workspace_id",
                DEFAULT_WORKSPACE_ID,
            ),
        )
        if action == "generate":
            item = await service.generate(
                job_id,
                owner_user_id=owner_user_id,
            )
            wake_error = await wake_krita(context="workspace watermark preview")
            status = "поставлено в очередь"
            if wake_error:
                status += "; Krita нужно открыть вручную"
            await core_watermark._safe_edit(
                callback,
                watermark_ui.format_watermark_caption(item, status_text=status),
                item,
            )
            return
        if action == "position":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                position=callback_data.value,
                enabled=True,
                draft=True,
            )
        elif action == "color":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                color=callback_data.value,
                enabled=True,
                draft=True,
            )
        elif action == "opacity":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                opacity_delta=int(callback_data.value),
                draft=True,
            )
        elif action == "size":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                size_delta=float(callback_data.value),
                draft=True,
            )
        elif action == "margin":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                margin_delta=float(callback_data.value),
                draft=True,
            )
        elif action == "undo":
            item = await service.undo(
                job_id,
                owner_user_id=owner_user_id,
                draft=True,
            )
        elif action == "remove":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                enabled=False,
                draft=True,
            )
        else:
            raise ValueError("Неизвестная настройка.")
    except (TypeError, ValueError, WorkspaceAccessError) as error:
        await _callback_error(callback, error)
        return

    await core_watermark._safe_edit(
        callback,
        watermark_ui.format_watermark_caption(item),
        item,
    )


@router.message(core_watermark.WatermarkColorReplyFilter(), F.text)
async def handle_watermark_draft_color(
    message: Message,
    watermark_job_id: int,
    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if not core_watermark._watermark_enabled():
        await message.answer("Krita bridge выключен.")
        return
    service = core_watermark._build_service(bot, database)
    color = (message.text or "").strip()
    try:
        current = await service.get_current(
            watermark_job_id,
            owner_user_id=message.from_user.id,
        )
        await core_watermark._require_job_workspace(
            database,
            workspace_service,
            user_id=message.from_user.id,
            workspace_id=current.job.workspace_id,
        )
        item = await service.revise(
            watermark_job_id,
            owner_user_id=message.from_user.id,
            color=color,
            enabled=True,
            draft=True,
        )
    except (ValueError, WorkspaceAccessError) as error:
        await message.answer(f"❌ {escape(str(error))}")
        return
    await message.answer(
        watermark_ui.format_watermark_caption(item),
        reply_markup=watermark_ui.build_watermark_keyboard(item),
    )


def install_workspace_product_experience() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    workspace_owner_controls._workspace_home_keyboard = _home_keyboard_with_hint_toggle
    workspace_owner_controls._render_home = _render_home_with_preferences
    workspace_owner_controls._render_member_home = _render_member_home_with_commands



__all__ = (
    "install_workspace_product_experience",
    "router",
)
