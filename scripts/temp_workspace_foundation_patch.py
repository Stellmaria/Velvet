from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_regex(path: str, pattern: str, replacement: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"Expected one regex match in {path}, found {count}: {pattern[:120]!r}")
    target.write_text(updated, encoding="utf-8")


def patch_database() -> None:
    path = "velvet_bot/database.py"
    replace_once(
        path,
        "from velvet_bot.media import MediaDescriptor\n",
        "from velvet_bot.media import MediaDescriptor\n"
        "from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID\n",
    )
    replace_once(
        path,
        "    archive_topic_url: str | None\n\n\n@dataclass(frozen=True, slots=True)\nclass SaveMediaResult:",
        "    archive_topic_url: str | None\n"
        "    workspace_id: int = DEFAULT_WORKSPACE_ID\n\n\n"
        "@dataclass(frozen=True, slots=True)\nclass SaveMediaResult:",
    )
    replace_regex(
        path,
        r"    async def create_character\(.*?\n        return self\._row_to_character\(row\), created\n",
        '''    async def create_character(
        self,
        name: str,
        *,
        created_by: int | None,
        created_in_chat: int | None,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> tuple[Character, bool]:
        display_name = clean_character_name(name)
        normalized_name = normalize_character_name(display_name)

        async with self._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO characters (
                    workspace_id,
                    name,
                    normalized_name,
                    created_by,
                    created_in_chat
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (workspace_id, normalized_name) DO NOTHING
                RETURNING
                    id,
                    workspace_id,
                    name,
                    created_by,
                    created_in_chat,
                    created_at,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url
                """,
                int(workspace_id),
                display_name,
                normalized_name,
                created_by,
                created_in_chat,
            )
            created = row is not None
            if row is None:
                row = await self._fetch_character_row(
                    connection,
                    normalized_name=normalized_name,
                    workspace_id=int(workspace_id),
                )

        if row is None:
            raise RuntimeError("Не удалось создать или получить профиль персонажа.")

        return self._row_to_character(row), created
''',
    )
    replace_regex(
        path,
        r"    async def bind_character_topic\(.*?\n        return self\._row_to_character\(row\)\n",
        '''    async def bind_character_topic(
        self,
        character_id: int,
        *,
        archive_chat_id: int,
        archive_thread_id: int,
        archive_topic_url: str,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> Character:
        try:
            async with self._require_pool().acquire() as connection:
                row = await connection.fetchrow(
                    """
                    UPDATE characters
                    SET archive_chat_id = $2,
                        archive_thread_id = $3,
                        archive_topic_url = $4
                    WHERE id = $1
                      AND workspace_id = $5
                    RETURNING
                        id,
                        workspace_id,
                        name,
                        created_by,
                        created_in_chat,
                        created_at,
                        archive_chat_id,
                        archive_thread_id,
                        archive_topic_url
                    """,
                    character_id,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url,
                    int(workspace_id),
                )
        except asyncpg.UniqueViolationError as error:
            raise ValueError(
                "Эта тема Telegram уже привязана к другому персонажу."
            ) from error

        if row is None:
            raise RuntimeError("Персонаж для привязки темы не найден.")
        return self._row_to_character(row)
''',
    )
    replace_regex(
        path,
        r"    async def get_character\(.*?\n        return self\._row_to_character\(row\) if row is not None else None\n",
        '''    async def get_character(
        self,
        name: str,
        *,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> Character | None:
        normalized_name = normalize_character_name(name)
        async with self._require_pool().acquire() as connection:
            row = await self._fetch_character_row(
                connection,
                normalized_name=normalized_name,
                workspace_id=int(workspace_id),
            )
        return self._row_to_character(row) if row is not None else None
''',
    )
    replace_regex(
        path,
        r"    async def get_character_by_archive_topic\(.*?\n        return self\._row_to_character\(row\) if row is not None else None\n",
        '''    async def get_character_by_archive_topic(
        self,
        archive_chat_id: int,
        archive_thread_id: int,
        *,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> Character | None:
        async with self._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    id,
                    workspace_id,
                    name,
                    created_by,
                    created_in_chat,
                    created_at,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url
                FROM characters
                WHERE workspace_id = $1
                  AND archive_chat_id = $2
                  AND archive_thread_id = $3
                """,
                int(workspace_id),
                archive_chat_id,
                archive_thread_id,
            )
        return self._row_to_character(row) if row is not None else None
''',
    )
    replace_regex(
        path,
        r"    async def list_characters\(.*?\n        return \[self\._row_to_character\(row\) for row in rows\]\n",
        '''    async def list_characters(
        self,
        *,
        limit: int = 100,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> list[Character]:
        safe_limit = max(1, min(limit, 100))
        async with self._require_pool().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    id,
                    workspace_id,
                    name,
                    created_by,
                    created_in_chat,
                    created_at,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url
                FROM characters
                WHERE workspace_id = $1
                ORDER BY normalized_name
                LIMIT $2
                """,
                int(workspace_id),
                safe_limit,
            )
        return [self._row_to_character(row) for row in rows]
''',
    )
    replace_regex(
        path,
        r"    @staticmethod\n    async def _fetch_character_row\(.*?\n        \)\n\n    @staticmethod\n    def _row_to_character",
        '''    @staticmethod
    async def _fetch_character_row(
        connection: asyncpg.Connection,
        *,
        normalized_name: str,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> asyncpg.Record | None:
        return await connection.fetchrow(
            """
            SELECT
                id,
                workspace_id,
                name,
                created_by,
                created_in_chat,
                created_at,
                archive_chat_id,
                archive_thread_id,
                archive_topic_url
            FROM characters
            WHERE workspace_id = $1
              AND normalized_name = $2
            """,
            int(workspace_id),
            normalized_name,
        )

    @staticmethod
    def _row_to_character''',
    )
    replace_once(
        path,
        '''            archive_topic_url=row["archive_topic_url"],
        )
''',
        '''            archive_topic_url=row["archive_topic_url"],
            workspace_id=(
                int(row["workspace_id"])
                if "workspace_id" in row
                else DEFAULT_WORKSPACE_ID
            ),
        )
''',
    )


