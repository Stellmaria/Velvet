from aiogram import Router

from velvet_bot.handlers.characters import router as characters_router
from velvet_bot.handlers.start import router as start_router

router = Router(name=__name__)
router.include_router(start_router)
router.include_router(characters_router)

__all__ = ("router",)
