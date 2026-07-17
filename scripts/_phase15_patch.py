from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_all(path: str, old: str, new: str, expected: int) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"Expected {expected} matches in {path}, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


replace_once(
    "velvet_bot/domains/stories/models.py",
    '''@dataclass(frozen=True, slots=True)\nclass StorySummary:\n''',
    '''@dataclass(frozen=True, slots=True)\nclass AssignedCharacterStory:\n    story: CharacterStory\n    is_primary: bool\n\n\n@dataclass(frozen=True, slots=True)\nclass StorySummary:\n''',
)
replace_once(
    "velvet_bot/domains/stories/models.py",
    '__all__ = ("CharacterStory", "StoryPage", "StorySummary")\n',
    '__all__ = ("AssignedCharacterStory", "CharacterStory", "StoryPage", "StorySummary")\n',
)
replace_once(
    "velvet_bot/domains/stories/__init__.py",
    'from velvet_bot.domains.stories.models import CharacterStory, StoryPage, StorySummary\n',
    '''from velvet_bot.domains.stories.models import (\n    AssignedCharacterStory,\n    CharacterStory,\n    StoryPage,\n    StorySummary,\n)\n''',
)
replace_once(
    "velvet_bot/domains/stories/__init__.py",
    '    "CharacterStory",\n',
    '    "AssignedCharacterStory",\n    "CharacterStory",\n',
)

replace_once(
    "velvet_bot/domains/characters/repository.py",
    '''    async def set_universe(self, *, character_id: int, universe: str | None) -> None:\n        async with self._database._require_pool().acquire() as connection:\n            result = await connection.execute(\n                """\n                UPDATE characters\n                SET story_id = CASE\n                        WHEN universe IS NOT DISTINCT FROM $2::VARCHAR THEN story_id\n                        ELSE NULL\n                    END,\n                    universe = $2::VARCHAR\n                WHERE id = $1::BIGINT\n                """,\n                int(character_id),\n                universe,\n            )\n        if result == "UPDATE 0":\n            raise ValueError("Персонаж не найден.")\n''',
    '''    async def set_universe(self, *, character_id: int, universe: str | None) -> None:\n        async with self._database._require_pool().acquire() as connection:\n            async with connection.transaction():\n                current = await connection.fetchrow(\n                    "SELECT universe FROM characters WHERE id = $1::BIGINT FOR UPDATE",\n                    int(character_id),\n                )\n                if current is None:\n                    raise ValueError("Персонаж не найден.")\n                if current["universe"] != universe:\n                    await connection.execute(\n                        "DELETE FROM character_story_links WHERE character_id = $1::BIGINT",\n                        int(character_id),\n                    )\n                    await connection.execute(\n                        """\n                        UPDATE characters\n                        SET universe = $2::VARCHAR, story_id = NULL\n                        WHERE id = $1::BIGINT\n                        """,\n                        int(character_id),\n                        universe,\n                    )\n                else:\n                    await connection.execute(\n                        "UPDATE characters SET universe = $2::VARCHAR WHERE id = $1::BIGINT",\n                        int(character_id),\n                        universe,\n                    )\n''',
)
replace_all(
    "velvet_bot/domains/characters/repository.py",
    "OR c.story_id IS NOT NULL",
    '''OR EXISTS (\n                                SELECT 1\n                                FROM character_story_links AS ready_link\n                                WHERE ready_link.character_id = c.id\n                            )''',
    3,
)
replace_once(
    "velvet_bot/domains/characters/repository.py",
    '        story_condition = "($4::BIGINT IS NULL OR c.story_id = $4)"\n',
    '''        story_condition = """\n            ($4::BIGINT IS NULL OR EXISTS (\n                SELECT 1\n                FROM character_story_links AS selected_link\n                WHERE selected_link.character_id = c.id\n                  AND selected_link.story_id = $4::BIGINT\n            ))\n        """\n''',
)

