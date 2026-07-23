from __future__ import annotations

from typing import Any

from velvet_bot import channel_analytics as channel_module


_original_parse_channel_post = channel_module.parse_channel_post


def _optional_metric(value: Any) -> int | None:
    """Normalize optional Telegram metrics without inventing missing values."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class _ChannelMessageProxy:
    """Expose optional channel counters expected by the legacy analytics parser.

    aiogram's Bot API ``Message`` model does not guarantee ``views`` or
    ``forward_count``. Older tests and imported Telegram payloads may still provide
    them, so the proxy preserves valid values and supplies ``None`` when Telegram
    omits the fields.
    """

    __slots__ = ("_message", "views", "forward_count")

    def __init__(self, message: Any) -> None:
        self._message = message
        self.views = _optional_metric(getattr(message, "views", None))
        self.forward_count = _optional_metric(getattr(message, "forward_count", None))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._message, name)


def parse_channel_post(message: Any):
    return _original_parse_channel_post(_ChannelMessageProxy(message))


def install() -> None:
    """Install Bot API compatibility before analytics controllers ingest posts."""
    if channel_module.parse_channel_post is parse_channel_post:
        return
    channel_module.parse_channel_post = parse_channel_post


__all__ = ("install", "parse_channel_post")
