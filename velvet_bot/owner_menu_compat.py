from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_OWNER_CALLBACK = "own:menu"
_INSTALLED = False


def _with_owner_home(keyboard: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    rows = [list(row) for row in keyboard.inline_keyboard]
    if any(
        button.callback_data == _OWNER_CALLBACK
        for row in rows
        for button in row
    ):
        return keyboard
    rows.append(
        [
            InlineKeyboardButton(
                text="🏠 Главная",
                callback_data=_OWNER_CALLBACK,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _patch_keyboard_factory(module: Any, name: str) -> None:
    original: Callable[..., InlineKeyboardMarkup] = getattr(module, name)
    if getattr(original, "__owner_menu_wrapped__", False):
        return

    def wrapped(*args: Any, **kwargs: Any) -> InlineKeyboardMarkup:
        return _with_owner_home(original(*args, **kwargs))

    wrapped.__name__ = getattr(original, "__name__", name)
    wrapped.__doc__ = getattr(original, "__doc__", None)
    wrapped.__owner_menu_wrapped__ = True  # type: ignore[attr-defined]
    setattr(module, name, wrapped)


def install_owner_menu_navigation() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from velvet_bot.presentation.telegram.routers.analytics_controllers import (
        dashboard as analytics_dashboard,
    )
    from velvet_bot.presentation.telegram.routers.characters import (
        directory as admin_directory,
    )
    from velvet_bot.presentation.telegram.routers.publication import (
        center as publication_center,
    )
    from velvet_bot.presentation.telegram.routers.quality_operations_controllers import (
        backup_center,
    )
    from velvet_bot.presentation.telegram.routers import system as system_center
    import velvet_bot.quality_ui as quality_ui

    _patch_keyboard_factory(admin_directory, "_category_keyboard")
    _patch_keyboard_factory(analytics_dashboard, "_main_keyboard")
    _patch_keyboard_factory(backup_center, "_main_keyboard")
    _patch_keyboard_factory(publication_center, "_center_keyboard")
    _patch_keyboard_factory(system_center, "_main_keyboard")

    original_dashboard = quality_ui.build_quality_dashboard
    if not getattr(original_dashboard, "__owner_menu_wrapped__", False):
        def wrapped_dashboard(*args: Any, **kwargs: Any):
            text, keyboard = original_dashboard(*args, **kwargs)
            return text, _with_owner_home(keyboard)

        wrapped_dashboard.__name__ = original_dashboard.__name__
        wrapped_dashboard.__doc__ = original_dashboard.__doc__
        wrapped_dashboard.__owner_menu_wrapped__ = True  # type: ignore[attr-defined]
        quality_ui.build_quality_dashboard = wrapped_dashboard

        # quality_center imports the function directly, so update its bound name too.
        from velvet_bot.presentation.telegram.routers.quality_operations_controllers import (
            quality_center,
        )

        quality_center.build_quality_dashboard = wrapped_dashboard

    _INSTALLED = True


__all__ = ("install_owner_menu_navigation",)
