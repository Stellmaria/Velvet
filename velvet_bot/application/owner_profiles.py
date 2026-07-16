from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from velvet_bot.character_aliases import (
    CharacterAlias,
    add_character_alias,
    delete_character_alias,
    ensure_name_aliases,
    list_character_aliases,
    rebuild_hashtag_character_links,
)
from velvet_bot.character_directory import (
    get_character_directory_item,
    normalize_category,
    normalize_universe,
    set_character_category,
    set_character_prompt_url,
    set_character_universe,
    validate_prompt_post_url,
)
from velvet_bot.database import Character, Database
from velvet_bot.reference_catalog import count_character_references
from velvet_bot.story_catalog import (
    CharacterStory,
    create_story,
    find_story,
    list_stories,
    set_character_story,
)
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


@dataclass(frozen=True, slots=True)
class CharacterValueResult:
    character: Character
    value: str | None


@dataclass(frozen=True, slots=True)
class StoryAssignmentResult:
    character: Character
    story: CharacterStory | None
    removed: bool


@dataclass(frozen=True, slots=True)
class StoryListResult:
    universe: str
    stories: tuple[CharacterStory, ...]


@dataclass(frozen=True, slots=True)
class AliasDeleteResult:
    character: Character
    alias: str
    deleted: bool


@dataclass(frozen=True, slots=True)
class AliasIndexResult:
    created_name_aliases: int
    matched_links: int
    total_hashtags: int


