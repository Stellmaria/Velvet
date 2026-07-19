from __future__ import annotations

import ast
import unittest
from pathlib import Path

from velvet_bot.presentation.telegram.owner_actions import (
    DATA_ACTIONS,
    MEDIA_ACTIONS,
    PROFILE_ACTIONS,
    REFERENCE_ACTIONS,
)


ROOT = Path(__file__).resolve().parents[1]


class OwnerActionsSplitTests(unittest.TestCase):
    def test_action_sets_are_disjoint(self) -> None:
        groups = [MEDIA_ACTIONS, PROFILE_ACTIONS, REFERENCE_ACTIONS, DATA_ACTIONS]
        for index, left in enumerate(groups):
            for right in groups[index + 1 :]:
                self.assertFalse(left & right)
        self.assertEqual(
            set().union(*groups),
            {
                "save_media",
                "save_spoiler",
                "check_post",
                "import_channel",
                "import_discussion",
                "create",
                "topic",
                "character",
                "category",
                "universe",
                "prompt",
                "story",
                "storyadd",
                "stories",
                "refadd",
                "refs",
                "refdel",
                "aliasadd",
                "aliases",
                "aliasdel",
                "tagstats",
                "trackdiscussion",
                "discussionstats",
            },
        )

    def test_owner_controller_has_no_business_branches(self) -> None:
        path = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/"
            "core_operations_controllers/owner_actions.py"
        )
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "handle_owner_action_reply"
        )
        function_source = ast.get_source_segment(source, function) or ""
        self.assertLessEqual(function.end_lineno - function.lineno + 1, 80)
        self.assertNotIn('if owner_action == "create"', function_source)
        self.assertNotIn('if owner_action == "refadd"', function_source)

    def test_subject_modules_parse_and_do_not_import_handlers(self) -> None:
        package = ROOT / "velvet_bot/presentation/telegram/owner_actions"
        for path in package.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path))
            self.assertNotIn("velvet_bot.handlers", source)


if __name__ == "__main__":
    unittest.main()
