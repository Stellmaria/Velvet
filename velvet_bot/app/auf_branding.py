from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiogram import Bot

_INSTALLED = False
_ORIGINAL_BOT_CALL = Bot.__call__

# These fields contain protocol identifiers rather than user-facing copy. Branding
# them would invalidate callback routing, Telegram file references, URLs, or chat ids.
_IDENTIFIER_FIELDS = frozenset(
    {
        "callback_data",
        "url",
        "file_id",
        "chat_id",
        "message_id",
        "inline_message_id",
        "business_connection_id",
        "parse_mode",
        "switch_inline_query",
        "switch_inline_query_current_chat",
        "switch_inline_query_chosen_chat",
        "copy_text",
    }
)


def _brand_auf_text(value: str) -> str:
    """Replace every user-facing spelling of the retired Meow brand."""

    return (
        value.replace("🐈 <b>Мяу</b>", "🐕 <b>Ауф</b>")
        .replace("🐈 Мяу", "🐕 Ауф")
        .replace("МЯУ", "АУФ")
        .replace("Мяу", "Ауф")
        .replace("мяу", "ауф")
        .replace("MEOW", "AUF")
        .replace("Meow", "Auf")
        .replace("meow", "auf")
    )


def _copy_model(value: Any, updates: Mapping[str, object]) -> Any:
    model_copy = getattr(value, "model_copy", None)
    if callable(model_copy):
        return model_copy(update=dict(updates))
    legacy_copy = getattr(value, "copy", None)
    if callable(legacy_copy):
        return legacy_copy(update=dict(updates))
    return value


def _brand_telegram_value(
    value: Any,
    *,
    depth: int = 0,
    field_name: str | None = None,
) -> Any:
    """Brand visible strings recursively without mutating Telegram identifiers."""

    if depth > 10:
        return value
    if isinstance(value, str):
        if field_name in _IDENTIFIER_FIELDS:
            return value
        return _brand_auf_text(value)
    if isinstance(value, list):
        return [
            _brand_telegram_value(
                item,
                depth=depth + 1,
                field_name=field_name,
            )
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _brand_telegram_value(
                item,
                depth=depth + 1,
                field_name=field_name,
            )
            for item in value
        )
    if isinstance(value, Mapping):
        return {
            key: _brand_telegram_value(
                item,
                depth=depth + 1,
                field_name=str(key),
            )
            for key, item in value.items()
        }

    fields = getattr(type(value), "model_fields", None)
    if not isinstance(fields, Mapping):
        fields = getattr(value, "__fields__", None)
    if not isinstance(fields, Mapping):
        return value

    updates: dict[str, object] = {}
    for model_field_name in fields:
        try:
            current = getattr(value, model_field_name)
        except (AttributeError, TypeError):
            continue
        branded = _brand_telegram_value(
            current,
            depth=depth + 1,
            field_name=str(model_field_name),
        )
        if branded != current:
            updates[str(model_field_name)] = branded
    return _copy_model(value, updates) if updates else value


async def _call_with_auf_branding(
    bot: Bot,
    method: Any,
    request_timeout: int | None = None,
) -> Any:
    branded_method = _brand_telegram_value(method)
    return await _ORIGINAL_BOT_CALL(
        bot,
        branded_method,
        request_timeout=request_timeout,
    )


def install_auf_branding() -> None:
    """Apply Auf branding as a final guard for Telegram output."""

    global _INSTALLED
    if _INSTALLED:
        return
    Bot.__call__ = _call_with_auf_branding  # type: ignore[method-assign]
    _INSTALLED = True


__all__ = (
    "_brand_auf_text",
    "_brand_telegram_value",
    "install_auf_branding",
)
