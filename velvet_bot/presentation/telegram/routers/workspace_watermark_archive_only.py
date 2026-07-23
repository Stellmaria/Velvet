from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.routers import workspace_owner_controls as owner_controls
from velvet_bot.workspace_watermark_ui import WorkspaceWatermarkCallback


router = Router(name=__name__)


async def _resolve_owner_page(
    *,
    callback: CallbackQuery,
    callback_data: owner_controls.WorkspacePersonalArchiveCallback,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
):
    workspace = await owner_controls._require_personal_module(
        workspace_service=workspace_service,
        workspace_product_service=workspace_product_service,
        user_id=callback.from_user.id,
        workspace_id=callback_data.workspace_id,
        module_key="archive",
        minimum_role="owner",
    )
    page = await owner_controls.get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
        workspace_id=workspace.id,
        include_adult_restricted=True,
        include_oversized_images=True,
    )
    if page is None:
        raise ValueError("Персонаж не найден в этом пространстве.")
    if page.media is None:
        raise ValueError("Архив персонажа пока пуст.")
    if callback_data.media_id and callback_data.media_id != page.media.id:
        raise ValueError("Архив изменился. Откройте материал заново.")
    return workspace, page


async def _refresh_page(
    *,
    callback: CallbackQuery,
    bot: Bot,
    database: Database,
    workspace_product_service: WorkspaceProductService,
    workspace_id: int,
    character_id: int,
    offset: int,
    user_id: int,
) -> None:
    page = await owner_controls.get_archive_page(
        database,
        character_id,
        offset,
        workspace_id=workspace_id,
        include_adult_restricted=True,
        include_oversized_images=True,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return
    await owner_controls._replace_archive_page(
        callback,
        bot,
        database=database,
        workspace_product_service=workspace_product_service,
        user_id=user_id,
        workspace_id=workspace_id,
        page=page,
        owner_access=True,
    )


async def handle_workspace_rework_action(
    callback: CallbackQuery,
    callback_data: owner_controls.WorkspacePersonalArchiveCallback,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace, page = await _resolve_owner_page(
            callback=callback,
            callback_data=callback_data,
            database=database,
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
        )
    except (WorkspaceAccessError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return

    repository = owner_controls.MediaReworkRepository(
        database,
        workspace_id=workspace.id,
    )
    if await repository.is_active(page.media.id):
        changed = await repository.accept(page.media.id, callback.from_user.id)
        result_text = (
            "Доработка завершена. Материал остаётся скрытым, пока вы отдельно не "
            "вернёте его в публичный архив."
            if changed
            else "Заявка уже была завершена."
        )
    else:
        try:
            changed = await owner_controls.request_manual_rework(
                database,
                media_id=page.media.id,
                user_id=callback.from_user.id,
                workspace_id=workspace.id,
                reason="Владелец пространства отправил работу на доработку.",
            )
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        result_text = (
            "Работа отправлена на доработку внутри этого пространства и скрыта из "
            "его публичного архива. Повторное нажатие завершит доработку."
            if changed
            else "Работа уже находится на доработке в этом пространстве."
        )

    await _refresh_page(
        callback=callback,
        bot=bot,
        database=database,
        workspace_product_service=workspace_product_service,
        workspace_id=workspace.id,
        character_id=page.character.id,
        offset=page.offset,
        user_id=callback.from_user.id,
    )
    if isinstance(callback.message, Message):
        await callback.message.answer(result_text)


async def handle_workspace_public_visibility_action(
    callback: CallbackQuery,
    callback_data: owner_controls.WorkspacePersonalArchiveCallback,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace, page = await _resolve_owner_page(
            callback=callback,
            callback_data=callback_data,
            database=database,
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
        )
    except (WorkspaceAccessError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return

    settings = await workspace_product_service.get_settings(workspace.id)
    if not settings.public_archive_enabled:
        await callback.answer(
            "Сначала включите публичный архив в настройках пространства.",
            show_alert=True,
        )
        return

    repository = owner_controls.MediaReworkRepository(
        database,
        workspace_id=workspace.id,
    )
    if not page.media.is_public and await repository.is_active(page.media.id):
        await callback.answer(
            "Сначала завершите доработку, затем верните материал в публичный архив.",
            show_alert=True,
        )
        return

    await owner_controls.toggle_archive_media_public_visibility(
        database,
        character_id=page.character.id,
        media_id=page.media.id,
        workspace_id=workspace.id,
    )
    await _refresh_page(
        callback=callback,
        bot=bot,
        database=database,
        workspace_product_service=workspace_product_service,
        workspace_id=workspace.id,
        character_id=page.character.id,
        offset=page.offset,
        user_id=callback.from_user.id,
    )


async def handle_removed_standalone_quick_watermark(callback: CallbackQuery) -> None:
    await callback.answer(
        "Быстрый watermark запускается на карточке изображения в архиве. "
        "Так сохраняется связь с материалом и не создаются бесхозные задания Krita.",
        show_alert=True,
    )


router.callback_query.register(
    handle_workspace_rework_action,
    owner_controls.WorkspacePersonalArchiveCallback.filter(F.action == "rework"),
)
router.callback_query.register(
    handle_workspace_public_visibility_action,
    owner_controls.WorkspacePersonalArchiveCallback.filter(F.action == "public"),
)
router.callback_query.register(
    handle_removed_standalone_quick_watermark,
    WorkspaceWatermarkCallback.filter(F.action == "create"),
)


__all__ = ("router",)
