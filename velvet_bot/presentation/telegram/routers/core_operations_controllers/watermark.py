from __future__ import annotations

import logging
import os
import re
from html import escape
from pathlib import Path
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, FSInputFile, Message
from PIL import Image, UnidentifiedImageError

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.domains.workspaces.watermark_assets import WorkspaceWatermarkAssetRepository
from velvet_bot.domains.public_archive.watermark_repository import (
    PublicArchiveWatermarkRepository,
)
from velvet_bot.domains.watermark.archive_output import (
    prepare_archive_watermark_output,
)
from velvet_bot.domains.watermark.models import WatermarkWorkItem
from velvet_bot.domains.watermark.repository import WatermarkRepository
from velvet_bot.domains.watermark.service import WatermarkService
from velvet_bot.infrastructure.krita_bridge import KritaBridge, default_krita_bridge_dir
from velvet_bot.krita_supervisor import build_krita_supervisor_client
from velvet_bot.presentation.telegram.routers.public_archive.watermark_actions import (
    handle_manager_fast_watermark,
)
from velvet_bot.public_ui import PublicArchiveCallback
from velvet_bot.supervisor_client import SupervisorClientError
from velvet_bot.watermark_ui import (
    WatermarkCallback,
    build_archive_watermark_edit_keyboard,
    build_watermark_keyboard,
    build_watermark_start_keyboard,
    format_watermark_caption,
)

logger = logging.getLogger(__name__)
router = Router(name=__name__)
_INPUT_MARKER = "#watermark-input"
_COLOR_MARKER = re.compile(r"#watermark-color:(\d+)")
_SUPPORTED_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".tif",
    ".tiff",
    ".bmp",
}
_MIME_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/tiff": ".tiff",
    "image/bmp": ".bmp",
}


def _watermark_enabled() -> bool:
    return os.getenv("KRITA_WATERMARK_ENABLED", "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
        "да",
    }