replace_once(
    "velvet_bot/domains/stories/repository.py",
    'from velvet_bot.domains.stories.models import CharacterStory, StoryPage, StorySummary\n',
    '''from velvet_bot.domains.stories.models import (\n    AssignedCharacterStory,\n    CharacterStory,\n    StoryPage,\n    StorySummary,\n)\n''',
)
replace_once(
    "velvet_bot/domains/stories/repository.py",
    '''    async def set_character_story(\n        self,\n        *,\n        character_id: int,\n        story_id: int | None,\n    ) -> None:\n        async with self._database._require_pool().acquire() as connection:\n            if story_id is None:\n                result = await connection.execute(\n                    """\n                    UPDATE characters\n                    SET story_id = NULL\n                    WHERE id = $1::BIGINT\n                    """,\n                    int(character_id),\n                )\n            else:\n                result = await connection.execute(\n                    """\n                    UPDATE characters AS c\n                    SET story_id = s.id\n                    FROM character_stories AS s\n                    WHERE c.id = $1::BIGINT\n                      AND s.id = $2::BIGINT\n                      AND c.universe = s.universe\n                    """,\n                    int(character_id),\n                    int(story_id),\n                )\n        if result == "UPDATE 0":\n            raise ValueError(\n                "Персонаж не найден или история относится к другой вселенной."\n            )\n''',
    '''    async def set_character_story(\n        self,\n        *,\n        character_id: int,\n        story_id: int | None,\n    ) -> None:\n        async with self._database._require_pool().acquire() as connection:\n            async with connection.transaction():\n                character = await connection.fetchrow(\n                    "SELECT id, universe FROM characters WHERE id = $1::BIGINT FOR UPDATE",\n                    int(character_id),\n                )\n                if character is None:\n                    raise ValueError("Персонаж не найден.")\n                if story_id is not None:\n                    story = await connection.fetchrow(\n                        "SELECT id, universe FROM character_stories WHERE id = $1::BIGINT",\n                        int(story_id),\n                    )\n                    if story is None or story["universe"] != character["universe"]:\n                        raise ValueError(\n                            "История относится к другой вселенной или больше не существует."\n                        )\n                await connection.execute(\n                    "DELETE FROM character_story_links WHERE character_id = $1::BIGINT",\n                    int(character_id),\n                )\n                if story_id is not None:\n                    await connection.execute(\n                        """\n                        INSERT INTO character_story_links (character_id, story_id, is_primary)\n                        VALUES ($1::BIGINT, $2::BIGINT, TRUE)\n                        """,\n                        int(character_id),\n                        int(story_id),\n                    )\n                await connection.execute(\n                    "UPDATE characters SET story_id = $2::BIGINT WHERE id = $1::BIGINT",\n                    int(character_id),\n                    int(story_id) if story_id is not None else None,\n                )\n\n    async def list_assigned_character_stories(\n        self,\n        *,\n        character_id: int,\n    ) -> list[AssignedCharacterStory]:\n        async with self._database._require_pool().acquire() as connection:\n            rows = await connection.fetch(\n                """\n                SELECT\n                    story.id, story.universe, story.key, story.short_label,\n                    story.title, story.sort_order, story.release_order,\n                    story.released_on, story.release_precision, link.is_primary\n                FROM character_story_links AS link\n                JOIN character_stories AS story ON story.id = link.story_id\n                WHERE link.character_id = $1::BIGINT\n                ORDER BY\n                    link.is_primary DESC,\n                    story.release_order DESC,\n                    story.released_on DESC NULLS LAST,\n                    story.title,\n                    story.id\n                """,\n                int(character_id),\n            )\n        return [\n            AssignedCharacterStory(\n                story=self._row_to_story(row),\n                is_primary=bool(row["is_primary"]),\n            )\n            for row in rows\n        ]\n\n    async def toggle_character_story(\n        self,\n        *,\n        character_id: int,\n        story_id: int,\n        assigned_by: int | None = None,\n    ) -> bool:\n        async with self._database._require_pool().acquire() as connection:\n            async with connection.transaction():\n                character = await connection.fetchrow(\n                    "SELECT id, universe, story_id FROM characters WHERE id = $1::BIGINT FOR UPDATE",\n                    int(character_id),\n                )\n                story = await connection.fetchrow(\n                    "SELECT id, universe FROM character_stories WHERE id = $1::BIGINT",\n                    int(story_id),\n                )\n                if character is None or story is None:\n                    raise ValueError("Персонаж или история больше не найдены.")\n                if character["universe"] != "kr" or story["universe"] != "kr":\n                    raise ValueError("Множественный выбор историй доступен только для КР.")\n\n                existing = await connection.fetchrow(\n                    """\n                    SELECT is_primary\n                    FROM character_story_links\n                    WHERE character_id = $1::BIGINT AND story_id = $2::BIGINT\n                    """,\n                    int(character_id),\n                    int(story_id),\n                )\n                if existing is not None:\n                    await connection.execute(\n                        """\n                        DELETE FROM character_story_links\n                        WHERE character_id = $1::BIGINT AND story_id = $2::BIGINT\n                        """,\n                        int(character_id),\n                        int(story_id),\n                    )\n                    if bool(existing["is_primary"]):\n                        await self._select_new_primary(connection, int(character_id))\n                    return False\n\n                has_primary = bool(\n                    await connection.fetchval(\n                        """\n                        SELECT TRUE\n                        FROM character_story_links\n                        WHERE character_id = $1::BIGINT AND is_primary\n                        LIMIT 1\n                        """,\n                        int(character_id),\n                    )\n                )\n                await connection.execute(\n                    """\n                    INSERT INTO character_story_links (\n                        character_id, story_id, is_primary, assigned_by\n                    )\n                    VALUES ($1::BIGINT, $2::BIGINT, $3::BOOLEAN, $4::BIGINT)\n                    """,\n                    int(character_id),\n                    int(story_id),\n                    not has_primary,\n                    assigned_by,\n                )\n                if not has_primary:\n                    await connection.execute(\n                        "UPDATE characters SET story_id = $2::BIGINT WHERE id = $1::BIGINT",\n                        int(character_id),\n                        int(story_id),\n                    )\n                return True\n\n    async def clear_character_stories(self, *, character_id: int) -> None:\n        async with self._database._require_pool().acquire() as connection:\n            async with connection.transaction():\n                character = await connection.fetchrow(\n                    "SELECT id FROM characters WHERE id = $1::BIGINT FOR UPDATE",\n                    int(character_id),\n                )\n                if character is None:\n                    raise ValueError("Персонаж не найден.")\n                await connection.execute(\n                    "DELETE FROM character_story_links WHERE character_id = $1::BIGINT",\n                    int(character_id),\n                )\n                await connection.execute(\n                    "UPDATE characters SET story_id = NULL WHERE id = $1::BIGINT",\n                    int(character_id),\n                )\n\n    @staticmethod\n    async def _select_new_primary(connection, character_id: int) -> int | None:\n        story_id = await connection.fetchval(\n            """\n            SELECT link.story_id\n            FROM character_story_links AS link\n            JOIN character_stories AS story ON story.id = link.story_id\n            WHERE link.character_id = $1::BIGINT\n            ORDER BY\n                story.release_order DESC,\n                story.released_on DESC NULLS LAST,\n                story.title,\n                story.id\n            LIMIT 1\n            """,\n            int(character_id),\n        )\n        await connection.execute(\n            "UPDATE character_story_links SET is_primary = FALSE WHERE character_id = $1::BIGINT",\n            int(character_id),\n        )\n        if story_id is not None:\n            await connection.execute(\n                """\n                UPDATE character_story_links\n                SET is_primary = TRUE\n                WHERE character_id = $1::BIGINT AND story_id = $2::BIGINT\n                """,\n                int(character_id),\n                int(story_id),\n            )\n        await connection.execute(\n            "UPDATE characters SET story_id = $2::BIGINT WHERE id = $1::BIGINT",\n            int(character_id),\n            int(story_id) if story_id is not None else None,\n        )\n        return int(story_id) if story_id is not None else None\n''',
)
replace_once(
    "velvet_bot/domains/stories/repository.py",
    '''                FROM character_stories AS s\n                LEFT JOIN characters AS c ON c.story_id = s.id\n                LEFT JOIN character_media AS cm ON cm.character_id = c.id\n''',
    '''                FROM character_stories AS s\n                LEFT JOIN character_story_links AS link ON link.story_id = s.id\n                LEFT JOIN characters AS c ON c.id = link.character_id\n                LEFT JOIN character_media AS cm ON cm.character_id = c.id\n''',
)

