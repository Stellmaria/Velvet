from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.character_management import (
    create_workspace_character,
    set_workspace_character_universe,
    toggle_workspace_character_story,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.presentation.telegram.routers.workspace_character_pickers import (
    WorkspaceCharacterPickerCallback,
    _load_character_page,
    _load_taxonomy_page,
    _resolve_category_key,
    _resolve_universe,
)

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceCharacterInlinePickerContractTests(unittest.TestCase):
    def test_picker_router_precedes_text_compatibility_router(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        picker_index = source.index(
            "router.include_router(workspace_character_pickers_router)"
        )
        compatibility_index = source.index(
            "router.include_router(workspace_character_management_router)"
        )
        self.assertLess(picker_index, compatibility_index)

    def test_callback_uses_numeric_ids_and_stays_under_telegram_limit(self) -> None:
        packed = WorkspaceCharacterPickerCallback(
            action="storyset",
            workspace_id=999_999_999,
            character_id=9_999_999_999,
            item_id=9_999_999_999,
            page=999,
        ).pack()
        self.assertLessEqual(len(packed.encode("utf-8")), 64)
        self.assertNotIn("custom-universe-key", packed)

    def test_canonical_requirements_name_inline_pickers_as_next_stage(self) -> None:
        requirements = (
            ROOT / "docs/requirements/workspace_product.md"
        ).read_text(encoding="utf-8")
        self.assertIn("редактированию категории", requirements)
        self.assertIn("выбору вселенной", requirements)
        self.assertIn("выбору истории", requirements)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLWorkspaceCharacterInlinePickerTests(unittest.IsolatedAsyncioTestCase):
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
            await connection.execute(
                "DELETE FROM workspaces WHERE id <> $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )
            await connection.execute("DELETE FROM workspace_creation_grants")
            await connection.execute("DELETE FROM user_public_workspace_preferences")

    async def _create_workspace(self, user_id: int, name: str):
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspaces (slug, name, is_system)
                VALUES ($1::VARCHAR, $2::VARCHAR, FALSE)
                RETURNING id
                """,
                f"picker-{int(user_id)}",
                name,
            )
            if row is None:
                raise RuntimeError("Не удалось создать тестовое пространство.")
            await connection.execute(
                """
                INSERT INTO workspace_modules (
                    workspace_id, module_key, is_allowed, is_enabled
                )
                VALUES ($1::BIGINT, 'characters', TRUE, TRUE)
                """,
                int(row["id"]),
            )
        return SimpleNamespace(id=int(row["id"]))

    async def _insert_category(
        self,
        *,
        workspace_id: int,
        key: str,
        label: str,
        emoji: str,
    ) -> int:
        async with self.database.acquire() as connection:
            value = await connection.fetchval(
                """
                INSERT INTO workspace_categories (
                    workspace_id, key, label, emoji
                )
                VALUES ($1::BIGINT, $2::VARCHAR, $3::VARCHAR, $4::VARCHAR)
                RETURNING id
                """,
                int(workspace_id),
                key,
                label,
                emoji,
            )
        return int(value)

    async def _insert_universe(
        self,
        *,
        workspace_id: int,
        key: str,
        label: str,
        emoji: str,
        requires_story: bool,
    ) -> int:
        async with self.database.acquire() as connection:
            value = await connection.fetchval(
                """
                INSERT INTO workspace_universes (
                    workspace_id, key, label, emoji, requires_story
                )
                VALUES (
                    $1::BIGINT, $2::VARCHAR, $3::VARCHAR, $4::VARCHAR, $5::BOOLEAN
                )
                RETURNING id
                """,
                int(workspace_id),
                key,
                label,
                emoji,
                bool(requires_story),
            )
        return int(value)

    async def _insert_story(
        self,
        *,
        workspace_id: int,
        universe_key: str,
        key: str,
        short_label: str,
        title: str,
    ) -> int:
        async with self.database.acquire() as connection:
            value = await connection.fetchval(
                """
                INSERT INTO workspace_stories (
                    workspace_id, universe_key, key, short_label, title
                )
                VALUES (
                    $1::BIGINT, $2::VARCHAR, $3::VARCHAR, $4::VARCHAR, $5::VARCHAR
                )
                RETURNING id
                """,
                int(workspace_id),
                universe_key,
                key,
                short_label,
                title,
            )
        return int(value)

    async def test_category_picker_uses_current_workspace_labels_and_ids(self) -> None:
        first = await self._create_workspace(701, "First")
        second = await self._create_workspace(702, "Second")
        first_category_id = await self._insert_category(
            workspace_id=first.id,
            key="solo",
            label="Сольные первого",
            emoji="🖤",
        )
        second_category_id = await self._insert_category(
            workspace_id=second.id,
            key="solo",
            label="Сольные второго",
            emoji="🤍",
        )
        character, _ = await create_workspace_character(
            self.database,
            workspace_id=first.id,
            name="Каэль",
            created_by=701,
            created_in_chat=1701,
        )

        page = await _load_taxonomy_page(
            self.database,
            workspace_id=first.id,
            character_id=character.id,
            kind="category",
            page=0,
        )

        self.assertEqual(["Сольные первого"], [item.label for item in page.items])
        self.assertEqual([first_category_id], [item.id for item in page.items])
        self.assertEqual(
            "solo",
            await _resolve_category_key(
                self.database,
                workspace_id=first.id,
                item_id=first_category_id,
            ),
        )
        with self.assertRaisesRegex(ValueError, "недоступна"):
            await _resolve_category_key(
                self.database,
                workspace_id=first.id,
                item_id=second_category_id,
            )

    async def test_universe_and_story_picker_reject_foreign_workspace_ids(self) -> None:
        first = await self._create_workspace(703, "Story First")
        second = await self._create_workspace(704, "Story Second")
        first_universe_id = await self._insert_universe(
            workspace_id=first.id,
            key="world",
            label="Мир первого",
            emoji="🌒",
            requires_story=True,
        )
        second_universe_id = await self._insert_universe(
            workspace_id=second.id,
            key="world",
            label="Мир второго",
            emoji="🌕",
            requires_story=True,
        )
        first_story_id = await self._insert_story(
            workspace_id=first.id,
            universe_key="world",
            key="chapter-one",
            short_label="Г1",
            title="Глава первого",
        )
        await self._insert_story(
            workspace_id=second.id,
            universe_key="world",
            key="chapter-one",
            short_label="Г1",
            title="Глава второго",
        )
        character, _ = await create_workspace_character(
            self.database,
            workspace_id=first.id,
            name="Эрик",
            created_by=703,
            created_in_chat=1703,
        )
        await set_workspace_character_universe(
            self.database,
            workspace_id=first.id,
            character_id=character.id,
            universe_key="world",
        )
        self.assertTrue(
            await toggle_workspace_character_story(
                self.database,
                workspace_id=first.id,
                character_id=character.id,
                story_id=first_story_id,
                assigned_by_user_id=703,
            )
        )

        story_page = await _load_taxonomy_page(
            self.database,
            workspace_id=first.id,
            character_id=character.id,
            kind="story",
            page=0,
        )
        self.assertEqual(["Г1 · Глава первого"], [item.label for item in story_page.items])
        self.assertTrue(story_page.items[0].selected)
        self.assertTrue(story_page.items[0].primary)
        self.assertEqual(
            ("world", True),
            await _resolve_universe(
                self.database,
                workspace_id=first.id,
                item_id=first_universe_id,
            ),
        )
        with self.assertRaisesRegex(ValueError, "недоступна"):
            await _resolve_universe(
                self.database,
                workspace_id=first.id,
                item_id=second_universe_id,
            )

    async def test_character_list_uses_workspace_taxonomy_labels(self) -> None:
        workspace = await self._create_workspace(705, "List")
        await self._insert_category(
            workspace_id=workspace.id,
            key="solo",
            label="Сольные",
            emoji="🖤",
        )
        await self._insert_universe(
            workspace_id=workspace.id,
            key="world",
            label="Мой мир",
            emoji="🌒",
            requires_story=False,
        )
        character, _ = await create_workspace_character(
            self.database,
            workspace_id=workspace.id,
            name="Лейн",
            created_by=705,
            created_in_chat=1705,
        )
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                UPDATE characters
                SET category = 'solo', universe = 'world'
                WHERE workspace_id = $1::BIGINT AND id = $2::BIGINT
                """,
                workspace.id,
                character.id,
            )

        page = await _load_character_page(
            self.database,
            workspace_id=workspace.id,
            page=0,
        )
        self.assertEqual(1, page.total_items)
        self.assertEqual("Сольные", page.items[0].category_label)
        self.assertEqual("Мой мир", page.items[0].universe_label)


if __name__ == "__main__":
    unittest.main()
