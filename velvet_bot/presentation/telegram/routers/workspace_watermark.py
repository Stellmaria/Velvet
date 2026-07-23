from __future__ import annotations

import io
from html import escape
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.archive_catalog import get_archive_page
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import (
    GLOBAL_WORKSPACE_CREATOR_ID,
)
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.domains.workspaces.watermark_assets import (
    WorkspaceWatermarkAssetRepository,
    WorkspaceWatermarkAssetService,
)
from velvet_bot.infrastructure.krita_bridge import KritaBridge, default_krita_bridge_dir
from velvet_bot.presentation.telegram.routers.core_operations_controllers.watermark import (
    _build_service as _build_watermark_service,
    _create_job_from_message,
    _watermark_enabled,
)
from velvet_bot.presentation.telegram.routers.public_archive.watermark_actions import (
    enqueue_archive_watermark,
)
from velvet_bot.presentation.telegram.routers.workspace_owner_controls import (
    WorkspacePersonalArchiveCallback,
    _is_global_owner as _is_workspace_global_owner,
    _require_personal_module,
)
from velvet_bot.workspace_ui import WorkspaceCallback, workspace_callback
from velvet_bot.workspace_watermark_ui import (
    WorkspaceWatermarkCallback,
    WorkspaceWatermarkForm,
    build_reset_confirmation_keyboard,
    build_workspace_watermark_input_keyboard,
    build_workspace_watermark_keyboard,
    format_workspace_watermark,
)

router = Router(name=__name__)


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
        if not _watermark_enabled():
            await callback.answer(
                "Krita bridge выключен. Включите KRITA_WATERMARK_ENABLED=true.",
                show_alert=True,
            )
            return
        await state.set_state(WorkspaceWatermarkForm.waiting_source)
        await state.update_data(workspace_id=workspace.id)
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "<b>⚡ Быстрый watermark</b>\n\n"
                "Просто отправьте следующим сообщением фото или изображение-файл. "
                "Бот возьмёт текущий логотип этого пространства, создаст отдельную "
                "копию и покажет кнопки положения, прозрачности, размера и отступа. "
                "Оригинал не изменяется.",
                reply_markup=build_workspace_watermark_input_keyboard(workspace.id),
            )
        await callback.answer()
        return
    await callback.answer("Неизвестное действие логотипа.", show_alert=True)


@router.message(
    StateFilter(WorkspaceWatermarkForm.waiting_source),
    F.photo | F.document,
)
async def handle_workspace_watermark_source(
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
        await _require_context(
            database=database,
            workspaces=workspace_service,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
        )
    except WorkspaceAccessError as error:
        await state.clear()
        await message.answer(escape(str(error)))
        return
    if not _watermark_enabled():
        await state.clear()
        await message.answer("Krita bridge выключен.")
        return

    item = await _create_job_from_message(
        message=message,
        source_message=message,
        bot=bot,
        database=database,
        workspace_service=workspace_service,
        watermark_service=_build_watermark_service(bot, database),
    )
    if item is not None:
        await state.clear()


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


async def handle_workspace_archive_fast_watermark(
    callback: CallbackQuery,
    callback_data: WorkspacePersonalArchiveCallback,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace = await _require_personal_module(
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=callback_data.workspace_id,
            module_key="archive",
            minimum_role="viewer",
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    membership = await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=callback.from_user.id,
        minimum_role="viewer",
        global_owner=_is_workspace_global_owner(callback.from_user.id),
    )
    if membership.role != "owner" and not _is_workspace_global_owner(
        callback.from_user.id
    ):
        await callback.answer(
            "Быстрый watermark доступен только владельцу пространства.",
            show_alert=True,
        )
        return

    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
        workspace_id=workspace.id,
        include_adult_restricted=True,
        include_oversized_images=True,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return
    if callback_data.media_id and callback_data.media_id != page.media.id:
        await callback.answer(
            "Архив изменился. Откройте материал заново.",
            show_alert=True,
        )
        return

    module_enabled = await workspace_product_service.is_module_enabled(
        workspace_id=workspace.id,
        module_key="watermark",
    )
    asset = await WorkspaceWatermarkAssetRepository(database).get(workspace.id)
    if not module_enabled or asset is None:
        if isinstance(callback.message, Message):
            reason = (
                "Сначала включите модуль watermark."
                if not module_enabled
                else "Сначала загрузите логотип пространства."
            )
            await callback.message.answer(
                f"<b>Быстрый watermark пока не настроен</b>\n\n{reason}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="⚙️ Настроить watermark",
                                callback_data=workspace_callback(
                                    "module",
                                    workspace_id=workspace.id,
                                    module_key="watermark",
                                ),
                            )
                        ]
                    ]
                ),
            )
        await callback.answer("Откройте настройки watermark.", show_alert=True)
        return

    await enqueue_archive_watermark(
        callback=callback,
        callback_data=callback_data,
        database=database,
        bot=bot,
        workspace_id=workspace.id,
        logo_asset=asset,
    )


router.callback_query.register(
    handle_workspace_archive_fast_watermark,
    WorkspacePersonalArchiveCallback.filter(F.action == "watermark"),
)


__all__ = ("router",)
