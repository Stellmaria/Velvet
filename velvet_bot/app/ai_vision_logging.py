from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable


_AI_VISION_LOGGER_NAME = "velvet_bot.ai_vision"
_TERMINAL_SKIP_MARKERS = (
    "ai semantic analysis failed media_id=",
    "file is too big",
    "повтор автоматически не требуется",
)


class _TerminalAISkipInfoFilter(logging.Filter):
    """Downgrade a successfully handled permanent AI skip from WARNING to INFO."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != _AI_VISION_LOGGER_NAME or record.levelno < logging.WARNING:
            return True
        try:
            message = record.getMessage().casefold()
        except Exception:
            return True
        if all(marker in message for marker in _TERMINAL_SKIP_MARKERS):
            record.levelno = logging.INFO
            record.levelname = logging.getLevelName(logging.INFO)
        return True


async def run_ai_vision_once_with_terminal_skip_info(
    runner: Callable[[], Awaitable[int]],
) -> int:
    """Run one AI iteration without reporting permanent oversized skips as incidents."""

    logger = logging.getLogger(_AI_VISION_LOGGER_NAME)
    filter_ = _TerminalAISkipInfoFilter()
    logger.addFilter(filter_)
    try:
        return await runner()
    finally:
        logger.removeFilter(filter_)


__all__ = ("run_ai_vision_once_with_terminal_skip_info",)
