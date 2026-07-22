from __future__ import annotations

import asyncpg

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, TypeAlias

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import WorkspaceChannelKind
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleKey

WorkspaceDestinationKey: TypeAlias = Literal[
    "characters",
    "media",
    "references",
    "public",
    "publications",
    "discussion",
    "analytics",
    "logs",
]

WORKSPACE_DESTINATION_KEYS: Final[tuple[WorkspaceDestinationKey, ...]] = (
    "characters",
    "media",
    "references",
    "public",
    "publications",
    "discussion",
    "analytics",
    "logs",
)


@dataclass(frozen=True, slots=True)
class WorkspaceDestinationSpec:
    key: WorkspaceDestinationKey
    label: str
    emoji: str
    description: str
    command_hint: str
    module_keys: tuple[WorkspaceModuleKey, ...]
    channel_kind: WorkspaceChannelKind | None
    requires_forum_admin: bool = False


DESTINATION_SPECS: Final[dict[WorkspaceDestinationKey, WorkspaceDestinationSpec]] = {
    "characters": WorkspaceDestinationSpec(
        key="characters",
        label="Персонажи",
        emoji="👥",
        description=(
            "Форумный чат архива персонажей. При создании персонажа бот создаёт "
            "в нём персональную тему и направляет туда копии сохранённых материалов."
        ),
        command_hint="/workspace_bind characters",
        module_keys=("characters", "archive"),
        channel_kind="archive",
        requires_forum_admin=True,
    ),
    "media": WorkspaceDestinationSpec(
        key="media",
        label="Материалы",
        emoji="🖼",
        description=(
            "Служебная отметка для уже существующего чата. Текущий поток сохранения "
            "не копирует сюда неразобранные материалы автоматически."
        ),
        command_hint="/workspace_bind media",
        module_keys=("archive",),
        channel_kind=None,
    ),
    "references": WorkspaceDestinationSpec(
        key="references",
        label="Референсы",
        emoji="🧬",
        description=(
            "Служебная отметка для чата команды. Референсы хранятся в библиотеке "
            "персонажа; автоматическое копирование в этот чат пока не выполняется."
        ),
        command_hint="/workspace_bind references",
        module_keys=("references",),
        channel_kind=None,
    ),
    "public": WorkspaceDestinationSpec(
        key="public",
        label="Публичный архив",
        emoji="🌐",
        description=(
            "Канал публичных постов для сбора статистики. Включение публичной "
            "витрины в боте не публикует материалы в этот канал автоматически."
        ),
        command_hint="/workspace_bind public",
        module_keys=("public_archive",),
        channel_kind="public",
    ),
    "publications": WorkspaceDestinationSpec(
        key="publications",
        label="Публикации",
        emoji="📣",
        description="Канал назначения для очереди и отправки готовых публикаций.",
        command_hint="/workspace_bind publications",
        module_keys=("publications",),
        channel_kind="publication",
    ),
    "discussion": WorkspaceDestinationSpec(
        key="discussion",
        label="Обсуждение",
        emoji="💬",
        description="Чат обсуждения публикаций и реакций аудитории.",
        command_hint="/workspace_bind discussion",
        module_keys=("publications", "analytics"),
        channel_kind="discussion",
    ),
    "analytics": WorkspaceDestinationSpec(
        key="analytics",
        label="Аналитика",
        emoji="📊",
        description=(
            "Канал-источник статистики. Бот обрабатывает channel posts; отдельная "
            "форумная тема не становится самостоятельным источником аналитики."
        ),
        command_hint="/workspace_bind analytics",
        module_keys=("analytics",),
        channel_kind="analytics",
    ),
    "logs": WorkspaceDestinationSpec(
        key="logs",
        label="Логи пространства",
        emoji="🧾",
        description=(
            "Служебная отметка для будущих уведомлений. В текущем личном потоке "
            "бот не отправляет туда сообщения автоматически."
        ),
        command_hint="/workspace_bind logs",
        module_keys=(),
        channel_kind="logs",
    ),
}


@dataclass(frozen=True, slots=True)
class WorkspaceOnboardingState:
    workspace_id: int
    status: str
    current_step: str
    modules_confirmed: bool
    guide_viewed: bool
    started_by_user_id: int | None
    completed_by_user_id: int | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceDestination:
    workspace_id: int
    destination_key: WorkspaceDestinationKey
    chat_id: int
    message_thread_id: int | None
    chat_type: str
    chat_title: str | None
    topic_title: str | None
    url: str | None
    bot_status: str
    can_post: bool
    can_manage_topics: bool
    configured_by_user_id: int
    verified_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceOnboardingReadiness:
    ready: bool
    missing_steps: tuple[str, ...]
    required_destinations: tuple[WorkspaceDestinationKey, ...]


