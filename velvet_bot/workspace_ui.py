from __future__ import annotations

from html import escape

from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import (
    WorkspaceCategory,
    WorkspaceModuleKey,
    WorkspaceModuleSetting,
    WorkspaceStory,
    WorkspaceUniverse,
)
from velvet_bot.public_ui import build_public_entry_keyboard

MODULE_LABELS: dict[WorkspaceModuleKey, str] = {
    "characters": "👥 Персонажи",
    "archive": "🖼 Архив",
    "taxonomy": "🗂 Категории и вселенные",
    "references": "🧬 Референсы",
    "public_archive": "🌐 Публичный архив",
    "watermark": "💧 Watermark",
    "qwen": "🤖 Qwen",
    "publications": "📣 Публикации",
    "analytics": "📊 Аналитика",
    "team": "👤 Команда",
    "auf": "🐺 Ауф",
}

MODULE_HELP: dict[WorkspaceModuleKey, str] = {
    "characters": "Создание и управление персонажами только внутри вашего архива.",
    "archive": "Сохранение фото, видео и документов, просмотр карточек и управление материалами.",
    "taxonomy": "Собственные категории, вселенные и истории. Значения не пересекаются с другими архивами.",
    "references": "Личная библиотека референсов персонажей и сравнение результата с внешностью.",
    "public_archive": "Перевод архива в режим read-only для публичного просмотра. По умолчанию выключен.",
    "watermark": "Подготовка публичных копий с вашим знаком и правилами скачивания.",
    "qwen": (
        "Сравнение результата с референсом доступно из личной библиотеки референсов. "
        "Полный Quality Center, медиасеты и общая AI-очередь пока остаются "
        "системными инструментами Velvet Anatomy."
    ),
    "publications": "Черновики, проверка, очередь и публикация материалов в подключённый канал пространства.",
    "analytics": "Статистика только подключённых каналов пространства: публикации, персонажи и обсуждения.",
    "team": "Добавление редакторов, проверяющих и администраторов вашего пространства.",
    "auf": "Генерация и оживление изображений, управление балансом и задачами Ауф внутри пространства.",
}


class WorkspaceCallback(CallbackData, prefix="wsp"):
    action: str
    workspace_id: int = 0
    module_key: str = ""


class WorkspaceForm(StatesGroup):
    waiting_workspace_name = State()
    waiting_category = State()
    waiting_universe = State()
    waiting_story = State()


def workspace_callback(
    action: str,
    *,
    workspace_id: int = 0,
    module_key: str = "",
) -> str:
    return WorkspaceCallback(
        action=action,
        workspace_id=workspace_id,
        module_key=module_key,
    ).pack()