write(
    "velvet_bot/multi_story_support.py",
    '''from __future__ import annotations\n\nfrom velvet_bot import character_directory, story_catalog\nfrom velvet_bot.database import Database\nfrom velvet_bot.domains.stories import AssignedCharacterStory, StoryRepository\n\n\nasync def list_assigned_character_stories(\n    database: Database,\n    *,\n    character_id: int,\n) -> list[AssignedCharacterStory]:\n    return await StoryRepository(database).list_assigned_character_stories(\n        character_id=character_id\n    )\n\n\nasync def toggle_character_story(\n    database: Database,\n    *,\n    character_id: int,\n    story_id: int,\n    assigned_by: int | None = None,\n) -> bool:\n    return await StoryRepository(database).toggle_character_story(\n        character_id=character_id,\n        story_id=story_id,\n        assigned_by=assigned_by,\n    )\n\n\nasync def clear_character_stories(\n    database: Database,\n    *,\n    character_id: int,\n) -> None:\n    await StoryRepository(database).clear_character_stories(character_id=character_id)\n\n\nasync def set_character_story(\n    database: Database,\n    *,\n    character_id: int,\n    story_id: int | None,\n) -> None:\n    await story_catalog.set_character_story(\n        database, character_id=character_id, story_id=story_id\n    )\n\n\nasync def set_character_universe(\n    database: Database,\n    *,\n    character_id: int,\n    universe: str | None,\n) -> None:\n    await character_directory.set_character_universe(\n        database, character_id=character_id, universe=universe\n    )\n\n\nasync def list_story_summaries(database: Database, **kwargs):\n    return await story_catalog.list_story_summaries(database, **kwargs)\n\n\nasync def list_category_summaries(database: Database, **kwargs):\n    return await character_directory.list_category_summaries(database, **kwargs)\n\n\nasync def list_universe_summaries(database: Database, **kwargs):\n    return await character_directory.list_universe_summaries(database, **kwargs)\n\n\nasync def list_character_directory(database: Database, **kwargs):\n    return await character_directory.list_character_directory(database, **kwargs)\n\n\ndef install_multi_story_support() -> None:\n    """Compatibility no-op: multi-story behavior is wired into repositories."""\n\n\n__all__ = (\n    "AssignedCharacterStory",\n    "clear_character_stories",\n    "install_multi_story_support",\n    "list_assigned_character_stories",\n    "list_category_summaries",\n    "list_character_directory",\n    "list_story_summaries",\n    "list_universe_summaries",\n    "set_character_story",\n    "set_character_universe",\n    "toggle_character_story",\n)\n''',
)
write(
    "velvet_bot/multi_story_queries.py",
    '''from __future__ import annotations\n\nfrom velvet_bot.database import Database\nfrom velvet_bot.domains.stories import AssignedCharacterStory, StoryRepository\n\n\nasync def list_assigned_character_stories(\n    database: Database,\n    *,\n    character_id: int,\n) -> list[AssignedCharacterStory]:\n    return await StoryRepository(database).list_assigned_character_stories(\n        character_id=character_id\n    )\n\n\n__all__ = ("list_assigned_character_stories",)\n''',
)
replace_once(
    "velvet_bot/presentation/telegram/compat.py",
    '''import velvet_bot.multi_story_support as multi_story_support\nfrom velvet_bot.multi_story_queries import list_assigned_character_stories\n''',
    "",
)
replace_once(
    "velvet_bot/presentation/telegram/compat.py",
    '''    multi_story_support.list_assigned_character_stories = list_assigned_character_stories\n    multi_story_support.install_multi_story_support()\n''',
    "",
)

