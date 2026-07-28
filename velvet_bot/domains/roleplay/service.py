from __future__ import annotations

import unicodedata
from dataclasses import replace
from typing import Any

from velvet_bot.domains.roleplay.models import JsonObject, RoleplayCharacterDraft


MAX_ROLEPLAY_CHARACTER_NAME_LENGTH = 120
MAX_PROFILE_TEXT_LENGTH = 12_000
MAX_PROFILE_LIST_ITEMS = 80
ROLEPLAY_MEMORY_KINDS = frozenset({"canonical", "episodic", "relationship", "scene"})
ROLEPLAY_MESSAGE_ROLES = frozenset({"user", "assistant", "system"})


def normalize_roleplay_name(value: str) -> tuple[str, str]:
    display = " ".join(unicodedata.normalize("NFKC", value).split()).strip()
    if not display:
        raise ValueError("Имя RP-персонажа не может быть пустым.")
    if len(display) > MAX_ROLEPLAY_CHARACTER_NAME_LENGTH:
        raise ValueError(
            "Имя RP-персонажа не должно быть длиннее "
            f"{MAX_ROLEPLAY_CHARACTER_NAME_LENGTH} символов."
        )
    return display, display.casefold()


def clean_optional_text(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned[:limit] or None


def _clean_json_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        raise ValueError("Профиль персонажа имеет слишком глубокую структуру.")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value.strip()[:MAX_PROFILE_TEXT_LENGTH]
    if isinstance(value, (list, tuple)):
        return [
            _clean_json_value(item, depth=depth + 1)
            for item in list(value)[:MAX_PROFILE_LIST_ITEMS]
        ]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, raw_item in list(value.items())[:MAX_PROFILE_LIST_ITEMS]:
            key = " ".join(str(raw_key).split()).strip()[:120]
            if key:
                result[key] = _clean_json_value(raw_item, depth=depth + 1)
        return result
    return str(value).strip()[:MAX_PROFILE_TEXT_LENGTH]


def clean_json_object(value: JsonObject | None) -> JsonObject:
    cleaned = _clean_json_value(value or {})
    if not isinstance(cleaned, dict):
        raise ValueError("Раздел профиля должен быть JSON-объектом.")
    return cleaned


def clean_text_items(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values[:MAX_PROFILE_LIST_ITEMS]:
        cleaned = " ".join(str(value).split()).strip()[:1000]
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def validate_character_draft(draft: RoleplayCharacterDraft) -> RoleplayCharacterDraft:
    display_name, _ = normalize_roleplay_name(draft.name)
    age_text = clean_optional_text(draft.age_text, limit=80)
    if not draft.adult_confirmed:
        raise ValueError(
            "Для RP-персонажа требуется явное подтверждение совершеннолетия."
        )
    return replace(
        draft,
        name=display_name,
        age_text=age_text,
        pronouns=clean_optional_text(draft.pronouns, limit=80),
        appearance=clean_json_object(draft.appearance),
        personality=clean_json_object(draft.personality),
        speech=clean_json_object(draft.speech),
        biography=clean_json_object(draft.biography),
        behavior_rules=clean_json_object(draft.behavior_rules),
        canonical_facts=clean_text_items(draft.canonical_facts),
        example_dialogue=clean_text_items(draft.example_dialogue),
        system_notes=clean_optional_text(draft.system_notes, limit=12_000),
    )


def validate_message(role: str, content: str) -> tuple[str, str]:
    cleaned_role = role.strip().casefold()
    if cleaned_role not in ROLEPLAY_MESSAGE_ROLES:
        raise ValueError("Неизвестная роль RP-сообщения.")
    cleaned_content = content.strip()
    if not cleaned_content:
        raise ValueError("RP-сообщение не может быть пустым.")
    if len(cleaned_content) > 40_000:
        raise ValueError("RP-сообщение превышает допустимый размер.")
    return cleaned_role, cleaned_content


def validate_memory(kind: str, content: str, importance: int) -> tuple[str, str, int]:
    cleaned_kind = kind.strip().casefold()
    if cleaned_kind not in ROLEPLAY_MEMORY_KINDS:
        raise ValueError("Неизвестный вид RP-памяти.")
    cleaned_content = content.strip()
    if not cleaned_content:
        raise ValueError("Запись RP-памяти не может быть пустой.")
    return cleaned_kind, cleaned_content[:12_000], max(0, min(int(importance), 100))


__all__ = (
    "MAX_ROLEPLAY_CHARACTER_NAME_LENGTH",
    "ROLEPLAY_MEMORY_KINDS",
    "ROLEPLAY_MESSAGE_ROLES",
    "clean_json_object",
    "clean_optional_text",
    "clean_text_items",
    "normalize_roleplay_name",
    "validate_character_draft",
    "validate_memory",
    "validate_message",
)
