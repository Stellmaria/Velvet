from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import replace
from html import escape
from typing import Any, cast

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import BaseFilter, Command
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
from velvet_bot.domains.watermark.models import WatermarkSettings, WatermarkWorkItem
from velvet_bot.domains.watermark.repository import WatermarkRepository
from velvet_bot.domains.watermark.service import WatermarkService
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID, Workspace, WorkspaceRole
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.domains.workspaces.watermark_templates import (
    WorkspaceWatermarkTemplateRepository,
)
from velvet_bot.presentation.telegram.middleware import access as access_middleware
from velvet_bot.presentation.telegram.routers import workspace_guided_actions
from velvet_bot.presentation.telegram.routers import workspace_owner_controls
from velvet_bot.presentation.telegram.routers.core_operations_controllers import (
    watermark as core_watermark,
)
from velvet_bot.presentation.telegram.routers.public_archive import (
    watermark_actions,
)
from velvet_bot.watermark_ui import WatermarkCallback
from velvet_bot.workspace_ui import WorkspaceCallback, workspace_callback

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
_ORIGINAL_QUICK_KEYBOARD = workspace_guided_actions._quick_keyboard
_ORIGINAL_MEMBER_CALLBACK_CHECK = access_middleware.is_workspace_member_callback_data
_ORIGINAL_SETTINGS_ROWS = watermark_ui._settings_rows
_ORIGINAL_WATERMARK_BUTTON = watermark_ui._button
_ORIGINAL_WATERMARK_KEYBOARD = watermark_ui.build_watermark_keyboard
_ORIGINAL_FORMAT_WATERMARK = watermark_ui.format_watermark_caption
_ORIGINAL_CORE_WAKE_KRITA = core_watermark._wake_krita


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


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
            ]
        )
    return tuple(commands)


async def _install_scoped_commands(
    callback: CallbackQuery,
    *,
    role: str,
) -> None:
    chat_id = (
        callback.message.chat.id
        if isinstance(callback.message, Message)
        else callback.from_user.id
    )
    try:
        await callback.bot.set_my_commands(
            list(_workspace_commands(role)),
            scope=BotCommandScopeChat(chat_id=chat_id),
        )
    except TelegramAPIError as error:
        logger.warning("Could not install workspace command menu for %s: %s", chat_id, error)


def _database_from_product_service(service: WorkspaceProductService) -> Database:
    repository = service._workspaces
    database = getattr(repository, "_database", None)
    if database is None:
        raise RuntimeError("Workspace repository does not expose its database boundary.")
    return cast(Database, database)


