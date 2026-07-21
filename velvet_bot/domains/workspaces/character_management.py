from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import asyncpg

from velvet_bot.database import (
    Database,
    clean_character_name,
    normalize_character_name,
)
from velvet_bot.domains.characters.catalog import validate_prompt_post_url
from velvet_bot.topics import TopicReference


@dataclass(frozen=True, slots=True)
class WorkspaceCharacterStory:
    id: int
    short_label: str
    title: str
    is_primary: bool


@dataclass(frozen=True, slots=True)
class WorkspaceCharacterAlias:
    id: int
    alias: str
    normalized_alias: str
    source: str


@dataclass(frozen=True, slots=True)
class WorkspaceCharacterRecord:
    id: int
    workspace_id: int
    name: str
    category: str | None
    universe: str | None
    prompt_post_url: str | None
    archive_chat_id: int | None
    archive_thread_id: int | None
    archive_topic_url: str | None
    stories: tuple[WorkspaceCharacterStory, ...] = ()
    aliases: tuple[WorkspaceCharacterAlias, ...] = ()


@dataclass(frozen=True, slots=True)
class DeletedWorkspaceCharacter:
    id: int
    name: str
    media_links: int
    aliases: int
    story_links: int


def normalize_workspace_character_alias(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _clean_alias(value: str) -> tuple[str, str]:
    cleaned = " ".join(unicodedata.normalize("NFKC", value).split())
    normalized = normalize_workspace_character_alias(cleaned)
    if not cleaned or not normalized:
        raise ValueError("Алиас не может быть пустым.")
    if len(cleaned) > 64:
        raise ValueError("Алиас не должен быть длиннее 64 символов.")
    return cleaned, normalized


async def _require_character(
    connection,
    *,
    workspace_id: int,
    character_id: int,
    for_update: bool = False,
):
    suffix = " FOR UPDATE" if for_update else ""
    row = await connection.fetchrow(
        f"""
        SELECT
            id,
            workspace_id,
            name,
            category,
            universe,
            prompt_post_url,
            archive_chat_id,
            archive_thread_id,
            archive_topic_url
        FROM characters
        WHERE workspace_id = $1::BIGINT
          AND id = $2::BIGINT
        {suffix}
        """,
        int(workspace_id),
        int(character_id),
    )
    if row is None:
        raise ValueError("Персонаж не найден в этом архиве.")
    return row


async def _ensure_name_alias(
    connection,
    *,
    workspace_id: int,
    character_id: int,
    name: str,
) -> None:
    normalized = normalize_workspace_character_alias(name)
    if not normalized:
        return
    await connection.execute(
        """
        DELETE FROM workspace_character_aliases
        WHERE workspace_id = $1::BIGINT
          AND character_id = $2::BIGINT
          AND source = 'name'
        """,
        int(workspace_id),
        int(character_id),
    )
    conflict = await connection.fetchrow(
        """
        SELECT alias, character_id
        FROM workspace_character_aliases
        WHERE workspace_id = $1::BIGINT
          AND normalized_alias = $2::VARCHAR
        """,
        int(workspace_id),
        normalized,
    )
    if conflict is not None and int(conflict["character_id"]) != int(character_id):
        raise ValueError("Имя конфликтует с алиасом другого персонажа этого архива.")
    await connection.execute(
        """
        INSERT INTO workspace_character_aliases (
            workspace_id,
            character_id,
            alias,
            normalized_alias,
            source
        )
        VALUES ($1::BIGINT, $2::BIGINT, $3::VARCHAR, $4::VARCHAR, 'name')
        ON CONFLICT (character_id, normalized_alias) DO UPDATE
        SET alias = EXCLUDED.alias,
            source = 'name',
            updated_at = NOW()
        """,
        int(workspace_id),
        int(character_id),
        name,
        normalized,
    )


async def create_workspace_character(
    database: Database,
    *,
    workspace_id: int,
    name: str,
    created_by: int | None,
    created_in_chat: int | None,
) -> tuple[WorkspaceCharacterRecord, bool]:
    character, created = await database.create_character(
        name,
        created_by=created_by,
        created_in_chat=created_in_chat,
        workspace_id=int(workspace_id),
    )
    async with database.acquire() as connection:
        async with connection.transaction():
            await _require_character(
                connection,
                workspace_id=workspace_id,
                character_id=character.id,
                for_update=True,
            )
            await _ensure_name_alias(
                connection,
                workspace_id=workspace_id,
                character_id=character.id,
                name=character.name,
            )
    record = await load_workspace_character(
        database,
        workspace_id=workspace_id,
        character_id=character.id,
    )
    if record is None:
        raise RuntimeError("Не удалось загрузить созданного персонажа.")
    return record, created


async def list_workspace_characters(
    database: Database,
    *,
    workspace_id: int,
    limit: int = 100,
) -> tuple[WorkspaceCharacterRecord, ...]:
    safe_limit = max(1, min(int(limit), 100))
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                character.id,
                character.workspace_id,
                character.name,
                character.category,
                character.universe,
                character.prompt_post_url,
                character.archive_chat_id,
                character.archive_thread_id,
                character.archive_topic_url
            FROM characters AS character
            WHERE character.workspace_id = $1::BIGINT
            ORDER BY character.normalized_name, character.id
            LIMIT $2::INTEGER
            """,
            int(workspace_id),
            safe_limit,
        )
        story_rows = await connection.fetch(
            """
            SELECT
                link.character_id,
                story.id,
                story.short_label,
                story.title,
                link.is_primary
            FROM workspace_character_story_links AS link
            JOIN workspace_stories AS story
              ON story.workspace_id = link.workspace_id
             AND story.id = link.story_id
            WHERE link.workspace_id = $1::BIGINT
            ORDER BY
                link.character_id,
                link.is_primary DESC,
                story.sort_order,
                story.title,
                story.id
            """,
            int(workspace_id),
        )
    stories_by_character: dict[int, list[WorkspaceCharacterStory]] = {}
    for row in story_rows:
        stories_by_character.setdefault(int(row["character_id"]), []).append(
            WorkspaceCharacterStory(
                id=int(row["id"]),
                short_label=str(row["short_label"]),
                title=str(row["title"]),
                is_primary=bool(row["is_primary"]),
            )
        )
    return tuple(
        _row_to_character(
            row,
            stories=tuple(stories_by_character.get(int(row["id"]), ())),
        )
        for row in rows
    )


async def load_workspace_character(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
) -> WorkspaceCharacterRecord | None:
    async with database.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                id,
                workspace_id,
                name,
                category,
                universe,
                prompt_post_url,
                archive_chat_id,
                archive_thread_id,
                archive_topic_url
            FROM characters
            WHERE workspace_id = $1::BIGINT
              AND id = $2::BIGINT
            """,
            int(workspace_id),
            int(character_id),
        )
        if row is None:
            return None
        story_rows = await connection.fetch(
            """
            SELECT
                story.id,
                story.short_label,
                story.title,
                link.is_primary
            FROM workspace_character_story_links AS link
            JOIN workspace_stories AS story
              ON story.workspace_id = link.workspace_id
             AND story.id = link.story_id
            WHERE link.workspace_id = $1::BIGINT
              AND link.character_id = $2::BIGINT
            ORDER BY
                link.is_primary DESC,
                story.sort_order,
                story.title,
                story.id
            """,
            int(workspace_id),
            int(character_id),
        )
        alias_rows = await connection.fetch(
            """
            SELECT id, alias, normalized_alias, source
            FROM workspace_character_aliases
            WHERE workspace_id = $1::BIGINT
              AND character_id = $2::BIGINT
            ORDER BY CASE source WHEN 'name' THEN 0 ELSE 1 END, alias, id
            """,
            int(workspace_id),
            int(character_id),
        )
    stories = tuple(
        WorkspaceCharacterStory(
            id=int(item["id"]),
            short_label=str(item["short_label"]),
            title=str(item["title"]),
            is_primary=bool(item["is_primary"]),
        )
        for item in story_rows
    )
    aliases = tuple(
        WorkspaceCharacterAlias(
            id=int(item["id"]),
            alias=str(item["alias"]),
            normalized_alias=str(item["normalized_alias"]),
            source=str(item["source"]),
        )
        for item in alias_rows
    )
    return _row_to_character(row, stories=stories, aliases=aliases)


