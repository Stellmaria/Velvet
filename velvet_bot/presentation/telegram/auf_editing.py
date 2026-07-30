from __future__ import annotations

from collections.abc import Callable

from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from velvet_bot.presentation.telegram.shared import edit_or_answer_callback_text

AufTextTransformer = Callable[[str], str]


def _identity_text(value: str) -> str:
    return value


_text_transformer: AufTextTransformer = _identity_text


def install_auf_text_transformer(
    transformer: AufTextTransformer,
) -> AufTextTransformer:
    """Install the public Auf card text transformer and return the previous hook."""

    global _text_transformer
    previous = _text_transformer
    _text_transformer = transformer
    return previous


async def edit_or_answer_auf_callback(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    """Render an Auf callback card through the canonical Telegram fallback contract."""

    await edit_or_answer_callback_text(
        callback,
        text=_text_transformer(text),
        reply_markup=reply_markup,
    )


__all__ = (
    "AufTextTransformer",
    "edit_or_answer_auf_callback",
    "install_auf_text_transformer",
)
