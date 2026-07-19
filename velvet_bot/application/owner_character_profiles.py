from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from velvet_bot.app.references import build_reference_service
from velvet_bot.archive_topic_links import bind_character_archive_topic
from velvet_bot.character_resolution import resolve_character
from velvet_bot.database import Character, Database
from velvet_bot.topics import TopicReference, split_character_and_topic

TopicValidator = Callable[[TopicReference], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class CharacterProfile:
    character: Character
    media_count: int
    reference_count: int


@dataclass(frozen=True, slots=True)
class CreateCharacterResult:
    profile: CharacterProfile
    created: bool
    topic_supplied: bool


async def load_character_profile(
    database: Database,
    character_name: str,
) -> CharacterProfile | None:
    character = await resolve_character(database, character_name)
    if character is None:
        return None
    return await _profile(database, character)


async def create_character_profile(
    database: Database,
    raw_value: str,
    *,
    actor_id: int | None,
    chat_id: int | None,
    validate_topic: TopicValidator,
) -> CreateCharacterResult:
    character_name, topic = split_character_and_topic(raw_value)
    character, created = await database.create_character(
        character_name,
        created_by=actor_id,
        created_in_chat=chat_id,
    )
    if topic is not None:
        await validate_topic(topic)
        character = await bind_character_archive_topic(
            database,
            character_id=character.id,
            topic=topic,
        )
    return CreateCharacterResult(
        profile=await _profile(database, character),
        created=created,
        topic_supplied=topic is not None,
    )


async def bind_character_topic(
    database: Database,
    raw_value: str,
    *,
    validate_topic: TopicValidator,
) -> CharacterProfile:
    character_name, topic = split_character_and_topic(raw_value)
    if topic is None:
        raise ValueError("После имени укажите ссылку на тему Telegram.")
    character = await resolve_character(database, character_name)
    if character is None:
        raise ValueError("Такой персонаж или быстрый тег не найден.")
    await validate_topic(topic)
    character = await bind_character_archive_topic(
        database,
        character_id=character.id,
        topic=topic,
    )
    return await _profile(database, character)


async def _profile(database: Database, character: Character) -> CharacterProfile:
    return CharacterProfile(
        character=character,
        media_count=await database.count_character_media(character.id),
        reference_count=await build_reference_service(database).count(character.id),
    )


__all__ = (
    "CharacterProfile",
    "CreateCharacterResult",
    "TopicValidator",
    "bind_character_topic",
    "create_character_profile",
    "load_character_profile",
)