async def rename_workspace_character(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
    new_name: str,
) -> WorkspaceCharacterRecord:
    display_name = clean_character_name(new_name)
    normalized_name = normalize_character_name(display_name)
    try:
        async with database.acquire() as connection:
            async with connection.transaction():
                await _require_character(
                    connection,
                    workspace_id=workspace_id,
                    character_id=character_id,
                    for_update=True,
                )
                conflict = await connection.fetchval(
                    """
                    SELECT TRUE
                    FROM workspace_character_aliases
                    WHERE workspace_id = $1::BIGINT
                      AND normalized_alias = $2::VARCHAR
                      AND character_id <> $3::BIGINT
                    """,
                    int(workspace_id),
                    normalize_workspace_character_alias(display_name),
                    int(character_id),
                )
                if conflict:
                    raise ValueError(
                        "Имя конфликтует с алиасом другого персонажа этого архива."
                    )
                result = await connection.execute(
                    """
                    UPDATE characters
                    SET name = $3::VARCHAR,
                        normalized_name = $4::VARCHAR
                    WHERE workspace_id = $1::BIGINT
                      AND id = $2::BIGINT
                    """,
                    int(workspace_id),
                    int(character_id),
                    display_name,
                    normalized_name,
                )
                if result == "UPDATE 0":
                    raise ValueError("Персонаж не найден в этом архиве.")
                await _ensure_name_alias(
                    connection,
                    workspace_id=workspace_id,
                    character_id=character_id,
                    name=display_name,
                )
    except asyncpg.UniqueViolationError as error:
        raise ValueError("Персонаж с таким именем уже существует в этом архиве.") from error
    record = await load_workspace_character(
        database,
        workspace_id=workspace_id,
        character_id=character_id,
    )
    if record is None:
        raise RuntimeError("Переименованный персонаж больше не найден.")
    return record


