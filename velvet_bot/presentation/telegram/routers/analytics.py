from __future__ import annotations

from aiogram import Router

from velvet_bot.presentation.telegram.routers.analytics_controllers.channel import (
    router as channel_analytics_router,
)
from velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard_overrides import (
    router as analytics_dashboard_overrides_router,
)
from velvet_bot.presentation.telegram.routers.analytics_controllers.discussion_overrides import (
    router as analytics_discussion_overrides_router,
)
from velvet_bot.presentation.telegram.routers.analytics_controllers.management import (
    router as analytics_management_router,
)
from velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard import (
    router as analytics_dashboard_router,
)

router = Router(name=__name__)
router.include_router(channel_analytics_router)
router.include_router(analytics_dashboard_overrides_router)
router.include_router(analytics_discussion_overrides_router)
router.include_router(analytics_management_router)
router.include_router(analytics_dashboard_router)

__all__ = ("router",)
