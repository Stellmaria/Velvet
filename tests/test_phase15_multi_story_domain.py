from __future__ import annotations

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.stories import AssignedCharacterStory, StoryRepository
from velvet_bot.multi_story_support import install_multi_story_support


ROOT = Path(__file__).resolve().parents[1]


class MultiStoryDomainTests(unittest.TestCase):
    def test_compat_install_is_a_noop(self) -> None:
        self.assertIsNone(install_multi_story_support())

    def test_runtime_compat_has_no_multi_story_monkeypatch(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/compat.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("multi_story_support", source)
        self.assertNotIn("list_assigned_character_stories =", source)
        self.assertNotIn("install_multi_story_support", source)

    def test_multi_story_facades_have_no_direct_sql(self) -> None:
        for name in ("multi_story_support.py", "multi_story_queries.py"):
            path = ROOT / "velvet_bot" / name
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path))
            self.assertNotIn("_require_pool", source)
            self.assertNotIn("SELECT ", source)

    def test_repository_exposes_multi_story_operations(self) -> None:
        for name in (
            "list_assigned_character_stories",
            "toggle_character_story",
            "clear_character_stories",
        ):
            self.assertTrue(hasattr(StoryRepository, name))

    def test_assigned_model_is_domain_owned(self) -> None:
        story = SimpleNamespace(id=1)
        assigned = AssignedCharacterStory(story=story, is_primary=True)
        self.assertIs(assigned.story, story)
        self.assertTrue(assigned.is_primary)


if __name__ == "__main__":
    unittest.main()
