from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from velvet_bot.access import AccessPolicy
from velvet_bot.archive_catalog import get_archive_page
from velvet_bot.database import Database
from velvet_bot.domains.media_rework.manual import request_manual_rework
from velvet_bot.public_manager_access import has_public_manager_access
from velvet_bot.public_ui import PublicArchiveCallback


async def handle_public_archive_rework(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    access_policy: AccessPolicy,
) -> None:
    if not has_public_manager_access(callback.from_user, access_policy):
        await callback.answer("Управление архивом для вас закрыто.", show_alert=True)
        return

    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
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

    changed = await request_manual_rework(
        database,
        media_id=page.media.id,
        user_id=callback.from_user.id,
    )
    await callback.answer(
        "Работа отправлена в очередь доработки."
        if changed
        else "Работа уже находится в очереди доработки.",
        show_alert=True,
    )


def register_public_archive_rework(router: Router) -> None:
    router.callback_query.register(
        handle_public_archive_rework,
        PublicArchiveCallback.filter(F.action == "prework"),
    )


__all__ = ("register_public_archive_rework",)
