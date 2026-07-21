from __future__ import annotations

from dataclasses import dataclass, replace

from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


@dataclass(frozen=True, slots=True)
class ReferenceUploadSession:
    character_id: int
    character_name: str
    workspace_id: int = DEFAULT_WORKSPACE_ID
    added_count: int = 0


class ReferenceUploadSessions:
    """Keep short-lived workspace-pinned reference upload sessions in memory."""

    def __init__(self) -> None:
        self._sessions: dict[int, ReferenceUploadSession] = {}

    def start(
        self,
        user_id: int,
        *,
        character_id: int,
        character_name: str,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> ReferenceUploadSession:
        session = ReferenceUploadSession(
            character_id=int(character_id),
            character_name=character_name,
            workspace_id=int(workspace_id),
        )
        self._sessions[int(user_id)] = session
        return session

    def get(self, user_id: int) -> ReferenceUploadSession | None:
        return self._sessions.get(int(user_id))

    def increment(self, user_id: int) -> ReferenceUploadSession | None:
        session = self._sessions.get(int(user_id))
        if session is None:
            return None
        updated = replace(session, added_count=session.added_count + 1)
        self._sessions[int(user_id)] = updated
        return updated

    def stop(self, user_id: int) -> ReferenceUploadSession | None:
        return self._sessions.pop(int(user_id), None)


__all__ = ("ReferenceUploadSession", "ReferenceUploadSessions")
