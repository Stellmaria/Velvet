from __future__ import annotations

import os
import unittest
from pathlib import Path

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.directory_catalog import (
    list_workspace_directory_categories,
    list_workspace_directory_characters,
    list_workspace_directory_stories,
    list_workspace_directory_universes,
)


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceRequirementsContractTests(unittest.TestCase):
    def test_workspace_requirements_are_pinned_as_normative_specification(self) -> None:
        path = ROOT / "docs/specifications/workspace_requirements.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("официальное техническое задание проекта", text)
        self.assertIn("## 15. Следующий этап", text)
        self.assertIn("подключить workspace taxonomy", text)
        self.assertIn("ролям команды", text)

    def test_workspace_catalog_router_is_registered_before_legacy_directory(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        self.assertLess(
            source.index("router.include_router(workspace_directory_catalog_router)"),
            source.index("router.include_router(admin_directory_router)"),
        )


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLWorkspaceDirectoryCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        await self._reset()

    async def asyncTearDown(self) -> None:
        await self._reset()
        await self.database.close()

    async def _reset(self) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                TRUNCATE
                    workspace_character_aliases,
                    workspace_character_story_links,
                    character_media,
                    media_files,
                    characters
                RESTART IDENTITY CASCADE
                """
            )
            await connection.execute("DELETE FROM workspaces WHERE id <> 1")

    async def _workspace(self, slug: str, owner_id: int) -> int:
        async with self.database.acquire() as connection:
            workspace_id = int(
                await connection.fetchval(
                    """
                    INSERT INTO workspaces (slug, name, is_system)
                    VALUES ($1::VARCHAR, $2::VARCHAR, FALSE)
                    RETURNING id
                    """,
                    slug,
                    slug.title(),
                )
            )
            await connection.execute(
                """
                INSERT INTO workspace_settings (workspace_id)
                VALUES ($1::BIGINT)
                """,
                workspace_id,
            )
            await connection.execute(
                """
                INSERT INTO workspace_members (workspace_id, user_id, role)
                VALUES ($1::BIGINT, $2::BIGINT, 'owner')
                """,
                workspace_id,
                owner_id,
            )
            await connection.executemany(
                """
                INSERT INTO workspace_modules (
                    workspace_id, module_key, is_allowed, is_enabled
                )
                VALUES ($1::BIGINT, $2::VARCHAR, TRUE, TRUE)
                """,
                [(workspace_id, "characters"), (workspace_id, "taxonomy")],
            )
        return workspace_id

    async def _seed_catalog(self, workspace_id: int, suffix: str) -> tuple[int, int]:
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO workspace_categories (
                    workspace_id, key, label, emoji, sort_order
                )
                VALUES
                    ($1::BIGINT, 'hero', $2::VARCHAR, '🖤', 10),
                    ($1::BIGINT, 'pair', $3::VARCHAR, '🫂', 20)
                """,
                workspace_id,
                f"Герои {suffix}",
                f"Пары {suffix}",
            )
            universe_id = int(
                await connection.fetchval(
                    """
                    INSERT INTO workspace_universes (
                        workspace_id, key, label, emoji, requires_story, sort_order
                    )
                    VALUES ($1::BIGINT, 'world', $2::VARCHAR, '🌒', TRUE, 10)
                    RETURNING id
                    """,
                    workspace_id,
                    f"Мир {suffix}",
                )
            )
            story_id = int(
                await connection.fetchval(
                    """
                    INSERT INTO workspace_stories (
                        workspace_id, universe_key, key, short_label, title, sort_order
                    )
                    VALUES (
                        $1::BIGINT, 'world', 'chapter', 'Г1', $2::VARCHAR, 10
                    )
                    RETURNING id
                    """,
                    workspace_id,
                    f"Глава {suffix}",
                )
            )
        return universe_id, story_id

    async def test_taxonomy_filters_are_workspace_scoped(self) -> None:
        first = await self._workspace("first-catalog", 8101)
        second = await self._workspace("second-catalog", 8102)
        _, first_story = await self._seed_catalog(first, "A")
        _, second_story = await self._seed_catalog(second, "B")

        async with self.database.acquire() as connection:
            first_character = int(
                await connection.fetchval(
                    """
                    INSERT INTO characters (
                        workspace_id, name, normalized_name, category, universe
                    )
                    VALUES ($1::BIGINT, 'Каэль', 'каэль', 'hero', 'world')
                    RETURNING id
                    """,
                    first,
                )
            )
            second_character = int(
                await connection.fetchval(
                    """
                    INSERT INTO characters (
                        workspace_id, name, normalized_name, category, universe
                    )
                    VALUES ($1::BIGINT, 'Эрик', 'эрик', 'hero', 'world')
                    RETURNING id
                    """,
                    second,
                )
            )
            await connection.executemany(
                """
                INSERT INTO workspace_character_story_links (
                    workspace_id, character_id, story_id, is_primary
                )
                VALUES ($1::BIGINT, $2::BIGINT, $3::BIGINT, TRUE)
                """,
                [
                    (first, first_character, first_story),
                    (second, second_character, second_story),
                ],
            )

        first_categories = await list_workspace_directory_categories(
            self.database,
            workspace_id=first,
        )
        second_categories = await list_workspace_directory_categories(
            self.database,
            workspace_id=second,
        )
        self.assertEqual("Герои A", first_categories[0].label)
        self.assertEqual("Герои B", second_categories[0].label)
        self.assertEqual(1, first_categories[0].character_count)
        self.assertEqual(1, second_categories[0].character_count)

        first_universes = await list_workspace_directory_universes(
            self.database,
            workspace_id=first,
            category_key="hero",
        )
        self.assertEqual("Мир A", first_universes[0].label)
        self.assertEqual(1, first_universes[0].character_count)

        first_stories = await list_workspace_directory_stories(
            self.database,
            workspace_id=first,
            universe_key="world",
        )
        self.assertEqual((first_story,), tuple(item.id for item in first_stories))
        self.assertEqual(1, first_stories[0].character_count)

        page = await list_workspace_directory_characters(
            self.database,
            workspace_id=first,
            category_key="hero",
            universe_key="world",
            story_id=first_story,
        )
        self.assertEqual(1, page.total_items)
        self.assertEqual("Каэль", page.items[0].name)
        self.assertEqual("Герои A", page.items[0].category_label)
        self.assertEqual("Мир A", page.items[0].universe_label)
        self.assertEqual("Г1", page.items[0].primary_story_short_label)

        with self.assertRaisesRegex(ValueError, "История не найдена"):
            await list_workspace_directory_characters(
                self.database,
                workspace_id=first,
                story_id=second_story,
            )


if __name__ == "__main__":
    unittest.main()
