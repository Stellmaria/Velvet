from __future__ import annotations

import ast
import importlib
import unittest
from pathlib import Path

from velvet_bot.presentation.telegram.routers.analytics_controllers.management_aliases import (
    ALIAS_ACTIONS,
)
from velvet_bot.presentation.telegram.routers.analytics_controllers.management_publications import (
    PUBLICATION_ACTIONS,
)
from velvet_bot.presentation.telegram.routers.analytics_controllers.management_tags import (
    TAG_ACTIONS,
)


ROOT = Path(__file__).resolve().parents[1]


class AnalyticsManagementSplitTests(unittest.TestCase):
    def test_action_sets_do_not_overlap(self) -> None:
        self.assertFalse(TAG_ACTIONS & ALIAS_ACTIONS)
        self.assertFalse(TAG_ACTIONS & PUBLICATION_ACTIONS)
        self.assertFalse(ALIAS_ACTIONS & PUBLICATION_ACTIONS)
        self.assertEqual(
            TAG_ACTIONS | ALIAS_ACTIONS | PUBLICATION_ACTIONS,
            {
                "unresolved",
                "tag",
                "tagchars",
                "tagassign",
                "aliases",
                "aliaschar",
                "aliasadd",
                "aliasdel",
                "aliasdelok",
                "review",
                "post",
                "ptype",
                "pauto",
                "reclassify",
            },
        )

    def test_canonical_facade_is_small_and_importable(self) -> None:
        module_name = (
            "velvet_bot.presentation.telegram.routers.analytics_controllers.management"
        )
        module = importlib.import_module(module_name)
        self.assertIsNotNone(module.router)
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/analytics_controllers/management.py"
        ).read_text(encoding="utf-8")
        self.assertLess(len(source.splitlines()), 100)
        self.assertNotIn("list_unresolved_tag_reviews", source)
        self.assertNotIn("set_manual_publication_type", source)
        self.assertNotIn("get_character_alias_summary", source)
        self.assertFalse(
            (ROOT / "velvet_bot/handlers/analytics_management.py").exists()
        )

    def test_domain_modules_are_separate_and_parse(self) -> None:
        root = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/analytics_controllers"
        )
        for name in (
            "management_tags.py",
            "management_aliases.py",
            "management_publications.py",
            "management_common.py",
        ):
            path = root / name
            self.assertTrue(path.is_file())
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_dashboard_override_uses_tag_module_directly(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/analytics_controllers/dashboard_overrides.py"
        ).read_text(encoding="utf-8")
        self.assertIn("management_tags import", source)
        self.assertNotIn(
            "analytics_management import _show_unresolved_queue",
            source,
        )
        self.assertNotIn("velvet_bot.handlers", source)


if __name__ == "__main__":
    unittest.main()
