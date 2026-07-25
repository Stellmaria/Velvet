from __future__ import annotations

from aiogram import Bot, Router
from aiogram.types import CallbackQuery

from velvet_bot.archive_catalog import (
    get_archive_page,
    toggle_archive_media_adult_requirement,
    toggle_archive_media_public_visibility,
    toggle_archive_media_spoiler,
)
from velvet_bot.database import Database
from velvet_bot.domains.media_rework.manual import request_manual_rework
from velvet_bot.domains.media_rework.repository import MediaReworkRepository
from velvet_bot.domains.workspaces.onboarding import WorkspaceOnboardingRepository
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.domains.workspaces.watermark_assets import (
    WorkspaceWatermarkAssetRepository,
)
from velvet_bot.presentation.telegram.routers.public_archive.watermark_actions import (
    enqueue_archive_watermark,
)
from velvet_bot.presentation.telegram.workspace_archive_access import (
    load_workspace_archive_action_page,
    resolve_workspace_archive_access,
)
from velvet_bot.presentation.telegram.workspace_archive_navigation import (
    replace_workspace_archive_page,
)
from velvet_bot.presentation.telegram.workspace_media_policy_controller import (
    show_workspace_media_policy,
)
from velvet_bot.presentation.telegram.workspace_personal_archive_contract import (
    WorkspacePersonalArchiveAction,
    WorkspacePersonalArchiveActionFilter,
)

_MUTATION_ACTIONS = frozenset({"watermark", "rework", "public", "adult", "blur"})


async def handle_workspace_archive_mutation(
    callback: CallbackQuery,
    archive_action: WorkspacePersonalArchiveAction,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace, owner_access = await resolve_workspace_archive_access(
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=archive_action.workspace_id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    if not owner_access:
        await callback.answer(
            "Эта кнопка доступна только владельцу пространства.",
            show_alert=True,
        )
        return

    page = await load_workspace_archive_action_page(
        callback,
        archive_action,
        database,
        workspace=workspace,
    )
    if page is None or page.media is None:
        return

    action = archive_action.action
    if action == "watermark":
        asset = await WorkspaceWatermarkAssetRepository(database).get(workspace.id)
        destinations = await WorkspaceOnboardingRepository(database).list_destinations(
            workspace.id
        )
        has_storage = any(
            item.destination_key == "watermarks" for item in destinations
        )
        module_enabled = await workspace_product_service.is_module_enabled(
            workspace_id=workspace.id,
            module_key="watermark",
        )
        if not module_enabled or asset is None or not has_storage:
            await show_workspace_media_policy(
                callback,
                database=database,
                workspace_product_service=workspace_product_service,
                workspace=workspace,
                page=page,
                alert=(
                    "Сначала включите модуль watermark и загрузите шаблон."
                    if not module_enabled
                    else "Сначала загрузите шаблон watermark."
                    if asset is None
                    else "Сначала подключите назначение «Watermark-копии»."
                ),
            )
            return
        await enqueue_archive_watermark(
            callback=callback,
            callback_data=archive_action,
            database=database,
            bot=bot,
            workspace_id=workspace.id,
            logo_asset=asset,
        )
        return

    if action == "rework":
        changed = await request_manual_rework(
            database,
            media_id=page.media.id,
            user_id=callback.from_user.id,
            reason="Владелец пространства отправил работу на доработку.",
        )
        await callback.answer(
            (
                "Работа отправлена в общую очередь доработки и скрыта из "
                "публичной выдачи. После проверки верните её отдельной кнопкой."
                if changed
                else "Работа уже находится в очереди доработки."
            ),
            show_alert=True,
        )
        return

    if action == "public":
        settings = await workspace_product_service.get_settings(workspace.id)
        if not settings.public_archive_enabled:
            await callback.answer(
                "Сначала включите публичный архив в настройках пространства.",
                show_alert=True,
            )
            return
        if (
            not page.media.is_public
            and await MediaReworkRepository(database).is_active(page.media.id)
        ):
            await callback.answer(
                "Сначала завершите проверку в очереди доработки, затем верните "
                "материал в публичный архив.",
                show_alert=True,
            )
            return
        await toggle_archive_media_public_visibility(
            database,
            character_id=page.character.id,
            media_id=page.media.id,
            workspace_id=workspace.id,
        )
    elif action == "adult":
        if not page.media.requires_adult_channel:
            channels = await workspace_product_service.list_channels(workspace.id)
            if not any(item.kind == "adult" for item in channels):
                await show_workspace_media_policy(
                    callback,
                    database=database,
                    workspace_product_service=workspace_product_service,
                    workspace=workspace,
                    page=page,
                    alert="Сначала подключите закрытый канал +18.",
                )
                return
        await toggle_archive_media_adult_requirement(
            database,
            character_id=page.character.id,
            media_id=page.media.id,
            workspace_id=workspace.id,
        )
    else:
        await toggle_archive_media_spoiler(
            database,
            character_id=page.character.id,
            media_id=page.media.id,
            workspace_id=workspace.id,
        )

    updated = await get_archive_page(
        database,
        page.character.id,
        page.offset,
        workspace_id=workspace.id,
        include_adult_restricted=True,
        include_oversized_images=True,
    )
    if updated is None or updated.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return
    await replace_workspace_archive_page(
        callback,
        bot,
        database=database,
        workspace_product_service=workspace_product_service,
        user_id=callback.from_user.id,
        workspace_id=workspace.id,
        page=updated,
        owner_access=True,
    )


def register_workspace_archive_mutations(router: Router) -> None:
    router.callback_query.register(
        handle_workspace_archive_mutation,
        WorkspacePersonalArchiveActionFilter(*sorted(_MUTATION_ACTIONS)),
    )


__all__ = (
    "handle_workspace_archive_mutation",
    "register_workspace_archive_mutations",
)
