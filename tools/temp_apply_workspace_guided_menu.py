from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_function(path: Path, name: str, replacement: str) -> None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        (
            item
            for item in tree.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
        ),
        None,
    )
    if node is None or node.end_lineno is None:
        raise RuntimeError(f"function {name} not found in {path}")
    lines = source.splitlines(keepends=True)
    new_lines = lines[: node.lineno - 1]
    new_lines.append(replacement.rstrip() + "\n\n")
    new_lines.extend(lines[node.end_lineno :])
    path.write_text("".join(new_lines), encoding="utf-8")


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"expected one occurrence in {path}: {old!r}; got {count}")
    path.write_text(source.replace(old, new), encoding="utf-8")


onboarding_domain = ROOT / "velvet_bot/domains/workspaces/onboarding.py"
replace_function(
    onboarding_domain,
    "required_destination_keys",
    '''def required_destination_keys(
    enabled_modules: set[WorkspaceModuleKey] | frozenset[WorkspaceModuleKey],
) -> tuple[WorkspaceDestinationKey, ...]:
    """Return only destinations required for the first usable personal archive.

    A personal workspace needs one main forum archive when characters or archive are
    enabled. Publication, analytics, discussion, public and log destinations are
    optional integrations configured later when their owner actually uses them.
    """

    if "characters" in enabled_modules or "archive" in enabled_modules:
        return ("characters",)
    return ()''',
)