async def delete_workspace_character(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
) -> DeletedWorkspaceCharacter:
    async with database.acquire() as connection:
        async with connection.transaction():
            character = await _require_character(
                connection,
                workspace_id=workspace_id,
                character_id=character_id,
                for_update=True,
            )
            media_links = int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM character_media WHERE character_id = $1::BIGINT",
                    int(character_id),
                )
                or 0
            )
            aliases = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM workspace_character_aliases
                    WHERE workspace_id = $1::BIGINT
                      AND character_id = $2::BIGINT
                    """,
                    int(workspace_id),
                    int(character_id),
                )
                or 0
            )
            story_links = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM workspace_character_story_links
                    WHERE workspace_id = $1::BIGINT
                      AND character_id = $2::BIGINT
                    """,
                    int(workspace_id),
                    int(character_id),
                )
                or 0
            )
            result = await connection.execute(
                """
                DELETE FROM characters
                WHERE workspace_id = $1::BIGINT
                  AND id = $2::BIGINT
                """,
                int(workspace_id),
                int(character_id),
            )
            if result == "DELETE 0":
                raise ValueError("Персонаж не найден в этом архиве.")
    return DeletedWorkspaceCharacter(
        id=int(character["id"]),
        name=str(character["name"]),
        media_links=media_links,
        aliases=aliases,
        story_links=story_links,
    )


async def set_workspace_character_category(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
    category_key: str | None,
) -> None:
    async with database.acquire() as connection:
        if category_key is not None:
            exists = await connection.fetchval(
                """
                SELECT TRUE
                FROM workspace_categories
                WHERE workspace_id = $1::BIGINT
                  AND key = $2::VARCHAR
                  AND is_enabled
                """,
                int(workspace_id),
                category_key,
            )
            if not exists:
                raise ValueError("Категория не найдена в структуре этого архива.")
        result = await connection.execute(
            """
            UPDATE characters
            SET category = $3::VARCHAR
            WHERE workspace_id = $1::BIGINT
              AND id = $2::BIGINT
            """,
            int(workspace_id),
            int(character_id),
            category_key,
        )
    if result == "UPDATE 0":
        raise ValueError("Персонаж не найден в этом архиве.")


async def set_workspace_character_universe(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
    universe_key: str | None,
) -> None:
    async with database.acquire() as connection:
        async with connection.transaction():
            if universe_key is not None:
                exists = await connection.fetchval(
                    """
                    SELECT TRUE
                    FROM workspace_universes
                    WHERE workspace_id = $1::BIGINT
                      AND key = $2::VARCHAR
                      AND is_enabled
                    """,
                    int(workspace_id),
                    universe_key,
                )
                if not exists:
                    raise ValueError("Вселенная не найдена в структуре этого архива.")
            result = await connection.execute(
                """
                UPDATE characters
                SET universe = $3::VARCHAR,
                    story_id = NULL
                WHERE workspace_id = $1::BIGINT
                  AND id = $2::BIGINT
                """,
                int(workspace_id),
                int(character_id),
                universe_key,
            )
            if result == "UPDATE 0":
                raise ValueError("Персонаж не найден в этом архиве.")
            await connection.execute(
                """
                DELETE FROM workspace_character_story_links
                WHERE workspace_id = $1::BIGINT
                  AND character_id = $2::BIGINT
                """,
                int(workspace_id),
                int(character_id),
            )