write(
    "tests/test_phase15_multi_story_domain.py",
    '''from __future__ import annotations\n\nimport ast\nimport unittest\nfrom pathlib import Path\nfrom types import SimpleNamespace\nfrom unittest.mock import AsyncMock\n\nfrom velvet_bot.domains.stories import AssignedCharacterStory, StoryRepository\nfrom velvet_bot.multi_story_support import install_multi_story_support\n\n\nROOT = Path(__file__).resolve().parents[1]\n\n\nclass MultiStoryDomainTests(unittest.TestCase):\n    def test_compat_install_is_a_noop(self) -> None:\n        self.assertIsNone(install_multi_story_support())\n\n    def test_runtime_compat_has_no_multi_story_monkeypatch(self) -> None:\n        source = (\n            ROOT / "velvet_bot/presentation/telegram/compat.py"\n        ).read_text(encoding="utf-8")\n        self.assertNotIn("multi_story_support", source)\n        self.assertNotIn("list_assigned_character_stories =", source)\n        self.assertNotIn("install_multi_story_support", source)\n\n    def test_multi_story_facades_have_no_direct_sql(self) -> None:\n        for name in ("multi_story_support.py", "multi_story_queries.py"):\n            path = ROOT / "velvet_bot" / name\n            source = path.read_text(encoding="utf-8")\n            ast.parse(source, filename=str(path))\n            self.assertNotIn("_require_pool", source)\n            self.assertNotIn("SELECT ", source)\n\n    def test_repository_exposes_multi_story_operations(self) -> None:\n        for name in (\n            "list_assigned_character_stories",\n            "toggle_character_story",\n            "clear_character_stories",\n        ):\n            self.assertTrue(hasattr(StoryRepository, name))\n\n    def test_assigned_model_is_domain_owned(self) -> None:\n        story = SimpleNamespace(id=1)\n        assigned = AssignedCharacterStory(story=story, is_primary=True)\n        self.assertIs(assigned.story, story)\n        self.assertTrue(assigned.is_primary)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
)

(ROOT / "scripts/_phase15_patch.py").unlink()
(ROOT / ".github/workflows/phase15-patch.yml").unlink()
