from __future__ import annotations

import re

from aiogram.filters import BaseFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.types import Message

_INPUT_MARKER_RE = re.compile(r"SUPERVISOR_INPUT:(codex|task|console)")


class SupervisorCallback(CallbackData, prefix="sup"):
    action: str
    task_id: str = ""


class SupervisorReplyMarkerFilter(BaseFilter):
    async def __call__(self, message: Message) -> dict[str, str] | bool:
        reply = message.reply_to_message
        if reply is None:
            return False
        source = reply.text or reply.caption or ""
        match = _INPUT_MARKER_RE.search(source)
        if match is None:
            return False
        return {"supervisor_input_kind": match.group(1)}


def supervisor_callback(action: str, *, task_id: str = "") -> str:
    return SupervisorCallback(action=action, task_id=task_id).pack()


__all__ = (
    "SupervisorCallback",
    "SupervisorReplyMarkerFilter",
    "supervisor_callback",
)