def build_start_keyboard(
    *,
    can_create: bool,
    has_workspace: bool,
    workspace_count: int = 0,
    has_owned_workspace: bool = True,
    has_member_workspace: bool = False,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="🌐 Посмотреть публичные архивы",
                callback_data=workspace_callback("publics"),
            )
        ]
    ]
    if can_create:
        rows.append(
            [
                InlineKeyboardButton(
                    text="➕ Создать свой архив",
                    callback_data=workspace_callback("create"),
                )
            ]
        )
    if has_workspace:
        count = max(1, int(workspace_count))
        if count > 1:
            text = "🗂 Мои пространства"
            action = "spaces"
        elif has_owned_workspace:
            text = "⚙️ Моё пространство"
            action = "home"
        else:
            text = "🤝 Рабочее пространство"
            action = "home"
        rows.append(
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=workspace_callback(action),
                )
            ]
        )
    if has_member_workspace:
        rows.append(
            [
                InlineKeyboardButton(
                    text="👥 Пространство команды",
                    callback_data=workspace_callback("memberhome"),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


_MEMBER_ROLE_LABELS = {
    "owner": "Владелец",
    "admin": "Администратор",
    "editor": "Редактор",
    "reviewer": "Проверяющий",
    "viewer": "Наблюдатель",
}
_MEMBER_MODULE_ROLES = {
    "characters": frozenset({"owner", "admin", "editor"}),
    "archive": frozenset({"owner", "admin", "editor", "reviewer", "viewer"}),
    "references": frozenset({"owner", "admin", "editor", "reviewer", "viewer"}),
    "watermark": frozenset({"owner", "admin"}),
    "qwen": frozenset({"owner", "admin", "editor", "reviewer"}),
    "publications": frozenset({"owner", "admin", "editor"}),
    "analytics": frozenset({"owner", "admin", "editor", "reviewer"}),
    "team": frozenset({"owner", "admin"}),
}


def build_member_workspace_select_keyboard(
    workspaces: tuple[Workspace, ...],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"👥 {item.name}"[:42],
                callback_data=workspace_callback("memberselect", workspace_id=item.id),
            )
        ]
        for item in workspaces
    ]
    rows.append(
        [InlineKeyboardButton(text="✖ Закрыть", callback_data=workspace_callback("close"))]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_workspace_member_home(
    workspace: Workspace,
    *,
    role: str,
    enabled_modules: int,
) -> str:
    role_label = _MEMBER_ROLE_LABELS.get(role, role)
    return (
        f"<b>{escape(workspace.name)}</b>\n\n"
        f"Ваша роль: <b>{escape(role_label)}</b>\n"
        f"Доступных разделов: <b>{enabled_modules}</b>\n\n"
        "Здесь показаны только действия, доступные вашей роли. Настройки "
        "пространства доступны владельцу и администраторам."
    )


def build_workspace_member_home_keyboard(
    workspace: Workspace,
    *,
    role: str,
    modules: tuple[WorkspaceModuleSetting, ...],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    settings = {item.module_key: item for item in modules}
    actions = {
        "characters": "characters",
        "archive": "archive",
        "references": "references",
        "watermark": "watermark",
        "qwen": "qwen",
        "publications": "publishing",
        "analytics": "analytics",
        "team": "team",
    }
    for key, action in actions.items():
        setting = settings.get(key)
        if (
            setting is None
            or not setting.is_allowed
            or not setting.is_enabled
            or role not in _MEMBER_MODULE_ROLES.get(key, frozenset())
        ):
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=MODULE_LABELS[key],
                    callback_data=workspace_callback(action, workspace_id=workspace.id),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="↩️ Другие пространства",
                    callback_data=workspace_callback("memberhome"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✖ Закрыть",
                    callback_data=workspace_callback("close", workspace_id=workspace.id),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_workspace_home_keyboard(
    workspace: Workspace,
    *,
    public_enabled: bool,
    modules: tuple[WorkspaceModuleSetting, ...],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    settings = {item.module_key: item for item in modules}
    actions = {
        "characters": "characters",
        "archive": "archive",
        "taxonomy": "taxonomy",
        "references": "references",
        "watermark": "watermark",
        "qwen": "qwen",
        "publications": "publishing",
        "analytics": "analytics",
        "team": "team",
    }
    for key, action in actions.items():
        setting = settings.get(key)
        if setting is None or not setting.is_allowed or not setting.is_enabled:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=MODULE_LABELS[key],
                    callback_data=workspace_callback(action, workspace_id=workspace.id),
                )
            ]
        )
    public_setting = settings.get("public_archive")
    if public_setting is not None and public_setting.is_allowed:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        "🔒 Сделать приватным" if public_enabled else "🌐 Сделать публичным"
                    ),
                    callback_data=workspace_callback(
                        "publicoff" if public_enabled else "publicon",
                        workspace_id=workspace.id,
                    ),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🧩 Выбрать модули",
                    callback_data=workspace_callback(
                        "modules",
                        workspace_id=workspace.id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✖ Закрыть",
                    callback_data=workspace_callback("close", workspace_id=workspace.id),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_workspace_home(
    workspace: Workspace,
    *,
    public_enabled: bool,
    enabled_modules: int,
    allowed_modules: int,
) -> str:
    return (
        f"<b>{escape(workspace.name)}</b>\n\n"
        f"Статус: {'🌐 публичный' if public_enabled else '🔒 приватный'}\n"
        f"Модули: <b>{enabled_modules}/{allowed_modules}</b> включено."
    )


def format_workspace_list_item(workspace: Workspace) -> str:
    suffix = " · системное" if workspace.is_system else ""
    return f"{escape(workspace.name)}{suffix}"


def build_workspace_list_keyboard(
    workspaces: tuple[Workspace, ...],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=format_workspace_list_item(workspace),
                callback_data=workspace_callback(
                    "select",
                    workspace_id=workspace.id,
                ),
            )
        ]
        for workspace in workspaces
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Назад",
                callback_data=workspace_callback("start"),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_module_settings_keyboard(
    workspace: Workspace,
    modules: tuple[WorkspaceModuleSetting, ...],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in modules:
        status = "✅" if item.is_enabled else "⛔"
        label = MODULE_LABELS[item.module_key]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {label}",
                    callback_data=workspace_callback(
                        "modtoggle",
                        workspace_id=workspace.id,
                        module_key=item.module_key,
                    ),
                ),
                InlineKeyboardButton(
                    text="?",
                    callback_data=workspace_callback(
                        "modhelp",
                        workspace_id=workspace.id,
                        module_key=item.module_key,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Моё пространство",
                callback_data=workspace_callback("home", workspace_id=workspace.id),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def module_help_text(module_key: WorkspaceModuleKey) -> str:
    return f"<b>{MODULE_LABELS[module_key]}</b>\n\n{MODULE_HELP[module_key]}"


def build_module_help_keyboard(
    workspace_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ К модулям",
                    callback_data=workspace_callback(
                        "modules",
                        workspace_id=workspace_id,
                    ),
                )
            ]
        ]
    )


def build_public_mode_keyboard() -> InlineKeyboardMarkup:
    return build_public_entry_keyboard()
