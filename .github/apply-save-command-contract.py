from pathlib import Path


runtime = Path("velvet_bot/presentation/telegram/save_mode_runtime.py")
text = runtime.read_text(encoding="utf-8")
text = text.replace(
    "from aiogram.types import BotCommand, Message\n",
    "from aiogram.types import Message\n",
    1,
)
text = text.replace(
    '''from velvet_bot.presentation.telegram.routers.core_operations_controllers import (
    workspace_product_experience,
)
''',
    "",
    1,
)
text = text.replace(
    "_ORIGINAL_WORKSPACE_COMMANDS = workspace_product_experience._workspace_commands\n",
    "",
    1,
)
start = text.index("def _workspace_commands_with_save_modes(")
end = text.index("def install_save_command_modes()")
text = text[:start] + text[end:]
old_install = '''    _INSTALLED = True
    workspace_product_experience._workspace_commands = _workspace_commands_with_save_modes
    legacy_save.handle_pending_save_upload = handle_pending_save_upload
'''
new_install = '''    _INSTALLED = True
    legacy_save.handle_pending_save_upload = handle_pending_save_upload
'''
if old_install not in text:
    raise RuntimeError("Save command monkeypatch block not found")
runtime.write_text(text.replace(old_install, new_install, 1), encoding="utf-8")


tests = Path("tests/test_save_single_and_set_modes.py")
text = tests.read_text(encoding="utf-8")
old_import = '''from velvet_bot.presentation.telegram import save_mode_runtime as save_modes
'''
new_import = '''from velvet_bot.presentation.telegram import save_mode_runtime as save_modes
from velvet_bot.presentation.telegram.workspace_command_menu import workspace_commands
'''
if old_import not in text:
    raise RuntimeError("Save mode test import not found")
text = text.replace(old_import, new_import, 1)
text = text.replace(
    'for item in save_modes._workspace_commands_with_save_modes("editor")',
    'for item in workspace_commands("editor")',
    1,
)
tests.write_text(text, encoding="utf-8")
