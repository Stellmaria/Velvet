from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path
from types import SimpleNamespace

from velvet_bot.database import Database
from velvet_bot.domains.characters import CharacterDirectoryRepository
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


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class MultiStoryPostgreSQLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database._require_pool().acquire() as connection:
            await connection.execute(
                """
                TRUNCATE
                    character_story_links,
                    character_media,
                    characters
                RESTART IDENTITY CASCADE
                """
            )
            self.character_id = int(
                await connection.fetchval(
                    """
                    INSERT INTO characters (
                        name, normalized_name, created_by, created_in_chat,
                        category, universe
                    )
                    VALUES ('Фаза 15', 'фаза 15', 1, 1, 'male', 'kr')
                    RETURNING id
                    """
                )
            )
            rows = await connection.fetch(
                """
                SELECT id
                FROM character_stories
                WHERE universe = 'kr'
                ORDER BY release_order DESC, id
                LIMIT 2
                """
            )
        if len(rows) < 2:
            self.skipTest("Для integration test нужны две истории КР.")
        self.first_story_id = int(rows[0]["id"])
        self.second_story_id = int(rows[1]["id"])
        self.stories = StoryRepository(self.database)
        self.characters = CharacterDirectoryRepository(self.database)

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_links_filters_primary_and_universe_cleanup(self) -> None:
        self.assertTrue(
            await self.stories.toggle_character_story(
                character_id=self.character_id,
                story_id=self.first_story_id,
                assigned_by=1,
            )
        )
        self.assertTrue(
            await self.stories.toggle_character_story(
                character_id=self.character_id,
                story_id=self.second_story_id,
                assigned_by=1,
            )
        )

        assigned = await self.stories.list_assigned_character_stories(
            character_id=self.character_id
        )
        self.assertEqual(2, len(assigned))
        self.assertTrue(assigned[0].is_primary)
        self.assertEqual(self.first_story_id, assigned[0].story.id)

        page = await self.characters.list_directory(
            category="male",
            universe="kr",
            story_id=self.second_story_id,
            public_only=False,
        )
        self.assertEqual([self.character_id], [item.character.id for item in page.items])

        self.assertFalse(
            await self.stories.toggle_character_story(
                character_id=self.character_id,
                story_id=self.first_story_id,
                assigned_by=1,
            )
        )
        assigned = await self.stories.list_assigned_character_stories(
            character_id=self.character_id
        )
        self.assertEqual(1, len(assigned))
        self.assertTrue(assigned[0].is_primary)
        self.assertEqual(self.second_story_id, assigned[0].story.id)

        async with self.database._require_pool().acquire() as connection:
            primary_story_id = await connection.fetchval(
                "SELECT story_id FROM characters WHERE id = $1",
                self.character_id,
            )
        self.assertEqual(self.second_story_id, int(primary_story_id))

        await self.characters.set_universe(
            character_id=self.character_id,
            universe="original",
        )
        self.assertEqual(
            [],
            await self.stories.list_assigned_character_stories(
                character_id=self.character_id
            ),
        )
        async with self.database._require_pool().acquire() as connection:
            primary_story_id = await connection.fetchval(
                "SELECT story_id FROM characters WHERE id = $1",
                self.character_id,
            )
        self.assertIsNone(primary_story_id)


if __name__ == "__main__":
    unittest.main()
