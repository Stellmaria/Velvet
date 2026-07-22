from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.domains.workspaces.administration import (
    WorkspaceAdminSummary,
    WorkspaceGrantAdminSummary,
)
from velvet_bot.domains.workspaces.product_models import (
    WORKSPACE_MODULE_KEYS,
    WorkspaceModuleKey,
    WorkspaceModuleSetting,
)
from velvet_bot.owner_callbacks import owner_callback
from velvet_bot.presentation.telegram.navigation import compact_button_text
from velvet_bot.workspace_ui import MODULE_LABELS


class WorkspaceAdminCallback(CallbackData, prefix="wad"):
    action: str
    user_id: int = 0
    workspace_id: int = 0
    module_key: str = ""
    page: int = 0


def workspace_admin_callback(
    action: str,
    *,
    user_id: int = 0,
    workspace_id: int = 0,
    module_key: str = "",
    page: int = 0,
) -> str:
    return WorkspaceAdminCallback(
        action=action,
        user_id=int(user_id),
        workspace_id=int(workspace_id),
        module_key=module_key,
        page=max(0, int(page)),
    ).pack()


def _module_rows(
    buttons: list[InlineKeyboardButton],
) -> list[list[InlineKeyboardButton]]:
    return [buttons[index : index + 2] for index in range(0, len(buttons), 2)]


def _pagination_row(
    *,
    action: str,
    page: int,
    total: int,
    page_size: int,
) -> list[InlineKeyboardButton]:
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=workspace_admin_callback(action, page=page - 1),
            )
        )
    buttons.append(
        InlineKeyboardButton(
            text=f"{page + 1} / {max(1, (total + page_size - 1) // page_size)}",
            callback_data=workspace_admin_callback("noop"),
        )
    )
    if (page + 1) * page_size < total:
        buttons.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=workspace_admin_callback(action, page=page + 1),
            )
        )
    return buttons


def build_workspace_admin_home_keyboard(
    *,
    grant_count: int,
    workspace_count: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Выдать доступ",
                    callback_data=workspace_admin_callback("new"),
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"👤 Разрешения · {grant_count}",
                    callback_data=workspace_admin_callback("users"),
                ),
                InlineKeyboardButton(
                    text=f"🗄 Архивы · {workspace_count}",
                    callback_data=workspace_admin_callback("spaces"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Центр управления",
                    callback_data=owner_callback("menu"),
                )
            ],
        ]
    )


