from __future__ import annotations

import os
import unittest
from pathlib import Path

from velvet_bot.character_directory import (
    get_character_directory_item,
    list_category_summaries,
    list_character_directory,
)
from velvet_bot.database import Database
from velvet_bot.public_catalog import (
    list_public_categories,
    list_public_characters,
    list_public_stories,
    list_public_universes,
)


ROOT = Path(__file__).resolve().parents[1]
_PREFIX = "catalog-test-"


class WorkspaceRequirementsContractTests(unittest.TestCase):
    def test_canonical_workspace_requirements_are_committed(self) -> None:
        path = ROOT / "docs/requirements/workspace_product.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("Статус: обязательное проектное требование", text)
        self.assertIn("## 15. Следующий этап", text)
        self.assertIn("фильтрам каталога", text)
        self.assertIn("ролям команды", text)

    def test_character_directory_facade_exposes_workspace_scope(self) -> None:
        source = (ROOT / "velvet_bot/character_directory.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("workspace_id: int = DEFAULT_WORKSPACE_ID", source)
        self.assertIn("list_workspace_character_directory", source)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class WorkspaceTaxonomyCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        await self._cleanup()
        self.first = await self._create_workspace("first")
        self.second = await self._create_workspace("second")

    async def asyncTearDown(self) -> None:
        await self._cleanup()
        await self.database.close()

    async def _cleanup(self) -> None:
        async with self.database.acquire() as connection:
            workspace_ids = await connection.fetch(
                "SELECT id FROM workspaces WHERE slug LIKE $1::TEXT",
                f"{_PREFIX}%",
            )
            ids = [int(row["id"]) for row in workspace_ids]
            if ids:
                await connection.execute(
                    "DELETE FROM characters WHERE workspace_id = ANY($1::BIGINT[])",
                    ids,
                )
                await connection.execute(
                    "DELETE FROM workspaces WHERE id = ANY($1::BIGINT[])",
                    ids,
                )
            await connection.execute(
                "DELETE FROM media_files WHERE telegram_file_unique_id LIKE $1::TEXT",
                f"{_PREFIX}%",
            )

    async def _create_workspace(self, suffix: str) -> int:
        async with self.database.acquire() as connection:
            workspace_id = await connection.fetchval(
                """
                INSERT INTO workspaces (slug, name, is_system)
                VALUES ($1::VARCHAR, $2::VARCHAR, FALSE)
                RETURNING id
                """,
                f"{_PREFIX}{suffix}",
                f"Catalog {suffix}",
            )
            await connection.execute(
                """
                INSERT INTO workspace_settings (
                    workspace_id,
                    public_archive_enabled,
                    downloads_mode,
                    qwen_enabled
                )
                VALUES ($1::BIGINT, TRUE, 'original', FALSE)
                """,
                int(workspace_id),
            )
        return int(workspace_id)

    async def _taxonomy(
        self,
        workspace_id: int,
        *,
        category_label: str,
        universe_label: str,
    ) -> int:
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO workspace_categories (
                    workspace_id, key, label, emoji, sort_order
                )
                VALUES ($1::BIGINT, 'solo', $2::VARCHAR, '🖤', 10)
                """,
                workspace_id,
                category_label,
            )
            await connection.execute(
                """
                INSERT INTO workspace_categories (
                    workspace_id, key, label, emoji, sort_order
                )
                VALUES ($1::BIGINT, 'empty', 'Пустая', '📁', 20)
                """,
                workspace_id,
            )
            await connection.execute(
                """
                INSERT INTO workspace_universes (
                    workspace_id, key, label, emoji, requires_story, sort_order
                )
                VALUES ($1::BIGINT, 'my-world', $2::VARCHAR, '🌒', TRUE, 10)
                """,
                workspace_id,
                universe_label,
            )
            story_id = await connection.fetchval(
                """
                INSERT INTO workspace_stories (
                    workspace_id,
                    universe_key,
                    key,
                    short_label,
                    title,
                    sort_order
                )
                VALUES (
                    $1::BIGINT,
                    'my-world',
                    'first-chapter',
                    'Г1',
                    'Первая глава',
                    10
                )
                RETURNING id
                """,
                workspace_id,
            )
        return int(story_id)

    async def _character(
        self,
        workspace_id: int,
        *,
        name: str,
        with_story: int | None,
        public_media: bool = True,
    ) -> int:
        character, _ = await self.database.create_character(
            name,
            created_by=9001,
            created_in_chat=8001,
            workspace_id=workspace_id,
        )
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                UPDATE characters
                SET category = 'solo',
                    universe = 'my-world'
                WHERE id = $1::BIGINT
                  AND workspace_id = $2::BIGINT
                """,
                character.id,
                workspace_id,
            )
            media_id = await connection.fetchval(
                """
                INSERT INTO media_files (
                    telegram_file_id,
                    telegram_file_unique_id,
                    storage_file_name,
                    media_type,
                    mime_type,
                    file_size
                )
                VALUES (
                    $1::TEXT,
                    $2::TEXT,
                    $3::TEXT,
                    'photo',
                    'image/jpeg',
                    1024
                )
                RETURNING id
                """,
                f"file-{workspace_id}-{character.id}",
                f"{_PREFIX}{workspace_id}-{character.id}",
                f"{_PREFIX}{workspace_id}-{character.id}.jpg",
            )
            await connection.execute(
                """
                INSERT INTO character_media (
                    character_id,
                    media_id,
                    saved_by,
                    saved_in_chat,
                    source_chat_id,
                    source_message_id,
                    command_message_id,
                    is_public,
                    requires_adult_channel
                )
                VALUES (
                    $1::BIGINT,
                    $2::BIGINT,
                    9001,
                    8001,
                    8001,
                    $3::BIGINT,
                    $3::BIGINT,
                    $4::BOOLEAN,
                    FALSE
                )
                """,
                character.id,
                int(media_id),
                100000 + character.id,
                public_media,
            )
            if with_story is not None:
                await connection.execute(
                    """
                    INSERT INTO workspace_character_story_links (
                        workspace_id,
                        character_id,
                        story_id,
                        is_primary,
                        assigned_by_user_id
                    )
                    VALUES (
                        $1::BIGINT,
                        $2::BIGINT,
                        $3::BIGINT,
                        TRUE,
                        9001
                    )
                    """,
                    workspace_id,
                    character.id,
                    with_story,
                )
        return character.id

    async def test_public_catalog_uses_workspace_labels_and_primary_story(self) -> None:
        first_story = await self._taxonomy(
            self.first,
            category_label="Сольные первого",
            universe_label="Мир первого",
        )
        await self._taxonomy(
            self.second,
            category_label="Сольные второго",
            universe_label="Мир второго",
        )
        character_id = await self._character(
            self.first,
            name="Каэль",
            with_story=first_story,
        )

        categories = await list_public_categories(
            self.database,
            workspace_id=self.first,
        )
        self.assertEqual(
            [("solo", "Сольные первого", 1)],
            [(item.key, item.label, item.character_count) for item in categories],
        )

        universes = await list_public_universes(
            self.database,
            workspace_id=self.first,
            category="solo",
        )
        self.assertEqual(
            [("my-world", "Мир первого", 1)],
            [(item.key, item.label, item.character_count) for item in universes],
        )

        stories = await list_public_stories(
            self.database,
            workspace_id=self.first,
            category="solo",
            universe="my-world",
        )
        self.assertEqual(
            [(first_story, "Г1", "Первая глава", 1)],
            [
                (item.id, item.short_label, item.title, item.character_count)
                for item in stories
            ],
        )

        page = await list_public_characters(
            self.database,
            workspace_id=self.first,
            category="solo",
            universe="my-world",
            story_id=first_story,
        )
        self.assertEqual(1, page.total_characters)
        self.assertEqual(character_id, page.items[0].character.id)
        self.assertEqual(self.first, page.items[0].character.workspace_id)
        self.assertEqual(first_story, page.items[0].story_id)
        self.assertEqual("Г1", page.items[0].story_short_label)

    async def test_required_story_hides_unlinked_character(self) -> None:
        story_id = await self._taxonomy(
            self.first,
            category_label="Сольные",
            universe_label="Мир",
        )
        character_id = await self._character(
            self.first,
            name="Без истории",
            with_story=None,
        )

        self.assertEqual(
            [],
            await list_public_categories(
                self.database,
                workspace_id=self.first,
            ),
        )
        private = await list_category_summaries(
            self.database,
            workspace_id=self.first,
            public_only=False,
        )
        self.assertEqual(
            [("solo", 1), ("empty", 0)],
            [(item.key, item.character_count) for item in private],
        )

        async with self.database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO workspace_character_story_links (
                    workspace_id,
                    character_id,
                    story_id,
                    is_primary,
                    assigned_by_user_id
                )
                VALUES ($1::BIGINT, $2::BIGINT, $3::BIGINT, TRUE, 9001)
                """,
                self.first,
                character_id,
                story_id,
            )
        categories = await list_public_categories(
            self.database,
            workspace_id=self.first,
        )
        self.assertEqual(
            [("solo", 1)],
            [(item.key, item.character_count) for item in categories],
        )

    async def test_same_keys_and_story_ids_are_isolated_by_workspace(self) -> None:
        first_story = await self._taxonomy(
            self.first,
            category_label="Первый",
            universe_label="Первый мир",
        )
        second_story = await self._taxonomy(
            self.second,
            category_label="Второй",
            universe_label="Второй мир",
        )
        first_character = await self._character(
            self.first,
            name="Первый герой",
            with_story=first_story,
        )
        second_character = await self._character(
            self.second,
            name="Второй герой",
            with_story=second_story,
        )

        first_item = await get_character_directory_item(
            self.database,
            first_character,
            workspace_id=self.first,
        )
        self.assertIsNotNone(first_item)
        self.assertIsNone(
            await get_character_directory_item(
                self.database,
                second_character,
                workspace_id=self.first,
            )
        )

        with self.assertRaisesRegex(ValueError, "История не найдена"):
            await list_character_directory(
                self.database,
                workspace_id=self.first,
                category="solo",
                universe="my-world",
                story_id=second_story,
                public_only=False,
            )


if __name__ == "__main__":
    unittest.main()
