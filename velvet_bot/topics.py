from __future__ import annotations

import re
from dataclasses import dataclass

_PRIVATE_TOPIC_LINK_PATTERN = re.compile(
    r"^https?://t\.me/c/(?P<chat>\d+)/(?P<thread>\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TopicReference:
    chat_id: int
    thread_id: int
    url: str


def parse_private_topic_link(value: str) -> TopicReference:
    """Parse a private Telegram forum-topic link into Bot API identifiers."""
    cleaned = value.strip()
    match = _PRIVATE_TOPIC_LINK_PATTERN.fullmatch(cleaned)
    if match is None:
        raise ValueError(
            "Нужна ссылка на тему приватной группы вида "
            "https://t.me/c/3951213065/1398"
        )

    internal_chat_id = int(match.group("chat"))
    thread_id = int(match.group("thread"))
    if internal_chat_id <= 0 or thread_id <= 0:
        raise ValueError("Некорректная ссылка на тему Telegram.")

    return TopicReference(
        chat_id=int(f"-100{internal_chat_id}"),
        thread_id=thread_id,
        url=f"https://t.me/c/{internal_chat_id}/{thread_id}",
    )


def split_character_and_topic(value: str) -> tuple[str, TopicReference | None]:
    """Split `/create Name [topic-url]` arguments without breaking multiword names."""
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Имя персонажа не может быть пустым.")

    parts = cleaned.rsplit(" ", 1)
    if len(parts) == 1 or not parts[1].lower().startswith(("https://t.me/", "http://t.me/")):
        return cleaned, None

    name, topic_url = parts
    if not name:
        raise ValueError("Укажите имя персонажа перед ссылкой на тему.")
    return name, parse_private_topic_link(topic_url)
