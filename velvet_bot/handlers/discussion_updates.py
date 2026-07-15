from aiogram import Router
from aiogram.types import Message

router = Router(name=__name__)


@router.edited_message()
async def handle_edited_discussion_passthrough(message: Message) -> None:
    """The analytics middleware stores the edit before this no-op handler runs."""
    return None
