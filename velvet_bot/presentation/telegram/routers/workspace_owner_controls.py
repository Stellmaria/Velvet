from __future__ import annotations

import io
from dataclasses import replace
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.archive_catalog import (
    delete_archive_item,
    get_archive_page,
    toggle_archive_media_adult_requirement,
    toggle_archive_media_public_visibility,
    toggle_archive_media_spoiler,
)
from velvet_bot.archive_ui import build_input_media, format_archive_caption, format_delete_caption
from velvet_bot.character_resolution import load_character_by_id
from velvet_bot.database import Database
from velvet_bot.domains.media_rework.manual import request_manual_rework
from velvet_bot.domains.media_rework.repository import MediaReworkRepository
from velvet_bot.domains.workspaces.models import (
    Workspace,
    WorkspaceRole,
)
from velvet_bot.domains.workspaces.media_preferences import (
    WorkspaceMediaPreferenceRepository,
)
from velvet_bot.domains.workspaces.onboarding import WorkspaceOnboardingRepository
from velvet_bot.domains.workspaces.product_models import (
    GLOBAL_WORKSPACE_CREATOR_ID,
    WorkspaceModuleKey,
)
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.domains.workspaces.watermark_assets import (
    WorkspaceWatermarkAssetRepository,
)
from velvet_bot.protected_bot import ProtectedMediaBot
from velvet_bot.public_catalog import (
    get_public_media_state,
    toggle_character_subscription,
    toggle_public_like,
)
from velvet_bot.presentation.telegram.routers.references.albums import (
    send_reference_collection,
)
from velvet_bot.presentation.telegram.routers.public_archive.watermark_actions import (
    enqueue_archive_watermark,
)
from velvet_bot.presentation.telegram.routers.workspace_guided_ui import (
    guided_workspace_callback,
)
from velvet_bot.presentation.telegram.workspace_command_menu import (
    install_workspace_scoped_commands,
)
from velvet_bot.presentation.telegram.routers.workspace_onboarding import (
    WorkspaceOnboardingCallback,
)
from velvet_bot.reference_catalog import list_character_references
from velvet_bot.workspace_ui import (
    WorkspaceCallback,
    build_start_keyboard,
    build_workspace_member_home_keyboard,
    build_workspace_home_keyboard,
    build_workspace_selector_keyboard,
    format_workspace_home,
    workspace_callback,
)

router = Router(name=__name__)
_ROLE_LABELS = {
    "viewer": "наблюдатель",
    "reviewer": "проверяющий",
    "editor": "редактор",
    "admin": "администратор",
    "owner": "владелец",
}
_DOWNLOAD_AUDIENCE_LABELS = {
    "disabled": "🚫 запрещено",
    "all": "🌐 всем читателям архива",
    "subscribers": "🔐 подписчикам выбранного канала",
}
_DOWNLOAD_VARIANT_LABELS = {
    "watermark": "🖼 одобренная watermark-копия",
    "original": "📦 сохранённый оригинал",
}
_DOWNLOAD_AUDIENCE_ACTIONS = {
    "dlaudnone": "disabled",
    "dlaudall": "all",
    "dlaudsub": "subscribers",
}
_DOWNLOAD_VARIANT_ACTIONS = {
    "dlvarwm": "watermark",
    "dlvarorig": "original",
}


class WorkspacePersonalArchiveCallback(CallbackData, prefix="wpa"):
    action: str
    workspace_id: int
    character_id: int = 0
    offset: int = 0
    media_id: int = 0


class WorkspaceReferenceEntryCallback(CallbackData, prefix="wref"):
    action: str
    workspace_id: int
    character_id: int = 0


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


def _archive_callback(
    action: str,
    *,
    workspace_id: int,
    character_id: int = 0,
    offset: int = 0,
    media_id: int = 0,
) -> str:
    return WorkspacePersonalArchiveCallback(
        action=action,
        workspace_id=int(workspace_id),
        character_id=int(character_id),
        offset=max(0, int(offset)),
        media_id=int(media_id),
    ).pack()


def _reference_callback(
    action: str,
    *,
    workspace_id: int,
    character_id: int = 0,
) -> str:
    return WorkspaceReferenceEntryCallback(
        action=action,
        workspace_id=int(workspace_id),
        character_id=int(character_id),
    ).pack()


async def _resolve_workspace(
    *,
    workspace_service: WorkspaceService,
    user_id: int,
    workspace_id: int = 0,
    minimum_role: WorkspaceRole = "viewer",
) -> Workspace:
    global_owner = _is_global_owner(user_id)
    if workspace_id:
        workspace = await workspace_service.set_active_workspace(
            workspace_id=int(workspace_id),
            user_id=int(user_id),
            global_owner=global_owner,
        )
    else:
        workspace = await workspace_service.resolve_active_workspace(
            user_id=int(user_id),
            global_owner=global_owner,
        )
    await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=int(user_id),
        minimum_role=minimum_role,
        global_owner=global_owner,
    )
    return workspace


async def _require_personal_module(
    *,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
    user_id: int,
    workspace_id: int,
    module_key: WorkspaceModuleKey,
    minimum_role: WorkspaceRole = "viewer",
) -> Workspace:
    workspace = await _resolve_workspace(
        workspace_service=workspace_service,
        user_id=user_id,
        workspace_id=workspace_id,
        minimum_role=minimum_role,
    )
    if workspace.is_system:
        raise WorkspaceAccessError(
            "Системный Velvet использует основной интерфейс Стэл, а не личный модуль."
        )
    if not await workspace_product_service.is_module_enabled(
        workspace_id=workspace.id,
        module_key=module_key,
    ):
        raise WorkspaceAccessError("Модуль выключен или не разрешён Стэл.")
    return workspace


