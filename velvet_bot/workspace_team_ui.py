from __future__ import annotations

from html import escape

from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.domains.workspaces.models import WorkspaceMembership, WorkspaceRole
from velvet_bot.workspace_ui import workspace_callback

ROLE_LABELS: dict[WorkspaceRole, str] = {
    "owner": "Владелец",
    "admin": "Администратор",
    "editor": "Редактор",
    "reviewer": "Проверяющий",
    "viewer": "Зритель",
}
ROLE_EMOJI: dict[WorkspaceRole, str] = {
    "owner": "👑",
    "admin": "🛡",
    "editor": "✍️",
    "reviewer": "🔎",
    "viewer": "👁",
}


class WorkspaceTeamCallback(CallbackData, prefix="wteam"):
    action: str
    workspace_id: int
    user_id: int = 0
    role: str = ""


class WorkspaceTeamForm(StatesGroup):
    waiting_user_id = State()


def team_callback(
    action: str,
    *,
    workspace_id: int,
    user_id: int = 0,
    role: str = "",
) -> str:
    return WorkspaceTeamCallback(
        action=action,
        workspace_id=workspace_id,
        user_id=user_id,
        role=role,
    ).pack()


def format_team(
    *,
    workspace_name: str,
    members: tuple[WorkspaceMembership, ...],
) -> str:
    counts = {role: 0 for role in ROLE_LABELS}
    for item in members:
        counts[item.role] += 1
    return (
        f"<b>👤 Команда · {escape(workspace_name)}</b>\n\n"
        f"Участников: <b>{len(members)}</b>\n"
        f"Владельцев: <b>{counts['owner']}</b> · "
        f"администраторов: <b>{counts['admin']}</b>\n"
        f"Редакторов: <b>{counts['editor']}</b> · "
        f"проверяющих: <b>{counts['reviewer']}</b> · "
        f"зрителей: <b>{counts['viewer']}</b>\n\n"
        "Выберите участника для смены роли или удаления. Telegram, видимо, "
        "так и не придумал человеческие каталоги сотрудников, поэтому основным ключом остаётся ID."
    )


def build_team_keyboard(
    *,
    workspace_id: int,
    members: tuple[WorkspaceMembership, ...],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in members:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{ROLE_EMOJI[item.role]} {item.user_id} · "
                        f"{ROLE_LABELS[item.role]}"
                    )[:56],
                    callback_data=team_callback(
                        "member",
                        workspace_id=workspace_id,
                        user_id=item.user_id,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="➕ Добавить по Telegram ID",
                callback_data=team_callback("add", workspace_id=workspace_id),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Моё пространство",
                callback_data=workspace_callback("home", workspace_id=workspace_id),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_member(item: WorkspaceMembership) -> str:
    return (
        "<b>Участник пространства</b>\n\n"
        f"Telegram ID: <code>{item.user_id}</code>\n"
        f"Роль: {ROLE_EMOJI[item.role]} <b>{ROLE_LABELS[item.role]}</b>\n"
        f"Добавлен: <b>{item.created_at.astimezone().strftime('%d.%m.%Y %H:%M')}</b>"
    )


def build_member_keyboard(
    *,
    workspace_id: int,
    item: WorkspaceMembership,
    actor_role: WorkspaceRole,
) -> InlineKeyboardMarkup:
    assignable: tuple[WorkspaceRole, ...]
    if actor_role == "owner":
        assignable = ("owner", "admin", "editor", "reviewer", "viewer")
    else:
        assignable = ("editor", "reviewer", "viewer")
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if role == item.role else "")
                + ROLE_EMOJI[role]
                + " "
                + ROLE_LABELS[role],
                callback_data=team_callback(
                    "role",
                    workspace_id=workspace_id,
                    user_id=item.user_id,
                    role=role,
                ),
            )
        ]
        for role in assignable
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="🗑 Удалить из команды",
                callback_data=team_callback(
                    "remove",
                    workspace_id=workspace_id,
                    user_id=item.user_id,
                ),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Команда",
                callback_data=team_callback("list", workspace_id=workspace_id),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_new_member_role_keyboard(
    *,
    workspace_id: int,
    user_id: int,
    actor_role: WorkspaceRole,
) -> InlineKeyboardMarkup:
    roles: tuple[WorkspaceRole, ...] = (
        ("owner", "admin", "editor", "reviewer", "viewer")
        if actor_role == "owner"
        else ("editor", "reviewer", "viewer")
    )
    rows = [
        [
            InlineKeyboardButton(
                text=f"{ROLE_EMOJI[role]} {ROLE_LABELS[role]}",
                callback_data=team_callback(
                    "addrole",
                    workspace_id=workspace_id,
                    user_id=user_id,
                    role=role,
                ),
            )
        ]
        for role in roles
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="✖ Отмена",
                callback_data=team_callback("list", workspace_id=workspace_id),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_remove_confirmation_keyboard(
    *,
    workspace_id: int,
    user_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Да, удалить",
                    callback_data=team_callback(
                        "removeok",
                        workspace_id=workspace_id,
                        user_id=user_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=team_callback(
                        "member",
                        workspace_id=workspace_id,
                        user_id=user_id,
                    ),
                )
            ],
        ]
    )


__all__ = (
    "ROLE_EMOJI",
    "ROLE_LABELS",
    "WorkspaceTeamCallback",
    "WorkspaceTeamForm",
    "build_member_keyboard",
    "build_new_member_role_keyboard",
    "build_remove_confirmation_keyboard",
    "build_team_keyboard",
    "format_member",
    "format_team",
    "team_callback",
)