async def toggle_workspace_character_story(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
    story_id: int,
    assigned_by_user_id: int,
) -> bool:
    async with database.acquire() as connection:
        async with connection.transaction():
            character = await _require_character(
                connection,
                workspace_id=workspace_id,
                character_id=character_id,
                for_update=True,
            )
            story = await connection.fetchrow(
                """
                SELECT id, universe_key
                FROM workspace_stories
                WHERE workspace_id = $1::BIGINT
                  AND id = $2::BIGINT
                  AND is_enabled
                """,
                int(workspace_id),
                int(story_id),
            )
            if story is None:
                raise ValueError("История не найдена в структуре этого архива.")
            if character["universe"] != story["universe_key"]:
                raise ValueError("Сначала назначьте персонажу вселенную этой истории.")
            existing = await connection.fetchrow(
                """
                SELECT is_primary
                FROM workspace_character_story_links
                WHERE workspace_id = $1::BIGINT
                  AND character_id = $2::BIGINT
                  AND story_id = $3::BIGINT
                """,
                int(workspace_id),
                int(character_id),
                int(story_id),
            )
            if existing is not None:
                await connection.execute(
                    """
                    DELETE FROM workspace_character_story_links
                    WHERE workspace_id = $1::BIGINT
                      AND character_id = $2::BIGINT
                      AND story_id = $3::BIGINT
                    """,
                    int(workspace_id),
                    int(character_id),
                    int(story_id),
                )
                if bool(existing["is_primary"]):
                    next_story_id = await connection.fetchval(
                        """
                        SELECT link.story_id
                        FROM workspace_character_story_links AS link
                        JOIN workspace_stories AS story
                          ON story.workspace_id = link.workspace_id
                         AND story.id = link.story_id
                        WHERE link.workspace_id = $1::BIGINT
                          AND link.character_id = $2::BIGINT
                        ORDER BY story.sort_order, story.title, story.id
                        LIMIT 1
                        """,
                        int(workspace_id),
                        int(character_id),
                    )
                    if next_story_id is not None:
                        await connection.execute(
                            """
                            UPDATE workspace_character_story_links
                            SET is_primary = TRUE
                            WHERE workspace_id = $1::BIGINT
                              AND character_id = $2::BIGINT
                              AND story_id = $3::BIGINT
                            """,
                            int(workspace_id),
                            int(character_id),
                            int(next_story_id),
                        )
                return False
            has_primary = bool(
                await connection.fetchval(
                    """
                    SELECT TRUE
                    FROM workspace_character_story_links
                    WHERE workspace_id = $1::BIGINT
                      AND character_id = $2::BIGINT
                      AND is_primary
                    LIMIT 1
                    """,
                    int(workspace_id),
                    int(character_id),
                )
            )
            await connection.execute(
                """
                INSERT INTO workspace_character_story_links (
                    workspace_id,
                    character_id,
                    story_id,
                    is_primary,
                    assigned_by_user_id
                )
                VALUES ($1::BIGINT, $2::BIGINT, $3::BIGINT, $4::BOOLEAN, $5::BIGINT)
                """,
                int(workspace_id),
                int(character_id),
                int(story_id),
                not has_primary,
                int(assigned_by_user_id),
            )
            return True


async def add_workspace_character_alias(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
    alias: str,
    created_by: int | None,
) -> WorkspaceCharacterAlias:
    cleaned, normalized = _clean_alias(alias)
    async with database.acquire() as connection:
        async with connection.transaction():
            character = await _require_character(
                connection,
                workspace_id=workspace_id,
                character_id=character_id,
                for_update=True,
            )
            conflict = await connection.fetchrow(
                """
                SELECT character_id
                FROM workspace_character_aliases
                WHERE workspace_id = $1::BIGINT
                  AND normalized_alias = $2::VARCHAR
                """,
                int(workspace_id),
                normalized,
            )
            if conflict is not None and int(conflict["character_id"]) != int(character_id):
                raise ValueError(
                    "Этот алиас уже принадлежит другому персонажу этого архива."
                )
            row = await connection.fetchrow(
                """
                INSERT INTO workspace_character_aliases (
                    workspace_id,
                    character_id,
                    alias,
                    normalized_alias,
                    source,
                    created_by
                )
                VALUES (
                    $1::BIGINT,
                    $2::BIGINT,
                    $3::VARCHAR,
                    $4::VARCHAR,
                    'manual',
                    $5::BIGINT
                )
                ON CONFLICT (character_id, normalized_alias) DO UPDATE
                SET alias = EXCLUDED.alias,
                    updated_at = NOW()
                RETURNING id, alias, normalized_alias, source
                """,
                int(workspace_id),
                int(character_id),
                cleaned,
                normalized,
                created_by,
            )
            if row is None:
                raise RuntimeError("Не удалось сохранить алиас.")
            if normalize_workspace_character_alias(str(character["name"])) == normalized:
                await connection.execute(
                    """
                    UPDATE workspace_character_aliases
                    SET source = 'name'
                    WHERE id = $1::BIGINT
                    """,
                    int(row["id"]),
                )
                source = "name"
            else:
                source = str(row["source"])
    return WorkspaceCharacterAlias(
        id=int(row["id"]),
        alias=str(row["alias"]),
        normalized_alias=str(row["normalized_alias"]),
        source=source,
    )


