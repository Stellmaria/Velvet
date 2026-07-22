from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from velvet_bot.access import AccessPolicy
from velvet_bot.archive_catalog import (
    ArchivePage,
    ArchivedMedia,
    get_archive_page,
    toggle_archive_media_adult_requirement,
    toggle_archive_media_public_visibility,
)
from velvet_bot.database import Database
from velvet_bot.domains.public_archive.models import PUBLIC_ARCHIVE_REVIEWER_ID
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.image_preview import ImagePreviewError
from velvet_bot.protected_bot import ProtectedMediaBot
from velvet_bot.public_archive_display import (
    refresh_viewer_archive_caption,
    replace_viewer_archive_page,
)
from velvet_bot.public_catalog import (
    record_public_media_download,
    record_public_media_view,
    resolve_public_download_source,
    toggle_character_subscription,
    toggle_public_like,
)
from velvet_bot.public_media_lookup import get_character_media_offset
from velvet_bot.public_manager_access import has_public_manager_access
from velvet_bot.public_adult_access import has_adult_channel_access
from velvet_bot.public_preview_overrides import (
    replace_viewer_archive_page as replace_preview_archive_page,
    send_viewer_archive_page,
)
from velvet_bot.public_ui import PublicArchiveCallback
from velvet_bot.presentation.telegram.workspace_public_access import (
    has_workspace_adult_access,
    has_workspace_download_access,
)

router = Router(name=__name__)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _PreparedMedia:
    page: ArchivePage | None
    manager_access: bool
    member_access: bool
    workspace_id: int = DEFAULT_WORKSPACE_ID
    error: str | None = None


async def _member_access(
    bot: Bot,
    user_id: int,
    *,
    adult_channel_id: int,
    manager_access: bool,
) -> bool:
    """Compatibility helper for the system Velvet +18 channel."""
    if manager_access:
        return True
    return await has_adult_channel_access(
        bot,
        user_id,
        channel_id=adult_channel_id,
    )


def _record_target_view_before_display(*, action: str, user_id: int) -> bool:
    """Keep regular view metrics, but delay the dedicated Stell review marker."""
    return int(user_id) != PUBLIC_ARCHIVE_REVIEWER_ID


def _owner_review_media_after_navigation(
    callback_data: PublicArchiveCallback,
    *,
    user_id: int,
) -> int | None:
    """Return the card being left by Stell, never the newly opened target card."""
    if (
        int(user_id) == PUBLIC_ARCHIVE_REVIEWER_ID
        and callback_data.action == "show"
        and callback_data.media_id > 0
    ):
        return int(callback_data.media_id)
    return None


async def _prepare_media(
    *,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    user_id: int,
    user,
    access_policy: AccessPolicy,
    adult_channel_id: int,
    workspace_product_service: WorkspaceProductService | None = None,
) -> _PreparedMedia:
    """Load one viewer-specific archive page before acknowledging the callback."""
    workspace_id = (
        await workspace_product_service.public_workspace_id_for_user(user_id)
        if workspace_product_service is not None
        else DEFAULT_WORKSPACE_ID
    )
    manager_access = has_public_manager_access(user, access_policy)
    try:
        if workspace_product_service is None or workspace_id == DEFAULT_WORKSPACE_ID:
            member_access = await _member_access(
                bot,
                user_id,
                adult_channel_id=adult_channel_id,
                manager_access=manager_access,
            )
        else:
            member_access = await has_workspace_adult_access(
                bot=bot,
                user_id=user_id,
                workspace_id=workspace_id,
                manager_access=manager_access,
                default_adult_channel_id=adult_channel_id,
                workspace_product_service=workspace_product_service,
            )
        public_only = not manager_access
        offset = callback_data.offset
        if callback_data.action == "open" and callback_data.media_id:
            exact_offset = await get_character_media_offset(
                database,
                character_id=callback_data.character_id,
                media_id=callback_data.media_id,
                workspace_id=workspace_id,
                public_only=public_only,
                include_restricted=member_access,
                include_oversized=(workspace_id != DEFAULT_WORKSPACE_ID or member_access),
            )
            if exact_offset is None:
                return _PreparedMedia(
                    page=None,
                    manager_access=manager_access,
                    member_access=member_access,
                    workspace_id=workspace_id,
                    error="Материал уже удалён или скрыт.",
                )
            offset = exact_offset

        page = await get_archive_page(
            database,
            callback_data.character_id,
            offset,
            workspace_id=workspace_id,
            public_only=public_only,
            include_adult_restricted=member_access,
            include_oversized_images=(workspace_id != DEFAULT_WORKSPACE_ID or member_access),
        )
    except Exception:  # p2-approved-boundary: report-public-media-prepare-failure
        logger.exception("Failed to prepare public archive media page")
        return _PreparedMedia(
            page=None,
            manager_access=manager_access,
            member_access=False,
            workspace_id=workspace_id,
            error="Не удалось открыть материал.",
        )

    if page is None or page.media is None:
        return _PreparedMedia(
            page=None,
            manager_access=manager_access,
            member_access=member_access,
            workspace_id=workspace_id,
            error="Материал больше недоступен.",
        )
    if (
        callback_data.media_id
        and callback_data.action != "show"
        and callback_data.media_id != page.media.id
    ):
        return _PreparedMedia(
            page=None,
            manager_access=manager_access,
            member_access=member_access,
            workspace_id=workspace_id,
            error="Архив изменился. Откройте материал заново.",
        )
    if (
        page.media.requires_adult_channel
        and not manager_access
        and not member_access
    ):
        return _PreparedMedia(
            page=None,
            manager_access=manager_access,
            member_access=member_access,
            workspace_id=workspace_id,
            error="Этот материал доступен только участникам настроенного канала +18.",
        )
    return _PreparedMedia(
        page=page,
        manager_access=manager_access,
        member_access=member_access,
        workspace_id=workspace_id,
    )


