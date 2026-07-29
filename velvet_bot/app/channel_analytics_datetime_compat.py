from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timezone
from typing import Any

import velvet_bot.channel_analytics as channel_analytics
from velvet_bot.channel_analytics import ParsedChannelPost

_ORIGINAL_PARSE_CHANNEL_POST = channel_analytics.parse_channel_post
_INSTALLED = False


def _normalize_telegram_datetime(
    value: object,
    *,
    field_name: str,
    required: bool,
) -> datetime | None:
    if value is None:
        if required:
            raise ValueError(f"Telegram update не содержит обязательное поле {field_name}.")
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, bool):
        raise TypeError(f"Telegram поле {field_name} не может быть boolean.")
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as error:
            raise ValueError(
                f"Telegram поле {field_name} содержит некорректный Unix timestamp: {value!r}."
            ) from error
    raise TypeError(
        f"Telegram поле {field_name} должно быть datetime или Unix timestamp, "
        f"получено {type(value).__name__}."
    )


def _parse_channel_post_with_normalized_dates(message: Any) -> ParsedChannelPost:
    parsed = _ORIGINAL_PARSE_CHANNEL_POST(message)
    posted_at = _normalize_telegram_datetime(
        parsed.posted_at,
        field_name="date",
        required=True,
    )
    edited_at = _normalize_telegram_datetime(
        parsed.edited_at,
        field_name="edit_date",
        required=False,
    )
    if posted_at is None:
        raise ValueError("Telegram update не содержит дату публикации.")
    if posted_at is parsed.posted_at and edited_at is parsed.edited_at:
        return parsed
    return replace(parsed, posted_at=posted_at, edited_at=edited_at)


def install_channel_analytics_datetime_compat() -> None:
    """Normalize Telegram epoch values before asyncpg receives them."""

    global _INSTALLED
    if _INSTALLED:
        return
    channel_analytics.parse_channel_post = _parse_channel_post_with_normalized_dates
    _INSTALLED = True


__all__ = ("install_channel_analytics_datetime_compat",)
