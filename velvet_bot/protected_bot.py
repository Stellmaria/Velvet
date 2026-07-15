from __future__ import annotations

from collections.abc import Collection
from typing import Any

from aiogram import Bot
from aiogram.methods import (
    SendAnimation,
    SendDocument,
    SendMediaGroup,
    SendPhoto,
    SendVideo,
)

_PROTECTED_MEDIA_METHODS = (
    SendAnimation,
    SendDocument,
    SendMediaGroup,
    SendPhoto,
    SendVideo,
)


def protect_private_media_method(
    method: Any,
    *,
    unprotected_private_user_ids: Collection[int],
) -> bool:
    """Protect media sent to ordinary private users.

    Telegram private user chat identifiers are positive integers. Group, supergroup,
    and channel identifiers are negative, so internal archive topics remain untouched.
    The explicitly allowed download recipient is exempt and can still receive a real
    downloadable document.
    """
    if not isinstance(method, _PROTECTED_MEDIA_METHODS):
        return False

    chat_id = getattr(method, "chat_id", None)
    if not isinstance(chat_id, int) or chat_id <= 0:
        return False
    if chat_id in unprotected_private_user_ids:
        return False

    method.protect_content = True
    return True


class ProtectedMediaBot(Bot):
    """Bot that automatically protects public media from forwarding and saving."""

    def __init__(
        self,
        *args: Any,
        unprotected_private_user_ids: Collection[int] = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._unprotected_private_user_ids = frozenset(
            int(user_id) for user_id in unprotected_private_user_ids
        )

    async def __call__(self, method: Any, request_timeout: int | None = None) -> Any:
        protect_private_media_method(
            method,
            unprotected_private_user_ids=self._unprotected_private_user_ids,
        )
        return await super().__call__(method, request_timeout=request_timeout)
