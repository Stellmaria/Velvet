from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"expected one occurrence in {path}: {old!r}; got {count}")
    path.write_text(source.replace(old, new), encoding="utf-8")


guided = ROOT / "velvet_bot/presentation/telegram/routers/workspace_guided_actions.py"
replace_once(
    guided,
    '''from velvet_bot.presentation.telegram.routers.workspace_character_pickers import (
    WorkspaceCharacterPickerCallback,
    build_character_module_keyboard,
)
''',
    '''from velvet_bot.presentation.telegram.routers.workspace_character_pickers import (
    WorkspaceCharacterPickerCallback,
    _render_card,
    _render_list,
)
''',
)
replace_once(
    guided,
    'router = Router(name=__name__)\n_PAGE_SIZE = 8\n',
    'router = Router(name=__name__)\n_PAGE_SIZE = 8\n_OPTIONAL_DESTINATION_KEYS = tuple(\n'
    '    key for key in WORKSPACE_DESTINATION_KEYS if key not in {"characters", "media"}\n'
    ')\n',
)

old_connections = '''def _connections_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📁 Основной архив",
                    callback_data=guided_workspace_callback(
                        "mainchat",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Быстрые действия",
                    callback_data=guided_workspace_callback(
                        "quick",
                        workspace_id=workspace_id,
                    ),
                )
            ],
        ]
    )
'''
new_connections = '''def _connections_keyboard(
    workspace_id: int,
    configured: frozenset[str],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=("✅" if "characters" in configured else "▫️")
                + " 📁 Основной архив",
                callback_data=guided_workspace_callback(
                    "mainchat",
                    workspace_id=workspace_id,
                ),
            )
        ]
    ]
    for index, key in enumerate(_OPTIONAL_DESTINATION_KEYS, start=1):
        spec = DESTINATION_SPECS[key]
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅" if key in configured else "▫️")
                    + f" {spec.emoji} {spec.label}"[:54],
                    callback_data=guided_workspace_callback(
                        "conhelp",
                        workspace_id=workspace_id,
                        item_id=index,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Быстрые действия",
                callback_data=guided_workspace_callback(
                    "quick",
                    workspace_id=workspace_id,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
'''
replace_once(guided, old_connections, new_connections)
replace_once(
    guided,
    '        reply_markup=_connections_keyboard(workspace.id),',
    '        reply_markup=_connections_keyboard(workspace.id, frozenset(configured)),',
)

replace_once(
    guided,
    '''        if action == "mainchat":
            await state.clear()
            await _render_main_chat(callback, workspace)
            return
        if action == "savepick":
''',
    '''        if action == "mainchat":
            await state.clear()
            await _render_main_chat(callback, workspace)
            return
        if action == "conhelp":
            index = int(callback_data.item_id) - 1
            if index < 0 or index >= len(_OPTIONAL_DESTINATION_KEYS):
                raise ValueError("Подключение больше недоступно.")
            key = _OPTIONAL_DESTINATION_KEYS[index]
            spec = DESTINATION_SPECS[key]
            await _edit(
                callback,
                text=(
                    f"<b>{spec.emoji} {escape(spec.label)} · необязательно</b>\\n\\n"
                    f"{escape(spec.description)}\\n\\n"
                    "Подключайте этот чат только когда используете соответствующий "
                    "модуль. Команда отправляется внутри выбранного чата:\\n"
                    f"<code>{escape(spec.command_hint)}</code>"
                ),
                reply_markup=build_prompt_back_keyboard(
                    workspace_id=workspace.id,
                    action="connections",
                    text="↩️ К подключениям",
                ),
            )
            return
        if action == "savepick":
''',
)

replace_once(
    guided,
    '''        if action == "backlist":
            await state.clear()
            await _edit(
                callback,
                text=f"<b>👥 Персонажи · {escape(workspace.name)}</b>",
                reply_markup=await build_character_module_keyboard(
                    database,
                    workspace_id=workspace.id,
                ),
            )
            return
        if action == "backcard":
            await state.clear()
            await callback.answer()
            if isinstance(callback.message, Message):
                await callback.message.edit_reply_markup(
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="👤 Вернуться к карточке",
                                    callback_data=_character_card_callback(
                                        workspace.id,
                                        callback_data.character_id,
                                        callback_data.page,
                                    ),
                                )
                            ]
                        ]
                    )
                )
            return
''',
    '''        if action == "backlist":
            await state.clear()
            await _render_list(
                callback,
                database=database,
                workspace_id=workspace.id,
                workspace_name=workspace.name,
                page_number=callback_data.page,
            )
            return
        if action == "backcard":
            await state.clear()
            await _render_card(
                callback,
                database=database,
                workspace_id=workspace.id,
                character_id=callback_data.character_id,
                list_page=callback_data.page,
            )
            return
''',
)

test = ROOT / "tests/test_workspace_guided_menu.py"
replace_once(
    test,
    '''        ui = (ROOT / "velvet_bot/workspace_ui.py").read_text(encoding="utf-8")
        self.assertIn('workspace_callback("home", workspace_id=workspace_id)', picker)
        self.assertIn('workspace_callback("taxonomy", workspace_id=workspace_id)', ui)
        self.assertNotIn("➕ Как создать персонажа", picker)
''',
    '''        ui = (ROOT / "velvet_bot/workspace_ui.py").read_text(encoding="utf-8")
        guided = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_guided_actions.py"
        ).read_text(encoding="utf-8")
        self.assertIn('workspace_callback("home", workspace_id=workspace_id)', picker)
        self.assertIn('workspace_callback("taxonomy", workspace_id=workspace_id)', ui)
        self.assertIn("await _render_list(", guided)
        self.assertIn("await _render_card(", guided)
        self.assertNotIn("👤 Вернуться к карточке", guided)
        self.assertNotIn("➕ Как создать персонажа", picker)
''',
)

Path(__file__).unlink()
(ROOT / ".github/workflows/temp_polish_workspace_guided_navigation.yml").unlink(
    missing_ok=True
)
