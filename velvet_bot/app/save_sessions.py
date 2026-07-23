from __future__ import annotations

from dataclasses import dataclass, replace
from time import monotonic
from typing import Callable, Literal

from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


DEFAULT_SAVE_SESSION_TTL_SECONDS = 10 * 60
SaveUploadMode = Literal["single", "set"]


@dataclass(frozen=True, slots=True)
class SaveUploadSession:
    chat_id: int
    user_id: int
    character_name: str
    command_message_id: int
    expires_at: float
    workspace_id: int = DEFAULT_WORKSPACE_ID
    character_id: int | None = None
    saved_count: int = 0
    mode: SaveUploadMode = "set"


class SaveUploadSessions:
    """Keep short-lived single-file and batch media save sessions in memory."""

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_SAVE_SESSION_TTL_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("Save session TTL must be positive.")
        self._ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._sessions: dict[tuple[int, int], SaveUploadSession] = {}

    @staticmethod
    def _key(chat_id: int, user_id: int) -> tuple[int, int]:
        return int(chat_id), int(user_id)

    def start(
        self,
        *,
        chat_id: int,
        user_id: int,
        character_name: str,
        command_message_id: int,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
        character_id: int | None = None,
        mode: SaveUploadMode = "set",
    ) -> SaveUploadSession:
        cleaned_name = character_name.strip()
        if not cleaned_name:
            raise ValueError("Character name cannot be empty.")
        if mode not in {"single", "set"}:
            raise ValueError("Unknown save upload mode.")
        session = SaveUploadSession(
            chat_id=int(chat_id),
            user_id=int(user_id),
            character_name=cleaned_name,
            command_message_id=int(command_message_id),
            expires_at=self._clock() + self._ttl_seconds,
            workspace_id=int(workspace_id),
            character_id=(int(character_id) if character_id is not None else None),
            mode=mode,
        )
        self._sessions[self._key(chat_id, user_id)] = session
        return session

    def record_saved(self, *, chat_id: int, user_id: int) -> SaveUploadSession | None:
        """Record one processed upload and extend the active session TTL."""
        current = self.get(chat_id=chat_id, user_id=user_id)
        if current is None:
            return None
        updated = replace(
            current,
            saved_count=current.saved_count + 1,
            expires_at=self._clock() + self._ttl_seconds,
        )
        self._sessions[self._key(chat_id, user_id)] = updated
        return updated

    def get(self, *, chat_id: int, user_id: int) -> SaveUploadSession | None:
        key = self._key(chat_id, user_id)
        session = self._sessions.get(key)
        if session is None:
            return None
        if session.expires_at <= self._clock():
            self._sessions.pop(key, None)
            return None
        return session

    def stop(self, *, chat_id: int, user_id: int) -> SaveUploadSession | None:
        return self._sessions.pop(self._key(chat_id, user_id), None)


__all__ = (
    "DEFAULT_SAVE_SESSION_TTL_SECONDS",
    "SaveUploadMode",
    "SaveUploadSession",
    "SaveUploadSessions",
)