def build_grants_keyboard(
    grants: tuple[WorkspaceGrantAdminSummary, ...],
    *,
    page: int,
    total: int,
    page_size: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in grants:
        state = "🟢" if item.is_active else "⚪"
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{state} {item.user_id} · "
                        f"{item.owned_workspace_count}/{item.max_workspaces}"
                    ),
                    callback_data=workspace_admin_callback(
                        "user",
                        user_id=item.user_id,
                        page=page,
                    ),
                )
            ]
        )
    rows.append(
        _pagination_row(
            action="users",
            page=page,
            total=total,
            page_size=page_size,
        )
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="➕ Выдать доступ",
                callback_data=workspace_admin_callback("new"),
            ),
            InlineKeyboardButton(
                text="↩️ Панель",
                callback_data=workspace_admin_callback("home"),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_grant_card_keyboard(
    grant: WorkspaceGrantAdminSummary,
    workspaces: tuple[WorkspaceAdminSummary, ...],
    *,
    page: int = 0,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="🧩 Модули будущего архива",
                callback_data=workspace_admin_callback(
                    "gmods",
                    user_id=grant.user_id,
                    page=page,
                ),
            )
        ]
    ]
    for workspace in workspaces:
        rows.append(
            [
                InlineKeyboardButton(
                    text=compact_button_text(
                        f"🗄 {workspace.name} · #{workspace.workspace_id}"
                    ),
                    callback_data=workspace_admin_callback(
                        "space",
                        user_id=grant.user_id,
                        workspace_id=workspace.workspace_id,
                        page=page,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=(
                    "🚫 Отозвать создание"
                    if grant.is_active
                    else "✅ Вернуть разрешение"
                ),
                callback_data=workspace_admin_callback(
                    "goff" if grant.is_active else "gon",
                    user_id=grant.user_id,
                    page=page,
                ),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Пользователи",
                callback_data=workspace_admin_callback("users", page=page),
            ),
            InlineKeyboardButton(
                text="🏠 Панель",
                callback_data=workspace_admin_callback("home"),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_grant_modules_keyboard(
    grant: WorkspaceGrantAdminSummary,
    *,
    page: int = 0,
) -> InlineKeyboardMarkup:
    selected = set(grant.allowed_modules)
    buttons = [
        InlineKeyboardButton(
            text=("✅ " if key in selected else "⛔ ") + MODULE_LABELS[key],
            callback_data=workspace_admin_callback(
                "gmt",
                user_id=grant.user_id,
                module_key=key,
                page=page,
            ),
        )
        for key in WORKSPACE_MODULE_KEYS
    ]
    rows = _module_rows(buttons)
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Пользователь",
                callback_data=workspace_admin_callback(
                    "user",
                    user_id=grant.user_id,
                    page=page,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_workspaces_keyboard(
    workspaces: tuple[WorkspaceAdminSummary, ...],
    *,
    page: int,
    total: int,
    page_size: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for workspace in workspaces:
        visibility = "🌐" if workspace.public_archive_enabled else "🔒"
        rows.append(
            [
                InlineKeyboardButton(
                    text=compact_button_text(
                        f"{visibility} {workspace.name} · "
                        f"{workspace.owner_user_id} · #{workspace.workspace_id}"
                    ),
                    callback_data=workspace_admin_callback(
                        "space",
                        user_id=workspace.owner_user_id,
                        workspace_id=workspace.workspace_id,
                        page=page,
                    ),
                )
            ]
        )
    rows.append(
        _pagination_row(
            action="spaces",
            page=page,
            total=total,
            page_size=page_size,
        )
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Панель",
                callback_data=workspace_admin_callback("home"),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_workspace_card_keyboard(
    workspace: WorkspaceAdminSummary,
    *,
    page: int = 0,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧩 Доступные модули",
                    callback_data=workspace_admin_callback(
                        "wmods",
                        user_id=workspace.owner_user_id,
                        workspace_id=workspace.workspace_id,
                        page=page,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="👤 Карточка владельца",
                    callback_data=workspace_admin_callback(
                        "user",
                        user_id=workspace.owner_user_id,
                        page=page,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Архивы",
                    callback_data=workspace_admin_callback("spaces", page=page),
                ),
                InlineKeyboardButton(
                    text="🏠 Панель",
                    callback_data=workspace_admin_callback("home"),
                ),
            ],
        ]
    )


def build_workspace_modules_keyboard(
    workspace: WorkspaceAdminSummary,
    modules: tuple[WorkspaceModuleSetting, ...],
    *,
    page: int = 0,
) -> InlineKeyboardMarkup:
    by_key = {item.module_key: item for item in modules}
    buttons: list[InlineKeyboardButton] = []
    for key in WORKSPACE_MODULE_KEYS:
        setting = by_key.get(key)
        if setting is None or not setting.is_allowed:
            marker = "⛔ "
        elif setting.is_enabled:
            marker = "✅ "
        else:
            marker = "➖ "
        buttons.append(
            InlineKeyboardButton(
                text=marker + MODULE_LABELS[key],
                callback_data=workspace_admin_callback(
                    "wmt",
                    user_id=workspace.owner_user_id,
                    workspace_id=workspace.workspace_id,
                    module_key=key,
                    page=page,
                ),
            )
        )
    rows = _module_rows(buttons)
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Пространство",
                callback_data=workspace_admin_callback(
                    "space",
                    user_id=workspace.owner_user_id,
                    workspace_id=workspace.workspace_id,
                    page=page,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_new_grant_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=workspace_admin_callback("home"),
                )
            ]
        ]
    )


__all__ = (
    "WorkspaceAdminCallback",
    "build_grant_card_keyboard",
    "build_grant_modules_keyboard",
    "build_grants_keyboard",
    "build_new_grant_prompt_keyboard",
    "build_workspace_admin_home_keyboard",
    "build_workspace_card_keyboard",
    "build_workspace_modules_keyboard",
    "build_workspaces_keyboard",
    "workspace_admin_callback",
)