def patch_character_models() -> None:
    path = "velvet_bot/domains/characters/models.py"
    replace_once(
        path,
        "from datetime import datetime\n",
        "from datetime import datetime\n\n"
        "from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID\n",
    )
    replace_once(
        path,
        "    archive_topic_url: str | None\n\n\n@dataclass(frozen=True, slots=True)\nclass CategorySummary:",
        "    archive_topic_url: str | None\n"
        "    workspace_id: int = DEFAULT_WORKSPACE_ID\n\n\n"
        "@dataclass(frozen=True, slots=True)\nclass CategorySummary:",
    )


def patch_character_repository() -> None:
    path = "velvet_bot/domains/characters/repository.py"
    replace_once(
        path,
        "from velvet_bot.database import Database\n",
        "from velvet_bot.database import Database\n"
        "from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID\n",
    )
    replace_once(
        path,
        '''    def __init__(self, database: Database) -> None:
        self._database = database
''',
        '''    def __init__(
        self,
        database: Database,
        *,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> None:
        self._database = database
        self._workspace_id = int(workspace_id)
''',
    )
    replace_regex(
        path,
        r"    async def set_category\(.*?\n            raise ValueError\(\"Персонаж не найден\.\"\)\n",
        '''    async def set_category(self, *, character_id: int, category: str | None) -> None:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE characters
                SET category = $2::VARCHAR
                WHERE id = $1::BIGINT
                  AND workspace_id = $3::BIGINT
                """,
                int(character_id),
                category,
                self._workspace_id,
            )
        if result == "UPDATE 0":
            raise ValueError("Персонаж не найден.")
''',
    )
    replace_regex(
        path,
        r"    async def set_universe\(.*?\n                    \)\n\n    async def set_prompt_url",
        '''    async def set_universe(self, *, character_id: int, universe: str | None) -> None:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    """
                    SELECT universe
                    FROM characters
                    WHERE id = $1::BIGINT
                      AND workspace_id = $2::BIGINT
                    FOR UPDATE
                    """,
                    int(character_id),
                    self._workspace_id,
                )
                if current is None:
                    raise ValueError("Персонаж не найден.")
                if current["universe"] != universe:
                    await connection.execute(
                        "DELETE FROM character_story_links WHERE character_id = $1::BIGINT",
                        int(character_id),
                    )
                    await connection.execute(
                        """
                        UPDATE characters
                        SET universe = $2::VARCHAR, story_id = NULL
                        WHERE id = $1::BIGINT
                          AND workspace_id = $3::BIGINT
                        """,
                        int(character_id),
                        universe,
                        self._workspace_id,
                    )
                else:
                    await connection.execute(
                        """
                        UPDATE characters
                        SET universe = $2::VARCHAR
                        WHERE id = $1::BIGINT
                          AND workspace_id = $3::BIGINT
                        """,
                        int(character_id),
                        universe,
                        self._workspace_id,
                    )

    async def set_prompt_url''',
    )
    replace_regex(
        path,
        r"    async def set_prompt_url\(.*?\n            raise ValueError\(\"Персонаж не найден\.\"\)\n",
        '''    async def set_prompt_url(
        self,
        *,
        character_id: int,
        prompt_post_url: str | None,
    ) -> None:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE characters
                SET prompt_post_url = $2::TEXT
                WHERE id = $1::BIGINT
                  AND workspace_id = $3::BIGINT
                """,
                int(character_id),
                prompt_post_url,
                self._workspace_id,
            )
        if result == "UPDATE 0":
            raise ValueError("Персонаж не найден.")
''',
    )
    replace_regex(
        path,
        r"    async def get_item\(.*?\n        return self\._row_to_directory_item\(row\) if row is not None else None\n",
        '''    async def get_item(self, character_id: int) -> CharacterDirectoryItem | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    c.id, c.workspace_id, c.name, c.created_by, c.created_in_chat, c.created_at,
                    c.archive_chat_id, c.archive_thread_id, c.archive_topic_url,
                    c.category, c.universe, c.prompt_post_url, c.story_id,
                    s.short_label AS story_short_label,
                    s.title AS story_title,
                    COUNT(cm.media_id) AS media_count
                FROM characters AS c
                LEFT JOIN character_stories AS s ON s.id = c.story_id
                LEFT JOIN character_media AS cm ON cm.character_id = c.id
                WHERE c.id = $1::BIGINT
                  AND c.workspace_id = $2::BIGINT
                GROUP BY c.id, s.id
                """,
                int(character_id),
                self._workspace_id,
            )
        return self._row_to_directory_item(row) if row is not None else None
''',
    )
    replace_regex(
        path,
        r"    async def list_category_summaries\(.*?\n        \)\n\n    async def list_universe_summaries",
        '''    async def list_category_summaries(
        self,
        *,
        public_only: bool,
        include_uncategorized: bool = False,
    ) -> tuple[CategorySummary, ...]:
        keys = list(CATEGORY_ORDER)
        if include_uncategorized:
            keys.append("uncategorized")

        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT
                    COALESCE(c.category, 'uncategorized') AS category,
                    COUNT(DISTINCT c.id) AS character_count
                FROM characters AS c
                LEFT JOIN character_media AS cm ON cm.character_id = c.id
                WHERE c.workspace_id = $1::BIGINT
                  AND (
                    $2::BOOLEAN = FALSE
                    OR (
                        cm.media_id IS NOT NULL
                        AND c.universe IS NOT NULL
                        AND (
                            c.universe NOT IN {STORY_REQUIRED_SQL}
                            OR EXISTS (
                                SELECT 1
                                FROM character_story_links AS ready_link
                                WHERE ready_link.character_id = c.id
                            )
                        )
                    )
                )
                GROUP BY COALESCE(c.category, 'uncategorized')
                """,
                self._workspace_id,
                bool(public_only),
            )
        counts = {
            str(row["category"]): int(row["character_count"] or 0)
            for row in rows
        }
        return tuple(
            CategorySummary(
                key=key,
                label=CATEGORY_LABELS[key],
                emoji=CATEGORY_EMOJI[key],
                character_count=counts.get(key, 0),
            )
            for key in keys
        )

    async def list_universe_summaries''',
    )
    replace_regex(
        path,
        r"    async def list_universe_summaries\(.*?\n        \)\n\n    async def list_directory",
        '''    async def list_universe_summaries(
        self,
        *,
        category: str,
        public_only: bool,
        include_unassigned: bool = False,
    ) -> tuple[UniverseSummary, ...]:
        keys = list(UNIVERSE_ORDER)
        if include_unassigned:
            keys.append("unassigned")

        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT
                    COALESCE(c.universe, 'unassigned') AS universe,
                    COUNT(DISTINCT c.id) AS character_count
                FROM characters AS c
                LEFT JOIN character_media AS cm ON cm.character_id = c.id
                WHERE c.workspace_id = $1::BIGINT
                  AND c.category = $2::VARCHAR
                  AND (
                        $3::BOOLEAN = FALSE
                        OR (
                            cm.media_id IS NOT NULL
                            AND (
                                c.universe NOT IN {STORY_REQUIRED_SQL}
                                OR EXISTS (
                                    SELECT 1
                                    FROM character_story_links AS ready_link
                                    WHERE ready_link.character_id = c.id
                                )
                            )
                        )
                      )
                GROUP BY COALESCE(c.universe, 'unassigned')
                """,
                self._workspace_id,
                category,
                bool(public_only),
            )
        counts = {
            str(row["universe"]): int(row["character_count"] or 0)
            for row in rows
        }
        return tuple(
            UniverseSummary(
                key=key,
                label=UNIVERSE_LABELS[key],
                emoji=UNIVERSE_EMOJI[key],
                character_count=counts.get(key, 0),
            )
            for key in keys
        )

    async def list_directory''',
    )
    replace_regex(
        path,
        r"    async def list_directory\(.*?\n        \)\n\n    @staticmethod\n    def _row_to_character",
        '''    async def list_directory(
        self,
        *,
        category: str,
        page: int = 0,
        page_size: int = 6,
        public_only: bool,
        universe: str | None = None,
        story_id: int | None = None,
    ) -> CharacterDirectoryPage:
        safe_page_size = max(1, min(int(page_size), 10))
        safe_page = max(0, int(page))
        category_condition = """
            (($2::TEXT = 'uncategorized' AND c.category IS NULL) OR c.category = $2)
        """
        universe_condition = "($4::TEXT IS NULL OR c.universe = $4)"
        story_condition = """
            ($5::BIGINT IS NULL OR EXISTS (
                SELECT 1
                FROM character_story_links AS selected_link
                WHERE selected_link.character_id = c.id
                  AND selected_link.story_id = $5::BIGINT
            ))
        """
        public_condition = f"""
            (
                $3::BOOLEAN = FALSE
                OR (
                    cm.media_id IS NOT NULL
                    AND c.universe IS NOT NULL
                    AND (
                        c.universe NOT IN {STORY_REQUIRED_SQL}
                        OR EXISTS (
                                SELECT 1
                                FROM character_story_links AS ready_link
                                WHERE ready_link.character_id = c.id
                            )
                    )
                )
            )
        """

        async with self._database.acquire() as connection:
            total = int(
                await connection.fetchval(
                    f"""
                    SELECT COUNT(*)
                    FROM (
                        SELECT c.id
                        FROM characters AS c
                        LEFT JOIN character_media AS cm ON cm.character_id = c.id
                        WHERE c.workspace_id = $1::BIGINT
                          AND {category_condition}
                          AND {public_condition}
                          AND {universe_condition}
                          AND {story_condition}
                        GROUP BY c.id
                    ) AS directory
                    """,
                    self._workspace_id,
                    category,
                    bool(public_only),
                    universe,
                    story_id,
                )
                or 0
            )
            total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
            normalized_page = min(safe_page, total_pages - 1)
            rows = await connection.fetch(
                f"""
                SELECT
                    c.id, c.workspace_id, c.name, c.created_by, c.created_in_chat, c.created_at,
                    c.archive_chat_id, c.archive_thread_id, c.archive_topic_url,
                    c.category, c.universe, c.prompt_post_url, c.story_id,
                    s.short_label AS story_short_label,
                    s.title AS story_title,
                    COUNT(cm.media_id) AS media_count
                FROM characters AS c
                LEFT JOIN character_stories AS s ON s.id = c.story_id
                LEFT JOIN character_media AS cm ON cm.character_id = c.id
                WHERE c.workspace_id = $1::BIGINT
                  AND {category_condition}
                  AND {public_condition}
                  AND {universe_condition}
                  AND {story_condition}
                GROUP BY c.id, s.id
                ORDER BY c.normalized_name ASC, c.id ASC
                OFFSET $6::INTEGER
                LIMIT $7::INTEGER
                """,
                self._workspace_id,
                category,
                bool(public_only),
                universe,
                story_id,
                normalized_page * safe_page_size,
                safe_page_size,
            )

            selected_story = None
            if story_id is not None:
                selected_story = await connection.fetchrow(
                    """
                    SELECT id, short_label, title
                    FROM character_stories
                    WHERE id = $1::BIGINT AND universe = $2::VARCHAR
                    """,
                    int(story_id),
                    universe,
                )

        return CharacterDirectoryPage(
            items=tuple(self._row_to_directory_item(row) for row in rows),
            category=category,
            page=normalized_page,
            page_size=safe_page_size,
            total_characters=total,
            universe=universe,
            story_id=story_id,
            story_short_label=(
                str(selected_story["short_label"])
                if selected_story is not None
                else None
            ),
            story_title=(
                str(selected_story["title"])
                if selected_story is not None
                else None
            ),
        )

    @staticmethod
    def _row_to_character''',
    )
    replace_once(
        path,
        '''            archive_topic_url=row["archive_topic_url"],
        )
''',
        '''            archive_topic_url=row["archive_topic_url"],
            workspace_id=(
                int(row["workspace_id"])
                if "workspace_id" in row
                else DEFAULT_WORKSPACE_ID
            ),
        )
''',
    )


def main() -> None:
    patch_database()
    patch_character_models()
    patch_character_repository()
    (ROOT / "scripts/temp_workspace_foundation_patch.py").unlink()
    (ROOT / ".github/workflows/temp-workspace-foundation.yml").unlink()


if __name__ == "__main__":
    main()