async def _show_button_hints(database: Database, workspace_id: int) -> bool:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT show_button_hints
            FROM workspace_settings
            WHERE workspace_id = $1::BIGINT
            """,
            int(workspace_id),
        )
    return True if value is None else bool(value)


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

    toggle_row = [
        InlineKeyboardButton(
            text=(
                "🙈 Скрыть все подсказки"
                if show_hints
                else "ℹ️ Показать подсказки"
            ),
            callback_data=workspace_callback(
                "helptoggle",
                workspace_id=workspace.id,
            ),
        )
    ]
    insert_at = len(rows)
    if rows and any(button.text == "✖ Закрыть" for button in rows[-1]):
        insert_at -= 1
    rows.insert(max(0, insert_at), toggle_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_home_with_preferences(
    callback: CallbackQuery,
    *,
    workspace: Workspace,
    user_id: int,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    database = _database_from_product_service(workspace_product_service)
    show_hints = await _show_button_hints(database, workspace.id)
    token = _SHOW_BUTTON_HINTS.set(show_hints)
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


def _quick_keyboard_with_references(
    workspace_id: int,
    enabled: frozenset[str],
) -> InlineKeyboardMarkup:
    keyboard = _ORIGINAL_QUICK_KEYBOARD(workspace_id, enabled)
    rows = [list(row) for row in keyboard.inline_keyboard]
    if "references" in enabled and not any(
        button.text == "🧬 Референсы" for row in rows for button in row
    ):
        insert_at = next(
            (
                index
                for index, row in enumerate(rows)
                if any(button.text == "🧭 Настройка архива" for button in row)
            ),
            len(rows),
        )
        rows.insert(
            insert_at,
            [
                InlineKeyboardButton(
                    text="🧬 Референсы",
                    callback_data=workspace_callback(
                        "module",
                        workspace_id=workspace_id,
                        module_key="references",
                    ),
                )
            ],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _workspace_callback_with_template(value: str | None) -> bool:
    return bool(
        _ORIGINAL_MEMBER_CALLBACK_CHECK(value)
        or (value and value.startswith("wmtpl:"))
    )


async def _create_draft_job(
    repository: WatermarkRepository,
    *,
    owner_user_id: int,
    chat_id: int,
    source_message_id: int,
    source_file_id: str,
    source_file_unique_id: str | None,
    source_path: str,
    settings: WatermarkSettings,
    workspace_id: int,
    logo_kind: str,
    logo_path: str | None,
    logo_width: float | None,
    logo_height: float | None,
    logo_name: str | None,
) -> WatermarkWorkItem:
    settings = settings.normalized()
    database = repository._database
    async with database.acquire() as connection:
        async with connection.transaction():
            job_row = await connection.fetchrow(
                """
                INSERT INTO watermark_jobs (
                    owner_user_id, chat_id, source_message_id,
                    source_file_id, source_file_unique_id, source_path,
                    workspace_id, logo_kind, logo_path, logo_width,
                    logo_height, logo_name
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING *
                """,
                owner_user_id,
                chat_id,
                source_message_id,
                source_file_id,
                source_file_unique_id,
                source_path,
                int(workspace_id),
                logo_kind,
                logo_path,
                logo_width,
                logo_height,
                logo_name,
            )
            if job_row is None:
                raise RuntimeError("Не удалось создать задание водяного знака.")
            revision_row = await connection.fetchrow(
                """
                INSERT INTO watermark_revisions (
                    job_id, revision, enabled, position, color,
                    opacity, size, margin, lock_layer, status
                )
                VALUES ($1, 1, $2, $3, $4, $5, $6, $7, $8, 'draft')
                RETURNING *
                """,
                int(job_row["id"]),
                settings.enabled,
                settings.position,
                settings.color,
                settings.opacity,
                settings.size,
                settings.margin,
                settings.lock,
            )
    if revision_row is None:
        raise RuntimeError("Не удалось создать черновик водяного знака.")
    return WatermarkWorkItem(
        job=repository._map_job(job_row),
        revision=repository._map_revision(revision_row),
    )


async def _create_draft_revision(
    repository: WatermarkRepository,
    job_id: int,
    *,
    settings: WatermarkSettings,
) -> WatermarkWorkItem:
    settings = settings.normalized()
    database = repository._database
    async with database.acquire() as connection:
        async with connection.transaction():
            job_row = await connection.fetchrow(
                "SELECT * FROM watermark_jobs WHERE id = $1 FOR UPDATE",
                job_id,
            )
            if job_row is None:
                raise ValueError("Задание водяного знака не найдено.")
            if str(job_row["status"]) in {"approved", "cancelled"}:
                raise ValueError("Задание уже завершено.")
            revision = int(job_row["current_revision"]) + 1
            revision_row = await connection.fetchrow(
                """
                INSERT INTO watermark_revisions (
                    job_id, revision, enabled, position, color,
                    opacity, size, margin, lock_layer, status
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'draft')
                RETURNING *
                """,
                job_id,
                revision,
                settings.enabled,
                settings.position,
                settings.color,
                settings.opacity,
                settings.size,
                settings.margin,
                settings.lock,
            )
            job_row = await connection.fetchrow(
                """
                UPDATE watermark_jobs
                SET current_revision = $2, status = 'active', updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                job_id,
                revision,
            )
    if job_row is None or revision_row is None:
        raise RuntimeError("Не удалось сохранить черновик водяного знака.")
    return WatermarkWorkItem(
        job=repository._map_job(job_row),
        revision=repository._map_revision(revision_row),
    )


