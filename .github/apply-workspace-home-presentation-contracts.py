from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Expected one block in {path}, found {count}: {old[:120]!r}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


owner_controls = Path(
    "velvet_bot/presentation/telegram/routers/workspace_owner_controls.py"
)
replace_once(
    owner_controls,
    '''from velvet_bot.presentation.telegram.routers.workspace_guided_ui import (
    guided_workspace_callback,
)
''',
    '''from velvet_bot.presentation.telegram.routers.workspace_guided_ui import (
    guided_workspace_callback,
)
from velvet_bot.presentation.telegram.workspace_command_menu import (
    install_workspace_scoped_commands,
)
''',
)
replace_once(
    owner_controls,
    '''def _workspace_home_keyboard(
    workspace: Workspace,
    *,
    public_enabled: bool,
    modules,
) -> InlineKeyboardMarkup:
    base = build_workspace_home_keyboard(
        workspace,
        public_enabled=public_enabled,
        modules=modules,
    )
    if workspace.is_system:
        return base

    rows = [list(row) for row in base.inline_keyboard]
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
    return InlineKeyboardMarkup(inline_keyboard=rows)
''',
    '''def _workspace_home_keyboard(
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
''',
)
replace_once(
    owner_controls,
    '''    settings = await workspace_product_service._workspaces.get_settings(workspace.id)
    if settings is None:
        await callback.answer("Настройки пространства не найдены.", show_alert=True)
        return
''',
    '''    try:
        settings = await workspace_product_service.get_settings(workspace.id)
        show_button_hints = await workspace_product_service.get_button_hints(
            workspace.id
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
''',
)
text = owner_controls.read_text(encoding="utf-8")
old_keyboard_call = '''                modules=modules,
            ),
'''
new_keyboard_call = '''                modules=modules,
                show_button_hints=show_button_hints,
            ),
'''
if text.count(old_keyboard_call) < 2:
    raise RuntimeError("Missing owner home keyboard calls")
text = text.replace(old_keyboard_call, new_keyboard_call, 2)
old_home_end = '''    await callback.answer()


async def _render_member_home(
'''
new_home_end = '''    await callback.answer()
    await install_workspace_scoped_commands(callback, role=membership.role)


async def _render_member_home(
'''
if old_home_end not in text:
    raise RuntimeError("Missing owner home render end")
text = text.replace(old_home_end, new_home_end, 1)
old_member_settings = '''    settings = await workspace_product_service._workspaces.get_settings(workspace.id)
    if settings is None:
        await callback.answer("Настройки пространства не найдены.", show_alert=True)
        return
'''
new_member_settings = '''    try:
        settings = await workspace_product_service.get_settings(workspace.id)
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
'''
if old_member_settings not in text:
    raise RuntimeError("Missing member settings private access")
text = text.replace(old_member_settings, new_member_settings, 1)
old_member_end = '''    await callback.answer()


async def _render_workspace_selector(
'''
new_member_end = '''    await callback.answer()
    await install_workspace_scoped_commands(callback, role=membership.role)


async def _render_workspace_selector(
'''
if old_member_end not in text:
    raise RuntimeError("Missing member home render end")
owner_controls.write_text(text.replace(old_member_end, new_member_end, 1), encoding="utf-8")


controller = Path(
    "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
    "workspace_product_experience.py"
)
text = controller.read_text(encoding="utf-8")
text = text.replace("import logging\n", "", 1)
text = text.replace("from contextvars import ContextVar\n", "", 1)
text = text.replace(
    "from aiogram.exceptions import TelegramAPIError, TelegramBadRequest\n",
    "from aiogram.exceptions import TelegramBadRequest\n",
    1,
)
old_types = '''from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
'''
new_types = '''from aiogram.types import CallbackQuery, Message
'''
if old_types not in text:
    raise RuntimeError("Missing product controller type imports")
