from __future__ import annotations

from functools import partial
from html import escape

from aiogram import Bot
from aiogram.types import Message

from velvet_bot.application.owner_profiles import (
    add_story_from_text,
    bind_character_topic,
    create_character_profile,
    list_stories_from_text,
    load_character_profile,
    set_category_from_text,
    set_prompt_from_text,
    set_story_from_text,
    set_universe_from_text,
)
from velvet_bot.archive_ui import build_character_archive_keyboard
from velvet_bot.character_directory import category_label, universe_label
from velvet_bot.database import Database
from velvet_bot.services.telegram_topics import validate_topic_access
from velvet_bot.story_catalog import format_story_release, universe_requires_story


PROFILE_ACTIONS = frozenset(
    {
        "create",
        "topic",
        "character",
        "category",
        "universe",
        "prompt",
        "story",
        "storyadd",
        "stories",
    }
)


def _topic_line(character) -> str:
    if not character.archive_topic_url:
        return "Тема архива: <b>не назначена</b>"
    return f'<a href="{escape(character.archive_topic_url, quote=True)}">Тема архива</a>'


async def _answer_profile(
    message: Message,
    profile,
    *,
    heading: str = "Профиль персонажа",
) -> None:
    character = profile.character
    created_at = character.created_at.astimezone().strftime("%d.%m.%Y %H:%M:%S %Z")
    await message.answer(
        f"<b>{heading}</b>\n\n"
        f"Имя: <b>{escape(character.name)}</b>\n"
        f"ID: <code>{character.id}</code>\n"
        f"Фото и видео в архиве: <b>{profile.media_count}</b>\n"
        f"Референсов: <b>{profile.reference_count}</b>\n"
        f"{_topic_line(character)}\n"
        f"Создан: <code>{escape(created_at)}</code>",
        reply_markup=build_character_archive_keyboard(character, profile.media_count),
    )


def _story_chunks(universe: str, stories) -> list[str]:
    header = (
        f"<b>Истории {escape(universe_label(universe))}</b>\n"
        "Сортировка: <b>от новых к старым</b>.\n\n"
    )
    chunks: list[str] = []
    current = header
    for story in stories:
        released = format_story_release(story.released_on, story.release_precision)
        prefix = "" if released == "дата не указана" else f"{released} · "
        line = f"• {prefix}<code>{escape(story.short_label)}</code> — {escape(story.title)}\n"
        if len(current) + len(line) > 3800:
            chunks.append(current.rstrip())
            current = header + line
        else:
            current += line
    chunks.append(current.rstrip())
    return chunks


async def handle_owner_profile_action(
    *,
    message: Message,
    owner_action: str,
    value: str,
    database: Database,
    bot: Bot,
    actor_id: int | None,
) -> bool:
    if owner_action not in PROFILE_ACTIONS:
        return False

    if owner_action == "create":
        result = await create_character_profile(
            database,
            value,
            actor_id=actor_id,
            chat_id=message.chat.id,
            validate_topic=partial(validate_topic_access, bot),
        )
        heading = (
            "Профиль персонажа создан"
            if result.created
            else (
                "Профиль уже существовал, тема архива обновлена"
                if result.topic_supplied
                else "Профиль уже существует"
            )
        )
        await _answer_profile(message, result.profile, heading=heading)
        return True

    if owner_action == "topic":
        profile = await bind_character_topic(
            database,
            value,
            validate_topic=partial(validate_topic_access, bot),
        )
        await _answer_profile(message, profile, heading="Тема архива назначена")
        return True

    if owner_action == "character":
        profile = await load_character_profile(database, value)
        if profile is None:
            raise ValueError("Такой персонаж не найден.")
        await _answer_profile(message, profile)
        return True

    if owner_action == "category":
        result = await set_category_from_text(database, value)
        await message.answer(
            f"Пол / состав персонажа <b>{escape(result.character.name)}</b>: "
            f"<b>{escape(category_label(result.value))}</b>."
        )
        return True

    if owner_action == "universe":
        result = await set_universe_from_text(database, value)
        suffix = (
            "\nТеперь назначьте историю через раздел профилей."
            if universe_requires_story(result.value)
            else ""
        )
        await message.answer(
            f"Вселенная персонажа <b>{escape(result.character.name)}</b>: "
            f"<b>{escape(universe_label(result.value))}</b>.{suffix}"
        )
        return True

    if owner_action == "prompt":
        result = await set_prompt_from_text(database, value)
        await message.answer(
            (
                f"Промт привязан к карточке <b>{escape(result.character.name)}</b>."
                if result.value
                else f"Ссылка на промт удалена у <b>{escape(result.character.name)}</b>."
            )
        )
        return True

    if owner_action == "story":
        result = await set_story_from_text(database, value)
        if result.removed:
            await message.answer(
                f"История у <b>{escape(result.character.name)}</b> удалена."
            )
        else:
            assert result.story is not None
            await message.answer(
                f"История персонажа <b>{escape(result.character.name)}</b>: "
                f"<b>{escape(result.story.short_label)} · "
                f"{escape(result.story.title)}</b>."
            )
        return True

    if owner_action == "storyadd":
        story = await add_story_from_text(database, value)
        await message.answer(
            f"История добавлена в <b>{escape(universe_label(story.universe))}</b>: "
            f"<b>{escape(story.short_label)} · {escape(story.title)}</b>."
        )
        return True

    result = await list_stories_from_text(database, value)
    if not result.stories:
        raise ValueError("Для этой вселенной истории ещё не добавлены.")
    for chunk in _story_chunks(result.universe, result.stories):
        await message.answer(chunk)
    return True


__all__ = ("PROFILE_ACTIONS", "handle_owner_profile_action")