def _workspace_home_keyboard(
    workspace: Workspace,
    *,
    public_enabled: bool,
    modules,
    show_button_hints: bool = True,
) -> InlineKeyboardMarkup:
    base = build_workspace_home_keyboard(
        workspace,
        public_enabled=public_enabled,
        modules=modules,
    )
    rows = [list(row) for row in base.inline_keyboard]
    if not workspace.is_system:
        close_row = rows.pop() if rows else []
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="🧭 Настроить архив",
                        callback_data=WorkspaceOnboardingCallback(
                            action="intro",
                            workspace_id=workspace.id,
                            key="",
                        ).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🗑 Удалить пространство",
                        callback_data=workspace_callback(
                            "delete",
                            workspace_id=workspace.id,
                        ),
                    )
                ],
            ]
        )
        if close_row:
            rows.append(close_row)

    filtered_rows: list[list[InlineKeyboardButton]] = []
    for row in rows:
        filtered = [
            button
            for button in row
            if not (
                button.text in {"🙈 Скрыть все подсказки", "ℹ️ Показать подсказки"}
                or (not show_button_hints and button.text == "ℹ️")
            )
        ]
        if filtered:
            filtered_rows.append(filtered)

    toggle = InlineKeyboardButton(
        text=(
            "🙈 Скрыть все подсказки"
            if show_button_hints
            else "ℹ️ Показать подсказки"
        ),
        callback_data=workspace_callback(
            "helptoggle",
            workspace_id=workspace.id,
        ),
    )
    insert_at = len(filtered_rows)
    if filtered_rows and any(
        button.text == "✖ Закрыть" for button in filtered_rows[-1]
    ):
        insert_at -= 1
    filtered_rows.insert(max(0, insert_at), [toggle])
    return InlineKeyboardMarkup(inline_keyboard=filtered_rows)


