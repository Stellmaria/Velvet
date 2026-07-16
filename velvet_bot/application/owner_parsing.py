from __future__ import annotations

from velvet_bot.database import Character, Database


async def require_character(database: Database, name: str) -> Character:
    character = await database.get_character(name)
    if character is None:
        raise ValueError("Такой персонаж не найден.")
    return character


def split_tail(raw_value: str, tail_label: str) -> tuple[str, str]:
    cleaned = " ".join(raw_value.split())
    parts = cleaned.rsplit(maxsplit=1)
    if len(parts) != 2:
        raise ValueError(f"Укажите имя персонажа и {tail_label}.")
    return parts[0], parts[1]


__all__ = ("require_character", "split_tail")
