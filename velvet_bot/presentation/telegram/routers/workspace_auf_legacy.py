"""Read-only compatibility definitions for pre-Auf Telegram payloads and FSM states."""

from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup


class LegacyMeowCallback(CallbackData, prefix="meow"):
    action: str
    workspace_id: int = 0
    value: str = ""
    item_id: int = 0
    offset: int = 0


class LegacyMeowVideoCallback(CallbackData, prefix="meowv"):
    action: str
    workspace_id: int = 0
    value: str = ""
    item_id: int = 0
    offset: int = 0


class MeowForm(StatesGroup):
    """Exact state names used by photo flows before the Auf migration."""

    collecting_references = State()
    waiting_prompt = State()
    reviewing_request = State()
    choosing_model = State()
    choosing_quality = State()


class MeowVideoForm(StatesGroup):
    """Exact state names used by video flows before the Auf migration."""

    choosing_reference = State()
    waiting_reference = State()
    waiting_prompt = State()
    choosing_settings = State()
    reviewing = State()


class MeowRuntimeForm(StatesGroup):
    """Exact state name used by runtime-limit input before the Auf migration."""

    waiting_limit = State()


__all__ = (
    "LegacyMeowCallback",
    "LegacyMeowVideoCallback",
    "MeowForm",
    "MeowRuntimeForm",
    "MeowVideoForm",
)
