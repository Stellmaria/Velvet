from __future__ import annotations

from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

TELEGRAM_TEXT_CHUNK_LIMIT = 3900


def _hard_split(value: str, limit: int) -> list[str]:
    return [value[index : index + limit] for index in range(0, len(value), limit)]


def chunk_telegram_text(
    text: str,
    *,
    limit: int = TELEGRAM_TEXT_CHUNK_LIMIT,
) -> tuple[str, ...]:
    """Split text predictably, preferring paragraph and line boundaries."""

    if limit < 1:
        raise ValueError("limit must be positive")
    if not text:
        return ("",)
    if len(text) <= limit:
        return (text,)

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(paragraph) <= limit:
            current = paragraph
            continue
        for line in paragraph.splitlines(keepends=True):
            candidate = f"{current}{line}"
            if len(candidate) <= limit:
                current = candidate
                continue
            if current:
                chunks.append(current.rstrip("\n"))
                current = ""
            if len(line) <= limit:
                current = line
            else:
                chunks.extend(_hard_split(line.rstrip("\n"), limit))
        current = current.rstrip("\n")
    if current:
        chunks.append(current)
    return tuple(chunks)


async def answer_text_chunks(
    message: Message,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    fallback_to_plain_text: bool = True,
    limit: int = TELEGRAM_TEXT_CHUNK_LIMIT,
    **answer_kwargs: Any,
) -> tuple[Message, ...]:
    """Send long text in chunks and retry malformed HTML as plain text."""

    sent: list[Message] = []
    for chunk in chunk_telegram_text(text, limit=limit):
        try:
            result = await message.answer(
                chunk,
                parse_mode=parse_mode,
                **answer_kwargs,
            )
        except TelegramBadRequest:
            if parse_mode is None or not fallback_to_plain_text:
                raise
            result = await message.answer(
                chunk,
                parse_mode=None,
                **answer_kwargs,
            )
        sent.append(result)
    return tuple(sent)


__all__ = (
    "TELEGRAM_TEXT_CHUNK_LIMIT",
    "answer_text_chunks",
    "chunk_telegram_text",
)
