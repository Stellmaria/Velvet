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
}

MODULE_HELP: dict[WorkspaceModuleKey, str] = {
    "characters": "Создание и управление персонажами только внутри вашего архива.",
    "archive": "Сохранение фото, видео и документов, просмотр карточек и управление материалами.",
    "taxonomy": "Собственные категории, вселенные и истории. Значения не пересекаются с другими архивами.",
    "references": "Личная библиотека референсов персонажей и сравнение результата с внешностью.",
    "public_archive": "Перевод архива в режим read-only для публичного просмотра. По умолчанию выключен.",
    "watermark": "Подготовка публичных копий с вашим знаком и правилами скачивания.",
    "qwen": "Проверка качества, сравнение с референсом, анализ композиции и очередь доработки.",
    "publications": "Черновики, очередь и публикация материалов в подключённые каналы.",
    "analytics": "Статистика только вашего пространства: персонажи, просмотры, лайки и публикации.",
    "team": "Добавление редакторов, проверяющих и администраторов вашего пространства.",
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
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_workspace_selector_keyboard(
    *,
    owned_workspaces: tuple[Workspace, ...],
    member_workspaces: tuple[Workspace, ...],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for workspace in owned_workspaces:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"⚙️ {workspace.name}"[:64],
                    callback_data=workspace_callback("home", workspace_id=workspace.id),
                )
            ]
        )
    for workspace in member_workspaces:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🤝 {workspace.name}"[:64],
                    callback_data=workspace_callback("home", workspace_id=workspace.id),
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="✖ Закрыть", callback_data=workspace_callback("close"))]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_public_workspaces_keyboard(
    workspaces: tuple[Workspace, ...],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=("🖤 " if item.is_system else "🌐 ") + item.name[:40],
                callback_data=workspace_callback(
                    "publicselect",
                    workspace_id=item.id,
                ),
            )
        ]
        for item in workspaces
    ]
    if not rows:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Публичных архивов пока нет",
                    callback_data=workspace_callback("noop"),
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="✖ Закрыть", callback_data=workspace_callback("close"))]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_selected_public_workspace_keyboard() -> InlineKeyboardMarkup:
    archive_button = build_public_entry_keyboard().inline_keyboard[0][0]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [archive_button],
            [
                InlineKeyboardButton(
                    text="↩️ Другие публичные архивы",
                    callback_data=workspace_callback("publics"),
                )
            ],
        ]
    )


def format_workspace_home(
    workspace: Workspace,
    *,
    public_enabled: bool,
    enabled_modules: int,
    allowed_modules: int,
) -> str:
    visibility = "🌐 публичный read-only" if public_enabled else "🔒 приватный"
    return (
        f"<b>{escape(workspace.name)}</b>\n\n"
        f"Статус архива: <b>{visibility}</b>\n"
        f"Модули: <b>{enabled_modules}/{allowed_modules}</b> включено\n\n"
        "Здесь отображаются только функции вашего пространства. "
        "Supervisor, Git, Codex и системные резервные копии сюда не входят."
    )


