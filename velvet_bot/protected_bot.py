from __future__ import annotations

from collections.abc import AsyncIterator, Collection
from contextlib import asynccontextmanager
from contextvars import ContextVar
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
    """Protect media sent to private users unless this send is explicitly scoped."""
    if not isinstance(method, _PROTECTED_MEDIA_METHODS):
        return False

    chat_id = getattr(method, "chat_id", None)
    if not isinstance(chat_id, int) or chat_id <= 0:
        return False
    if chat_id in unprotected_private_user_ids:
        return False

    changed = method.protect_content is not True
    method.protect_content = True
    return changed


class ProtectedMediaBot(Bot):
    """Protect private media and allow only one explicit manager download."""

    def __init__(
        self,
        *args: Any,
        unprotected_private_user_ids: Collection[int] = (),
        **kwargs: Any,
    ) -> None:
        if unprotected_private_user_ids:
            raise ValueError(
                "Permanent unprotected recipients are disabled. "
                "Use allow_unprotected_private_user() immediately before one download."
            )
        super().__init__(*args, **kwargs)
        self._scoped_unprotected_private_user_ids: ContextVar[frozenset[int]] = (
            ContextVar(
                f"velvet_unprotected_private_media_{id(self)}",
                default=frozenset(),
            )
        )

    @asynccontextmanager
    async def unprotected_private_media(self, user_id: int) -> AsyncIterator[None]:
        """Allow one unprotected media send in this task, then restore protection."""
        current = self._scoped_unprotected_private_user_ids.get()
        token = self._scoped_unprotected_private_user_ids.set(
            current | {int(user_id)}
        )
        try:
            yield
        finally:
            self._scoped_unprotected_private_user_ids.reset(token)

    def allow_unprotected_private_user(self, user_id: int) -> None:
        """Allow only the next private media send to this verified manager."""
        current = self._scoped_unprotected_private_user_ids.get()
        self._scoped_unprotected_private_user_ids.set(current | {int(user_id)})

    async def __call__(self, method: Any, request_timeout: int | None = None) -> Any:
        unprotected_ids = self._scoped_unprotected_private_user_ids.get()
        chat_id = getattr(method, "chat_id", None)
        if (
            isinstance(method, _PROTECTED_MEDIA_METHODS)
            and isinstance(chat_id, int)
            and chat_id > 0
            and chat_id in unprotected_ids
        ):
            self._scoped_unprotected_private_user_ids.set(
                unprotected_ids - {chat_id}
            )

        protect_private_media_method(
            method,
            unprotected_private_user_ids=unprotected_ids,
        )
        return await super().__call__(method, request_timeout=request_timeout)
