from aiogram import Router

from velvet_bot.handlers.archive import router as archive_router
from velvet_bot.handlers.characters import router as characters_router
from velvet_bot.handlers.guest_archive import router as guest_archive_router
from velvet_bot.handlers.media_browser import router as media_browser_router
from velvet_bot.handlers.start import router as start_router

router = Router(name=__name__)
router.include_router(start_router)
router.include_router(characters_router)
router.include_router(media_browser_router)
router.include_router(guest_archive_router)
router.include_router(archive_router)

__all__ = ("router",)