def build_workspace_home_keyboard(
    workspace: Workspace,
    *,
    public_enabled: bool,
    modules: tuple[WorkspaceModuleSetting, ...],
) -> InlineKeyboardMarkup:
    enabled = {item.module_key for item in modules if item.is_allowed and item.is_enabled}
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="🧭 Быстрые действия",
                callback_data=workspace_callback("quick", workspace_id=workspace.id),
            )
        ]
    ]
    if "characters" in enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="👥 Персонажи",
                    callback_data=workspace_callback(
                        "module",
                        workspace_id=workspace.id,
                        module_key="characters",
                    ),
                ),
                InlineKeyboardButton(
                    text="ℹ️",
                    callback_data=workspace_callback(
                        "modulehelp",
                        workspace_id=workspace.id,
                        module_key="characters",
                    ),
                ),
            ]
        )
    if "archive" in enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🖼 Архив",
                    callback_data=workspace_callback(
                        "module",
                        workspace_id=workspace.id,
                        module_key="archive",
                    ),
                ),
                InlineKeyboardButton(
                    text="ℹ️",
                    callback_data=workspace_callback(
                        "modulehelp",
                        workspace_id=workspace.id,
                        module_key="archive",
                    ),
                ),
            ]
        )
    if "taxonomy" in enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗂 Категории и вселенные",
                    callback_data=workspace_callback(
                        "taxonomy",
                        workspace_id=workspace.id,
                    ),
                ),
                InlineKeyboardButton(
                    text="ℹ️",
                    callback_data=workspace_callback(
                        "modulehelp",
                        workspace_id=workspace.id,
                        module_key="taxonomy",
                    ),
                ),
            ]
        )
    for module_key in (
        "references",
        "watermark",
        "qwen",
        "publications",
        "analytics",
        "team",
    ):
        if module_key not in enabled:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=MODULE_LABELS[module_key],
                    callback_data=workspace_callback(
                        "module",
                        workspace_id=workspace.id,
                        module_key=module_key,
                    ),
                ),
                InlineKeyboardButton(
                    text="ℹ️",
                    callback_data=workspace_callback(
                        "modulehelp",
                        workspace_id=workspace.id,
                        module_key=module_key,
                    ),
                ),
            ]
        )
    if "public_archive" in enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text=("🔒 Сделать приватным" if public_enabled else "🌐 Сделать публичным"),
                    callback_data=workspace_callback(
                        "visibility",
                        workspace_id=workspace.id,
                    ),
                )
            ],
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
            [InlineKeyboardButton(text="✖ Закрыть", callback_data=workspace_callback("close"))],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_workspace_member_home_keyboard(
    workspace: Workspace,
    *,
    role: str,
    modules: tuple[WorkspaceModuleSetting, ...],
) -> InlineKeyboardMarkup:
    """Show only entries whose handlers accept the member's role."""
    enabled = {item.module_key for item in modules if item.is_allowed and item.is_enabled}
    role_rank = {"viewer": 10, "reviewer": 20, "editor": 30, "admin": 40}.get(
        role,
        0,
    )
    rows: list[list[InlineKeyboardButton]] = []

    def add_module(module_key: WorkspaceModuleKey) -> None:
        if module_key not in enabled:
            return
        rows.append(
            [
                InlineKeyboardButton(
                    text=MODULE_LABELS[module_key],
                    callback_data=workspace_callback(
                        "module",
                        workspace_id=workspace.id,
                        module_key=module_key,
                    ),
                )
            ]
        )

    if role_rank >= 30:
        add_module("characters")
    add_module("archive")
    add_module("references")
    if role_rank >= 20:
        add_module("qwen")
        add_module("analytics")
    if role_rank >= 30:
        add_module("publications")
    if role_rank >= 40:
        add_module("watermark")
        add_module("team")
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🗂 Выбрать пространство",
                    callback_data=workspace_callback("spaces"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✖ Закрыть",
                    callback_data=workspace_callback("close"),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_modules_keyboard(
    workspace_id: int,
    modules: tuple[WorkspaceModuleSetting, ...],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in modules:
        if not item.is_allowed:
            status = "⛔"
        else:
            status = "✅" if item.is_enabled else "➖"
        label = MODULE_LABELS[item.module_key]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {label}"[:42],
                    callback_data=workspace_callback(
                        "modtoggle",
                        workspace_id=workspace_id,
                        module_key=item.module_key,
                    ),
                ),
                InlineKeyboardButton(
                    text="ℹ️",
                    callback_data=workspace_callback(
                        "modulehelpmodules",
                        workspace_id=workspace_id,
                        module_key=item.module_key,
                    ),
                ),
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


def build_module_help_keyboard(
    workspace_id: int,
    *,
    parent: str = "home",
) -> InlineKeyboardMarkup:
    action = "modules" if parent == "modules" else "home"
    text = "↩️ Назад к модулям" if parent == "modules" else "↩️ Моё пространство"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=workspace_callback(action, workspace_id=workspace_id),
                )
            ]
        ]
    )



def format_taxonomy(
    workspace: Workspace,
    *,
    categories: tuple[WorkspaceCategory, ...],
    universes: tuple[WorkspaceUniverse, ...],
    stories: tuple[WorkspaceStory, ...],
) -> str:
    return (
        f"<b>🗂 {escape(workspace.name)} · структура</b>\n\n"
        f"Категории: <b>{len(categories)}</b>\n"
        f"Вселенные: <b>{len(universes)}</b>\n"
        f"Истории: <b>{len(stories)}</b>\n\n"
        "Можно создавать свои значения. Они принадлежат только этому архиву. "
        "КР доступна как необязательный шаблон из Velvet Anatomy."
    )


def build_taxonomy_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📁 Категории",
                    callback_data=workspace_callback("categories", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="🎭 Вселенные",
                    callback_data=workspace_callback("universes", workspace_id=workspace_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📖 Истории",
                    callback_data=workspace_callback("stories", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="💎 Добавить КР",
                    callback_data=workspace_callback("krimport", workspace_id=workspace_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="➕ Категория",
                    callback_data=workspace_callback("addcategory", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="➕ Вселенная",
                    callback_data=workspace_callback("adduniverse", workspace_id=workspace_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="➕ История",
                    callback_data=workspace_callback("addstory", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="ℹ️ Что это",
                    callback_data=workspace_callback(
                        "modulehelp",
                        workspace_id=workspace_id,
                        module_key="taxonomy",
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Моё пространство",
                    callback_data=workspace_callback("home", workspace_id=workspace_id),
                )
            ],
        ]
    )


def build_taxonomy_list_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ Структура",
                    callback_data=workspace_callback("taxonomy", workspace_id=workspace_id),
                )
            ]
        ]
    )


__all__ = (
    "MODULE_HELP",
    "MODULE_LABELS",
    "WorkspaceCallback",
    "WorkspaceForm",
    "build_module_help_keyboard",
    "build_modules_keyboard",
    "build_public_workspaces_keyboard",
    "build_selected_public_workspace_keyboard",
    "build_start_keyboard",
    "build_taxonomy_keyboard",
    "build_taxonomy_list_keyboard",
    "build_workspace_member_home_keyboard",
    "build_workspace_home_keyboard",
    "build_workspace_selector_keyboard",
    "format_taxonomy",
    "format_workspace_home",
    "workspace_callback",
)