async def _can_download(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    workspace_id: int,
    member_access: bool,
    download_access: bool,
) -> bool:
    source = await resolve_public_download_source(
        database,
        character_id=character_id,
        media_id=media_id,
        workspace_id=workspace_id,
        member_access=member_access,
        download_access=download_access,
    )
    return source is not None


async def _send_as_document(
    *,
    bot: Bot,
    media: ArchivedMedia,
    telegram_file_id: str,
    chat_id: int,
    variant: str,
) -> Message:
    caption = (
        "Оригинал из Velvet Archive"
        if variant == "original"
        else "Версия с watermark из Velvet Archive"
    )
    if media.media_type == "document":
        return await bot.send_document(
            chat_id=chat_id,
            document=telegram_file_id,
            caption=caption,
        )
    destination = io.BytesIO()
    await bot.download(telegram_file_id, destination=destination, seek=True)
    payload = destination.getvalue()
    if not payload:
        raise RuntimeError("Telegram вернул пустой файл.")
    return await bot.send_document(
        chat_id=chat_id,
        document=BufferedInputFile(payload, filename=media.display_file_name),
        caption=caption,
    )


@router.callback_query(
    PublicArchiveCallback.filter(F.action.in_({"open", "show"}))
)
async def handle_spoiler_aware_open(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    access_policy: AccessPolicy,
    adult_channel_id: int,
    workspace_product_service: WorkspaceProductService | None = None,
) -> None:
    prepared = await _prepare_media(
        callback_data=callback_data,
        database=database,
        bot=bot,
        user_id=callback.from_user.id,
        user=callback.from_user,
        access_policy=access_policy,
        adult_channel_id=adult_channel_id,
        workspace_product_service=workspace_product_service,
    )
    if prepared.error or prepared.page is None or prepared.page.media is None:
        await callback.answer(
            prepared.error or "Материал больше недоступен.",
            show_alert=True,
        )
        return
    if callback_data.action == "open" and not isinstance(callback.message, Message):
        await callback.answer("Не удалось определить чат.", show_alert=True)
        return

    await callback.answer()
    page = prepared.page
    owner_review_media_id = _owner_review_media_after_navigation(
        callback_data,
        user_id=callback.from_user.id,
    )
    if _record_target_view_before_display(
        action=callback_data.action,
        user_id=callback.from_user.id,
    ):
        try:
            await record_public_media_view(
                database,
                character_id=page.character.id,
                media_id=page.media.id,
                user_id=callback.from_user.id,
                workspace_id=prepared.workspace_id,
            )
        except Exception:  # p2-approved-boundary: preserve-public-open-on-metric-failure
            logger.exception("Failed to record public archive view")

    download_access = await has_workspace_download_access(
        bot=bot,
        user_id=callback.from_user.id,
        workspace_id=prepared.workspace_id,
        member_access=prepared.member_access,
        manager_access=prepared.manager_access,
        workspace_product_service=workspace_product_service,
    )
    can_download = await _can_download(
        database,
        character_id=page.character.id,
        media_id=page.media.id,
        workspace_id=prepared.workspace_id,
        member_access=prepared.member_access,
        download_access=download_access,
    )
    try:
        if callback_data.action == "open":
            assert isinstance(callback.message, Message)
            await send_viewer_archive_page(
                bot=bot,
                database=database,
                chat_id=callback.message.chat.id,
                page=page,
                viewer_user_id=callback.from_user.id,
                manager_access=prepared.manager_access,
                member_access=prepared.member_access,
                can_download=can_download,
                menu_page=callback_data.page,
                category=callback_data.category,
                universe=callback_data.universe,
                story_id=callback_data.story_id,
            )
        else:
            await replace_preview_archive_page(
                callback=callback,
                bot=bot,
                database=database,
                page=page,
                viewer_user_id=callback.from_user.id,
                manager_access=prepared.manager_access,
                member_access=prepared.member_access,
                can_download=can_download,
                menu_page=callback_data.page,
                category=callback_data.category,
                universe=callback_data.universe,
                story_id=callback_data.story_id,
            )
    except ImagePreviewError as error:
        if isinstance(callback.message, Message):
            await callback.message.answer(str(error))
        else:
            logger.info("Public image preview unavailable: %s", error)
        return

    if owner_review_media_id is not None:
        try:
            await record_public_media_view(
                database,
                character_id=page.character.id,
                media_id=owner_review_media_id,
                user_id=callback.from_user.id,
                workspace_id=prepared.workspace_id,
            )
        except Exception:  # p2-approved-boundary: preserve-navigation-on-owner-review-failure
            logger.exception("Failed to record Stell public archive review")