async def _service_create_draft_job(
    self: WatermarkService,
    *,
    owner_user_id: int,
    chat_id: int,
    source_message_id: int,
    source_file_id: str,
    source_file_unique_id: str | None,
    source_path: str,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    logo_kind: str = "builtin",
    logo_path: str | None = None,
    logo_width: float | None = None,
    logo_height: float | None = None,
    logo_name: str | None = None,
) -> WatermarkWorkItem:
    repository = self._repository
    database = repository._database
    settings = WatermarkSettings()
    if int(workspace_id) != DEFAULT_WORKSPACE_ID:
        settings = await WorkspaceWatermarkTemplateRepository(database).get(workspace_id)
    return await _create_draft_job(
        repository,
        owner_user_id=owner_user_id,
        chat_id=chat_id,
        source_message_id=source_message_id,
        source_file_id=source_file_id,
        source_file_unique_id=source_file_unique_id,
        source_path=source_path,
        settings=settings,
        workspace_id=workspace_id,
        logo_kind=logo_kind,
        logo_path=logo_path,
        logo_width=logo_width,
        logo_height=logo_height,
        logo_name=logo_name,
    )


async def _service_revise_draft(
    self: WatermarkService,
    job_id: int,
    *,
    owner_user_id: int,
    position: str | None = None,
    color: str | None = None,
    opacity_delta: int = 0,
    size_delta: float = 0.0,
    margin_delta: float = 0.0,
    enabled: bool | None = None,
) -> WatermarkWorkItem:
    current = await self.get_current(job_id, owner_user_id=owner_user_id)
    settings = current.revision.settings
    next_settings = replace(
        settings,
        position=position if position is not None else settings.position,
        color=color if color is not None else settings.color,
        opacity=settings.opacity + opacity_delta,
        size=settings.size + size_delta,
        margin=settings.margin + margin_delta,
        enabled=enabled if enabled is not None else settings.enabled,
    ).normalized()
    return await _create_draft_revision(
        self._repository,
        job_id,
        settings=next_settings,
    )


