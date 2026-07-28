from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Sequence

from velvet_bot.domains.roleplay.models import (
    RoleplayCharacter,
    RoleplayContext,
    RoleplayMemory,
    RoleplayMessage,
)


@dataclass(frozen=True, slots=True)
class RoleplayContextBudget:
    num_ctx: int = 8192
    max_output_tokens: int = 900
    recent_message_limit: int = 16
    summary_trigger_tokens: int = 5600

    def __post_init__(self) -> None:
        if not 2048 <= self.num_ctx <= 32_768:
            raise ValueError("RP num_ctx должен быть от 2048 до 32768.")
        if not 128 <= self.max_output_tokens <= 4096:
            raise ValueError("RP max_output_tokens должен быть от 128 до 4096.")
        if self.max_output_tokens >= self.num_ctx:
            raise ValueError("RP max_output_tokens должен быть меньше num_ctx.")
        if not 4 <= self.recent_message_limit <= 80:
            raise ValueError("RP recent_message_limit должен быть от 4 до 80.")
        if not 1024 <= self.summary_trigger_tokens < self.num_ctx:
            raise ValueError(
                "RP summary_trigger_tokens должен быть от 1024 и меньше num_ctx."
            )

    @property
    def input_limit(self) -> int:
        return max(1024, self.num_ctx - self.max_output_tokens - 256)


def estimate_tokens(value: str) -> int:
    """Return a conservative tokenizer-free estimate for mixed Russian text."""
    cleaned = value.strip()
    return 0 if not cleaned else max(1, (len(cleaned) + 2) // 3)


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _character_block(index: int, character: RoleplayCharacter) -> str:
    return "\n".join(
        [
            f"P{index}: {character.name}",
            f"Возраст: {character.age_text or 'совершеннолетний персонаж'}",
            f"Местоимения: {character.pronouns or 'не указаны'}",
            f"Внешность: {_json_text(character.appearance)}",
            f"Характер: {_json_text(character.personality)}",
            f"Речь: {_json_text(character.speech)}",
            f"Биография: {_json_text(character.biography)}",
            f"Правила поведения: {_json_text(character.behavior_rules)}",
            "Канонические факты: "
            + (
                _json_text(character.canonical_facts)
                if character.canonical_facts
                else "[]"
            ),
            "Примеры реплик: "
            + (
                _json_text(character.example_dialogue)
                if character.example_dialogue
                else "[]"
            ),
            f"Служебные заметки: {character.system_notes or 'нет'}",
        ]
    )


def _memory_block(memories: Iterable[RoleplayMemory]) -> str:
    lines: list[str] = []
    for memory in memories:
        if not memory.active:
            continue
        marker = "закреплено" if memory.pinned else f"важность {memory.importance}"
        character = f", персонаж #{memory.character_id}" if memory.character_id else ""
        lines.append(f"- [{memory.kind}, {marker}{character}] {memory.content}")
    return "\n".join(lines) or "Нет сохранённых фактов."


def _system_prompt(
    *,
    characters: Sequence[RoleplayCharacter],
    scenario: str,
    world_lore: str,
    summary: str,
    scene_state: dict[str, object],
    memories: Sequence[RoleplayMemory],
) -> str:
    character_text = "\n\n".join(
        _character_block(index, character)
        for index, character in enumerate(characters, start=1)
    )
    return f"""
Ты локальный литературный движок ролевого отыгрыша.

Все персонажи и участники сцены подтверждены как совершеннолетние.
Строго сохраняй заданные внешность, характер, манеру речи, знания и отношения.
Не переходи в режим помощника и не обсуждай внутренний процесс генерации.
Не управляй действиями, мыслями или репликами пользователя.
Не меняй канонические факты без явного сообщения пользователя.
Продолжай сцену инициативно, но логично и в пределах уже заданного мира.
Различай голоса персонажей и не смешивай их знания.
Учитывай физическое положение, одежду, предметы и незавершённые действия.
Не заканчивай каждый ответ вопросом и не повторяй предыдущий текст.

ПЕРСОНАЖИ
{character_text or "Персонажи не назначены."}

СЦЕНАРИЙ
{scenario.strip() or "Не задан."}

МИР И ЛОР
{world_lore.strip() or "Не заданы."}

СВОДКА ПРЕДЫДУЩИХ СОБЫТИЙ
{summary.strip() or "Сцена только началась."}

ТЕКУЩЕЕ СОСТОЯНИЕ СЦЕНЫ
{_json_text(scene_state)}

ДОЛГОВРЕМЕННАЯ ПАМЯТЬ
{_memory_block(memories)}
""".strip()


def build_roleplay_context(
    *,
    characters: Sequence[RoleplayCharacter],
    scenario: str,
    world_lore: str,
    summary: str,
    scene_state: dict[str, object],
    memories: Sequence[RoleplayMemory],
    recent_messages: Sequence[RoleplayMessage],
    user_message: str,
    budget: RoleplayContextBudget,
) -> RoleplayContext:
    if not characters:
        raise ValueError("Для RP-контекста нужен хотя бы один персонаж.")
    if any(not character.adult_confirmed for character in characters):
        raise ValueError(
            "Все RP-персонажи должны быть подтверждены как совершеннолетние."
        )

    system = _system_prompt(
        characters=characters,
        scenario=scenario,
        world_lore=world_lore,
        summary=summary,
        scene_state=scene_state,
        memories=memories,
    )
    cleaned_user_message = user_message.strip()
    if not cleaned_user_message:
        raise ValueError("Сообщение пользователя не может быть пустым.")

    history = list(recent_messages[-budget.recent_message_limit :])
    trimmed = max(0, len(recent_messages) - len(history))
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]

    fixed_tokens = (
        estimate_tokens(system) + 8 + estimate_tokens(cleaned_user_message) + 8
    )
    if fixed_tokens > budget.input_limit:
        raise ValueError(
            "Постоянные RP-данные превышают бюджет контекста. "
            "Сократите карточки, лор, сводку или память."
        )
    available = budget.input_limit - fixed_tokens

    selected: list[RoleplayMessage] = []
    used = 0
    for message in reversed(history):
        cost = estimate_tokens(message.content) + 8
        if selected and used + cost > available:
            trimmed += 1
            continue
        if not selected and cost > available:
            trimmed += 1
            continue
        selected.append(message)
        used += cost
    selected.reverse()

    for message in selected:
        messages.append({"role": message.role, "content": message.content})
    messages.append({"role": "user", "content": cleaned_user_message})

    estimated = sum(estimate_tokens(message["content"]) + 8 for message in messages)
    return RoleplayContext(
        messages=tuple(messages),
        estimated_input_tokens=estimated,
        trimmed_message_count=trimmed,
    )


__all__ = (
    "RoleplayContextBudget",
    "build_roleplay_context",
    "estimate_tokens",
)
