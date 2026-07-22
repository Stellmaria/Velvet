from __future__ import annotations

import io
from html import escape
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.domains.workspaces.watermark_assets import (
    WorkspaceWatermarkAssetRepository,
    WorkspaceWatermarkAssetService,
)
from velvet_bot.infrastructure.krita_bridge import KritaBridge, default_krita_bridge_dir
from velvet_bot.workspace_ui import WorkspaceCallback
from velvet_bot.workspace_watermark_ui import (
    WorkspaceWatermarkCallback,
    WorkspaceWatermarkForm,
    build_reset_confirmation_keyboard,
    build_workspace_watermark_keyboard,
    format_workspace_watermark,
)

router = Router(name=__name__)
_INPUT_MARKER = "#watermark-input"


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


def _asset_service(database: Database) -> WorkspaceWatermarkAssetService:
    return WorkspaceWatermarkAssetService(
        repository=WorkspaceWatermarkAssetRepository(database),
        bridge_paths=KritaBridge(default_krita_bridge_dir()).paths,
    )


async def _module_enabled(database: Database, workspace_id: int) -> bool:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT
              AND module_key = 'watermark'
            """,
            int(workspace_id),
        )
    return bool(value)


async def _require_context(
    *,
    database: Database,
    workspaces: WorkspaceService,
    workspace_id: int,
    actor_user_id: int,
) -> Workspace:
    global_owner = _is_global_owner(actor_user_id)
    active = await workspaces.resolve_active_workspace(
        user_id=actor_user_id,
        global_owner=global_owner,
    )
    if active.id != int(workspace_id):
        raise WorkspaceAccessError(
            "Кнопка относится не к активному пространству. Откройте меню заново."
        )
    if active.is_system:
        raise WorkspaceAccessError(
            "Стандартный логотип системного Velvet изменяется только в коде плагина."
        )
    await workspaces.require_role(
        workspace_id=active.id,
        user_id=actor_user_id,
        minimum_role="admin",
        global_owner=global_owner,
    )
    if not await _module_enabled(database, active.id):
        raise WorkspaceAccessError("Модуль watermark выключен или не разрешён Стэл.")
    return active


async def _edit(
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


async def _show(
    callback: CallbackQuery,
    *,
    database: Database,
    workspaces: WorkspaceService,
    workspace_id: int,
) -> None:
    actor_id = int(callback.from_user.id)
    workspace = await _require_context(
        database=database,
        workspaces=workspaces,
        workspace_id=workspace_id,
        actor_user_id=actor_id,
    )
    asset = await _asset_service(database).get(workspace.id)
    await _edit(
        callback,
        text=format_workspace_watermark(
            workspace_name=workspace.name,
            asset=asset,
        ),
        reply_markup=build_workspace_watermark_keyboard(
            workspace_id=workspace.id,
            has_asset=asset is not None,
        ),
    )


@router.callback_query(
    WorkspaceCallback.filter((F.action == "module") & (F.module_key == "watermark"))
)
async def handle_watermark_module(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    try:
        await _show(
            callback,
            database=database,
            workspaces=workspace_service,
            workspace_id=callback_data.workspace_id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)


@router.callback_query(WorkspaceWatermarkCallback.filter())
async def handle_workspace_watermark_callback(
    callback: CallbackQuery,
    callback_data: WorkspaceWatermarkCallback,
    state: FSMContext,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    actor_id = int(callback.from_user.id)
    try:
        workspace = await _require_context(
            database=database,
            workspaces=workspace_service,
            workspace_id=callback_data.workspace_id,
            actor_user_id=actor_id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    action = callback_data.action
    if action == "show":
        await state.clear()
        await _show(
            callback,
            database=database,
            workspaces=workspace_service,
            workspace_id=workspace.id,
        )
        return
    if action == "upload":
        await state.set_state(WorkspaceWatermarkForm.waiting_asset)
        await state.update_data(workspace_id=workspace.id)
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "<b>Загрузите логотип</b>\n\n"
                "Поддерживаются:\n"
                "• SVG без скриптов и внешних ссылок, до 5 МБ;\n"
                "• PNG или WebP с реальной прозрачностью, до 10 МБ.\n\n"
                "Отправляйте растровый логотип <b>как файл</b>. Режим «фото» Telegram "
                "обычно превращает прозрачный PNG в JPEG, потому что спокойная жизнь была бы слишком проста."
            )
        await callback.answer()
        return
    if action == "reset":
        await _edit(
            callback,
            text=(
                "<b>Вернуть стандартный логотип Velvet?</b>\n\n"
                "Новые задания будут использовать встроенный знак. Уже созданные "
                "watermark-задания сохранят свой snapshot."
            ),
            reply_markup=build_reset_confirmation_keyboard(workspace.id),
        )
        return
    if action == "resetok":
        changed = await _asset_service(database).reset(workspace.id)
        await callback.answer(
            "Стандартный логотип восстановлен."
            if changed
            else "Собственный логотип уже не установлен."
        )
        await _show(
            callback,
            database=database,
            workspaces=workspace_service,
            workspace_id=workspace.id,
        )
        return
    if action == "create":
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "<b>Создание watermark</b>\n\n"
                "Ответьте изображением на это сообщение. Бот возьмёт текущий логотип "
                "активного пространства и зафиксирует его в новом задании.\n\n"
                f"<code>{_INPUT_MARKER}</code>"
            )
        await callback.answer()
        return
    await callback.answer("Неизвестное действие логотипа.", show_alert=True)


@router.message(
    StateFilter(WorkspaceWatermarkForm.waiting_asset),
    F.document | F.photo,
)
async def handle_workspace_watermark_upload(
    message: Message,
    state: FSMContext,
    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    actor_id = int(message.from_user.id) if message.from_user else 0
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    try:
        workspace = await _require_context(
            database=database,
            workspaces=workspace_service,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
        )
    except WorkspaceAccessError as error:
        await state.clear()
        await message.answer(escape(str(error)))
        return

    if message.document is not None:
        source = message.document
        file_id = source.file_id
        unique_id = source.file_unique_id
        file_name = source.file_name or "workspace-logo"
        mime_type = source.mime_type
    elif message.photo:
        source = message.photo[-1]
        file_id = source.file_id
        unique_id = source.file_unique_id
        file_name = "telegram-photo.jpg"
        mime_type = "image/jpeg"
    else:
        await message.answer("Отправьте SVG, PNG или WebP.")
        return

    buffer = io.BytesIO()
    await bot.download(file_id, destination=buffer)
    raw = buffer.getvalue()
    try:
        asset = await _asset_service(database).store(
            workspace_id=workspace.id,
            raw=raw,
            file_name=Path(file_name).name,
            mime_type=mime_type,
            telegram_file_id=file_id,
            telegram_file_unique_id=unique_id,
            uploaded_by=actor_id,
        )
    except ValueError as error:
        suffix = (
            "\n\nОтправьте прозрачный PNG/WebP как <b>документ</b>, а не как фото."
            if message.photo
            else ""
        )
        await message.answer(f"❌ {escape(str(error))}{suffix}")
        return

    await state.clear()
    await message.answer(
        format_workspace_watermark(
            workspace_name=workspace.name,
            asset=asset,
        ),
        reply_markup=build_workspace_watermark_keyboard(
            workspace_id=workspace.id,
            has_asset=True,
        ),
    )


__all__ = ("router",)
