from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one block in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


policy = Path("velvet_bot/core/access/policy.py")
replace_once(
    policy,
    """    "wlogo:",
    "wm:",
)
""",
    """    "wlogo:",
    "wmtpl:",
    "wm:",
)
""",
)

controller = Path(
    "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
    "workspace_product_experience.py"
)
text = controller.read_text(encoding="utf-8")
old = "from velvet_bot.presentation.telegram.middleware import access as access_middleware\n"
if old not in text:
    raise RuntimeError("Missing access middleware import")
text = text.replace(old, "", 1)
old = "_ORIGINAL_MEMBER_CALLBACK_CHECK = access_middleware.is_workspace_member_callback_data\n"
if old not in text:
    raise RuntimeError("Missing original callback classifier alias")
text = text.replace(old, "", 1)
start = text.index("def _workspace_callback_with_template(")
end = text.index("class PersonalArchiveCommandFilter")
text = text[:start] + text[end:]
old = """    access_middleware.is_workspace_member_callback_data = (
        _workspace_callback_with_template
    )
"""
if old not in text:
    raise RuntimeError("Missing callback classifier monkeypatch")
text = text.replace(old, "", 1)
controller.write_text(text, encoding="utf-8")

existing_test = Path("tests/test_workspace_commands_and_watermark_drafts.py")
text = existing_test.read_text(encoding="utf-8")
text = text.replace(
    """from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_product_experience import (
    _SHOW_BUTTON_HINTS,
    _home_keyboard_with_hint_toggle,
    _workspace_callback_with_template,
    _workspace_commands,
)
""",
    """from velvet_bot.core.access import is_workspace_member_callback_data
from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_product_experience import (
    _SHOW_BUTTON_HINTS,
    _home_keyboard_with_hint_toggle,
    _workspace_commands,
)
""",
    1,
)
text = text.replace(
    'self.assertTrue(_workspace_callback_with_template("wmtpl:show:9:"))',
    'self.assertTrue(is_workspace_member_callback_data("wmtpl:show:9:"))',
    1,
)
existing_test.write_text(text, encoding="utf-8")