def required_destination_keys(
    enabled_modules: set[WorkspaceModuleKey] | frozenset[WorkspaceModuleKey],
) -> tuple[WorkspaceDestinationKey, ...]:
    """Return only destinations required for the first usable personal archive.

    A personal workspace needs one main forum archive when characters or archive are
    enabled. Publication, analytics, discussion, public and log destinations are
    optional integrations configured later when their owner actually uses them.
    """

    if "characters" in enabled_modules or "archive" in enabled_modules:
        return ("characters",)
    return ()



def onboarding_readiness(
    *,
    modules_confirmed: bool,
    guide_viewed: bool,
    enabled_modules: set[WorkspaceModuleKey] | frozenset[WorkspaceModuleKey],
    configured_destinations: set[WorkspaceDestinationKey]
    | frozenset[WorkspaceDestinationKey],
) -> WorkspaceOnboardingReadiness:
    required = required_destination_keys(enabled_modules)
    missing: list[str] = []
    if not guide_viewed:
        missing.append("Откройте краткий гид по работе пространства.")
    if not modules_confirmed:
        missing.append("Подтвердите выбранные модули.")
    for key in required:
        if key not in configured_destinations:
            spec = DESTINATION_SPECS[key]
            missing.append(f"Подключите назначение «{spec.label}».")
    return WorkspaceOnboardingReadiness(
        ready=not missing,
        missing_steps=tuple(missing),
        required_destinations=required,
    )


class WorkspaceOnboardingRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def ensure_started(
        self,
        *,
        workspace_id: int,
        user_id: int,
    ) -> WorkspaceOnboardingState:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspace_onboarding (
                    workspace_id,
                    status,
                    current_step,
                    started_by_user_id,
                    started_at
                )
                VALUES ($1::BIGINT, 'in_progress', 'intro', $2::BIGINT, NOW())
                ON CONFLICT (workspace_id) DO UPDATE
                SET status = CASE
                        WHEN workspace_onboarding.status = 'completed'
                            THEN workspace_onboarding.status
                        ELSE 'in_progress'
                    END,
                    started_by_user_id = COALESCE(
                        workspace_onboarding.started_by_user_id,
                        EXCLUDED.started_by_user_id
                    ),
                    started_at = COALESCE(workspace_onboarding.started_at, NOW()),
                    updated_at = NOW()
                RETURNING *
                """,
                int(workspace_id),
                int(user_id),
            )
        if row is None:
            raise RuntimeError("Не удалось запустить настройку пространства.")
        return self._row_to_state(row)

    async def get_state(self, workspace_id: int) -> WorkspaceOnboardingState | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT * FROM workspace_onboarding WHERE workspace_id = $1::BIGINT",
                int(workspace_id),
            )
        return self._row_to_state(row) if row is not None else None

    async def set_step(self, *, workspace_id: int, step: str) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE workspace_onboarding
                SET current_step = $2::VARCHAR,
                    status = CASE WHEN status = 'completed' THEN status ELSE 'in_progress' END,
                    updated_at = NOW()
                WHERE workspace_id = $1::BIGINT
                """,
                int(workspace_id),
                step[:32],
            )

    async def mark_modules_confirmed(self, workspace_id: int) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE workspace_onboarding
                SET modules_confirmed = TRUE,
                    current_step = 'destinations',
                    updated_at = NOW()
                WHERE workspace_id = $1::BIGINT
                """,
                int(workspace_id),
            )

    async def mark_guide_viewed(self, workspace_id: int) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE workspace_onboarding
                SET guide_viewed = TRUE,
                    updated_at = NOW()
                WHERE workspace_id = $1::BIGINT
                """,
                int(workspace_id),
            )

    async def complete(self, *, workspace_id: int, user_id: int) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE workspace_onboarding
                SET status = 'completed',
                    current_step = 'complete',
                    completed_by_user_id = $2::BIGINT,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE workspace_id = $1::BIGINT
                """,
                int(workspace_id),
                int(user_id),
            )

    @staticmethod
    async def _upsert_destination_row(
        connection,
        *,
        workspace_id: int,
        destination_key: WorkspaceDestinationKey,
        chat_id: int,
        message_thread_id: int | None,
        chat_type: str,
        chat_title: str | None,
        topic_title: str | None,
        url: str | None,
        bot_status: str,
        can_post: bool,
        can_manage_topics: bool,
        configured_by_user_id: int,
    ):
        return await connection.fetchrow(
            """
            INSERT INTO workspace_destinations (
                workspace_id,
                destination_key,
                chat_id,
                message_thread_id,
                chat_type,
                chat_title,
                topic_title,
                url,
                bot_status,
                can_post,
                can_manage_topics,
                configured_by_user_id
            )
            VALUES (
                $1::BIGINT, $2::VARCHAR, $3::BIGINT, $4::BIGINT,
                $5::VARCHAR, $6::VARCHAR, $7::VARCHAR, $8::TEXT,
                $9::VARCHAR, $10::BOOLEAN, $11::BOOLEAN, $12::BIGINT
            )
            ON CONFLICT (workspace_id, destination_key) DO UPDATE
            SET chat_id = EXCLUDED.chat_id,
                message_thread_id = EXCLUDED.message_thread_id,
                chat_type = EXCLUDED.chat_type,
                chat_title = EXCLUDED.chat_title,
                topic_title = EXCLUDED.topic_title,
                url = EXCLUDED.url,
                bot_status = EXCLUDED.bot_status,
                can_post = EXCLUDED.can_post,
                can_manage_topics = EXCLUDED.can_manage_topics,
                configured_by_user_id = EXCLUDED.configured_by_user_id,
                verified_at = NOW(),
                updated_at = NOW()
            RETURNING *
            """,
            int(workspace_id),
            destination_key,
            int(chat_id),
            int(message_thread_id) if message_thread_id is not None else None,
            chat_type[:32],
            chat_title[:255] if chat_title else None,
            topic_title[:255] if topic_title else None,
            url,
            bot_status[:32],
            bool(can_post),
            bool(can_manage_topics),
            int(configured_by_user_id),
        )

    async def upsert_destination(
        self,
        *,
        workspace_id: int,
        destination_key: WorkspaceDestinationKey,
        chat_id: int,
        message_thread_id: int | None,
        chat_type: str,
        chat_title: str | None,
        topic_title: str | None,
        url: str | None,
        bot_status: str,
        can_post: bool,
        can_manage_topics: bool,
        configured_by_user_id: int,
    ) -> WorkspaceDestination:
        try:
            async with self._database.acquire() as connection:
                row = await self._upsert_destination_row(
                    connection,
                    workspace_id=workspace_id,
                    destination_key=destination_key,
                    chat_id=chat_id,
                    message_thread_id=message_thread_id,
                    chat_type=chat_type,
                    chat_title=chat_title,
                    topic_title=topic_title,
                    url=url,
                    bot_status=bot_status,
                    can_post=can_post,
                    can_manage_topics=can_manage_topics,
                    configured_by_user_id=configured_by_user_id,
                )
        except asyncpg.UniqueViolationError as error:
            raise ValueError(
                "Этот Telegram-чат уже подключён к другому пространству."
            ) from error
        if row is None:
            raise RuntimeError("Не удалось сохранить назначение пространства.")
        return self._row_to_destination(row)

    async def configure_destination(
        self,
        *,
        workspace_id: int,
        destination_key: WorkspaceDestinationKey,
        chat_id: int,
        message_thread_id: int | None,
        chat_type: str,
        chat_title: str | None,
        topic_title: str | None,
        url: str | None,
        bot_status: str,
        can_post: bool,
        can_manage_topics: bool,
        configured_by_user_id: int,
        channel_kind: WorkspaceChannelKind | None,
    ) -> WorkspaceDestination:
        """Persist wizard metadata and runtime routing atomically for one chat."""
        try:
            async with self._database.acquire() as connection:
                async with connection.transaction():
                    row = await self._upsert_destination_row(
                        connection,
                        workspace_id=workspace_id,
                        destination_key=destination_key,
                        chat_id=chat_id,
                        message_thread_id=message_thread_id,
                        chat_type=chat_type,
                        chat_title=chat_title,
                        topic_title=topic_title,
                        url=url,
                        bot_status=bot_status,
                        can_post=can_post,
                        can_manage_topics=can_manage_topics,
                        configured_by_user_id=configured_by_user_id,
                    )
                    if channel_kind is not None:
                        await connection.execute(
                            "SELECT pg_advisory_xact_lock($1::BIGINT)",
                            int(chat_id),
                        )
                        conflict_workspace_id = await connection.fetchval(
                            """
                            SELECT workspace_id
                            FROM workspace_channels
                            WHERE chat_id = $1::BIGINT
                              AND workspace_id <> $2::BIGINT
                            LIMIT 1
                            """,
                            int(chat_id),
                            int(workspace_id),
                        )
                        if conflict_workspace_id is not None:
                            raise ValueError(
                                "Этот Telegram-чат уже подключён к другому пространству."
                            )
                        await connection.execute(
                            """
                            INSERT INTO workspace_channels (workspace_id, kind, chat_id, url)
                            VALUES ($1::BIGINT, $2::VARCHAR, $3::BIGINT, $4::TEXT)
                            ON CONFLICT (workspace_id, kind) DO UPDATE
                            SET chat_id = EXCLUDED.chat_id,
                                url = EXCLUDED.url,
                                updated_at = NOW()
                            """,
                            int(workspace_id),
                            channel_kind,
                            int(chat_id),
                            url,
                        )
        except asyncpg.UniqueViolationError as error:
            raise ValueError(
                "Этот Telegram-чат уже подключён к другому пространству."
            ) from error
        if row is None:
            raise RuntimeError("Не удалось сохранить назначение пространства.")
        return self._row_to_destination(row)

    async def delete_destination(
        self,
        *,
        workspace_id: int,
        destination_key: WorkspaceDestinationKey,
    ) -> bool:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                DELETE FROM workspace_destinations
                WHERE workspace_id = $1::BIGINT
                  AND destination_key = $2::VARCHAR
                """,
                int(workspace_id),
                destination_key,
            )
        return result != "DELETE 0"

    async def unbind_destination(
        self,
        *,
        workspace_id: int,
        destination_key: WorkspaceDestinationKey,
        channel_kind: WorkspaceChannelKind | None,
    ) -> bool:
        """Remove an onboarding destination and its runtime channel as one change.

        `workspace_destinations` is the wizard's verified Telegram metadata,
        while `workspace_channels` is consumed by archive/publication/analytics
        workflows. Keeping the delete transactional prevents a supposedly
        disconnected channel from remaining active in those workflows.
        """
        async with self._database.acquire() as connection:
            async with connection.transaction():
                destination_result = await connection.execute(
                    """
                    DELETE FROM workspace_destinations
                    WHERE workspace_id = $1::BIGINT
                      AND destination_key = $2::VARCHAR
                    """,
                    int(workspace_id),
                    destination_key,
                )
                channel_result = "DELETE 0"
                if channel_kind is not None:
                    channel_result = await connection.execute(
                        """
                        DELETE FROM workspace_channels
                        WHERE workspace_id = $1::BIGINT
                          AND kind = $2::VARCHAR
                        """,
                        int(workspace_id),
                        channel_kind,
                    )
        return destination_result != "DELETE 0" or channel_result != "DELETE 0"

    async def list_destinations(
        self,
        workspace_id: int,
    ) -> tuple[WorkspaceDestination, ...]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT *
                FROM workspace_destinations
                WHERE workspace_id = $1::BIGINT
                ORDER BY destination_key ASC
                """,
                int(workspace_id),
            )
        return tuple(self._row_to_destination(row) for row in rows)

    @staticmethod
    def _row_to_state(row) -> WorkspaceOnboardingState:
        return WorkspaceOnboardingState(
            workspace_id=int(row["workspace_id"]),
            status=str(row["status"]),
            current_step=str(row["current_step"]),
            modules_confirmed=bool(row["modules_confirmed"]),
            guide_viewed=bool(row["guide_viewed"]),
            started_by_user_id=(
                int(row["started_by_user_id"])
                if row["started_by_user_id"] is not None
                else None
            ),
            completed_by_user_id=(
                int(row["completed_by_user_id"])
                if row["completed_by_user_id"] is not None
                else None
            ),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_destination(row) -> WorkspaceDestination:
        return WorkspaceDestination(
            workspace_id=int(row["workspace_id"]),
            destination_key=str(row["destination_key"]),
            chat_id=int(row["chat_id"]),
            message_thread_id=(
                int(row["message_thread_id"])
                if row["message_thread_id"] is not None
                else None
            ),
            chat_type=str(row["chat_type"]),
            chat_title=str(row["chat_title"]) if row["chat_title"] else None,
            topic_title=str(row["topic_title"]) if row["topic_title"] else None,
            url=str(row["url"]) if row["url"] else None,
            bot_status=str(row["bot_status"]),
            can_post=bool(row["can_post"]),
            can_manage_topics=bool(row["can_manage_topics"]),
            configured_by_user_id=int(row["configured_by_user_id"]),
            verified_at=row["verified_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


__all__ = (
    "DESTINATION_SPECS",
    "WORKSPACE_DESTINATION_KEYS",
    "WorkspaceDestination",
    "WorkspaceDestinationKey",
    "WorkspaceDestinationSpec",
    "WorkspaceOnboardingReadiness",
    "WorkspaceOnboardingRepository",
    "WorkspaceOnboardingState",
    "onboarding_readiness",
    "required_destination_keys",
)
