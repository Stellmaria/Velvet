from __future__ import annotations

from collections.abc import Iterable

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID, Workspace
from velvet_bot.domains.workspaces.product_models import (
    WORKSPACE_MODULE_KEYS,
    WorkspaceCategory,
    WorkspaceCreationGrant,
    WorkspaceModuleKey,
    WorkspaceModuleSetting,
    WorkspaceStory,
    WorkspaceUniverse,
)


class WorkspaceProductRepository:
    """Persistence for workspace grants, modules, public discovery and taxonomy."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_creation_grant(self, user_id: int) -> WorkspaceCreationGrant | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT user_id, granted_by_user_id, allowed_modules, max_workspaces,
                       is_active, granted_at, updated_at
                FROM workspace_creation_grants
                WHERE user_id = $1::BIGINT
                """,
                int(user_id),
            )
        return self._row_to_grant(row) if row is not None else None

    async def upsert_creation_grant(
        self,
        *,
        user_id: int,
        granted_by_user_id: int,
        allowed_modules: Iterable[WorkspaceModuleKey],
        max_workspaces: int = 1,
    ) -> WorkspaceCreationGrant:
        modules = list(dict.fromkeys(str(item) for item in allowed_modules))
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspace_creation_grants (
                    user_id, granted_by_user_id, allowed_modules, max_workspaces, is_active
                )
                VALUES ($1::BIGINT, $2::BIGINT, $3::TEXT[], $4::INTEGER, TRUE)
                ON CONFLICT (user_id) DO UPDATE
                SET granted_by_user_id = EXCLUDED.granted_by_user_id,
                    allowed_modules = EXCLUDED.allowed_modules,
                    max_workspaces = EXCLUDED.max_workspaces,
                    is_active = TRUE,
                    updated_at = NOW()
                RETURNING user_id, granted_by_user_id, allowed_modules, max_workspaces,
                          is_active, granted_at, updated_at
                """,
                int(user_id),
                int(granted_by_user_id),
                modules,
                int(max_workspaces),
            )
        if row is None:
            raise RuntimeError("Не удалось выдать право на создание архива.")
        return self._row_to_grant(row)

    async def revoke_creation_grant(self, user_id: int) -> bool:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE workspace_creation_grants
                SET is_active = FALSE,
                    updated_at = NOW()
                WHERE user_id = $1::BIGINT
                  AND is_active
                """,
                int(user_id),
            )
        return result != "UPDATE 0"

    async def count_owned_personal_workspaces(self, user_id: int) -> int:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM workspace_members AS member
                JOIN workspaces AS workspace ON workspace.id = member.workspace_id
                WHERE member.user_id = $1::BIGINT
                  AND member.role = 'owner'
                  AND workspace.is_system = FALSE
                """,
                int(user_id),
            )
        return int(value or 0)

    async def list_owned_personal_workspaces(self, user_id: int) -> tuple[Workspace, ...]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT workspace.id, workspace.slug, workspace.name, workspace.is_system,
                       workspace.created_at, workspace.updated_at
                FROM workspace_members AS member
                JOIN workspaces AS workspace ON workspace.id = member.workspace_id
                WHERE member.user_id = $1::BIGINT
                  AND member.role = 'owner'
                  AND workspace.is_system = FALSE
                ORDER BY workspace.created_at, workspace.id
                """,
                int(user_id),
            )
        return tuple(self._row_to_workspace(row) for row in rows)

    async def list_public_workspaces(self) -> tuple[Workspace, ...]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT workspace.id, workspace.slug, workspace.name, workspace.is_system,
                       workspace.created_at, workspace.updated_at
                FROM workspaces AS workspace
                JOIN workspace_settings AS settings
                  ON settings.workspace_id = workspace.id
                WHERE settings.public_archive_enabled
                ORDER BY workspace.is_system DESC, workspace.name, workspace.id
                """
            )
        return tuple(self._row_to_workspace(row) for row in rows)

    async def set_public_browse_workspace(self, *, user_id: int, workspace_id: int) -> bool:
        async with self._database.acquire() as connection:
            selected = await connection.fetchval(
                """
                SELECT TRUE
                FROM workspace_settings
                WHERE workspace_id = $1::BIGINT
                  AND public_archive_enabled
                """,
                int(workspace_id),
            )
            if not selected:
                return False
            await connection.execute(
                """
                INSERT INTO user_public_workspace_preferences (user_id, workspace_id)
                VALUES ($1::BIGINT, $2::BIGINT)
                ON CONFLICT (user_id) DO UPDATE
                SET workspace_id = EXCLUDED.workspace_id,
                    updated_at = NOW()
                """,
                int(user_id),
                int(workspace_id),
            )
        return True

    async def get_public_browse_workspace_id(self, user_id: int) -> int:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT preference.workspace_id
                FROM user_public_workspace_preferences AS preference
                JOIN workspace_settings AS settings
                  ON settings.workspace_id = preference.workspace_id
                 AND settings.public_archive_enabled
                WHERE preference.user_id = $1::BIGINT
                """,
                int(user_id),
            )
        return int(value) if value is not None else DEFAULT_WORKSPACE_ID

    async def initialize_modules(
        self,
        *,
        workspace_id: int,
        allowed_modules: Iterable[WorkspaceModuleKey],
        updated_by_user_id: int,
    ) -> None:
        allowed = {str(item) for item in allowed_modules}
        async with self._database.acquire() as connection:
            async with connection.transaction():
                for module_key in WORKSPACE_MODULE_KEYS:
                    is_allowed = module_key in allowed
                    await connection.execute(
                        """
                        INSERT INTO workspace_modules (
                            workspace_id, module_key, is_allowed, is_enabled,
                            updated_by_user_id
                        )
                        VALUES ($1::BIGINT, $2::VARCHAR, $3::BOOLEAN, $3::BOOLEAN, $4::BIGINT)
                        ON CONFLICT (workspace_id, module_key) DO UPDATE
                        SET is_allowed = EXCLUDED.is_allowed,
                            is_enabled = CASE
                                WHEN EXCLUDED.is_allowed THEN workspace_modules.is_enabled
                                ELSE FALSE
                            END,
                            updated_by_user_id = EXCLUDED.updated_by_user_id,
                            updated_at = NOW()
                        """,
                        int(workspace_id),
                        module_key,
                        is_allowed,
                        int(updated_by_user_id),
                    )

    async def list_modules(self, workspace_id: int) -> tuple[WorkspaceModuleSetting, ...]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT workspace_id, module_key, is_allowed, is_enabled,
                       updated_by_user_id, created_at, updated_at
                FROM workspace_modules
                WHERE workspace_id = $1::BIGINT
                ORDER BY module_key
                """,
                int(workspace_id),
            )
        return tuple(self._row_to_module(row) for row in rows)

    async def set_module_policy(
        self,
        *,
        workspace_id: int,
        module_key: WorkspaceModuleKey,
        is_allowed: bool,
        updated_by_user_id: int,
    ) -> WorkspaceModuleSetting:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspace_modules (
                    workspace_id, module_key, is_allowed, is_enabled, updated_by_user_id
                )
                VALUES ($1::BIGINT, $2::VARCHAR, $3::BOOLEAN, $3::BOOLEAN, $4::BIGINT)
                ON CONFLICT (workspace_id, module_key) DO UPDATE
                SET is_allowed = EXCLUDED.is_allowed,
                    is_enabled = CASE
                        WHEN EXCLUDED.is_allowed THEN workspace_modules.is_enabled
                        ELSE FALSE
                    END,
                    updated_by_user_id = EXCLUDED.updated_by_user_id,
                    updated_at = NOW()
                RETURNING workspace_id, module_key, is_allowed, is_enabled,
                          updated_by_user_id, created_at, updated_at
                """,
                int(workspace_id),
                module_key,
                bool(is_allowed),
                int(updated_by_user_id),
            )
        if row is None:
            raise RuntimeError("Не удалось изменить доступность модуля.")
        return self._row_to_module(row)

    async def set_module_enabled(
        self,
        *,
        workspace_id: int,
        module_key: WorkspaceModuleKey,
        is_enabled: bool,
        updated_by_user_id: int,
    ) -> WorkspaceModuleSetting | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE workspace_modules
                SET is_enabled = $3::BOOLEAN,
                    updated_by_user_id = $4::BIGINT,
                    updated_at = NOW()
                WHERE workspace_id = $1::BIGINT
                  AND module_key = $2::VARCHAR
                  AND is_allowed
                RETURNING workspace_id, module_key, is_allowed, is_enabled,
                          updated_by_user_id, created_at, updated_at
                """,
                int(workspace_id),
                module_key,
                bool(is_enabled),
                int(updated_by_user_id),
            )
        return self._row_to_module(row) if row is not None else None

    async def upsert_category(
        self,
        *,
        workspace_id: int,
        key: str,
        label: str,
        emoji: str,
        created_by_user_id: int,
    ) -> WorkspaceCategory:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspace_categories (
                    workspace_id, key, label, emoji, created_by_user_id
                )
                VALUES ($1::BIGINT, $2::VARCHAR, $3::VARCHAR, $4::VARCHAR, $5::BIGINT)
                ON CONFLICT (workspace_id, key) DO UPDATE
                SET label = EXCLUDED.label,
                    emoji = EXCLUDED.emoji,
                    is_enabled = TRUE,
                    updated_at = NOW()
                RETURNING id, workspace_id, key, label, emoji, sort_order, is_enabled
                """,
                int(workspace_id),
                key,
                label,
                emoji,
                int(created_by_user_id),
            )
        if row is None:
            raise RuntimeError("Не удалось сохранить категорию.")
        return self._row_to_category(row)

    async def list_categories(self, workspace_id: int) -> tuple[WorkspaceCategory, ...]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT id, workspace_id, key, label, emoji, sort_order, is_enabled
                FROM workspace_categories
                WHERE workspace_id = $1::BIGINT
                ORDER BY is_enabled DESC, sort_order, label, id
                """,
                int(workspace_id),
            )
        return tuple(self._row_to_category(row) for row in rows)

    async def upsert_universe(
        self,
        *,
        workspace_id: int,
        key: str,
        label: str,
        emoji: str,
        requires_story: bool,
        created_by_user_id: int,
        source_workspace_id: int | None = None,
        source_universe_key: str | None = None,
    ) -> WorkspaceUniverse:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspace_universes (
                    workspace_id, key, label, emoji, requires_story,
                    source_workspace_id, source_universe_key, created_by_user_id
                )
                VALUES (
                    $1::BIGINT, $2::VARCHAR, $3::VARCHAR, $4::VARCHAR, $5::BOOLEAN,
                    $6::BIGINT, $7::VARCHAR, $8::BIGINT
                )
                ON CONFLICT (workspace_id, key) DO UPDATE
                SET label = EXCLUDED.label,
                    emoji = EXCLUDED.emoji,
                    requires_story = EXCLUDED.requires_story,
                    is_enabled = TRUE,
                    source_workspace_id = COALESCE(
                        EXCLUDED.source_workspace_id,
                        workspace_universes.source_workspace_id
                    ),
                    source_universe_key = COALESCE(
                        EXCLUDED.source_universe_key,
                        workspace_universes.source_universe_key
                    ),
                    updated_at = NOW()
                RETURNING id, workspace_id, key, label, emoji, requires_story,
                          sort_order, is_enabled, source_workspace_id, source_universe_key
                """,
                int(workspace_id),
                key,
                label,
                emoji,
                bool(requires_story),
                source_workspace_id,
                source_universe_key,
                int(created_by_user_id),
            )
        if row is None:
            raise RuntimeError("Не удалось сохранить вселенную.")
        return self._row_to_universe(row)

    async def list_universes(self, workspace_id: int) -> tuple[WorkspaceUniverse, ...]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT id, workspace_id, key, label, emoji, requires_story,
                       sort_order, is_enabled, source_workspace_id, source_universe_key
                FROM workspace_universes
                WHERE workspace_id = $1::BIGINT
                ORDER BY is_enabled DESC, sort_order, label, id
                """,
                int(workspace_id),
            )
        return tuple(self._row_to_universe(row) for row in rows)

    async def upsert_story(
        self,
        *,
        workspace_id: int,
        universe_key: str,
        key: str,
        short_label: str,
        title: str,
        created_by_user_id: int,
        source_story_id: int | None = None,
    ) -> WorkspaceStory:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspace_stories (
                    workspace_id, universe_key, key, short_label, title,
                    source_story_id, created_by_user_id
                )
                VALUES (
                    $1::BIGINT, $2::VARCHAR, $3::VARCHAR, $4::VARCHAR,
                    $5::VARCHAR, $6::BIGINT, $7::BIGINT
                )
                ON CONFLICT (workspace_id, universe_key, key) DO UPDATE
                SET short_label = EXCLUDED.short_label,
                    title = EXCLUDED.title,
                    is_enabled = TRUE,
                    source_story_id = COALESCE(
                        EXCLUDED.source_story_id,
                        workspace_stories.source_story_id
                    ),
                    updated_at = NOW()
                RETURNING id, workspace_id, universe_key, key, short_label, title,
                          sort_order, is_enabled, source_story_id
                """,
                int(workspace_id),
                universe_key,
                key,
                short_label,
                title,
                source_story_id,
                int(created_by_user_id),
            )
        if row is None:
            raise RuntimeError("Не удалось сохранить историю.")
        return self._row_to_story(row)

    async def list_stories(
        self,
        *,
        workspace_id: int,
        universe_key: str | None = None,
    ) -> tuple[WorkspaceStory, ...]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT id, workspace_id, universe_key, key, short_label, title,
                       sort_order, is_enabled, source_story_id
                FROM workspace_stories
                WHERE workspace_id = $1::BIGINT
                  AND ($2::VARCHAR IS NULL OR universe_key = $2::VARCHAR)
                ORDER BY universe_key, is_enabled DESC, sort_order, title, id
                """,
                int(workspace_id),
                universe_key,
            )
        return tuple(self._row_to_story(row) for row in rows)

    async def import_universe_template(
        self,
        *,
        target_workspace_id: int,
        source_workspace_id: int,
        universe_key: str,
        created_by_user_id: int,
    ) -> tuple[WorkspaceUniverse, int]:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                source = await connection.fetchrow(
                    """
                    SELECT key, label, emoji, requires_story, sort_order
                    FROM workspace_universes
                    WHERE workspace_id = $1::BIGINT
                      AND key = $2::VARCHAR
                      AND is_enabled
                    """,
                    int(source_workspace_id),
                    universe_key,
                )
                if source is None:
                    raise ValueError("Шаблон вселенной не найден.")
                row = await connection.fetchrow(
                    """
                    INSERT INTO workspace_universes (
                        workspace_id, key, label, emoji, requires_story, sort_order,
                        source_workspace_id, source_universe_key, created_by_user_id
                    )
                    VALUES (
                        $1::BIGINT, $2::VARCHAR, $3::VARCHAR, $4::VARCHAR,
                        $5::BOOLEAN, $6::INTEGER, $7::BIGINT, $2::VARCHAR, $8::BIGINT
                    )
                    ON CONFLICT (workspace_id, key) DO UPDATE
                    SET label = EXCLUDED.label,
                        emoji = EXCLUDED.emoji,
                        requires_story = EXCLUDED.requires_story,
                        is_enabled = TRUE,
                        source_workspace_id = EXCLUDED.source_workspace_id,
                        source_universe_key = EXCLUDED.source_universe_key,
                        updated_at = NOW()
                    RETURNING id, workspace_id, key, label, emoji, requires_story,
                              sort_order, is_enabled, source_workspace_id,
                              source_universe_key
                    """,
                    int(target_workspace_id),
                    str(source["key"]),
                    str(source["label"]),
                    str(source["emoji"]),
                    bool(source["requires_story"]),
                    int(source["sort_order"] or 100),
                    int(source_workspace_id),
                    int(created_by_user_id),
                )
                copied = await connection.fetchval(
                    """
                    WITH inserted AS (
                        INSERT INTO workspace_stories (
                            workspace_id, universe_key, key, short_label, title,
                            sort_order, source_story_id, created_by_user_id
                        )
                        SELECT
                            $1::BIGINT,
                            source.universe_key,
                            source.key,
                            source.short_label,
                            source.title,
                            source.sort_order,
                            source.source_story_id,
                            $4::BIGINT
                        FROM workspace_stories AS source
                        WHERE source.workspace_id = $2::BIGINT
                          AND source.universe_key = $3::VARCHAR
                          AND source.is_enabled
                        ON CONFLICT (workspace_id, universe_key, key) DO UPDATE
                        SET short_label = EXCLUDED.short_label,
                            title = EXCLUDED.title,
                            is_enabled = TRUE,
                            source_story_id = EXCLUDED.source_story_id,
                            updated_at = NOW()
                        RETURNING 1
                    )
                    SELECT COUNT(*) FROM inserted
                    """,
                    int(target_workspace_id),
                    int(source_workspace_id),
                    universe_key,
                    int(created_by_user_id),
                )
        if row is None:
            raise RuntimeError("Не удалось импортировать вселенную.")
        return self._row_to_universe(row), int(copied or 0)

    @staticmethod
    def _row_to_grant(row) -> WorkspaceCreationGrant:
        modules = tuple(
            item for item in row["allowed_modules"] if item in WORKSPACE_MODULE_KEYS
        )
        return WorkspaceCreationGrant(
            user_id=int(row["user_id"]),
            granted_by_user_id=int(row["granted_by_user_id"]),
            allowed_modules=modules,
            max_workspaces=int(row["max_workspaces"]),
            is_active=bool(row["is_active"]),
            granted_at=row["granted_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_workspace(row) -> Workspace:
        return Workspace(
            id=int(row["id"]),
            slug=str(row["slug"]),
            name=str(row["name"]),
            is_system=bool(row["is_system"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_module(row) -> WorkspaceModuleSetting:
        return WorkspaceModuleSetting(
            workspace_id=int(row["workspace_id"]),
            module_key=str(row["module_key"]),
            is_allowed=bool(row["is_allowed"]),
            is_enabled=bool(row["is_enabled"]),
            updated_by_user_id=(
                int(row["updated_by_user_id"])
                if row["updated_by_user_id"] is not None
                else None
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_category(row) -> WorkspaceCategory:
        return WorkspaceCategory(
            id=int(row["id"]),
            workspace_id=int(row["workspace_id"]),
            key=str(row["key"]),
            label=str(row["label"]),
            emoji=str(row["emoji"]),
            sort_order=int(row["sort_order"]),
            is_enabled=bool(row["is_enabled"]),
        )

    @staticmethod
    def _row_to_universe(row) -> WorkspaceUniverse:
        return WorkspaceUniverse(
            id=int(row["id"]),
            workspace_id=int(row["workspace_id"]),
            key=str(row["key"]),
            label=str(row["label"]),
            emoji=str(row["emoji"]),
            requires_story=bool(row["requires_story"]),
            sort_order=int(row["sort_order"]),
            is_enabled=bool(row["is_enabled"]),
            source_workspace_id=(
                int(row["source_workspace_id"])
                if row["source_workspace_id"] is not None
                else None
            ),
            source_universe_key=(
                str(row["source_universe_key"])
                if row["source_universe_key"] is not None
                else None
            ),
        )

    @staticmethod
    def _row_to_story(row) -> WorkspaceStory:
        return WorkspaceStory(
            id=int(row["id"]),
            workspace_id=int(row["workspace_id"]),
            universe_key=str(row["universe_key"]),
            key=str(row["key"]),
            short_label=str(row["short_label"]),
            title=str(row["title"]),
            sort_order=int(row["sort_order"]),
            is_enabled=bool(row["is_enabled"]),
            source_story_id=(
                int(row["source_story_id"])
                if row["source_story_id"] is not None
                else None
            ),
        )


__all__ = ("WorkspaceProductRepository",)
