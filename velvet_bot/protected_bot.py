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
    """Protect media sent to ordinary private users."""
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
    """Bot that protects public media while allowing explicit manager downloads."""

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

    def allow_unprotected_private_user(self, user_id: int) -> None:
        """Permit one verified archive manager to receive downloadable originals."""
        self._unprotected_private_user_ids = (
            self._unprotected_private_user_ids | {int(user_id)}
        )

    async def __call__(self, method: Any, request_timeout: int | None = None) -> Any:
        protect_private_media_method(
            method,
            unprotected_private_user_ids=self._unprotected_private_user_ids,
        )
        return await super().__call__(method, request_timeout=request_timeout)