async def _apply_engagement(
    *,
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    access_policy: AccessPolicy,
    adult_channel_id: int,
    workspace_product_service: WorkspaceProductService | None = None,
) -> tuple[str, bool]:
    prepared = await _prepare_media(
        callback_data=callback_data,
        database=database,
        bot=bot,
        user_id=callback.from_user.id,
        user=callback.from_user,
        access_policy=access_policy,
        adult_channel_id=adult_channel_id,
        workspace_product_service=workspace_product_service,
    )
    if prepared.error or prepared.page is None or prepared.page.media is None:
        return prepared.error or "Материал больше недоступен.", True
    page = prepared.page

    try:
        if callback_data.action == "like":
            liked, _ = await toggle_public_like(
                database,
                character_id=page.character.id,
                media_id=page.media.id,
                user_id=callback.from_user.id,
                workspace_id=prepared.workspace_id,
            )
            alert = "Отметка поставлена." if liked else "Отметка снята."
        else:
            subscribed = await toggle_character_subscription(
                database,
                character_id=page.character.id,
                user_id=callback.from_user.id,
                workspace_id=prepared.workspace_id,
            )
            alert = "Подписка включена." if subscribed else "Подписка отключена."
    except Exception:  # p2-approved-boundary: report-public-engagement-write-failure
        logger.exception("Failed to update public archive engagement")
        return "Не удалось сохранить изменение.", True

    download_access = await has_workspace_download_access(
        bot=bot,
        user_id=callback.from_user.id,
        workspace_id=prepared.workspace_id,
        member_access=prepared.member_access,
        manager_access=prepared.manager_access,
        workspace_product_service=workspace_product_service,
    )
    can_download = await _can_download(
        database,
        character_id=page.character.id,
        media_id=page.media.id,
        workspace_id=prepared.workspace_id,
        member_access=prepared.member_access,
        download_access=download_access,
    )
    try:
        await refresh_viewer_archive_caption(
            callback=callback,
            database=database,
            page=page,
            viewer_user_id=callback.from_user.id,
            manager_access=prepared.manager_access,
            can_download=can_download,
            menu_page=callback_data.page,
            category=callback_data.category,
            universe=callback_data.universe,
            story_id=callback_data.story_id,
        )
    except Exception:  # p2-approved-boundary: preserve-engagement-on-ui-refresh-failure
        logger.exception("Failed to refresh public archive engagement card")
        return f"{alert} Карточку не удалось обновить.", True
    return alert, False


@router.callback_query(
    PublicArchiveCallback.filter(F.action.in_({"like", "sub"}))
)
async def handle_like_and_subscription(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    access_policy: AccessPolicy,
    adult_channel_id: int,
    workspace_product_service: WorkspaceProductService | None = None,
) -> None:
    message, show_alert = await _apply_engagement(
        callback=callback,
        callback_data=callback_data,
        database=database,
        bot=bot,
        access_policy=access_policy,
        adult_channel_id=adult_channel_id,
        workspace_product_service=workspace_product_service,
    )
    await callback.answer(message, show_alert=show_alert)