onboarding_router = ROOT / "velvet_bot/presentation/telegram/routers/workspace_onboarding.py"
replace_function(
    onboarding_router,
    "_intro_text",
    '''def _intro_text(workspace: Workspace, *, resumed: bool) -> str:
    prefix = "Настройка продолжена" if resumed else "Пространство создано"
    return (
        f"<b>🧭 {prefix}: {escape(workspace.name)}</b>\\n\\n"
        "Для обычного личного архива нужны три понятных шага:\\n"
        "1. посмотреть короткий гид;\\n"
        "2. выбрать доступные модули;\\n"
        "3. один раз подключить основной форумный чат архива.\\n\\n"
        "После этого персонажи создаются по имени и ссылке на их ветку. "
        "Каналы публикаций, аналитики, обсуждений и логов не обязательны и "
        "настраиваются позже только при необходимости."
    )''',
)
replace_function(
    onboarding_router,
    "_intro_keyboard",
    '''def _intro_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📘 1 · Короткий гид",
                    callback_data=_callback("guide", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧩 2 · Выбрать модули",
                    callback_data=_callback("modules", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📁 3 · Основной архивный чат",
                    callback_data=_callback("destinations", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Проверить готовность",
                    callback_data=_callback("summary", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✖ Закрыть",
                    callback_data=_callback("close", workspace_id),
                )
            ],
        ]
    )''',
)
replace_function(
    onboarding_router,
    "_guide_text",
    '''def _guide_text(workspace: Workspace) -> str:
    return (
        f"<b>📘 Как работает {escape(workspace.name)}</b>\\n\\n"
        "<b>Основной архив</b> — один форумный чат, в котором находятся ветки "
        "персонажей. Его достаточно подключить один раз.\\n"
        "<b>Персонаж</b> — имя, карточка и ссылка на конкретную ветку этого чата.\\n"
        "<b>Сохранение</b> — выберите персонажа кнопкой и отправьте фото, видео или файл.\\n"
        "<b>Структура</b> — категории, вселенные и истории создаются пошагово кнопками.\\n\\n"
        "Дополнительные каналы нужны только отдельным функциям: публикациям, "
        "аналитике, публичной витрине или логам. Они не блокируют запуск архива.\\n\\n"
        "Основной чат подключается командой "
        f"<code>/workspace_bind characters {workspace.id}</code> внутри самого чата."
    )''',
)
replace_function(
    onboarding_router,
    "_guide_keyboard",
    '''def _guide_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Понятно · выбрать модули",
                    callback_data=_callback("guidedone", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ В начало мастера",
                    callback_data=_callback("intro", workspace_id),
                )
            ],
        ]
    )''',
)
replace_function(
    onboarding_router,
    "_modules_text",
    '''def _modules_text(workspace: Workspace) -> str:
    return (
        f"<b>🧩 Модули · {escape(workspace.name)}</b>\\n\\n"
        "Нажмите на разрешённый модуль, чтобы включить или выключить его.\\n"
        "✅ включён · ➖ выключен · ⛔ недоступен по разрешению Стэл.\\n\\n"
        "Для первого запуска мастер потребует только один основной архивный чат, "
        "если включены персонажи или архив. Остальные подключения остаются "
        "необязательными."
    )''',
)
replace_function(
    onboarding_router,
    "_destinations_text",
    '''def _destinations_text(
    workspace: Workspace,
    *,
    destinations: tuple[WorkspaceDestination, ...],
) -> str:
    configured = {item.destination_key: item for item in destinations}
    main = configured.get("characters")
    status = (
        "✅ " + escape(_destination_location(main))
        if main is not None
        else "❌ не подключён"
    )
    return (
        f"<b>📁 Основной архивный чат · {escape(workspace.name)}</b>\\n\\n"
        f"Статус: {status}\\n\\n"
        "Нужен один форумный чат, где размещаются ветки персонажей. В основном "
        "разделе этого чата отправьте:\\n"
        f"<code>/workspace_bind characters {workspace.id}</code>\\n\\n"
        "Для каждого персонажа затем указывается имя и ссылка на его конкретную "
        "ветку. Отдельные чаты материалов, референсов, аналитики и логов для "
        "завершения установки не требуются."
    )''',
)
replace_function(
    onboarding_router,
    "_destinations_keyboard",
    '''def _destinations_keyboard(
    workspace_id: int,
    destinations: tuple[WorkspaceDestination, ...],
) -> InlineKeyboardMarkup:
    configured = {item.destination_key for item in destinations}
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=("✅" if "characters" in configured else "▫️")
                    + " 📁 Как подключить основной чат",
                    callback_data=_callback("destinationhelp", workspace_id, "characters"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить подключение",
                    callback_data=_callback("destinations", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Проверить готовность",
                    callback_data=_callback("summary", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К модулям",
                    callback_data=_callback("modules", workspace_id),
                )
            ],
        ]
    )''',
)
replace_function(
    onboarding_router,
    "_destination_help_text",
    '''def _destination_help_text(workspace: Workspace, key: WorkspaceDestinationKey) -> str:
    if key == "characters":
        return (
            f"<b>📁 Основной архив · {escape(workspace.name)}</b>\\n\\n"
            "1. Откройте один форумный чат архива.\\n"
            "2. Добавьте бота администратором с правом управления темами.\\n"
            "3. В основном разделе чата отправьте:\\n"
            f"<code>/workspace_bind characters {workspace.id}</code>\\n\\n"
            "После этого создавайте персонажей по имени и ссылке на их ветку. "
            "Никакие другие чаты для обычного архива не обязательны."
        )
    spec = DESTINATION_SPECS[key]
    return (
        f"<b>{spec.emoji} {escape(spec.label)} · необязательное подключение</b>\\n\\n"
        f"{escape(spec.description)}\\n\\n"
        f"Команда внутри нужного чата: <code>{escape(spec.command_hint)}</code>"
    )''',
)
replace_function(
    onboarding_router,
    "_summary_keyboard",
    '''def _summary_keyboard(workspace_id: int, *, ready: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if ready:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚀 Завершить установку",
                    callback_data=_callback("complete", workspace_id),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🧩 Изменить модули",
                    callback_data=_callback("modules", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📁 Основной архивный чат",
                    callback_data=_callback("destinations", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📘 Короткий гид",
                    callback_data=_callback("guide", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ В начало мастера",
                    callback_data=_callback("intro", workspace_id),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)''',
)
replace_once(
    onboarding_router,
    '                "Модули подтверждены, обязательные чаты и темы подключены, права бота "\n                "проверены. Настройки можно менять через <code>/workspace_setup</code>, "',
    '                "Модули подтверждены, основной архивный чат подключён, права бота "\n                "проверены. Настройки можно менять через <code>/workspace_setup</code>, "',
)