text = text.replace(old_types, new_types, 1)
text = text.replace(
    '''from velvet_bot.presentation.telegram.routers.core_operations_controllers import (
    watermark as core_watermark,
)
''',
    '''from velvet_bot.presentation.telegram.routers.core_operations_controllers import (
    watermark as core_watermark,
)
from velvet_bot.presentation.telegram.workspace_command_menu import (
    set_workspace_chat_commands,
)
''',
    1,
)
text = text.replace("logger = logging.getLogger(__name__)\n", "", 1)
text = text.replace(
    '_ROLE_RANK = {"viewer": 10, "reviewer": 20, "editor": 30, "admin": 40, "owner": 50}\n',
    "",
    1,
)
start = text.index("_SHOW_BUTTON_HINTS: ContextVar[bool]")
end = text.index("def _is_global_owner")
text = text[:start] + text[end:]
start = text.index("def _workspace_commands(")
end = text.index("class PersonalArchiveCommandFilter")
text = text[:start] + text[end:]
text = text.replace("await _set_chat_commands(", "await set_workspace_chat_commands(")
old_hint_keyboard = '''    token = _SHOW_BUTTON_HINTS.set(show_button_hints)
    try:
        keyboard = _home_keyboard_with_hint_toggle(
            workspace,
            public_enabled=settings.public_archive_enabled,
            modules=modules,
        )
    finally:
        _SHOW_BUTTON_HINTS.reset(token)
'''
new_hint_keyboard = '''    keyboard = workspace_owner_controls._workspace_home_keyboard(
        workspace,
        public_enabled=settings.public_archive_enabled,
        modules=modules,
        show_button_hints=show_button_hints,
    )
'''
if old_hint_keyboard not in text:
    raise RuntimeError("Missing hint keyboard ContextVar block")
text = text.replace(old_hint_keyboard, new_hint_keyboard, 1)
start = text.index("def install_workspace_product_experience()")
end = text.index("__all__ =")
text = text[:start] + text[end:]
text = text.replace(
    '''__all__ = (
    "install_workspace_product_experience",
    "router",
)
''',
    '''__all__ = ("router",)
''',
    1,
)
controller.write_text(text, encoding="utf-8")


owner_menu = Path(
    "velvet_bot/presentation/telegram/routers/core_operations_controllers/owner_menu.py"
)
replace_once(
    owner_menu,
    '''from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_product_experience import (
    install_workspace_product_experience,
    router as workspace_product_experience_router,
)

install_workspace_product_experience()
''',
    '''from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_product_experience import (
    router as workspace_product_experience_router,
)
''',
)


tests = Path("tests/test_workspace_commands_and_watermark_drafts.py")
text = tests.read_text(encoding="utf-8")
old_import = '''from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_product_experience import (
    _SHOW_BUTTON_HINTS,
    _home_keyboard_with_hint_toggle,
    _workspace_commands,
)
'''
new_import = '''from velvet_bot.presentation.telegram.routers.workspace_owner_controls import (
    _workspace_home_keyboard,
)
from velvet_bot.presentation.telegram.workspace_command_menu import workspace_commands
'''
if old_import not in text:
    raise RuntimeError("Missing legacy workspace presentation test imports")
text = text.replace(old_import, new_import, 1)
text = text.replace("_workspace_commands(", "workspace_commands(")
old_hidden = '''        token = _SHOW_BUTTON_HINTS.set(False)
        try:
            keyboard = _home_keyboard_with_hint_toggle(
                _workspace(), public_enabled=False, modules=_modules()
            )
        finally:
            _SHOW_BUTTON_HINTS.reset(token)
'''
new_hidden = '''        keyboard = _workspace_home_keyboard(
            _workspace(),
            public_enabled=False,
            modules=_modules(),
            show_button_hints=False,
        )
'''
if old_hidden not in text:
    raise RuntimeError("Missing hidden hints test block")
text = text.replace(old_hidden, new_hidden, 1)
old_visible = '''        token = _SHOW_BUTTON_HINTS.set(True)
        try:
            keyboard = _home_keyboard_with_hint_toggle(
                _workspace(), public_enabled=False, modules=_modules()
            )
        finally:
            _SHOW_BUTTON_HINTS.reset(token)
'''
new_visible = '''        keyboard = _workspace_home_keyboard(
            _workspace(),
            public_enabled=False,
            modules=_modules(),
            show_button_hints=True,
        )
'''
if old_visible not in text:
    raise RuntimeError("Missing visible hints test block")
tests.write_text(text.replace(old_visible, new_visible, 1), encoding="utf-8")
