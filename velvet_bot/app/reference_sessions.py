from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class ReferenceUploadSession:
    character_id: int
    character_name: str
    added_count: int = 0


class ReferenceUploadSessions:
    """Keep short-lived owner upload sessions in application memory."""

    def __init__(self) -> None:
        self._sessions: dict[int, ReferenceUploadSession] = {}

    def start(
        self,
        user_id: int,
        *,
        character_id: int,
        character_name: str,
    ) -> ReferenceUploadSession:
        session = ReferenceUploadSession(
            character_id=character_id,
            character_name=character_name,
        )
        self._sessions[user_id] = session
        return session

    def get(self, user_id: int) -> ReferenceUploadSession | None:
        return self._sessions.get(user_id)

    def increment(self, user_id: int) -> ReferenceUploadSession | None:
        session = self._sessions.get(user_id)
        if session is None:
            return None
        updated = replace(session, added_count=session.added_count + 1)
        self._sessions[user_id] = updated
        return updated

    def stop(self, user_id: int) -> ReferenceUploadSession | None:
        return self._sessions.pop(user_id, None)


__all__ = ("ReferenceUploadSession", "ReferenceUploadSessions")
