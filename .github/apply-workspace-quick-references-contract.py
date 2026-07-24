from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Expected one block in {path}, found {count}: {old[:120]!r}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


guided = Path(
    "velvet_bot/presentation/telegram/routers/workspace_guided_actions.py"
)
replace_once(
    guided,
    '''    if "taxonomy" in enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗂 Структура архива",
                    callback_data=workspace_callback(
                        "taxonomy",
                        workspace_id=workspace_id,
                    ),
                )
            ]
        )
    rows.extend(
''',
    '''    if "taxonomy" in enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗂 Структура архива",
                    callback_data=workspace_callback(
                        "taxonomy",
                        workspace_id=workspace_id,
                    ),
                )
            ]
        )
    if "references" in enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🧬 Референсы",
                    callback_data=workspace_callback(
                        "module",
                        workspace_id=workspace_id,
                        module_key="references",
                    ),
                )
            ]
        )
    rows.extend(
''',
)

controller = Path(
    "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
    "workspace_product_experience.py"
)
replace_once(
    controller,
    "from velvet_bot.presentation.telegram.routers import workspace_guided_actions\n",
    "",
)
replace_once(
    controller,
    "_ORIGINAL_QUICK_KEYBOARD = workspace_guided_actions._quick_keyboard\n",
    "",
)
text = controller.read_text(encoding="utf-8")
start = text.index("def _quick_keyboard_with_references(")
end = text.index("class PersonalArchiveCommandFilter")
text = text[:start] + text[end:]
old_install = (
    "    workspace_owner_controls._render_member_home = "
    "_render_member_home_with_commands\n"
    "    workspace_guided_actions._quick_keyboard = "
    "_quick_keyboard_with_references\n"
)
new_install = (
    "    workspace_owner_controls._render_member_home = "
    "_render_member_home_with_commands\n"
)
if old_install not in text:
    raise RuntimeError("Missing quick keyboard runtime assignment")
controller.write_text(text.replace(old_install, new_install, 1), encoding="utf-8")
