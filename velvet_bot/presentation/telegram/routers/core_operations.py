from __future__ import annotations

from aiogram import Router

from velvet_bot.handlers.error_center import router as error_center_router
from velvet_bot.handlers.owner_actions import router as owner_actions_router
from velvet_bot.handlers.owner_menu import router as owner_menu_router
from velvet_bot.handlers.supervisor_control import router as supervisor_control_router
from velvet_bot.handlers.system_center import router as system_center_router

router = Router(name=__name__)
router.include_router(error_center_router)
router.include_router(owner_actions_router)
router.include_router(owner_menu_router)
router.include_router(supervisor_control_router)
router.include_router(system_center_router)

__all__ = ("router",)