async def _render_home(
    callback: CallbackQuery,
    *,
    workspace: Workspace,
    user_id: int,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    membership = await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=user_id,
        minimum_role="owner",
        global_owner=_is_global_owner(user_id),
    )
    modules = await workspace_product_service.list_modules(
        workspace_id=workspace.id,
        actor_user_id=user_id,
        global_owner=_is_global_owner(user_id),
    )
    try:
        settings = await workspace_product_service.get_settings(workspace.id)
        show_button_hints = await workspace_product_service.get_button_hints(
            workspace.id
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return

    allowed_modules = sum(item.is_allowed for item in modules)
    enabled_modules = sum(item.is_allowed and item.is_enabled for item in modules)
    role_label = "владелец" if membership.role == "owner" else membership.role
    text = (
        format_workspace_home(
            workspace,
            public_enabled=settings.public_archive_enabled,
            enabled_modules=enabled_modules,
            allowed_modules=allowed_modules,
        )
        + f"\nРоль: <b>{escape(role_label)}</b>"
    )
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            text,
            reply_markup=_workspace_home_keyboard(
                workspace,
                public_enabled=settings.public_archive_enabled,
                modules=modules,
                show_button_hints=show_button_hints,
            ),
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            await callback.message.answer(
                text,
                reply_markup=_workspace_home_keyboard(
                    workspace,
                    public_enabled=settings.public_archive_enabled,
                    modules=modules,
                    show_button_hints=show_button_hints,
                ),
            )
    await callback.answer()
    await install_workspace_scoped_commands(callback, role=membership.role)


async def _render_member_home(
    callback: CallbackQuery,
    *,
    workspace: Workspace,
    user_id: int,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    membership = await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=user_id,
        minimum_role="viewer",
        global_owner=_is_global_owner(user_id),
    )
    modules = await workspace_product_service.list_modules_for_member(
        workspace_id=workspace.id,
        actor_user_id=user_id,
        global_owner=_is_global_owner(user_id),
    )
    try:
        settings = await workspace_product_service.get_settings(workspace.id)
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
    allowed_modules = sum(item.is_allowed for item in modules)
    enabled_modules = sum(item.is_allowed and item.is_enabled for item in modules)
    role_label = _ROLE_LABELS.get(membership.role, membership.role)
    text = (
        format_workspace_home(
            workspace,
            public_enabled=settings.public_archive_enabled,
            enabled_modules=enabled_modules,
            allowed_modules=allowed_modules,
        )
        + f"\nРоль: <b>{escape(role_label)}</b>\n\n"
        "Показаны только разделы, доступные по вашей роли. Настройка модулей, "
        "публичность и удаление остаются у владельца."
    )
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    keyboard = build_workspace_member_home_keyboard(
        workspace,
        role=membership.role,
        modules=modules,
    )
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()
    await install_workspace_scoped_commands(callback, role=membership.role)


async def _render_workspace_selector(
    callback: CallbackQuery,
    *,
    user_id: int,
    state: FSMContext,
    workspace_product_service: WorkspaceProductService,
) -> None:
    await state.clear()
    start_state = await workspace_product_service.get_start_state(user_id)
    if not start_state.owned_workspaces and not start_state.member_workspaces:
        await callback.answer("У вас пока нет личных или командных пространств.", show_alert=True)
        return
    text = (
        "<b>🗂 Пространства</b>\n\n"
        "⚙️ — ваш личный архив: доступны настройки и управление.\n"
        "🤝 — пространство команды: показаны только разделы, разрешённые вашей ролью.\n\n"
        "Выберите пространство, с которым хотите работать сейчас."
    )
    keyboard = build_workspace_selector_keyboard(
        owned_workspaces=start_state.owned_workspaces,
        member_workspaces=start_state.member_workspaces,
    )
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


async def _load_archive_characters(
    database: Database,
    *,
    workspace_id: int,
):
    async with database.acquire() as connection:
        return await connection.fetch(
            """
            SELECT
                character.id,
                character.name,
                character.archive_topic_url,
                COUNT(link.media_id) AS media_count
            FROM characters AS character
            LEFT JOIN character_media AS link
              ON link.character_id = character.id
            WHERE character.workspace_id = $1::BIGINT
            GROUP BY character.id
            ORDER BY character.normalized_name, character.id
            LIMIT 60
            """,
            int(workspace_id),
        )


def _archive_dashboard_keyboard(
    *,
    workspace_id: int,
    rows,
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    for row in rows:
        media_count = int(row["media_count"] or 0)
        if media_count:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"🖼 {row['name']} · {media_count}"[:60],
                        callback_data=_archive_callback(
                            "open",
                            workspace_id=workspace_id,
                            character_id=int(row["id"]),
                        ),
                    )
                ]
            )
        elif row["archive_topic_url"]:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"📂 {row['name']} · пусто"[:60],
                        url=str(row["archive_topic_url"]),
                    )
                ]
            )
        else:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"➖ {row['name']} · пусто"[:60],
                        callback_data=_archive_callback(
                            "empty",
                            workspace_id=workspace_id,
                            character_id=int(row["id"]),
                        ),
                    )
                ]
            )
    buttons.extend(
        [
            [
                InlineKeyboardButton(
                    text="➕ Как сохранить материал",
                    callback_data=_archive_callback(
                        "help",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Моё пространство",
                    callback_data=workspace_callback("home", workspace_id=workspace_id),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _render_archive_dashboard(
    callback: CallbackQuery,
    *,
    database: Database,
    workspace: Workspace,
) -> None:
    rows = await _load_archive_characters(database, workspace_id=workspace.id)
    text = (
        f"<b>🖼 Архив · {escape(workspace.name)}</b>\n\n"
        f"Персонажей: <b>{len(rows)}</b>\n\n"
        "Выберите персонажа, чтобы открыть сохранённые фото, видео и документы. "
        "Пустые архивы остаются видимыми, чтобы было понятно, куда ещё ничего не положили."
    )
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            text,
            reply_markup=_archive_dashboard_keyboard(
                workspace_id=workspace.id,
                rows=rows,
            ),
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            await callback.message.answer(
                text,
                reply_markup=_archive_dashboard_keyboard(
                    workspace_id=workspace.id,
                    rows=rows,
                ),
            )
    await callback.answer()


def _archive_navigation(
    page,
    *,
    workspace_id: int,
    owner_access: bool = False,
    public_state=None,
    public_enabled: bool = False,
    has_watermark_asset: bool = False,
    personal_like: bool = False,
) -> InlineKeyboardMarkup:
    if page.media is None:
        return InlineKeyboardMarkup(inline_keyboard=[])

    media_id = page.media.id
    counter = InlineKeyboardButton(
        text=f"{page.offset + 1} / {page.total}",
        callback_data=_archive_callback(
            "noop",
            workspace_id=workspace_id,
            character_id=page.character.id,
            offset=page.offset,
            media_id=media_id,
        ),
    )
    if page.total > 1:
        rows = [
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_archive_callback(
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
                    callback_data=_archive_callback(
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
                    callback_data=_archive_callback(
                        "like",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
                    ),
                ),
                InlineKeyboardButton(
                    text=(
                        "🔕 Отписаться"
                        if public_state.subscribed
                        else "🔔 Подписаться"
                    ),
                    callback_data=_archive_callback(
                        "sub",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
                    ),
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="❓ Что делают кнопки",
                    callback_data=_archive_callback(
                        "mediahelp",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
                    ),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="📥 Скачать оригинал",
                    callback_data=_archive_callback(
                        "download",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
                    ),
                ),
                InlineKeyboardButton(
                    text=(
                        "⚡ Быстрый watermark"
                        if has_watermark_asset
                        else "⚙️ Настроить watermark"
                    ),
                    callback_data=_archive_callback(
                        "watermark",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
                    ),
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🛠 Отправить на доработку",
                    callback_data=_archive_callback(
                        "rework",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
                    ),
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
                    callback_data=_archive_callback(
                        "public",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
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
                callback_data=_archive_callback(
                    "adult",
                    workspace_id=workspace_id,
                    character_id=page.character.id,
                    offset=page.offset,
                    media_id=media_id,
                ),
            )
        )
        rows.append(visibility_row)
        rows.append(
            [
                InlineKeyboardButton(
                    text=("🌫 Убрать блюр" if page.media.is_spoiler else "🌫 Включить блюр"),
                    callback_data=_archive_callback(
                        "blur",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="⚙️ Доступ и скачивание",
                    callback_data=_archive_callback(
                        "settings",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
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
                callback_data=_archive_callback(
                    "delete",
                    workspace_id=workspace_id,
                    character_id=page.character.id,
                    offset=page.offset,
                    media_id=media_id,
                ),
            )
        )
    final_row.extend(
        [
            InlineKeyboardButton(
                text="✖ Закрыть",
                callback_data=_archive_callback(
                    "close",
                    workspace_id=workspace_id,
                    character_id=page.character.id,
                    offset=page.offset,
                    media_id=media_id,
                ),
            ),
        ]
    )
    rows.append(final_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _archive_delete_keyboard(page, *, workspace_id: int) -> InlineKeyboardMarkup:
    media_id = page.media.id if page.media else 0
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=_archive_callback(
                        "deleteconfirm",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=_archive_callback(
                        "show",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=media_id,
                    ),
                ),
            ]
        ]
    )


async def _archive_ui_context(
    *,
    database: Database,
    workspace_product_service: WorkspaceProductService,
    workspace_id: int,
    user_id: int,
    page,
    owner_access: bool,
):
    if not owner_access or page.media is None:
        return None, False, False, False
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
    return state, settings.public_archive_enabled, watermark_ready, personal_like


def _workspace_archive_caption(page) -> str:
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


async def _send_archive_page(
    bot: Bot,
    *,
    database: Database,
    workspace_product_service: WorkspaceProductService,
    chat_id: int,
    user_id: int,
    workspace_id: int,
    page,
    owner_access: bool,
) -> Message:
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")
    public_state, public_enabled, has_watermark_asset, personal_like = await _archive_ui_context(
        database=database,
        workspace_product_service=workspace_product_service,
        workspace_id=workspace_id,
        user_id=user_id,
        page=page,
        owner_access=owner_access,
    )
    common = {
        "chat_id": chat_id,
        "caption": _workspace_archive_caption(page),
        "reply_markup": _archive_navigation(
            page,
            workspace_id=workspace_id,
            owner_access=owner_access,
            public_state=public_state,
            public_enabled=public_enabled,
            has_watermark_asset=has_watermark_asset,
            personal_like=personal_like,
        ),
        "protect_content": True,
    }
    if page.media.media_type == "photo":
        return await bot.send_photo(photo=page.media.telegram_file_id, **common)
    if page.media.media_type == "video":
        return await bot.send_video(video=page.media.telegram_file_id, **common)
    if page.media.media_type == "animation":
        return await bot.send_animation(animation=page.media.telegram_file_id, **common)
    return await bot.send_document(document=page.media.telegram_file_id, **common)


async def _replace_archive_page(
    callback: CallbackQuery,
    bot: Bot,
    *,
    database: Database,
    workspace_product_service: WorkspaceProductService,
    user_id: int,
    workspace_id: int,
    page,
    owner_access: bool,
) -> None:
    if page.media is None:
        await callback.answer("Архив персонажа пуст.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение архива больше недоступно.", show_alert=True)
        return
    public_state, public_enabled, has_watermark_asset, personal_like = await _archive_ui_context(
        database=database,
        workspace_product_service=workspace_product_service,
        workspace_id=workspace_id,
        user_id=user_id,
        page=page,
        owner_access=owner_access,
    )
    try:
        await callback.message.edit_media(
            media=build_input_media(page.media, _workspace_archive_caption(page)),
            reply_markup=_archive_navigation(
                page,
                workspace_id=workspace_id,
                owner_access=owner_access,
                public_state=public_state,
                public_enabled=public_enabled,
            has_watermark_asset=has_watermark_asset,
            personal_like=personal_like,
            ),
        )
    except TelegramBadRequest:
        try:
            await _send_archive_page(
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


async def _load_reference_characters(
    database: Database,
    *,
    workspace_id: int,
):
    async with database.acquire() as connection:
        return await connection.fetch(
            """
            SELECT
                character.id,
                character.name,
                COUNT(reference.id) AS reference_count
            FROM characters AS character
            LEFT JOIN character_references AS reference
              ON reference.workspace_id = character.workspace_id
             AND reference.character_id = character.id
            WHERE character.workspace_id = $1::BIGINT
            GROUP BY character.id
            ORDER BY character.normalized_name, character.id
            LIMIT 60
            """,
            int(workspace_id),
        )


def _reference_dashboard_keyboard(
    *,
    workspace_id: int,
    rows,
) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"🧬 {row['name']} · {int(row['reference_count'] or 0)}"[:60],
                callback_data=_reference_callback(
                    "open",
                    workspace_id=workspace_id,
                    character_id=int(row["id"]),
                ),
            )
        ]
        for row in rows
    ]
    buttons.extend(
        [
            [
                InlineKeyboardButton(
                    text="➕ Как добавить референс",
                    callback_data=_reference_callback(
                        "help",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Моё пространство",
                    callback_data=workspace_callback("home", workspace_id=workspace_id),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _render_reference_dashboard(
    callback: CallbackQuery,
    *,
    database: Database,
    workspace: Workspace,
) -> None:
    rows = await _load_reference_characters(database, workspace_id=workspace.id)
    text = (
        f"<b>🧬 Референсы · {escape(workspace.name)}</b>\n\n"
        f"Персонажей: <b>{len(rows)}</b>\n\n"
        "Выберите персонажа, чтобы открыть его личную библиотеку референсов."
    )
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            text,
            reply_markup=_reference_dashboard_keyboard(
                workspace_id=workspace.id,
                rows=rows,
            ),
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            await callback.message.answer(
                text,
                reply_markup=_reference_dashboard_keyboard(
                    workspace_id=workspace.id,
                    rows=rows,
                ),
            )
    await callback.answer()


def _workspace_delete_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Да, удалить безвозвратно",
                    callback_data=workspace_callback(
                        "deleteconfirm",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=workspace_callback(
                        "deletecancel",
                        workspace_id=workspace_id,
                    ),
                )
            ],
        ]
    )


async def _show_workspace_delete_confirmation(
    event: Message | CallbackQuery,
    *,
    workspace: Workspace,
) -> None:
    text = (
        f"<b>Удалить пространство «{escape(workspace.name)}»?</b>\n\n"
        "Будут удалены персонажи, материалы, референсы, категории, истории, "
        "назначения чатов, настройки и участники этого пространства.\n\n"
        "<b>Отменить это действие после подтверждения нельзя.</b>"
    )
    keyboard = _workspace_delete_keyboard(workspace.id)
    if isinstance(event, CallbackQuery):
        if not isinstance(event.message, Message):
            await event.answer("Меню больше недоступно.", show_alert=True)
            return
        try:
            await event.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                await event.message.answer(text, reply_markup=keyboard)
        await event.answer()
        return
    await event.answer(text, reply_markup=keyboard)


async def _delete_workspace_data(
    database: Database,
    *,
    workspace_id: int,
) -> int:
    async with database.acquire() as connection:
        async with connection.transaction():
            workspace = await connection.fetchrow(
                """
                SELECT id, is_system
                FROM workspaces
                WHERE id = $1::BIGINT
                FOR UPDATE
                """,
                int(workspace_id),
            )
            if workspace is None:
                raise ValueError("Пространство уже удалено.")
            if bool(workspace["is_system"]):
                raise ValueError("Системное пространство удалить нельзя.")
            character_count = int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM characters WHERE workspace_id = $1::BIGINT",
                    int(workspace_id),
                )
                or 0
            )
            await connection.execute(
                "DELETE FROM characters WHERE workspace_id = $1::BIGINT",
                int(workspace_id),
            )
            result = await connection.execute(
                """
                DELETE FROM workspaces
                WHERE id = $1::BIGINT
                  AND NOT is_system
                """,
                int(workspace_id),
            )
            if result == "DELETE 0":
                raise ValueError("Пространство уже удалено.")
    return character_count


async def _handle_workspace_owner_home(
    callback: CallbackQuery,
    *,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    await state.clear()
    try:
        workspace = await _resolve_workspace(
            workspace_service=workspace_service,
            user_id=callback.from_user.id,
            workspace_id=callback_data.workspace_id,
            minimum_role="viewer",
        )
        membership = await workspace_service.require_role(
            workspace_id=workspace.id,
            user_id=callback.from_user.id,
            minimum_role="viewer",
            global_owner=_is_global_owner(callback.from_user.id),
        )
        if membership.role == "owner":
            await _render_home(
                callback,
                workspace=workspace,
                user_id=callback.from_user.id,
                workspace_service=workspace_service,
                workspace_product_service=workspace_product_service,
            )
        else:
            await _render_member_home(
                callback,
                workspace=workspace,
                user_id=callback.from_user.id,
                workspace_service=workspace_service,
                workspace_product_service=workspace_product_service,
            )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)


@router.callback_query(WorkspaceCallback.filter(F.action == "home"))
async def handle_workspace_owner_home(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    await _handle_workspace_owner_home(
        callback,
        callback_data=callback_data,
        state=state,
        workspace_service=workspace_service,
        workspace_product_service=workspace_product_service,
    )


@router.callback_query(WorkspaceCallback.filter(F.action == "spaces"))
async def handle_workspace_selector(
    callback: CallbackQuery,
    state: FSMContext,
    workspace_product_service: WorkspaceProductService,
) -> None:
    await _render_workspace_selector(
        callback,
        user_id=callback.from_user.id,
        state=state,
        workspace_product_service=workspace_product_service,
    )


@router.callback_query(
    WorkspaceCallback.filter((F.action == "module") & (F.module_key == "archive"))
)
async def handle_workspace_archive_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    database: Database,
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
    await _render_archive_dashboard(callback, database=database, workspace=workspace)


@router.callback_query(
    WorkspaceCallback.filter((F.action == "module") & (F.module_key == "references"))
)
async def handle_workspace_reference_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace = await _require_personal_module(
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=callback_data.workspace_id,
            module_key="references",
            minimum_role="viewer",
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await _render_reference_dashboard(callback, database=database, workspace=workspace)


def _media_settings_keyboard(
    *,
    workspace_id: int,
    character_id: int,
    offset: int,
    media_id: int,
    download_audience: str,
    download_variant: str,
) -> InlineKeyboardMarkup:
    rows = []
    common = {
        "workspace_id": workspace_id,
        "character_id": character_id,
        "offset": offset,
        "media_id": media_id,
    }
    rows.append(
        [
            InlineKeyboardButton(
                text="Кто может скачивать",
                callback_data=_archive_callback("noop", **common),
            )
        ]
    )
    for action, audience, label in (
        ("dlaudnone", "disabled", "🚫 Никто"),
        ("dlaudall", "all", "🌐 Все читатели"),
        ("dlaudsub", "subscribers", "🔐 Подписчики канала"),
    ):
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅ " if download_audience == audience else "") + label,
                    callback_data=_archive_callback(
                        action,
                        workspace_id=workspace_id,
                        character_id=character_id,
                        offset=offset,
                        media_id=media_id,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="Какую версию выдавать",
                callback_data=_archive_callback("noop", **common),
            )
        ]
    )
    for action, variant, label in (
        ("dlvarwm", "watermark", "🖼 Только с watermark"),
        ("dlvarorig", "original", "📦 Оригинал"),
    ):
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅ " if download_variant == variant else "") + label,
                    callback_data=_archive_callback(
                        action,
                        workspace_id=workspace_id,
                        character_id=character_id,
                        offset=offset,
                        media_id=media_id,
                    ),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🔌 Каналы доступа",
                    callback_data=guided_workspace_callback(
                        "connections",
                        workspace_id=workspace_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="💧 Настроить watermark",
                    callback_data=workspace_callback(
                        "module",
                        workspace_id=workspace_id,
                        module_key="watermark",
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К материалу",
                    callback_data=_archive_callback(
                        "show",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        offset=offset,
                        media_id=media_id,
                    ),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_media_settings(
    callback: CallbackQuery,
    *,
    database: Database,
    workspace_product_service: WorkspaceProductService,
    workspace: Workspace,
    page,
    alert: str | None = None,
) -> None:
    settings = await workspace_product_service.get_settings(workspace.id)
    channels = await workspace_product_service.list_channels(workspace.id)
    channel_kinds = {item.kind for item in channels}
    destinations = await WorkspaceOnboardingRepository(database).list_destinations(
        workspace.id
    )
    destination_keys = {item.destination_key for item in destinations}
    watermark_asset = await WorkspaceWatermarkAssetRepository(database).get(workspace.id)
    text = (
        f"<b>⚙️ Доступ к медиа · {escape(workspace.name)}</b>\n\n"
        "Публичный архив: "
        f"<b>{'включён' if settings.public_archive_enabled else 'выключен'}</b>\n"
        "Кто может скачивать: "
        f"<b>{_DOWNLOAD_AUDIENCE_LABELS[settings.download_audience]}</b>\n"
        "Какую версию выдавать: "
        f"<b>{_DOWNLOAD_VARIANT_LABELS[settings.download_variant]}</b>\n"
        "Канал проверки скачивания: "
        f"<b>{'подключён' if 'download' in channel_kinds else 'не подключён'}</b>\n"
        f"Канал +18: <b>{'подключён' if 'adult' in channel_kinds else 'не подключён'}</b>\n"
        "Оригиналы: "
        f"<b>{'форум персонажей подключён' if 'characters' in destination_keys else 'форум персонажей не подключён'}</b>\n"
        "Watermark-копии: "
        f"<b>{'назначение подключено' if 'watermarks' in destination_keys else 'назначение не подключено'}</b>\n"
        f"Шаблон watermark: <b>{'настроен' if watermark_asset is not None else 'не настроен'}</b>\n\n"
        "По умолчанию карточки отправляются с защитой Telegram от пересылки и "
        "сохранения. Кнопка скачивания появляется у читателя только когда это "
        "разрешают оба параметра. Оригинал хранится в теме персонажа и не "
        "заменяется: подтверждённый watermark сохраняется отдельным Telegram-файлом "
        "в выбранном назначении.\n\n"
        "⚠️ Для изображений больше 20 МБ cloud Bot API может не построить превью. "
        "Владелец всё равно видит кнопку оригинала; читатель получает файл только "
        "когда политика скачивания это разрешает."
    )
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    keyboard = _media_settings_keyboard(
        workspace_id=workspace.id,
        character_id=page.character.id,
        offset=page.offset,
        media_id=page.media.id,
        download_audience=settings.download_audience,
        download_variant=settings.download_variant,
    )
    if callback.message.text:
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise
    else:
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer(alert)


async def _show_media_help(callback: CallbackQuery, *, workspace_id: int, page) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    text = (
        "<b>Справка по карточке персонажа</b>\n\n"
        "<b>Промт</b> — ссылка на исходный промт персонажа. Она нужна как "
        "творческий референс и для AI-проверок; изображения эта кнопка не загружает.\n\n"
        "<b>Сохранить / Загрузить медиа</b> — выбирает персонажа и включает "
        "пакетную загрузку. Можно прислать несколько фото, альбом, видео и "
        "документы подряд, затем нажать «Завершить загрузку».\n\n"
        "<b>+ Создать персонажа</b> — создаёт карточку и архивную ветку; медиа "
        "добавляются после создания через «Загрузить медиа».\n\n"
        "<b>Лайк</b> и <b>Подписаться</b> доступны владельцу и читателям "
        "публичного архива. <b>Скачать оригинал</b> всегда доступно владельцу; "
        "для читателей кнопкой «Доступ и скачивание» отдельно выбираются "
        "аудитория и версия файла. По умолчанию скачивание запрещено.\n\n"
        "<b>Быстрый watermark</b> создаёт отдельную версию, не заменяя оригинал. "
        "<b>Доработка</b> кладёт материал в общую очередь и скрывает его из "
        "публичной выдачи. После проверки владелец возвращает работу кнопкой "
        "«Вернуть в публичный». <b>Скрыть</b>, <b>+18</b> и <b>Блюр</b> "
        "управляют видимостью конкретного материала."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ К материалу",
                    callback_data=_archive_callback(
                        "show",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=page.media.id,
                    ),
                )
            ]
        ]
    )
    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


async def _send_owner_original(bot: Bot, *, user_id: int, media) -> None:
    source_file_id = getattr(
        media,
        "original_download_file_id",
        getattr(media, "source_telegram_file_id", None) or media.telegram_file_id,
    )
    if isinstance(bot, ProtectedMediaBot):
        bot.allow_unprotected_private_user(user_id)
    if media.media_type == "document":
        await bot.send_document(
            chat_id=user_id,
            document=source_file_id,
            caption="Оригинал из вашего личного архива",
        )
        return
    payload = io.BytesIO()
    await bot.download(source_file_id, destination=payload, seek=True)
    raw = payload.getvalue()
    if not raw:
        raise RuntimeError("Telegram вернул пустой файл.")
    await bot.send_document(
        chat_id=user_id,
        document=BufferedInputFile(raw, filename=media.display_file_name),
        caption="Оригинал из вашего личного архива",
    )


@router.callback_query(WorkspacePersonalArchiveCallback.filter())
async def handle_workspace_personal_archive(
    callback: CallbackQuery,
    callback_data: WorkspacePersonalArchiveCallback,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    action = callback_data.action
    owner_actions = {
        "delete",
        "deleteconfirm",
        "like",
        "sub",
        "download",
        "watermark",
        "rework",
        "public",
        "adult",
        "blur",
        "settings",
        "mediahelp",
        *_DOWNLOAD_AUDIENCE_ACTIONS,
        *_DOWNLOAD_VARIANT_ACTIONS,
    }
    if action == "close":
        if isinstance(callback.message, Message):
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
        await callback.answer()
        return
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
        global_owner=_is_global_owner(callback.from_user.id),
    )
    owner_access = membership.role == "owner" or _is_global_owner(callback.from_user.id)
    if action in owner_actions and not owner_access:
        await callback.answer(
            "Эта кнопка доступна только владельцу пространства.",
            show_alert=True,
        )
        return

    if action == "noop":
        await callback.answer()
        return
    if action == "empty":
        await callback.answer(
            "У этого персонажа пока нет материалов. Сохраните их командой /save.",
            show_alert=True,
        )
        return
    if action == "help":
        await callback.answer(
            "Выберите персонажа кнопкой «Сохранить», затем присылайте несколько "
            "фото, видео или документов подряд. После последнего файла нажмите "
            "«Завершить загрузку».",
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
    if page is None:
        await callback.answer("Персонаж не найден в этом пространстве.", show_alert=True)
        return
    if page.media is None:
        await callback.answer("Архив персонажа пока пуст.", show_alert=True)
        return
    if (
        callback_data.media_id
        and action not in {"open", "show"}
        and callback_data.media_id != page.media.id
    ):
        await callback.answer(
            "Архив изменился. Откройте материал заново.",
            show_alert=True,
        )
        return

    if action == "open":
        if not isinstance(callback.message, Message):
            await callback.answer("Не удалось определить чат.", show_alert=True)
            return
        try:
            await _send_archive_page(
                bot,
                database=database,
                workspace_product_service=workspace_product_service,
                chat_id=callback.message.chat.id,
                user_id=callback.from_user.id,
                workspace_id=workspace.id,
                page=page,
                owner_access=owner_access,
            )
        except TelegramAPIError:
            await callback.answer(
                "Telegram больше не может открыть этот файл.",
                show_alert=True,
            )
            return
        await callback.answer()
        return
    if action == "show":
        await _replace_archive_page(
            callback,
            bot,
            database=database,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=workspace.id,
            page=page,
            owner_access=owner_access,
        )
        return
    if action == "settings":
        await _show_media_settings(
            callback,
            database=database,
            workspace_product_service=workspace_product_service,
            workspace=workspace,
            page=page,
        )
        return
    if action == "mediahelp":
        await _show_media_help(callback, workspace_id=workspace.id, page=page)
        return
    if action in _DOWNLOAD_AUDIENCE_ACTIONS or action in _DOWNLOAD_VARIANT_ACTIONS:
        settings = await workspace_product_service.get_settings(workspace.id)
        audience = _DOWNLOAD_AUDIENCE_ACTIONS.get(
            action,
            settings.download_audience,
        )
        variant = _DOWNLOAD_VARIANT_ACTIONS.get(
            action,
            settings.download_variant,
        )
        channels = await workspace_product_service.list_channels(workspace.id)
        channel_kinds = {item.kind for item in channels}
        destinations = await WorkspaceOnboardingRepository(database).list_destinations(
            workspace.id
        )
        destination_keys = {item.destination_key for item in destinations}
        watermark_asset = await WorkspaceWatermarkAssetRepository(database).get(
            workspace.id
        )
        if audience == "subscribers" and "download" not in channel_kinds:
            await _show_media_settings(
                callback,
                database=database,
                workspace_product_service=workspace_product_service,
                workspace=workspace,
                page=page,
                alert="Сначала подключите канал «Проверка скачивания».",
            )
            return
        if audience != "disabled" and variant == "watermark" and watermark_asset is None:
            await _show_media_settings(
                callback,
                database=database,
                workspace_product_service=workspace_product_service,
                workspace=workspace,
                page=page,
                alert="Сначала загрузите шаблон watermark.",
            )
            return
        if (
            audience != "disabled"
            and variant == "watermark"
            and "watermarks" not in destination_keys
        ):
            await _show_media_settings(
                callback,
                database=database,
                workspace_product_service=workspace_product_service,
                workspace=workspace,
                page=page,
                alert="Сначала подключите назначение «Watermark-копии».",
            )
            return
        await workspace_product_service.set_download_policy(
            workspace_id=workspace.id,
            actor_user_id=callback.from_user.id,
            download_audience=audience,
            download_variant=variant,
            global_owner=_is_global_owner(callback.from_user.id),
        )
        await _show_media_settings(
            callback,
            database=database,
            workspace_product_service=workspace_product_service,
            workspace=workspace,
            page=page,
            alert="Настройка скачивания сохранена.",
        )
        return
    if action == "download":
        try:
            await _send_owner_original(
                bot,
                user_id=callback.from_user.id,
                media=page.media,
            )
        except (TelegramAPIError, RuntimeError):
            await callback.answer("Не удалось отправить оригинал.", show_alert=True)
            return
        await callback.answer("Оригинал отправлен вам в личный чат.")
        return
    if action in {"like", "sub"}:
        if action == "like":
            settings = await workspace_product_service.get_settings(workspace.id)
            if not settings.public_archive_enabled or not page.media.is_public:
                liked = await WorkspaceMediaPreferenceRepository(
                    database
                ).toggle_favorite(
                    workspace_id=workspace.id,
                    character_id=page.character.id,
                    media_id=page.media.id,
                    user_id=callback.from_user.id,
                )
                result_text = (
                    "Личная отметка поставлена. Она не входит в публичные лайки."
                    if liked
                    else "Личная отметка снята."
                )
            else:
                liked, _ = await toggle_public_like(
                    database,
                    character_id=page.character.id,
                    media_id=page.media.id,
                    user_id=callback.from_user.id,
                    workspace_id=workspace.id,
                )
                result_text = "Лайк поставлен." if liked else "Лайк снят."
        else:
            subscribed = await toggle_character_subscription(
                database,
                character_id=page.character.id,
                user_id=callback.from_user.id,
                workspace_id=workspace.id,
            )
            result_text = "Подписка включена." if subscribed else "Подписка отключена."
        await _replace_archive_page(
            callback,
            bot,
            database=database,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=workspace.id,
            page=page,
            owner_access=True,
        )
        if isinstance(callback.message, Message):
            await callback.message.answer(result_text)
        return
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
            await _show_media_settings(
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
            callback_data=callback_data,
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
                await _show_media_settings(
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
    elif action == "blur":
        await toggle_archive_media_spoiler(
            database,
            character_id=page.character.id,
            media_id=page.media.id,
            workspace_id=workspace.id,
        )
    if action in {"public", "adult", "blur"}:
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
        await _replace_archive_page(
            callback,
            bot,
            database=database,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=workspace.id,
            page=updated,
            owner_access=True,
        )
        return
    if action == "delete":
        if not isinstance(callback.message, Message):
            await callback.answer("Сообщение архива больше недоступно.", show_alert=True)
            return
        try:
            await callback.message.edit_caption(
                caption=format_delete_caption(page),
                reply_markup=_archive_delete_keyboard(
                    page,
                    workspace_id=workspace.id,
                ),
            )
        except TelegramBadRequest:
            await callback.answer("Не удалось открыть подтверждение.", show_alert=True)
            return
        await callback.answer()
        return
    if action == "deleteconfirm":
        deleted = await delete_archive_item(
            database,
            callback_data.character_id,
            callback_data.media_id or page.media.id,
            workspace_id=workspace.id,
        )
        if deleted is None:
            await callback.answer("Материал уже удалён.", show_alert=True)
            return
        if (
            deleted.media.archive_message_id is not None
            and deleted.character.archive_chat_id is not None
        ):
            try:
                await bot.delete_message(
                    chat_id=deleted.character.archive_chat_id,
                    message_id=deleted.media.archive_message_id,
                )
            except TelegramAPIError:
                pass
        if deleted.remaining_total == 0:
            if isinstance(callback.message, Message):
                try:
                    await callback.message.delete()
                except TelegramBadRequest:
                    pass
            await callback.answer("Удалено. Архив персонажа пуст.", show_alert=True)
            return
        next_page = await get_archive_page(
            database,
            callback_data.character_id,
            min(page.offset, deleted.remaining_total - 1),
            workspace_id=workspace.id,
            include_adult_restricted=True,
            include_oversized_images=True,
        )
        if next_page is None or next_page.media is None:
            await callback.answer("Материал удалён.", show_alert=True)
            return
        await _replace_archive_page(
            callback,
            bot,
            database=database,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=workspace.id,
            page=next_page,
            owner_access=True,
        )
        return
    await callback.answer("Неизвестное действие.", show_alert=True)


@router.callback_query(WorkspaceReferenceEntryCallback.filter())
async def handle_workspace_reference_dashboard(
    callback: CallbackQuery,
    callback_data: WorkspaceReferenceEntryCallback,
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
            module_key="references",
            minimum_role="viewer",
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    if callback_data.action == "help":
        await callback.answer(
            "Добавление: /refadd Имя персонажа. Затем отправляйте фото или "
            "изображения-документы и завершите /refdone.",
            show_alert=True,
        )
        return
    if callback_data.action != "open":
        await callback.answer("Неизвестное действие.", show_alert=True)
        return

    character = await load_character_by_id(
        database,
        character_id=callback_data.character_id,
        workspace_id=workspace.id,
    )
    if character is None:
        await callback.answer("Персонаж не найден в этом пространстве.", show_alert=True)
        return
    references = await list_character_references(
        database,
        character.id,
        limit=50,
        workspace_id=workspace.id,
    )
    if not references:
        await callback.answer(
            f"У {character.name} пока нет референсов. Добавление: /refadd {character.name}",
            show_alert=True,
        )
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Не удалось определить чат.", show_alert=True)
        return
    try:
        await send_reference_collection(
            bot=bot,
            chat_id=callback.message.chat.id,
            character=character,
            references=references,
        )
    except TelegramAPIError:
        await callback.answer("Telegram не смог открыть один из референсов.", show_alert=True)
        return
    await callback.answer()


@router.message(Command("workspace_delete"))
async def handle_workspace_delete_command(
    message: Message,
    workspace_service: WorkspaceService,
) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("Удаление пространства выполняется только в личных сообщениях.")
        return
    parts = (message.text or "").split()
    explicit_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    try:
        workspace = await _resolve_workspace(
            workspace_service=workspace_service,
            user_id=message.from_user.id if message.from_user else 0,
            workspace_id=explicit_id,
            minimum_role="owner",
        )
    except WorkspaceAccessError as error:
        await message.answer(str(error))
        return
    if workspace.is_system:
        await message.answer("Системное пространство Velvet удалить нельзя.")
        return
    await _show_workspace_delete_confirmation(message, workspace=workspace)


@router.callback_query(WorkspaceCallback.filter(F.action == "delete"))
async def handle_workspace_delete_prompt(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    workspace_service: WorkspaceService,
) -> None:
    try:
        workspace = await _resolve_workspace(
            workspace_service=workspace_service,
            user_id=callback.from_user.id,
            workspace_id=callback_data.workspace_id,
            minimum_role="owner",
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    if workspace.is_system:
        await callback.answer("Системное пространство удалить нельзя.", show_alert=True)
        return
    await _show_workspace_delete_confirmation(callback, workspace=workspace)


async def _handle_workspace_delete_cancel(
    callback: CallbackQuery,
    *,
    callback_data: WorkspaceCallback,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace = await _resolve_workspace(
            workspace_service=workspace_service,
            user_id=callback.from_user.id,
            workspace_id=callback_data.workspace_id,
            minimum_role="owner",
        )
        await _render_home(
            callback,
            workspace=workspace,
            user_id=callback.from_user.id,
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)


@router.callback_query(WorkspaceCallback.filter(F.action == "deletecancel"))
async def handle_workspace_delete_cancel(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    await _handle_workspace_delete_cancel(
        callback,
        callback_data=callback_data,
        workspace_service=workspace_service,
        workspace_product_service=workspace_product_service,
    )


@router.callback_query(WorkspaceCallback.filter(F.action == "deleteconfirm"))
async def handle_workspace_delete_confirm(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace = await _resolve_workspace(
            workspace_service=workspace_service,
            user_id=callback.from_user.id,
            workspace_id=callback_data.workspace_id,
            minimum_role="owner",
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    if workspace.is_system:
        await callback.answer("Системное пространство удалить нельзя.", show_alert=True)
        return

    try:
        deleted_characters = await _delete_workspace_data(
            database,
            workspace_id=workspace.id,
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return

    await state.clear()
    start_state = await workspace_product_service.get_start_state(callback.from_user.id)
    personal_count = len(start_state.owned_workspaces) + len(start_state.member_workspaces)
    text = (
        f"<b>Пространство «{escape(workspace.name)}» удалено</b>\n\n"
        f"Удалено персонажей: <b>{deleted_characters}</b>.\n"
        "Разрешение Стэл не отозвано. Если лимит позволяет, новый архив можно создать снова."
    )
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                text,
                reply_markup=build_start_keyboard(
                    can_create=start_state.can_create,
                    has_workspace=bool(personal_count),
                    workspace_count=personal_count,
                    has_owned_workspace=bool(start_state.owned_workspaces),
                ),
            )
        except TelegramBadRequest:
            await callback.message.answer(
                text,
                reply_markup=build_start_keyboard(
                    can_create=start_state.can_create,
                    has_workspace=bool(personal_count),
                    workspace_count=personal_count,
                    has_owned_workspace=bool(start_state.owned_workspaces),
                ),
            )
    await callback.answer("Пространство удалено.")


__all__ = (
    "WorkspacePersonalArchiveCallback",
    "WorkspaceReferenceEntryCallback",
    "router",
)