async def _service_undo_draft(
    self: WatermarkService,
    job_id: int,
    *,
    owner_user_id: int,
) -> WatermarkWorkItem:
    await self.get_current(job_id, owner_user_id=owner_user_id)
    repository = self._repository
    async with repository._database.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT r.*
            FROM watermark_jobs AS j
            JOIN watermark_revisions AS r ON r.job_id = j.id
            WHERE j.id = $1 AND r.revision < j.current_revision
            ORDER BY r.revision DESC
            LIMIT 1
            """,
            job_id,
        )
    if row is None:
        raise ValueError("Предыдущей версии настроек нет.")
    return await _create_draft_revision(
        repository,
        job_id,
        settings=repository._settings_from_row(row),
    )


async def _service_generate(
    self: WatermarkService,
    job_id: int,
    *,
    owner_user_id: int,
) -> WatermarkWorkItem:
    current = await self.get_current(job_id, owner_user_id=owner_user_id)
    status = current.revision.status
    if status not in {"draft", "error"}:
        if status in {"pending", "processing"}:
            raise ValueError("Генерация этой версии уже запущена.")
        raise ValueError("Сначала измените настройки, затем запустите новую генерацию.")
    repository = self._repository
    async with repository._database.acquire() as connection:
        async with connection.transaction():
            result = await connection.execute(
                """
                UPDATE watermark_revisions
                SET status = 'pending',
                    request_path = NULL,
                    output_path = NULL,
                    response_path = NULL,
                    telegram_preview_file_id = NULL,
                    error = NULL,
                    completed_at = NULL
                WHERE job_id = $1
                  AND revision = $2
                  AND status IN ('draft', 'error')
                """,
                job_id,
                current.revision.revision,
            )
            if not result.endswith("1"):
                raise ValueError("Черновик уже изменился. Обновите карточку.")
            row = await connection.fetchrow(repository._current_query(), job_id)
    if row is None:
        raise ValueError("Задание водяного знака не найдено.")
    return repository._map_work_item(row)


def _draft_watermark_keyboard(item: WatermarkWorkItem) -> InlineKeyboardMarkup:
    status = item.revision.status
    if status in {"draft", "error"}:
        rows = _ORIGINAL_SETTINGS_ROWS(item)
        rows.append(
            [
                _ORIGINAL_WATERMARK_BUTTON(
                    "▶️ Сгенерировать preview",
                    "generate",
                    item.job.id,
                )
            ]
        )
        rows.append(
            [_ORIGINAL_WATERMARK_BUTTON("✖ Отмена", "cancel", item.job.id)]
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)
    if status in {"pending", "processing"}:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _ORIGINAL_WATERMARK_BUTTON(
                        "⏳ Генерация выполняется",
                        "draft_noop",
                        item.job.id,
                    )
                ],
                [_ORIGINAL_WATERMARK_BUTTON("✖ Отмена", "cancel", item.job.id)],
            ]
        )
    return _ORIGINAL_WATERMARK_KEYBOARD(item)


def _draft_watermark_caption(
    item: WatermarkWorkItem,
    *,
    status_text: str | None = None,
) -> str:
    if item.revision.status == "draft":
        status_text = "черновик: настройте параметры и нажмите «Сгенерировать preview»"
    elif item.revision.status == "error" and status_text is None:
        status_text = "ошибка: измените параметры или повторите генерацию"
    return _ORIGINAL_FORMAT_WATERMARK(item, status_text=status_text)


async def _defer_krita_start() -> str | None:
    return None


class ActivePersonalArchiveFilter(BaseFilter):
    async def __call__(
        self,
        message: Message,
        workspace_service: WorkspaceService,
        workspace_product_service: WorkspaceProductService,
    ) -> dict[str, Any] | bool:
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
            if not await workspace_product_service.is_module_enabled(
                workspace_id=workspace.id,
                module_key="archive",
            ):
                return False
        except WorkspaceAccessError:
            return False
        return {"personal_workspace": workspace, "workspace_role": membership.role}


@router.message(Command("archive"), ActivePersonalArchiveFilter())
async def handle_personal_archive_command(
    message: Message,
    personal_workspace: Workspace,
    workspace_role: str,
) -> None:
    await message.answer(
        f"<b>🖼 {escape(personal_workspace.name)} · архив</b>\n\n"
        "Открывается архив активного пространства. Системный Velvet и чужие "
        "пространства в эту кнопку больше не подмешиваются.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🖼 Открыть свой архив",
                        callback_data=workspace_callback(
                            "module",
                            workspace_id=personal_workspace.id,
                            module_key="archive",
                        ),
                    )
                ]
            ]
        ),
    )
    try:
        await message.bot.set_my_commands(
            list(_workspace_commands(workspace_role)),
            scope=BotCommandScopeChat(chat_id=message.chat.id),
        )
    except TelegramAPIError as error:
        logger.warning("Could not refresh personal archive commands: %s", error)


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
        if workspace.is_system:
            raise WorkspaceAccessError("Системная панель использует отдельные настройки.")
        await workspace_service.require_role(
            workspace_id=workspace.id,
            user_id=user_id,
            minimum_role="owner",
            global_owner=_is_global_owner(user_id),
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    database = _database_from_product_service(workspace_product_service)
    async with database.acquire() as connection:
        await connection.execute(
            """
            UPDATE workspace_settings
            SET show_button_hints = NOT show_button_hints,
                updated_at = NOW()
            WHERE workspace_id = $1::BIGINT
            """,
            workspace.id,
        )
    await workspace_owner_controls._render_home(
        callback,
        workspace=workspace,
        user_id=user_id,
        workspace_service=workspace_service,
        workspace_product_service=workspace_product_service,
    )


@router.message(Command("watermark"))
async def handle_deferred_watermark_command(
    message: Message,
    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if not core_watermark._watermark_enabled():
        await message.answer("Krita bridge выключен. Включите KRITA_WATERMARK_ENABLED=true.")
        return
    source = message.reply_to_message
    if source is None:
        await message.answer(
            "Ответьте командой <code>/watermark</code> на изображение или отправьте "
            "изображение ответом на эту форму. Сначала откроется черновик настроек. "
            "Krita запустится только после кнопки «Сгенерировать preview».\n\n"
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
                "Ответьте изображением на это сообщение. Бот создаст черновик, "
                "где можно подряд менять положение, цвет, прозрачность, размер и "
                "отступ. Krita запустится только после кнопки генерации.\n\n"
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

    service = core_watermark._build_service(bot, database)
    owner_user_id = callback.from_user.id
    job_id = callback_data.job_id
    try:
        current = await service.get_current(job_id, owner_user_id=owner_user_id)
        await core_watermark._require_job_workspace(
            database,
            workspace_service,
            user_id=owner_user_id,
            workspace_id=getattr(current.job, "workspace_id", DEFAULT_WORKSPACE_ID),
        )
        if action == "generate":
            item = await _service_generate(
                service,
                job_id,
                owner_user_id=owner_user_id,
            )
            wake_error = await _ORIGINAL_CORE_WAKE_KRITA()
            status = "поставлено в очередь"
            if wake_error:
                status += "; Krita нужно открыть вручную"
            await callback.answer("Генерация preview запущена.")
            await core_watermark._safe_edit(
                callback,
                _draft_watermark_caption(item, status_text=status),
                item,
            )
            return
        if action == "position":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                position=callback_data.value,
                enabled=True,
            )
        elif action == "color":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                color=callback_data.value,
                enabled=True,
            )
        elif action == "opacity":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                opacity_delta=int(callback_data.value),
            )
        elif action == "size":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                size_delta=float(callback_data.value),
            )
        elif action == "margin":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                margin_delta=float(callback_data.value),
            )
        elif action == "undo":
            item = await service.undo(job_id, owner_user_id=owner_user_id)
        elif action == "remove":
            item = await service.revise(
                job_id,
                owner_user_id=owner_user_id,
                enabled=False,
            )
        else:
            await callback.answer("Неизвестная настройка.", show_alert=True)
            return
    except (TypeError, ValueError, WorkspaceAccessError) as error:
        await callback.answer(str(error), show_alert=True)
        return

    await callback.answer("Настройка сохранена в черновике.")
    await core_watermark._safe_edit(
        callback,
        _draft_watermark_caption(item),
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
        )
    except (ValueError, WorkspaceAccessError) as error:
        await message.answer(f"❌ {escape(str(error))}")
        return
    await message.answer(
        _draft_watermark_caption(item),
        reply_markup=_draft_watermark_keyboard(item),
    )


def install_workspace_product_experience() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    workspace_owner_controls._workspace_home_keyboard = _home_keyboard_with_hint_toggle
    workspace_owner_controls._render_home = _render_home_with_preferences
    workspace_owner_controls._render_member_home = _render_member_home_with_commands
    workspace_guided_actions._quick_keyboard = _quick_keyboard_with_references
    access_middleware.is_workspace_member_callback_data = _workspace_callback_with_template

    WatermarkService.create_job = _service_create_draft_job  # type: ignore[method-assign]
    WatermarkService.revise = _service_revise_draft  # type: ignore[method-assign]
    WatermarkService.undo = _service_undo_draft  # type: ignore[method-assign]
    setattr(WatermarkService, "generate", _service_generate)

    watermark_ui.build_watermark_keyboard = _draft_watermark_keyboard
    watermark_ui.format_watermark_caption = _draft_watermark_caption
    core_watermark.build_watermark_keyboard = _draft_watermark_keyboard
    core_watermark.format_watermark_caption = _draft_watermark_caption
    core_watermark._wake_krita = _defer_krita_start

    from velvet_bot.domains.watermark import service as watermark_service_module

    watermark_service_module.build_watermark_keyboard = _draft_watermark_keyboard
    watermark_service_module.format_watermark_caption = _draft_watermark_caption
    watermark_actions.build_watermark_keyboard = _draft_watermark_keyboard
    watermark_actions.format_watermark_caption = _draft_watermark_caption
    watermark_actions._wake_krita = _defer_krita_start


__all__ = (
    "install_workspace_product_experience",
    "router",
)
