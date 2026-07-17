from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import velvet_bot.quality_ui as quality_ui
from velvet_bot.ai_quality import AIQualitySummary
from velvet_bot.quality_audit import QualitySummary

_INSTALLED = False


def install_set_consistency_dashboard() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original = quality_ui.build_quality_dashboard

    def wrapped(
        summary: QualitySummary,
        ai_quality: AIQualitySummary | None = None,
    ) -> tuple[str, InlineKeyboardMarkup]:
        text, markup = original(summary, ai_quality)
        rows = [list(row) for row in markup.inline_keyboard]
        rows.insert(
            min(2, len(rows)),
            [
                InlineKeyboardButton(
                    text="🧠 Целостность медиасетов",
                    callback_data=quality_ui.quality_callback("setreports"),
                )
            ],
        )
        return text, InlineKeyboardMarkup(inline_keyboard=rows)

    quality_ui.build_quality_dashboard = wrapped
    _INSTALLED = True


install_set_consistency_dashboard()


__all__ = ("install_set_consistency_dashboard",)