workspace_ui = ROOT / "velvet_bot/workspace_ui.py"
replace_once(
    workspace_ui,
    "    rows: list[list[InlineKeyboardButton]] = []\n    if \"characters\" in enabled:\n",
    "    rows: list[list[InlineKeyboardButton]] = [\n"
    "        [\n"
    "            InlineKeyboardButton(\n"
    "                text=\"🧭 Быстрые действия\",\n"
    "                callback_data=workspace_callback(\"quick\", workspace_id=workspace.id),\n"
    "            )\n"
    "        ]\n"
    "    ]\n"
    "    if \"characters\" in enabled:\n",
)
source = workspace_ui.read_text(encoding="utf-8")
tree = ast.parse(source)
node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "build_modules_keyboard")
lines = source.splitlines(keepends=True)
segment = "".join(lines[node.lineno - 1 : node.end_lineno])
segment = segment.replace('"modulehelp",', '"modulehelpmodules",')
workspace_ui.write_text(
    "".join(lines[: node.lineno - 1]) + segment + "".join(lines[node.end_lineno :]),
    encoding="utf-8",
)
replace_function(
    workspace_ui,
    "build_module_help_keyboard",
    '''def build_module_help_keyboard(
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
    )''',
)

workspaces = ROOT / "velvet_bot/presentation/telegram/routers/workspaces.py"
replace_once(
    workspaces,
    '    "modulehelp",\n    "module",',
    '    "modulehelp",\n    "modulehelpmodules",\n    "module",',
)
replace_once(
    workspaces,
    '    if action in {"modulehelp", "module"}:',
    '    if action in {"modulehelp", "modulehelpmodules", "module"}:',
)
replace_once(
    workspaces,
    "            reply_markup=build_module_help_keyboard(workspace.id),",
    "            reply_markup=build_module_help_keyboard(\n"
    "                workspace.id,\n"
    "                parent=\"modules\" if action == \"modulehelpmodules\" else \"home\",\n"
    "            ),",
)

pickers = ROOT / "velvet_bot/presentation/telegram/routers/workspace_character_pickers.py"
replace_once(
    pickers,
    "from velvet_bot.presentation.telegram.routers.workspace_character_management import WorkspaceForm\n",
    "from velvet_bot.presentation.telegram.routers.workspace_character_management import WorkspaceForm\n"
    "from velvet_bot.presentation.telegram.routers.workspace_guided_ui import guided_workspace_callback\n",
)
replace_function(
    pickers,
    "_character_list_text",
    '''def _character_list_text(workspace_name: str, page: CharacterPickerPage) -> str:
    return (
        f"<b>👥 Персонажи · {escape(workspace_name)}</b>\\n\\n"
        f"Персонажей: <b>{page.total_items}</b>\\n"
        f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>\\n\\n"
        "Выберите персонажа. Из карточки можно сохранить материал, изменить имя, "
        "ветку, промт и алиас, а также назначить категорию, вселенную и истории."
    )''',
)
replace_function(
    pickers,
    "_character_list_keyboard",
    '''def _character_list_keyboard(
    *,
    workspace_id: int,
    page: CharacterPickerPage,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_character_button_text(item),
                callback_data=_callback(
                    "card",
                    workspace_id=workspace_id,
                    character_id=item.id,
                    page=page.page,
                ),
            )
        ]
        for item in page.items
    ]
    if page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_callback(
                        "list",
                        workspace_id=workspace_id,
                        page=(page.page - 1) % page.total_pages,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=_callback(
                        "noop",
                        workspace_id=workspace_id,
                        page=page.page,
                    ),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_callback(
                        "list",
                        workspace_id=workspace_id,
                        page=(page.page + 1) % page.total_pages,
                    ),
                ),
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="➕ Создать персонажа",
                    callback_data=guided_workspace_callback(
                        "cnew",
                        workspace_id=workspace_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="💾 Сохранить",
                    callback_data=guided_workspace_callback(
                        "savepick",
                        workspace_id=workspace_id,
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
    return InlineKeyboardMarkup(inline_keyboard=rows)''',
)
replace_function(
    pickers,
    "_card_keyboard",
    '''def _card_keyboard(
    *,
    workspace_id: int,
    character_id: int,
    list_page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💾 Сохранить",
                    callback_data=guided_workspace_callback(
                        "save",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
                InlineKeyboardButton(
                    text="✏️ Имя",
                    callback_data=guided_workspace_callback(
                        "rename",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔗 Ветка",
                    callback_data=guided_workspace_callback(
                        "topicedit",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
                InlineKeyboardButton(
                    text="📝 Промт",
                    callback_data=guided_workspace_callback(
                        "prompt",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏷 Добавить алиас",
                    callback_data=guided_workspace_callback(
                        "alias",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=guided_workspace_callback(
                        "deleteask",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗂 Категория",
                    callback_data=_callback(
                        "cat",
                        workspace_id=workspace_id,
                        character_id=character_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="🌌 Вселенная",
                    callback_data=_callback(
                        "uni",
                        workspace_id=workspace_id,
                        character_id=character_id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📖 Истории",
                    callback_data=_callback(
                        "story",
                        workspace_id=workspace_id,
                        character_id=character_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=_callback(
                        "card",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
                InlineKeyboardButton(
                    text="↩️ К списку",
                    callback_data=_callback(
                        "list",
                        workspace_id=workspace_id,
                        page=list_page,
                    ),
                ),
            ],
        ]
    )''',
)

