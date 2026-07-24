from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from velvet_bot import watermark_ui
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.krita_supervisor import wake_krita
from velvet_bot.presentation.telegram.routers.core_operations_controllers import (
    watermark as core_watermark,
)
from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_command_filtering import (
    command_name,
)
from velvet_bot.watermark_ui import WatermarkCallback

router = Router(name=__name__)

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


class WatermarkCommandFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return command_name(message) == "watermark"


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


__all__ = ("WatermarkCommandFilter", "router")
