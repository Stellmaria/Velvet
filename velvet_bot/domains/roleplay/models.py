from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RoleplaySession:
    chat_id: int
    user_id: int
    enabled: bool
    title: str | None
    system_prompt: str
    summary: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RoleplayMessage:
    id: int
    chat_id: int
    user_id: int
    role: str
    content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RoleplayReply:
    text: str
    provider: str
    model: str


__all__ = (
    "RoleplayMessage",
    "RoleplayReply",
    "RoleplaySession",
)