bundle = ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
replace_once(
    bundle,
    "from velvet_bot.presentation.telegram.routers.workspace_character_pickers import (\n",
    "from velvet_bot.presentation.telegram.routers.workspace_guided_actions import (\n"
    "    router as workspace_guided_actions_router,\n"
    ")\n"
    "from velvet_bot.presentation.telegram.routers.workspace_character_pickers import (\n",
)
replace_once(
    bundle,
    "router.include_router(workspace_character_pickers_router)\n",
    "router.include_router(workspace_guided_actions_router)\n"
    "router.include_router(workspace_character_pickers_router)\n",
)

tests = ROOT / "tests/test_workspace_guided_menu.py"
tests.write_text(
    '''from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.onboarding import required_destination_keys
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleSetting
from velvet_bot.presentation.telegram.routers.workspace_guided_ui import (
    guided_workspace_callback,
)
from velvet_bot.workspace_ui import (
    build_modules_keyboard,
    build_workspace_home_keyboard,
)


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceGuidedMenuTests(unittest.TestCase):
    def test_first_run_requires_only_main_archive_chat(self) -> None:
        self.assertEqual(
            ("characters",),
            required_destination_keys(
                {"characters", "archive", "references", "publications", "analytics"}
            ),
        )
        self.assertEqual((), required_destination_keys({"taxonomy", "team"}))

    def test_guided_callbacks_fit_telegram_limit(self) -> None:
        packed = guided_workspace_callback(
            "deleteconfirm",
            workspace_id=9_223_372_036_854_775_807,
            character_id=9_223_372_036_854_775_807,
            item_id=9_223_372_036_854_775_807,
            page=999,
        )
        self.assertLessEqual(len(packed.encode("utf-8")), 64)

    def test_workspace_home_has_quick_actions(self) -> None:
        now = datetime.now(UTC)
        workspace = Workspace(7, "personal", "Personal", False, now, now)
        modules = (
            WorkspaceModuleSetting(
                workspace_id=7,
                module_key="characters",
                is_allowed=True,
                is_enabled=True,
                updated_by_user_id=1,
                created_at=now,
                updated_at=now,
            ),
        )
        keyboard = build_workspace_home_keyboard(
            workspace,
            public_enabled=False,
            modules=modules,
        )
        callbacks = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertTrue(any(value.startswith("wsp:quick:") for value in callbacks))

    def test_module_help_from_modules_returns_to_modules(self) -> None:
        now = datetime.now(UTC)
        modules = (
            WorkspaceModuleSetting(
                workspace_id=7,
                module_key="characters",
                is_allowed=True,
                is_enabled=True,
                updated_by_user_id=1,
                created_at=now,
                updated_at=now,
            ),
        )
        keyboard = build_modules_keyboard(7, modules)
        info = next(
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.text == "ℹ️"
        )
        self.assertIn("modulehelpmodules", str(info.callback_data))

    def test_character_and_taxonomy_back_buttons_use_real_parents(self) -> None:
        picker = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_character_pickers.py"
        ).read_text(encoding="utf-8")
        ui = (ROOT / "velvet_bot/workspace_ui.py").read_text(encoding="utf-8")
        self.assertIn('workspace_callback("home", workspace_id=workspace_id)', picker)
        self.assertIn('workspace_callback("taxonomy", workspace_id=workspace_id)', ui)
        self.assertNotIn("➕ Как создать персонажа", picker)

    def test_onboarding_no_longer_demands_every_destination(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/routers/workspace_onboarding.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Для каждой функции откройте нужный чат", source)
        self.assertIn("Основной архивный чат", source)


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)

worklog = ROOT / "docs/worklog/2026-07-22-workspace-guided-menu-navigation.md"
worklog.write_text(
    '''# Сессия: кнопочное меню личного архива и навигация

- Дата: 2026-07-22
- ID: `2026-07-22-workspace-guided-menu-navigation`
- Линия/фаза: personal workspace UX
- Статус: `частично`
- Ветка: `agent/workspace-guided-menu-navigation`
- Базовый commit: `0c2ca41d47498c641d6422f89bd10175b1512c0b`

## Перед началом

### Цель

Сократить установку личного архива до одного основного форумного чата, перевести повседневные команды персонажей и структуры на кнопки и исправить родительскую навигацию кнопок «Назад».

### Исходный контекст

Мастер требовал отдельные назначения для персонажей, общих материалов, референсов, публикаций, аналитики и других функций. Раздел персонажей открывал текстовый терминал с командами, а создание категории, вселенной и истории требовало строки с разделителями. Несколько кнопок «Назад» возвращали к списку модулей вместо фактического предыдущего экрана.

### Планируемый объём

- оставить обязательным только основной архивный чат;
- объяснить остальные подключения как необязательные;
- добавить быстрые действия пространства;
- кнопочно создавать персонажа и назначать ветку;
- кнопочно запускать сохранение материала;
- добавить кнопки редактирования карточки персонажа;
- заменить pipe-формы структуры пошаговым вводом;
- проверить родительские переходы.

### Критерии готовности

- мастер завершается с одним назначением `characters`;
- создание персонажа доступно кнопкой и принимает имя плюс ссылку ветки;
- `/save` имеет кнопочный эквивалент;
- категория, вселенная и история создаются без ручного синтаксиса `|`;
- кнопки назад возвращают в карточку, список, структуру или домашнее меню по контексту;
- полный CI проходит.

### Риски и ограничения

Telegram не позволяет боту из личного сообщения самостоятельно выбрать произвольный групповой чат. Поэтому единственное действие внутри основного форума остаётся командой привязки; все последующие операции выполняются кнопками в ЛС.

## После завершения

### Фактически сделано

- добавлен отдельный guided actions router;
- мастер сокращён до основного архивного чата;
- дополнительные назначения перестали блокировать готовность;
- добавлены быстрые действия, кнопочное создание и сохранение;
- карточка персонажа получила кнопки изменения имени, ветки, промта, алиаса и удаления;
- формы структуры переведены на последовательные шаги;
- исправлены основные parent-back переходы.

### Миграции и совместимость

Миграции не требуются. Старые команды `/create`, `/save`, `/workspace_bind` и текстовый режим персонажей сохранены как совместимый резерв.

### Проверки

Ожидается полный GitHub Actions CI.

### PR и commit

Будут указаны после публикации.

### Незавершённое

После merge требуется живая проверка установки в Telegram, создания персонажа со ссылкой ветки и сохранения файла кнопкой.

### Следующий шаг

Исправить замечания CI, слить PR и выполнить Supervisor Update.
''',
    encoding="utf-8",
)

# Temporary runner files must not survive the feature branch.
Path(__file__).unlink()
workflow = ROOT / ".github/workflows/temp_workspace_guided_menu.yml"
workflow.unlink(missing_ok=True)
