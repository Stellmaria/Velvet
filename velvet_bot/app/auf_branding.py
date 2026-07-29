from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiogram import Bot

_INSTALLED = False
_ORIGINAL_BOT_CALL = Bot.__call__


def _brand_auf_text(value: str) -> str:
    """Replace the former owner-facing Meow brand without touching internal ids."""

    return (
        value.replace("🐈 <b>Мяу</b>", "🐕 <b>Ауф</b>")
        .replace("🐈 Мяу", "🐕 Ауф")
        .replace("МЯУ", "АУФ")
        .replace("Мяу", "Ауф")
    )


def _copy_model(value: Any, updates: Mapping[str, object]) -> Any:
    model_copy = getattr(value, "model_copy", None)
    if callable(model_copy):
        return model_copy(update=dict(updates))
    legacy_copy = getattr(value, "copy", None)
    if callable(legacy_copy):
        return legacy_copy(update=dict(updates))
    return value


def _brand_telegram_value(value: Any, *, depth: int = 0) -> Any:
    """Brand strings recursively inside aiogram Telegram method payloads."""

    if depth > 10:
        return value
    if isinstance(value, str):
        return _brand_auf_text(value)
    if isinstance(value, list):
        return [_brand_telegram_value(item, depth=depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(_brand_telegram_value(item, depth=depth + 1) for item in value)
    if isinstance(value, Mapping):
        return {
            key: _brand_telegram_value(item, depth=depth + 1)
            for key, item in value.items()
        }

    fields = getattr(type(value), "model_fields", None)
    if not isinstance(fields, Mapping):
        fields = getattr(value, "__fields__", None)
    if not isinstance(fields, Mapping):
        return value

    updates: dict[str, object] = {}
    for field_name in fields:
        try:
            current = getattr(value, field_name)
        except (AttributeError, TypeError):
            continue
        branded = _brand_telegram_value(current, depth=depth + 1)
        if branded != current:
            updates[str(field_name)] = branded
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
    """Apply Auf branding to all owner-facing Telegram output."""

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