def _build_service(bot: Bot, database: Database) -> WatermarkService:
    return WatermarkService(
        bot=bot,
        repository=WatermarkRepository(database),
        bridge=KritaBridge(default_krita_bridge_dir()),
    )


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _workspace_logo_context(
    database: Database,
    workspace_service: WorkspaceService,
    *,
    user_id: int,
):
    global_owner = _is_global_owner(user_id)
    workspace = await workspace_service.resolve_active_workspace(
        user_id=user_id,
        global_owner=global_owner,
    )
    if workspace.id == DEFAULT_WORKSPACE_ID:
        return DEFAULT_WORKSPACE_ID, None
    await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=user_id,
        minimum_role="editor",
        global_owner=global_owner,
    )
    async with database.acquire() as connection:
        enabled = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT
              AND module_key = 'watermark'
            """,
            workspace.id,
        )
    if not enabled:
        raise WorkspaceAccessError("Модуль watermark выключен или не разрешён Стэл.")
    asset = await WorkspaceWatermarkAssetRepository(database).get(workspace.id)
    return workspace.id, asset


async def _require_job_workspace(
    database: Database,
    workspace_service: WorkspaceService | None,
    *,
    user_id: int,
    workspace_id: int,
) -> None:
    if int(workspace_id) == DEFAULT_WORKSPACE_ID:
        return
    if workspace_service is None:
        raise WorkspaceAccessError(
            "Сервис пространства недоступен для личного watermark-задания."
        )
    active_id, _ = await _workspace_logo_context(
        database, workspace_service, user_id=user_id
    )
    if active_id != int(workspace_id):
        raise WorkspaceAccessError(
            "Задание относится не к активному пространству. Откройте его заново."
        )


async def _wake_krita() -> str | None:
    client = build_krita_supervisor_client()
    if client is None:
        return None
    try:
        await client.ensure_krita()
    except SupervisorClientError as error:
        logger.warning("Could not wake Krita through Supervisor: %s", error)
        return str(error)
    return None


class WatermarkInputReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        reply = message.reply_to_message
        return bool(reply and _INPUT_MARKER in (reply.text or reply.caption or ""))


class WatermarkColorReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> dict | bool:
        reply = message.reply_to_message
        match = _COLOR_MARKER.search((reply.text or reply.caption or "") if reply else "")
        if match is None:
            return False
        return {"watermark_job_id": int(match.group(1))}


def _source_file(message: Message):
    if message.photo:
        photo = message.photo[-1]
        return photo.file_id, photo.file_unique_id, ".jpg"
    document = message.document
    if document is None:
        return None
    mime_type = (document.mime_type or "").strip().casefold()
    filename_suffix = Path(document.file_name or "").suffix.lower()
    if filename_suffix in _SUPPORTED_IMAGE_SUFFIXES:
        suffix = filename_suffix
    else:
        suffix = _MIME_SUFFIXES.get(mime_type)
    if suffix is None:
        return None
    return document.file_id, document.file_unique_id, suffix


async def _create_job_from_message(
    *,
    message: Message,
    source_message: Message,
    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
    watermark_service: WatermarkService,
) -> WatermarkWorkItem | None:
    try:
        workspace_id, logo_asset = await _workspace_logo_context(
            database,
            workspace_service,
            user_id=int(message.from_user.id),
        )
    except WorkspaceAccessError as error:
        await message.answer(f"❌ {escape(str(error))}")
        return None
    source = _source_file(source_message)
    if source is None:
        await message.answer(
            "Нужно изображение, отправленное как фото или документ "
            "PNG/JPG/JPEG/WEBP/TIFF/BMP."
        )
        return None
    wake_error = await _wake_krita()
    if wake_error:
        await message.answer(
            "⚠️ Не удалось автоматически запустить Krita. "
            "Задание будет создано, но Krita нужно открыть вручную.\n\n"
            f"<code>{escape(wake_error[:800])}</code>"
        )

    file_id, file_unique_id, suffix = source
    source_path = watermark_service.bridge.paths.sources / (
        f"tg-{message.chat.id}-{source_message.message_id}-{uuid4().hex}{suffix}"
    )
    source_path = watermark_service.bridge.paths.ensure_in(
        source_path,
        watermark_service.bridge.paths.sources,
    )
    await bot.download(file_id, destination=source_path)
    try:
        with Image.open(source_path) as image:
            image.verify()
    except (OSError, UnidentifiedImageError, ValueError):
        source_path.unlink(missing_ok=True)
        await message.answer(
            "❌ Документ не является поддерживаемым изображением или повреждён."
        )
        return None
    item = await watermark_service.create_job(
        owner_user_id=message.from_user.id,
        chat_id=message.chat.id,
        source_message_id=source_message.message_id,
        source_file_id=file_id,
        source_file_unique_id=file_unique_id,
        source_path=str(source_path),
        workspace_id=workspace_id,
        logo_kind=(logo_asset.asset_kind if logo_asset is not None else "builtin"),
        logo_path=(logo_asset.local_path if logo_asset is not None else None),
        logo_width=(logo_asset.width if logo_asset is not None else None),
        logo_height=(logo_asset.height if logo_asset is not None else None),
        logo_name=(logo_asset.file_name if logo_asset is not None else None),
    )
    control = await message.answer(
        format_watermark_caption(item, status_text="поставлено в очередь"),
        reply_markup=build_watermark_keyboard(item),
    )
    await watermark_service.set_control_message(item.job.id, control.message_id)
    return item


async def _safe_edit(
    callback: CallbackQuery,
    text: str,
    item: WatermarkWorkItem | None = None,
    *,
    keyboard=None,
) -> None:
    if not isinstance(callback.message, Message):
        return
    reply_markup = (
        keyboard
        if keyboard is not None
        else (build_watermark_keyboard(item) if item is not None else None)
    )
    try:
        if callback.message.photo or callback.message.document:
            await callback.message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


@router.message(Command("watermark"))
async def handle_watermark_command(
    message: Message,
    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if not _watermark_enabled():
        await message.answer("Krita bridge выключен. Включите KRITA_WATERMARK_ENABLED=true.")
        return
    source = message.reply_to_message
    if source is None:
        wake_error = await _wake_krita()
        warning = (
            f"\n\n⚠️ Автозапуск Krita: <code>{escape(wake_error[:500])}</code>"
            if wake_error
            else ""
        )
        await message.answer(
            "Ответьте командой <code>/watermark</code> на изображение. "
            "Команда является аварийным резервом; обычный вход доступен из меню."
            + warning
        )
        return
    await _create_job_from_message(
        message=message,
        source_message=source,
        bot=bot,
        database=database,
        workspace_service=workspace_service,
        watermark_service=_build_service(bot, database),
    )


@router.message(WatermarkInputReplyFilter(), F.photo | F.document)
async def handle_watermark_form_image(
    message: Message,
    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if not _watermark_enabled():
        await message.answer("Krita bridge выключен.")
        return
    await _create_job_from_message(
        message=message,
        source_message=message,
        bot=bot,
        database=database,
        workspace_service=workspace_service,
        watermark_service=_build_service(bot, database),
    )


@router.message(WatermarkColorReplyFilter(), F.text)
async def handle_watermark_custom_color(
    message: Message,
    watermark_job_id: int,
    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if not _watermark_enabled():
        await message.answer("Krita bridge выключен.")
        return
    await _wake_krita()
    service = _build_service(bot, database)
    color = (message.text or "").strip()
    try:
        current = await service.get_current(
            watermark_job_id, owner_user_id=message.from_user.id
        )
        await _require_job_workspace(
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
    except ValueError as error:
        await message.answer(f"❌ {escape(str(error))}")
        return
    await message.answer(
        format_watermark_caption(item, status_text="новый цвет поставлен в очередь"),
        reply_markup=build_watermark_keyboard(item),
    )


@router.callback_query(WatermarkCallback.filter())
async def handle_watermark_callback(
    callback: CallbackQuery,
    callback_data: WatermarkCallback,
    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService | None = None,
) -> None:
    action = callback_data.action
    if action != "menu" and not _watermark_enabled():
        await callback.answer("Krita bridge выключен.", show_alert=True)
        return
    if action in {"start", "help"}:
        wake_error = await _wake_krita()
        await callback.answer()
        if isinstance(callback.message, Message):
            warning = (
                "\n\n⚠️ Krita не запустилась автоматически. Откройте её вручную.\n"
                f"<code>{escape(wake_error[:800])}</code>"
                if wake_error
                else "\n\nKrita запущена автоматически и закроется после 10 минут простоя."
            )
            await callback.message.answer(
                "<b>Водяной знак Velvet Anatomy</b>\n\n"
                "Ответьте изображением на это сообщение. Бот сохранит неизменяемый "
                "исходник, а Krita будет строить отдельные preview."
                + warning
                + f"\n\n<code>{_INPUT_MARKER}</code>",
                reply_markup=build_watermark_start_keyboard(),
            )
        return
    if action == "menu":
        await callback.answer()
        if isinstance(callback.message, Message):
            from velvet_bot.presentation.telegram.routers.core_operations_controllers.owner_menu import (
                show_owner_menu,
            )

            await show_owner_menu(callback.message)
        return

    service = _build_service(bot, database)
    owner_user_id = callback.from_user.id
    job_id = callback_data.job_id

    if action == "archive_edit":
        try:
            item = await service.get_current(
                job_id,
                owner_user_id=owner_user_id,
            )
            await _require_job_workspace(
                database,
                workspace_service,
                user_id=owner_user_id,
                workspace_id=getattr(
                    item.job,
                    "workspace_id",
                    DEFAULT_WORKSPACE_ID,
                ),
            )
        except (WorkspaceAccessError, ValueError):
            # Do not reveal whether an archive job exists for another owner/workspace.
            await callback.answer("Архивное задание не найдено.", show_alert=True)
            return
        if item.job.archive_media_id is None:
            await callback.answer("Архивное задание не найдено.", show_alert=True)
            return
        await callback.answer("Настройки открыты.")
        await _safe_edit(
            callback,
            format_watermark_caption(item, status_text="измените шаблон"),
            item,
            keyboard=build_archive_watermark_edit_keyboard(item),
        )
        return

    try:
        current = await service.get_current(job_id, owner_user_id=owner_user_id)
        await _require_job_workspace(
            database,
            workspace_service,
            user_id=owner_user_id,
            workspace_id=getattr(
                current.job,
                "workspace_id",
                DEFAULT_WORKSPACE_ID,
            ),
        )
    except (WorkspaceAccessError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return

    if action == "custom_color":
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "Ответьте на это сообщение HEX-цветом, например "
                "<code>#D8C8B8</code>.\n\n"
                f"<code>#watermark-color:{job_id}</code>"
            )
        return

    await callback.answer("Принято, готовлю новую версию…")
    if action != "cancel":
        await _wake_krita()

    try:
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
        elif action in {"approve", "archive_approve"}:
            item = await service.approve(job_id, owner_user_id=owner_user_id)
            final_path = item.job.final_path
            if not final_path:
                raise ValueError("Финальный путь задания не сохранён.")
            if not isinstance(callback.message, Message):
                raise ValueError("Сообщение preview больше недоступно.")

            archive_media_id = item.job.archive_media_id
            if archive_media_id is not None:
                prepared = prepare_archive_watermark_output(
                    item.job.source_path,
                    final_path,
                )
                sent = await callback.message.answer_document(
                    FSInputFile(
                        prepared.path,
                        filename=f"velvet-archive-{archive_media_id}-watermarked.png",
                    ),
                    caption=(
                        "✅ PNG без потерь подтверждён для публичного архива.\n"
                        f"Размер: <b>{prepared.output_bytes / 1024 / 1024:.2f} МБ</b> · "
                        f"{prepared.width}×{prepared.height}."
                    ),
                )
                if sent.document is None:
                    raise ValueError("Telegram не вернул file_id загруженного PNG.")
                updated = await PublicArchiveWatermarkRepository(
                    database
                ).approve_replacement(
                    media_id=archive_media_id,
                    telegram_file_id=sent.document.file_id,
                    file_size=int(sent.document.file_size or prepared.output_bytes),
                    approved_by=owner_user_id,
                    settings=item.revision.settings,
                )
                if not updated:
                    raise ValueError("Материал публичного архива больше не найден.")
                await _safe_edit(
                    callback,
                    format_watermark_caption(
                        item,
                        status_text="одобрен и заменён в публичном архиве",
                    ),
                    None,
                )
                return

            await callback.message.answer_document(
                FSInputFile(
                    final_path,
                    filename=f"velvet-watermark-job-{job_id}.png",
                ),
                caption=f"✅ PNG без сжатия · задание <b>{job_id}</b>.",
            )
            await _safe_edit(
                callback,
                format_watermark_caption(item, status_text="PNG отправлен"),
                None,
            )
            return
        elif action == "cancel":
            result = await service.cancel(job_id, owner_user_id=owner_user_id)
            if result == "approved":
                text = f"Задание <b>{job_id}</b> уже подтверждено. Отмена проигнорирована."
            elif result == "already_cancelled":
                text = f"Задание <b>{job_id}</b> уже отменено."
            else:
                text = f"Задание <b>{job_id}</b> отменено."
            await _safe_edit(callback, text)
            return
        else:
            raise ValueError("Неизвестное действие водяного знака.")
    except (TypeError, ValueError) as error:
        if isinstance(callback.message, Message):
            await callback.message.answer(f"❌ {escape(str(error))}")
        return

    await _safe_edit(
        callback,
        format_watermark_caption(item, status_text="поставлено в очередь"),
        item,
    )


router.callback_query.register(
    handle_manager_fast_watermark,
    PublicArchiveCallback.filter(F.action == "pwm"),
)


__all__ = ("router",)
