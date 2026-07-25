from __future__ import annotations

from dataclasses import dataclass, replace

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.archive_ui import build_input_media, format_archive_caption
from velvet_bot.database import Database
from velvet_bot.domains.archive.models import ArchivePage
from velvet_bot.domains.public_archive.models import PublicMediaState
from velvet_bot.domains.workspaces.media_preferences import (
    WorkspaceMediaPreferenceRepository,
)
from velvet_bot.domains.workspaces.onboarding import WorkspaceOnboardingRepository
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.watermark_assets import (
    WorkspaceWatermarkAssetRepository,
)
from velvet_bot.public_catalog import get_public_media_state
from velvet_bot.presentation.telegram.workspace_personal_archive_contract import (
    workspace_personal_archive_callback,
)


@dataclass(frozen=True, slots=True)
class WorkspaceArchiveCardContext:
    public_state: PublicMediaState | None
    public_enabled: bool
    has_watermark_asset: bool
    personal_like: bool


async def load_workspace_archive_card_context(
    database: Database,
    *,
    workspace_product_service: WorkspaceProductService,
    workspace_id: int,
    user_id: int,
    page: ArchivePage,
    owner_access: bool,
) -> WorkspaceArchiveCardContext:
    if not owner_access or page.media is None:
        return WorkspaceArchiveCardContext(
            public_state=None,
            public_enabled=False,
            has_watermark_asset=False,
            personal_like=False,
        )

    state = await get_public_media_state(
        database,
        character_id=page.character.id,
        media_id=page.media.id,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    settings = await workspace_product_service.get_settings(workspace_id)
    personal_like = not settings.public_archive_enabled or not page.media.is_public
    if personal_like:
        favorite = await WorkspaceMediaPreferenceRepository(database).is_favorite(
            workspace_id=workspace_id,
            character_id=page.character.id,
            media_id=page.media.id,
            user_id=user_id,
        )
        state = replace(state, liked_by_user=favorite, like_count=0)

    asset = await WorkspaceWatermarkAssetRepository(database).get(workspace_id)
    destinations = await WorkspaceOnboardingRepository(database).list_destinations(
        workspace_id
    )
    watermark_ready = asset is not None and any(
        item.destination_key == "watermarks" for item in destinations
    )
    return WorkspaceArchiveCardContext(
        public_state=state,
        public_enabled=settings.public_archive_enabled,
        has_watermark_asset=watermark_ready,
        personal_like=personal_like,
    )


def build_workspace_archive_navigation(
    page: ArchivePage,
    *,
    workspace_id: int,
    owner_access: bool = False,
    public_state: PublicMediaState | None = None,
    public_enabled: bool = False,
    has_watermark_asset: bool = False,
    personal_like: bool = False,
) -> InlineKeyboardMarkup:
    if page.media is None:
        return InlineKeyboardMarkup(inline_keyboard=[])

    media_id = page.media.id
    common = {
        "workspace_id": workspace_id,
        "character_id": page.character.id,
        "offset": page.offset,
        "media_id": media_id,
    }
    counter = InlineKeyboardButton(
        text=f"{page.offset + 1} / {page.total}",
        callback_data=workspace_personal_archive_callback("noop", **common),
    )
    if page.total > 1:
        rows: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=workspace_personal_archive_callback(
                        "show",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=(page.offset - 1) % page.total,
                        media_id=media_id,
                    ),
                ),
                counter,
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=workspace_personal_archive_callback(
                        "show",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=(page.offset + 1) % page.total,
                        media_id=media_id,
                    ),
                ),
            ]
        ]
    else:
        rows = [[counter]]

    if owner_access and public_state is not None:
        if personal_like:
            like_label = (
                "❤️ Личная отметка"
                if public_state.liked_by_user
                else "🤍 Личная отметка"
            )
        else:
            like_label = (
                ("❤️" if public_state.liked_by_user else "🤍")
                + f" {public_state.like_count}"
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text=like_label,
                    callback_data=workspace_personal_archive_callback("like", **common),
                ),
                InlineKeyboardButton(
                    text=(
                        "🔕 Отписаться"
                        if public_state.subscribed
                        else "🔔 Подписаться"
                    ),
                    callback_data=workspace_personal_archive_callback("sub", **common),
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="❓ Что делают кнопки",
                    callback_data=workspace_personal_archive_callback(
                        "mediahelp", **common
                    ),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="📥 Скачать оригинал",
                    callback_data=workspace_personal_archive_callback(
                        "download", **common
                    ),
                ),
                InlineKeyboardButton(
                    text=(
                        "⚡ Быстрый watermark"
                        if has_watermark_asset
                        else "⚙️ Настроить watermark"
                    ),
                    callback_data=workspace_personal_archive_callback(
                        "watermark", **common
                    ),
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🛠 Отправить на доработку",
                    callback_data=workspace_personal_archive_callback("rework", **common),
                )
            ]
        )
        visibility_row: list[InlineKeyboardButton] = []
        if public_enabled:
            visibility_row.append(
                InlineKeyboardButton(
                    text=(
                        "👁 Вернуть в публичный"
                        if not page.media.is_public
                        else "🙈 Скрыть из публичного"
                    ),
                    callback_data=workspace_personal_archive_callback(
                        "public", **common
                    ),
                )
            )
        visibility_row.append(
            InlineKeyboardButton(
                text=(
                    "🔞 Снять +18"
                    if page.media.requires_adult_channel
                    else "🔞 Пометить +18"
                ),
                callback_data=workspace_personal_archive_callback("adult", **common),
            )
        )
        rows.append(visibility_row)
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        "🌫 Убрать блюр"
                        if page.media.is_spoiler
                        else "🌫 Включить блюр"
                    ),
                    callback_data=workspace_personal_archive_callback("blur", **common),
                ),
                InlineKeyboardButton(
                    text="⚙️ Доступ и скачивание",
                    callback_data=workspace_personal_archive_callback(
                        "settings", **common
                    ),
                ),
            ]
        )

    final_row: list[InlineKeyboardButton] = []
    if page.character.archive_topic_url:
        final_row.append(
            InlineKeyboardButton(
                text="📂 Ветка",
                url=page.character.archive_topic_url,
            )
        )
    if owner_access:
        final_row.append(
            InlineKeyboardButton(
                text="🗑 Удалить",
                callback_data=workspace_personal_archive_callback("delete", **common),
            )
        )
    final_row.append(
        InlineKeyboardButton(
            text="✖ Закрыть",
            callback_data=workspace_personal_archive_callback("close", **common),
        )
    )
    rows.append(final_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_workspace_archive_caption(page: ArchivePage) -> str:
    caption = format_archive_caption(page)
    if (
        page.media is not None
        and page.media.is_image_document
        and page.media.file_size is not None
        and page.media.file_size > 20 * 1024 * 1024
    ):
        caption += (
            "\n\n⚠️ Файл больше 20 МБ. Cloud Bot API не всегда может сделать "
            "из него превью; владелец может получить оригинал кнопкой «Скачать»."
        )
    return caption


async def send_workspace_archive_page(
    bot: Bot,
    *,
    database: Database,
    workspace_product_service: WorkspaceProductService,
    chat_id: int,
    user_id: int,
    workspace_id: int,
    page: ArchivePage,
    owner_access: bool,
) -> Message:
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")

    context = await load_workspace_archive_card_context(
        database,
        workspace_product_service=workspace_product_service,
        workspace_id=workspace_id,
        user_id=user_id,
        page=page,
        owner_access=owner_access,
    )
    caption = format_workspace_archive_caption(page)
    keyboard = build_workspace_archive_navigation(
        page,
        workspace_id=workspace_id,
        owner_access=owner_access,
        public_state=context.public_state,
        public_enabled=context.public_enabled,
        has_watermark_asset=context.has_watermark_asset,
        personal_like=context.personal_like,
    )
    if page.media.media_type == "photo":
        return await bot.send_photo(
            chat_id=chat_id,
            photo=page.media.telegram_file_id,
            caption=caption,
            reply_markup=keyboard,
            protect_content=True,
        )
    if page.media.media_type == "video":
        return await bot.send_video(
            chat_id=chat_id,
            video=page.media.telegram_file_id,
            caption=caption,
            reply_markup=keyboard,
            protect_content=True,
        )
    if page.media.media_type == "animation":
        return await bot.send_animation(
            chat_id=chat_id,
            animation=page.media.telegram_file_id,
            caption=caption,
            reply_markup=keyboard,
            protect_content=True,
        )
    return await bot.send_document(
        chat_id=chat_id,
        document=page.media.telegram_file_id,
        caption=caption,
        reply_markup=keyboard,
        protect_content=True,
    )


async def replace_workspace_archive_page(
    callback: CallbackQuery,
    bot: Bot,
    *,
    database: Database,
    workspace_product_service: WorkspaceProductService,
    user_id: int,
    workspace_id: int,
    page: ArchivePage,
    owner_access: bool,
) -> None:
    if page.media is None:
        await callback.answer("Архив персонажа пуст.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer(
            "Сообщение архива больше недоступно.",
            show_alert=True,
        )
        return

    context = await load_workspace_archive_card_context(
        database,
        workspace_product_service=workspace_product_service,
        workspace_id=workspace_id,
        user_id=user_id,
        page=page,
        owner_access=owner_access,
    )
    keyboard = build_workspace_archive_navigation(
        page,
        workspace_id=workspace_id,
        owner_access=owner_access,
        public_state=context.public_state,
        public_enabled=context.public_enabled,
        has_watermark_asset=context.has_watermark_asset,
        personal_like=context.personal_like,
    )
    try:
        await callback.message.edit_media(
            media=build_input_media(page.media, format_workspace_archive_caption(page)),
            reply_markup=keyboard,
        )
    except TelegramBadRequest:
        try:
            await send_workspace_archive_page(
                bot,
                database=database,
                workspace_product_service=workspace_product_service,
                chat_id=callback.message.chat.id,
                user_id=user_id,
                workspace_id=workspace_id,
                page=page,
                owner_access=owner_access,
            )
            await callback.message.delete()
        except (TelegramAPIError, TelegramBadRequest):
            await callback.answer(
                "Telegram больше не может открыть этот файл.",
                show_alert=True,
            )
            return
    await callback.answer()


__all__ = (
    "WorkspaceArchiveCardContext",
    "build_workspace_archive_navigation",
    "format_workspace_archive_caption",
    "load_workspace_archive_card_context",
    "replace_workspace_archive_page",
    "send_workspace_archive_page",
)
