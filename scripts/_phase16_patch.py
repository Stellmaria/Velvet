from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "velvet_bot/handlers/owner_actions.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
LINES = SOURCE.splitlines()
TREE = ast.parse(SOURCE)
TARGET = next(
    node
    for node in TREE.body
    if isinstance(node, ast.AsyncFunctionDef) and node.name == "handle_owner_action_reply"
)
START = min(item.lineno for item in TARGET.decorator_list)
END = TARGET.end_lineno

package = ROOT / "velvet_bot/presentation/telegram/owner_actions"
package.mkdir(parents=True, exist_ok=True)
for source_name, target_name in (
    ("owner_actions_media.py", "media.py"),
    ("owner_actions_profiles.py", "profiles.py"),
    ("owner_actions_references.py", "references.py"),
    ("owner_actions_data.py", "data.py"),
):
    source = ROOT / "velvet_bot/handlers" / source_name
    target = package / target_name
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    source.unlink()

(package / "__init__.py").write_text(
    '''from velvet_bot.presentation.telegram.owner_actions.data import (\n    DATA_ACTIONS,\n    handle_owner_data_action,\n)\nfrom velvet_bot.presentation.telegram.owner_actions.media import (\n    MEDIA_ACTIONS,\n    handle_owner_media_action,\n)\nfrom velvet_bot.presentation.telegram.owner_actions.profiles import (\n    PROFILE_ACTIONS,\n    handle_owner_profile_action,\n)\nfrom velvet_bot.presentation.telegram.owner_actions.references import (\n    REFERENCE_ACTIONS,\n    handle_owner_reference_action,\n)\n\n__all__ = (\n    "DATA_ACTIONS",\n    "MEDIA_ACTIONS",\n    "PROFILE_ACTIONS",\n    "REFERENCE_ACTIONS",\n    "handle_owner_data_action",\n    "handle_owner_media_action",\n    "handle_owner_profile_action",\n    "handle_owner_reference_action",\n)\n''',
    encoding="utf-8",
)

imports = '''from velvet_bot.presentation.telegram.owner_actions import (\n    handle_owner_data_action,\n    handle_owner_media_action,\n    handle_owner_profile_action,\n    handle_owner_reference_action,\n)\n'''
marker = "from velvet_bot.story_catalog import format_story_release, universe_requires_story\n"
if SOURCE.count(marker) != 1:
    raise RuntimeError("Owner action import marker changed")
SOURCE = SOURCE.replace(marker, marker + imports, 1)
LINES = SOURCE.splitlines()

replacement = '''@router.message(OwnerActionReplyFilter())\nasync def handle_owner_action_reply(\n    message: Message,\n    owner_action: str,\n    database: Database,\n    bot: Bot,\n    audit_logger: TelegramAuditLogger,\n    reference_uploads: ReferenceUploadSessions,\n    analytics_channel_ids: frozenset[int],\n    publication_timezone: str = "Europe/Berlin",\n) -> None:\n    del publication_timezone\n    value = (message.text or message.caption or "").strip()\n    if value.casefold() in {"отмена", "cancel"}:\n        await message.answer(_main_text(), reply_markup=_main_keyboard())\n        return\n\n    actor_id = message.from_user.id if message.from_user else None\n    try:\n        if await handle_owner_media_action(\n            message=message,\n            owner_action=owner_action,\n            value=value,\n            database=database,\n            bot=bot,\n            audit_logger=audit_logger,\n            analytics_channel_ids=analytics_channel_ids,\n            actor_id=actor_id,\n        ):\n            return\n        if await handle_owner_profile_action(\n            message=message,\n            owner_action=owner_action,\n            value=value,\n            database=database,\n            bot=bot,\n            actor_id=actor_id,\n        ):\n            return\n        if await handle_owner_reference_action(\n            message=message,\n            owner_action=owner_action,\n            value=value,\n            database=database,\n            bot=bot,\n            audit_logger=audit_logger,\n            reference_uploads=reference_uploads,\n            actor_id=actor_id,\n        ):\n            return\n        if await handle_owner_data_action(\n            message=message,\n            owner_action=owner_action,\n            value=value,\n            database=database,\n            bot=bot,\n            analytics_channel_ids=analytics_channel_ids,\n            actor_id=actor_id,\n        ):\n            return\n        raise ValueError("Неизвестная форма действия.")\n    except (ValueError, RuntimeError) as error:\n        await message.answer(\n            escape(str(error)),\n            reply_markup=InlineKeyboardMarkup(inline_keyboard=[_back_row()]),\n        )\n'''
new_lines = LINES[: START - 1] + replacement.splitlines() + LINES[END:]
SOURCE_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

(ROOT / "tests/test_phase16_owner_actions_split.py").write_text(
    '''from __future__ import annotations\n\nimport ast\nimport unittest\nfrom pathlib import Path\n\nfrom velvet_bot.presentation.telegram.owner_actions import (\n    DATA_ACTIONS,\n    MEDIA_ACTIONS,\n    PROFILE_ACTIONS,\n    REFERENCE_ACTIONS,\n)\n\n\nROOT = Path(__file__).resolve().parents[1]\n\n\nclass OwnerActionsSplitTests(unittest.TestCase):\n    def test_action_sets_are_disjoint(self) -> None:\n        groups = [MEDIA_ACTIONS, PROFILE_ACTIONS, REFERENCE_ACTIONS, DATA_ACTIONS]\n        for index, left in enumerate(groups):\n            for right in groups[index + 1 :]:\n                self.assertFalse(left & right)\n        self.assertEqual(\n            set().union(*groups),\n            {\n                "save_media", "save_spoiler", "check_post",\n                "import_channel", "import_discussion",\n                "create", "topic", "character", "category", "universe",\n                "prompt", "story", "storyadd", "stories",\n                "refadd", "refs", "refdel",\n                "aliasadd", "aliases", "aliasdel", "tagstats",\n                "trackdiscussion", "discussionstats",\n            },\n        )\n\n    def test_owner_controller_has_no_business_branches(self) -> None:\n        path = ROOT / "velvet_bot/handlers/owner_actions.py"\n        source = path.read_text(encoding="utf-8")\n        tree = ast.parse(source, filename=str(path))\n        function = next(\n            node\n            for node in tree.body\n            if isinstance(node, ast.AsyncFunctionDef)\n            and node.name == "handle_owner_action_reply"\n        )\n        self.assertLessEqual(function.end_lineno - function.lineno + 1, 80)\n        self.assertNotIn("if owner_action == \"create\"", ast.get_source_segment(source, function))\n        self.assertNotIn("if owner_action == \"refadd\"", ast.get_source_segment(source, function))\n\n    def test_subject_modules_parse_and_do_not_import_handlers(self) -> None:\n        package = ROOT / "velvet_bot/presentation/telegram/owner_actions"\n        for path in package.glob("*.py"):\n            source = path.read_text(encoding="utf-8")\n            ast.parse(source, filename=str(path))\n            self.assertNotIn("velvet_bot.handlers", source)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

(ROOT / "scripts/_phase16_patch.py").unlink()
(ROOT / ".github/workflows/phase16-patch.yml").unlink()
