from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from velvet_bot.archive_topic_links import bind_character_archive_topic
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.character_management import WorkspaceCharacterRecord
from velvet_bot.topics import TopicReference

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CharacterTopicProvisionResult:
    linked: bool
    created: bool
    topic: TopicReference | None
    error: str | None = None


def _private_topic_url(chat_id: int, thread_id: int) -> str:
    raw = str(abs(int(chat_id)))
    internal = raw[3:] if raw.startswith("100") else raw
    return f"https://t.me/c/{internal}/{int(thread_id)}"


async def _character_destination(database: Database, *, workspace_id: int):
    async with database.acquire() as connection:
        return await connection.fetchrow(
            """
            SELECT
                chat_id,
                can_manage_topics,
                bot_status
            FROM workspace_destinations
            WHERE workspace_id = $1::BIGINT
              AND destination_key = 'characters'
            """,
            int(workspace_id),
        )


async def ensure_character_archive_topic(
    *,
    bot: Bot,
    database: Database,
    workspace_id: int,
    character: WorkspaceCharacterRecord,
) -> CharacterTopicProvisionResult:
    """Create and bind one forum topic for a workspace character when configured.

    Character creation remains successful if Telegram is temporarily unavailable.
    The result explains the missing topic so the owner can retry through the
    character panel instead of losing the character record.
    """

    if character.archive_chat_id is not None and character.archive_thread_id is not None:
        topic = TopicReference(
            chat_id=int(character.archive_chat_id),
            thread_id=int(character.archive_thread_id),
            url=(
                character.archive_topic_url
                or _private_topic_url(
                    int(character.archive_chat_id),
                    int(character.archive_thread_id),
                )
            ),
        )
        return CharacterTopicProvisionResult(
            linked=True,
            created=False,
            topic=topic,
        )

    destination = await _character_destination(
        database,
        workspace_id=int(workspace_id),
    )
    if destination is None:
        return CharacterTopicProvisionResult(
            linked=False,
            created=False,
            topic=None,
            error=(
                "В мастере пространства не подключён форум «Персонажи». "
                "Откройте /workspace_setup и завершите настройку чатов."
            ),
        )
    if not bool(destination["can_manage_topics"]):
        return CharacterTopicProvisionResult(
            linked=False,
            created=False,
            topic=None,
            error=(
                "У бота нет права управления темами в форуме персонажей. "
                "Выдайте право и заново подключите назначение."
            ),
        )

    chat_id = int(destination["chat_id"])
    created_topic = None
    try:
        created_topic = await bot.create_forum_topic(
            chat_id=chat_id,
            name=character.name[:128],
        )
        topic = TopicReference(
            chat_id=chat_id,
            thread_id=int(created_topic.message_thread_id),
            url=_private_topic_url(chat_id, int(created_topic.message_thread_id)),
        )
        await bind_character_archive_topic(
            database,
            character_id=character.id,
            topic=topic,
            workspace_id=int(workspace_id),
        )
    except TelegramAPIError as error:
        logger.warning(
            "Could not create workspace character topic workspace=%s character=%s: %s",
            workspace_id,
            character.id,
            error,
        )
        return CharacterTopicProvisionResult(
            linked=False,
            created=False,
            topic=None,
            error=f"Telegram не создал тему персонажа: {error}",
        )
    except Exception:  # p2-approved-boundary: cleanup-orphan-character-topic
        if created_topic is not None:
            try:
                await bot.delete_forum_topic(
                    chat_id=chat_id,
                    message_thread_id=int(created_topic.message_thread_id),
                )
            except TelegramAPIError:
                logger.warning(
                    "Could not remove orphan character topic chat=%s thread=%s",
                    chat_id,
                    created_topic.message_thread_id,
                )
        raise

    return CharacterTopicProvisionResult(
        linked=True,
        created=True,
        topic=topic,
    )


__all__ = (
    "CharacterTopicProvisionResult",
    "ensure_character_archive_topic",
)
