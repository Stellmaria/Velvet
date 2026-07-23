from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from velvet_bot.workspace_watermark_ui import WorkspaceWatermarkCallback


router = Router(name=__name__)


@router.callback_query(
    WorkspaceWatermarkCallback.filter(F.action == "create")
)
async def handle_removed_standalone_quick_watermark(callback: CallbackQuery) -> None:
    await callback.answer(
        "Быстрый watermark запускается на карточке изображения в архиве. "
        "Так сохраняется связь с материалом и не создаются бесхозные задания Krita.",
        show_alert=True,
    )


__all__ = ("router",)
