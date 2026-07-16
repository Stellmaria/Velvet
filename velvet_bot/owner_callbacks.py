from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class OwnerMenuCallback(CallbackData, prefix="own"):
    action: str


class OwnerActionCallback(CallbackData, prefix="oact"):
    action: str


def owner_callback(action: str) -> str:
    return OwnerMenuCallback(action=action).pack()


def owner_action_callback(action: str) -> str:
    return OwnerActionCallback(action=action).pack()


__all__ = (
    "OwnerActionCallback",
    "OwnerMenuCallback",
    "owner_action_callback",
    "owner_callback",
)
