from __future__ import annotations

from html import escape

import velvet_bot.archive_ui as archive_ui
import velvet_bot.media_set_actions  # noqa: F401
import velvet_bot.public_ui as public_ui
import velvet_bot.quality_set_audit_compat  # noqa: F401

_INSTALLED = False
_ORIGINAL_ARCHIVE_CAPTION = archive_ui.format_archive_caption
_ORIGINAL_PUBLIC_CAPTION = public_ui.format_public_archive_caption


def _set_line(page) -> str | None:
    media = getattr(page, "media", None)
    title = getattr(media, "media_set_title", None) if media is not None else None
    if not title:
        return None
    return f"Сет: <b>{escape(str(title))}</b>"


def format_archive_caption_with_set(page) -> str:
    text = _ORIGINAL_ARCHIVE_CAPTION(page)
    line = _set_line(page)
    if line is None or line in text:
        return text
    return f"{text}\n{line}"


def format_public_archive_caption_with_set(page, state) -> str:
    text = _ORIGINAL_PUBLIC_CAPTION(page, state)
    line = _set_line(page)
    if line is None or line in text:
        return text
    return f"{text}\n{line}"


def install_media_set_ui() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    archive_ui.format_archive_caption = format_archive_caption_with_set
    public_ui.format_public_archive_caption = format_public_archive_caption_with_set

    # These modules copy the function into their namespace with ``from ... import``.
    # Update already-imported compatibility layers as well.
    try:
        import velvet_bot.public_preview_overrides as public_preview_overrides

        public_preview_overrides.format_public_archive_caption = (
            format_public_archive_caption_with_set
        )
    except ImportError:
        pass

    _INSTALLED = True


__all__ = (
    "format_archive_caption_with_set",
    "format_public_archive_caption_with_set",
    "install_media_set_ui",
)
