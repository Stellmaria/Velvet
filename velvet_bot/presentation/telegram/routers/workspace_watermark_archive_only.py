from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from velvet_bot.archive_catalog import get_archive_page
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.onboarding import WorkspaceOnboardingRepository
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.domains.workspaces.watermark_assets import WorkspaceWatermarkAssetRepository
from velvet_bot.presentation.telegram.routers.public_archive.watermark_actions import (
    enqueue_archive_watermark,
)
from velvet_bot.presentation.telegram.routers.workspace_owner_controls import (
    WorkspacePersonalArchiveCallback,
    _DOWNLOAD_AUDIENCE_ACTIONS,
    _DOWNLOAD_VARIANT_ACTIONS,
    _require_personal_module,
    _show_media_settings,
)
from velvet_bot.workspace_watermark_ui import WorkspaceWatermarkCallback


router = Router(name=__name__)
_DOWNLOAD_POLICY_ACTIONS = tuple(
    (*_DOWNLOAD_AUDIENCE_ACTIONS.keys(), *_DOWNLOAD_VARIANT_ACTIONS.keys())
)


def _watermark_prerequisite_error(
    *,
    module_enabled: bool,
    has_asset: bool,
) -> str | None:
    if not module_enabled:
        return "Сначала включите модуль watermark и загрузите шаблон."
    if not has_asset:
        return "Сначала загрузите шаблон watermark."
    return None


def _download_policy_error(
    *,
    audience: str,
    variant: str,
    channel_kinds: set[str],
    has_watermark_asset: bool,
) -> str | None:
    if audience == "subscribers" and "download" not in channel_kinds:
        return "Сначала подключите канал «Проверка скачивания»."
    if audience != "disabled" and variant == "watermark" and not has_watermark_asset:
        return "Сначала загрузите шаблон watermark."
    return None


async def _resolve_owner_page(
    *,
    callback: CallbackQuery,
    callback_data: WorkspacePersonalArchiveCallback,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
):
    workspace = await _require_personal_module(
        workspace_service=workspace_service,
        workspace_product_service=workspace_product_service,
        user_id=callback.from_user.id,
        workspace_id=callback_data.workspace_id,
        module_key="archive",
        minimum_role="owner",
    )
    page = await get_archive_page(
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


async def handle_workspace_archive_watermark_with_chat_fallback(
    callback: CallbackQuery,
    callback_data: WorkspacePersonalArchiveCallback,
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

    module_enabled = await workspace_product_service.is_module_enabled(
        workspace_id=workspace.id,
        module_key="watermark",
    )
    asset = await WorkspaceWatermarkAssetRepository(database).get(workspace.id)
    error = _watermark_prerequisite_error(
        module_enabled=module_enabled,
        has_asset=asset is not None,
    )
    if error is not None:
        await _show_media_settings(
            callback,
            database=database,
            workspace_product_service=workspace_product_service,
            workspace=workspace,
            page=page,
            alert=error,
        )
        return

    destinations = await WorkspaceOnboardingRepository(database).list_destinations(
        workspace.id
    )
    has_storage = any(item.destination_key == "watermarks" for item in destinations)
    if not has_storage and isinstance(callback.message, Message):
        await callback.message.answer(
            "ℹ️ Отдельное назначение «Watermark-копии» не подключено. После "
            "подтверждения готовый PNG будет отправлен в этот чат и сохранён как "
            "watermark-версия материала. Оригинал останется доступен владельцу."
        )

    await enqueue_archive_watermark(
        callback=callback,
        callback_data=callback_data,
        database=database,
        bot=bot,
        workspace_id=workspace.id,
        logo_asset=asset,
    )


async def handle_workspace_download_policy_without_storage_requirement(
    callback: CallbackQuery,
    callback_data: WorkspacePersonalArchiveCallback,
    database: Database,
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
    audience = _DOWNLOAD_AUDIENCE_ACTIONS.get(
        callback_data.action,
        settings.download_audience,
    )
    variant = _DOWNLOAD_VARIANT_ACTIONS.get(
        callback_data.action,
        settings.download_variant,
    )
    channels = await workspace_product_service.list_channels(workspace.id)
    channel_kinds = {item.kind for item in channels}
    watermark_asset = await WorkspaceWatermarkAssetRepository(database).get(workspace.id)
    error = _download_policy_error(
        audience=audience,
        variant=variant,
        channel_kinds=channel_kinds,
        has_watermark_asset=watermark_asset is not None,
    )
    if error is not None:
        await _show_media_settings(
            callback,
            database=database,
            workspace_product_service=workspace_product_service,
            workspace=workspace,
            page=page,
            alert=error,
        )
        return

    await workspace_product_service.set_download_policy(
        workspace_id=workspace.id,
        actor_user_id=callback.from_user.id,
        download_audience=audience,
        download_variant=variant,
        global_owner=False,
    )
    await _show_media_settings(
        callback,
        database=database,
        workspace_product_service=workspace_product_service,
        workspace=workspace,
        page=page,
        alert="Настройка скачивания сохранена.",
    )


async def handle_removed_standalone_quick_watermark(callback: CallbackQuery) -> None:
    await callback.answer(
        "Быстрый watermark запускается на карточке изображения в архиве. "
        "Так сохраняется связь с материалом и не создаются бесхозные задания Krita.",
        show_alert=True,
    )


router.callback_query.register(
    handle_workspace_archive_watermark_with_chat_fallback,
    WorkspacePersonalArchiveCallback.filter(F.action == "watermark"),
)
router.callback_query.register(
    handle_workspace_download_policy_without_storage_requirement,
    WorkspacePersonalArchiveCallback.filter(F.action.in_(_DOWNLOAD_POLICY_ACTIONS)),
)
router.callback_query.register(
    handle_removed_standalone_quick_watermark,
    WorkspaceWatermarkCallback.filter(F.action == "create"),
)


__all__ = (
    "_download_policy_error",
    "_watermark_prerequisite_error",
    "router",
)