async def load_character_profile(
    database: Database,
    character_name: str,
) -> CharacterProfile | None:
    character = await database.get_character(character_name)
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
        character = await database.bind_character_topic(
            character.id,
            archive_chat_id=topic.chat_id,
            archive_thread_id=topic.thread_id,
            archive_topic_url=topic.url,
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
    character = await _require_character(database, character_name)
    await validate_topic(topic)
    character = await database.bind_character_topic(
        character.id,
        archive_chat_id=topic.chat_id,
        archive_thread_id=topic.thread_id,
        archive_topic_url=topic.url,
    )
    return await _profile(database, character)


async def set_category_from_text(
    database: Database,
    raw_value: str,
) -> CharacterValueResult:
    character_name, raw_category = _split_tail(raw_value, "категорию")
    character = await _require_character(database, character_name)
    category = normalize_category(raw_category, allow_uncategorized=True)
    stored = None if category == "uncategorized" else category
    await set_character_category(
        database,
        character_id=character.id,
        category=stored,
    )
    return CharacterValueResult(character=character, value=stored)


async def set_universe_from_text(
    database: Database,
    raw_value: str,
) -> CharacterValueResult:
    character_name, raw_universe = _split_tail(raw_value, "вселенную")
    character = await _require_character(database, character_name)
    universe = normalize_universe(raw_universe, allow_unassigned=True)
    stored = None if universe == "unassigned" else universe
    await set_character_universe(
        database,
        character_id=character.id,
        universe=stored,
    )
    return CharacterValueResult(character=character, value=stored)


async def set_prompt_from_text(
    database: Database,
    raw_value: str,
) -> CharacterValueResult:
    character_name, prompt_value = _split_tail(raw_value, "ссылку на промт")
    character = await _require_character(database, character_name)
    if prompt_value.casefold() in {"off", "нет", "удалить", "-"}:
        prompt_url = None
    else:
        prompt_url = validate_prompt_post_url(prompt_value)
    await set_character_prompt_url(
        database,
        character_id=character.id,
        prompt_post_url=prompt_url,
    )
    return CharacterValueResult(character=character, value=prompt_url)


async def set_story_from_text(
    database: Database,
    raw_value: str,
) -> StoryAssignmentResult:
    character_name, raw_story = _split_tail(raw_value, "сокращение истории")
    character = await _require_character(database, character_name)
    item = await get_character_directory_item(database, character.id)
    if item is None or not item.universe:
        raise ValueError("Сначала назначьте персонажу вселенную.")

    if raw_story.casefold() in {"без", "нет", "off", "удалить", "-"}:
        await set_character_story(
            database,
            character_id=character.id,
            story_id=None,
        )
        return StoryAssignmentResult(character=character, story=None, removed=True)

    story = await find_story(
        database,
        universe=item.universe,
        value=raw_story,
    )
    if story is None:
        raise ValueError("История не найдена в этой вселенной.")
    await set_character_story(
        database,
        character_id=character.id,
        story_id=story.id,
    )
    return StoryAssignmentResult(character=character, story=story, removed=False)


async def add_story_from_text(
    database: Database,
    raw_value: str,
) -> CharacterStory:
    parts = raw_value.split(maxsplit=2)
    if len(parts) != 3:
        raise ValueError("Укажите вселенную, сокращение и полное название истории.")
    raw_universe, short_label, title = parts
    universe = normalize_universe(raw_universe)
    return await create_story(
        database,
        universe=universe,
        short_label=short_label,
        title=title,
    )


async def list_stories_from_text(
    database: Database,
    raw_value: str,
) -> StoryListResult:
    universe = normalize_universe(raw_value)
    stories = await list_stories(database, universe=universe)
    return StoryListResult(universe=universe, stories=tuple(stories))


async def add_alias_from_text(
    database: Database,
    raw_value: str,
    *,
    actor_id: int | None,
) -> CharacterAlias:
    character_name, alias = _split_tail(raw_value, "алиас")
    character = await _require_character(database, character_name)
    return await add_character_alias(
        database,
        character_id=character.id,
        alias=alias,
        created_by=actor_id,
    )


async def list_aliases_from_text(
    database: Database,
    raw_value: str,
) -> tuple[Character, tuple[CharacterAlias, ...]]:
    character = await _require_character(database, raw_value)
    aliases = await list_character_aliases(database, character_id=character.id)
    return character, tuple(aliases)


async def delete_alias_from_text(
    database: Database,
    raw_value: str,
) -> AliasDeleteResult:
    character_name, alias = _split_tail(raw_value, "алиас")
    character = await _require_character(database, character_name)
    deleted = await delete_character_alias(
        database,
        character_id=character.id,
        alias=alias,
    )
    return AliasDeleteResult(character=character, alias=alias, deleted=deleted)


async def rebuild_alias_index(database: Database) -> AliasIndexResult:
    created = await ensure_name_aliases(database)
    matched, total = await rebuild_hashtag_character_links(database)
    return AliasIndexResult(
        created_name_aliases=created,
        matched_links=matched,
        total_hashtags=total,
    )


async def _profile(database: Database, character: Character) -> CharacterProfile:
    return CharacterProfile(
        character=character,
        media_count=await database.count_character_media(character.id),
        reference_count=await count_character_references(database, character.id),
    )


async def _require_character(database: Database, name: str) -> Character:
    character = await database.get_character(name)
    if character is None:
        raise ValueError("Такой персонаж не найден.")
    return character


def _split_tail(raw_value: str, tail_label: str) -> tuple[str, str]:
    cleaned = " ".join(raw_value.split())
    parts = cleaned.rsplit(maxsplit=1)
    if len(parts) != 2:
        raise ValueError(f"Укажите имя персонажа и {tail_label}.")
    return parts[0], parts[1]


__all__ = (
    "AliasDeleteResult",
    "AliasIndexResult",
    "CharacterProfile",
    "CharacterValueResult",
    "CreateCharacterResult",
    "StoryAssignmentResult",
    "StoryListResult",
    "TopicValidator",
    "add_alias_from_text",
    "add_story_from_text",
    "bind_character_topic",
    "create_character_profile",
    "delete_alias_from_text",
    "list_aliases_from_text",
    "list_stories_from_text",
    "load_character_profile",
    "rebuild_alias_index",
    "set_category_from_text",
    "set_prompt_from_text",
    "set_story_from_text",
    "set_universe_from_text",
)
