from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.domains.auf_runtime import (
    AUF_MODULE_KEY,
    AUF_WORKSPACE_ACTION,
    AufRuntimeService,
)
from velvet_bot.domains.workspaces.models import Workspace, WorkspaceRole
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleSetting
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceService
from velvet_bot.presentation.telegram.routers.workspace_onboarding import (
    WorkspaceOnboardingCallback,
)
from velvet_bot.workspace_ui import (
    build_workspace_home_keyboard,
    build_workspace_member_home_keyboard,
    format_workspace_home,
    workspace_callback,
)

_ROLE_LABELS = {
    "viewer": "наблюдатель",
    "reviewer": "проверяющий",
    "editor": "редактор",
    "admin": "администратор",
    "owner": "владелец",
}


@dataclass(frozen=True, slots=True)
class WorkspaceHomePresentation:
    """Ready-to-render workspace home view and its command role."""

    text: str
    keyboard: InlineKeyboardMarkup
    role: WorkspaceRole


def build_workspace_owner_home_keyboard(
    workspace: Workspace,
    *,
    public_enabled: bool,
    modules: Sequence[WorkspaceModuleSetting],
    show_button_hints: bool = True,
    auf_visible: bool = True,
    meow_visible: bool | None = None,
) -> InlineKeyboardMarkup:
    """Build the canonical owner keyboard without hidden controller state.

    ``meow_visible`` remains a keyword-only compatibility alias for stacked code.
    """

    if meow_visible is not None:
        auf_visible = meow_visible

    base = build_workspace_home_keyboard(
        workspace,
        public_enabled=public_enabled,
        modules=tuple(modules),
    )
    rows = [list(row) for row in base.inline_keyboard]
    auf_enabled = any(
        item.module_key == AUF_MODULE_KEY and item.is_allowed and item.is_enabled
        for item in modules
    )
    if auf_enabled and auf_visible:
        rows.insert(
            1 if rows else 0,
            [
                InlineKeyboardButton(
                    text="Ауф",
                    callback_data=workspace_callback(
                        AUF_WORKSPACE_ACTION,
                        workspace_id=workspace.id,
                    ),
                )
            ],
        )
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


async def build_workspace_home_presentation(
    *,
    workspace: Workspace,
    user_id: int,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
    global_owner: bool,
    auf_runtime_service: AufRuntimeService | None = None,
) -> WorkspaceHomePresentation:
    """Load role-aware workspace home data through public service contracts."""

    membership = await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=user_id,
        minimum_role="viewer",
        global_owner=global_owner,
    )
    settings = await workspace_product_service.get_settings(workspace.id)

    if membership.role == "owner":
        modules = await workspace_product_service.list_modules(
            workspace_id=workspace.id,
            actor_user_id=user_id,
            global_owner=global_owner,
        )
        show_button_hints = await workspace_product_service.get_button_hints(
            workspace.id
        )
        auf_visible = True
        if auf_runtime_service is not None:
            auf_visible = await auf_runtime_service.module_is_visible(
                workspace_id=workspace.id,
                actor_user_id=user_id,
                module_key=AUF_MODULE_KEY,
            )
        keyboard = build_workspace_owner_home_keyboard(
            workspace,
            public_enabled=settings.public_archive_enabled,
            modules=modules,
            show_button_hints=show_button_hints,
            auf_visible=auf_visible,
        )
        role_label = "владелец"
        suffix = f"\nРоль: <b>{role_label}</b>"
    else:
        modules = await workspace_product_service.list_modules_for_member(
            workspace_id=workspace.id,
            actor_user_id=user_id,
            global_owner=global_owner,
        )
        keyboard = build_workspace_member_home_keyboard(
            workspace,
            role=membership.role,
            modules=modules,
        )
        role_label = _ROLE_LABELS.get(membership.role, membership.role)
        suffix = (
            f"\nРоль: <b>{escape(role_label)}</b>\n\n"
            "Показаны только разделы, доступные по вашей роли. Настройка модулей, "
            "публичность и удаление остаются у владельца."
        )

    allowed_modules = sum(item.is_allowed for item in modules)
    enabled_modules = sum(item.is_allowed and item.is_enabled for item in modules)
    text = format_workspace_home(
        workspace,
        public_enabled=settings.public_archive_enabled,
        enabled_modules=enabled_modules,
        allowed_modules=allowed_modules,
    ) + suffix
    return WorkspaceHomePresentation(
        text=text,
        keyboard=keyboard,
        role=membership.role,
    )


__all__ = (
    "WorkspaceHomePresentation",
    "build_workspace_home_presentation",
    "build_workspace_owner_home_keyboard",
)