async def delete_workspace_character_alias(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
    alias: str,
) -> bool:
    normalized = normalize_workspace_character_alias(alias)
    if not normalized:
        return False
    async with database.acquire() as connection:
        await _require_character(
            connection,
            workspace_id=workspace_id,
            character_id=character_id,
        )
        row = await connection.fetchrow(
            """
            DELETE FROM workspace_character_aliases
            WHERE workspace_id = $1::BIGINT
              AND character_id = $2::BIGINT
              AND normalized_alias = $3::VARCHAR
              AND source <> 'name'
            RETURNING id
            """,
            int(workspace_id),
            int(character_id),
            normalized,
        )
    return row is not None


async def set_workspace_character_prompt_url(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
    prompt_post_url: str | None,
) -> None:
    cleaned = (
        validate_prompt_post_url(prompt_post_url)
        if prompt_post_url is not None
        else None
    )
    async with database.acquire() as connection:
        result = await connection.execute(
            """
            UPDATE characters
            SET prompt_post_url = $3::TEXT
            WHERE workspace_id = $1::BIGINT
              AND id = $2::BIGINT
            """,
            int(workspace_id),
            int(character_id),
            cleaned,
        )
    if result == "UPDATE 0":
        raise ValueError("Персонаж не найден в этом архиве.")


async def set_workspace_character_topic(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
    topic: TopicReference | None,
) -> None:
    async with database.acquire() as connection:
        async with connection.transaction():
            await _require_character(
                connection,
                workspace_id=workspace_id,
                character_id=character_id,
                for_update=True,
            )
            await connection.execute(
                "DELETE FROM character_archive_topics WHERE character_id = $1::BIGINT",
                int(character_id),
            )
            if topic is not None:
                await connection.execute(
                    """
                    INSERT INTO character_archive_topics (
                        character_id,
                        archive_chat_id,
                        archive_thread_id,
                        archive_topic_url
                    )
                    VALUES ($1::BIGINT, $2::BIGINT, $3::BIGINT, $4::TEXT)
                    """,
                    int(character_id),
                    int(topic.chat_id),
                    int(topic.thread_id),
                    topic.url,
                )
            result = await connection.execute(
                """
                UPDATE characters
                SET archive_chat_id = $3::BIGINT,
                    archive_thread_id = $4::BIGINT,
                    archive_topic_url = $5::TEXT
                WHERE workspace_id = $1::BIGINT
                  AND id = $2::BIGINT
                """,
                int(workspace_id),
                int(character_id),
                int(topic.chat_id) if topic is not None else None,
                int(topic.thread_id) if topic is not None else None,
                topic.url if topic is not None else None,
            )
            if result == "UPDATE 0":
                raise ValueError("Персонаж не найден в этом архиве.")


def _row_to_character(
    row,
    *,
    stories: tuple[WorkspaceCharacterStory, ...] = (),
    aliases: tuple[WorkspaceCharacterAlias, ...] = (),
) -> WorkspaceCharacterRecord:
    return WorkspaceCharacterRecord(
        id=int(row["id"]),
        workspace_id=int(row["workspace_id"]),
        name=str(row["name"]),
        category=row["category"],
        universe=row["universe"],
        prompt_post_url=row["prompt_post_url"],
        archive_chat_id=row["archive_chat_id"],
        archive_thread_id=row["archive_thread_id"],
        archive_topic_url=row["archive_topic_url"],
        stories=stories,
        aliases=aliases,
    )


__all__ = (
    "DeletedWorkspaceCharacter",
    "WorkspaceCharacterAlias",
    "WorkspaceCharacterRecord",
    "WorkspaceCharacterStory",
    "add_workspace_character_alias",
    "create_workspace_character",
    "delete_workspace_character",
    "delete_workspace_character_alias",
    "list_workspace_characters",
    "load_workspace_character",
    "normalize_workspace_character_alias",
    "rename_workspace_character",
    "set_workspace_character_category",
    "set_workspace_character_prompt_url",
    "set_workspace_character_topic",
    "set_workspace_character_universe",
    "toggle_workspace_character_story",
)