async def handle_public_download(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    access_policy: AccessPolicy,
    adult_channel_id: int,
    workspace_product_service: WorkspaceProductService | None = None,
) -> None:
    prepared = await _prepare_media(
        callback_data=callback_data,
        database=database,
        bot=bot,
        user_id=callback.from_user.id,
        user=callback.from_user,
        access_policy=access_policy,
        adult_channel_id=adult_channel_id,
        workspace_product_service=workspace_product_service,
    )
    if prepared.error or prepared.page is None or prepared.page.media is None:
        await callback.answer(
            prepared.error or "Материал больше недоступен.",
            show_alert=True,
        )
        return
    page = prepared.page

    download_access = await has_workspace_download_access(
        bot=bot,
        user_id=callback.from_user.id,
        workspace_id=prepared.workspace_id,
        member_access=prepared.member_access,
        manager_access=prepared.manager_access,
        workspace_product_service=workspace_product_service,
    )
    source = await resolve_public_download_source(
        database,
        character_id=page.character.id,
        media_id=page.media.id,
        member_access=prepared.member_access,
        download_access=download_access,
        workspace_id=prepared.workspace_id,
    )
    if source is None:
        mode = "watermark"
        if (
            workspace_product_service is not None
            and prepared.workspace_id != DEFAULT_WORKSPACE_ID
        ):
            mode = (
                await workspace_product_service.get_settings(
                    prepared.workspace_id
                )
            ).downloads_mode
        denied = {
            "disabled": "Владелец архива запретил скачивание.",
            "subscription": (
                "Скачивание доступно после подписки на настроенный канал владельца."
            ),
            "watermark": "Скачивание откроется после одобрения watermark-копии.",
            "original": "Файл временно недоступен для скачивания.",
        }.get(mode, "Файл недоступен для скачивания.")
        await callback.answer(
            denied,
            show_alert=True,
        )
        return
    try:
        if isinstance(bot, ProtectedMediaBot):
            bot.allow_unprotected_private_user(callback.from_user.id)
        await _send_as_document(
            bot=bot,
            media=page.media,
            telegram_file_id=source.telegram_file_id,
            chat_id=callback.from_user.id,
            variant=source.variant,
        )
        await record_public_media_download(
            database,
            character_id=page.character.id,
            media_id=page.media.id,
            user_id=callback.from_user.id,
            variant=source.variant,
            workspace_id=prepared.workspace_id,
        )
    except Exception:  # p2-approved-boundary: report-public-download-failure
        logger.exception("Failed to send public archive download")
        await callback.answer("Не удалось отправить файл.", show_alert=True)
        return
    await callback.answer("Файл отправлен в личный чат.")


async def handle_manager_access_flags(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    access_policy: AccessPolicy,
    workspace_product_service: WorkspaceProductService | None = None,
) -> None:
    workspace_id = (
        await workspace_product_service.public_workspace_id_for_user(
            callback.from_user.id
        )
        if workspace_product_service is not None
        else DEFAULT_WORKSPACE_ID
    )
    if not has_public_manager_access(callback.from_user, access_policy):
        await callback.answer("Управление архивом для вас закрыто.", show_alert=True)
        return
    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
        workspace_id=workspace_id,
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

    if callback_data.action == "ppub":
        enabled = await toggle_archive_media_public_visibility(
            database,
            character_id=page.character.id,
            media_id=page.media.id,
            workspace_id=workspace_id,
        )
        alert = (
            "Материал возвращён в публичный архив."
            if enabled
            else "Материал скрыт из публичного архива."
        )
    else:
        enabled = await toggle_archive_media_adult_requirement(
            database,
            character_id=page.character.id,
            media_id=page.media.id,
            workspace_id=workspace_id,
        )
        alert = (
            "Для материала включена проверка участия в закрытом канале."
            if enabled
            else "Проверка участия в закрытом канале отключена."
        )

    updated_page = await get_archive_page(
        database,
        page.character.id,
        page.offset,
        workspace_id=workspace_id,
    )
    if updated_page is None or updated_page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return
    await replace_viewer_archive_page(
        callback=callback,
        bot=bot,
        database=database,
        page=updated_page,
        viewer_user_id=callback.from_user.id,
        manager_access=True,
        can_download=True,
    )
    await callback.answer(alert, show_alert=True)


router.callback_query.register(
    handle_public_download,
    PublicArchiveCallback.filter(F.action == "download"),
)
router.callback_query.register(
    handle_manager_access_flags,
    PublicArchiveCallback.filter(F.action.in_({"ppub", "p18"})),
)
