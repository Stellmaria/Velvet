from __future__ import annotations

import importlib

from velvet_bot.app.auf_owner_cost_privacy.progress import (
    install_owner_aware_progress_policy,
    install_public_receipt_policy,
)
from velvet_bot.app.auf_owner_cost_privacy.queue import (
    install_owner_queue_confirmations,
)
from velvet_bot.app.auf_owner_cost_privacy.reviews import (
    install_owner_review_screens,
)
from velvet_bot.domains.media_generation.friendly_worker import (
    FriendlyKieGenerationWorker,
)

_INSTALLED = False


def install_auf_owner_cost_privacy() -> None:
    """Separate public generation UI from creator-only provider economics."""

    global _INSTALLED
    if _INSTALLED:
        return

    photo_ui = importlib.import_module("velvet_bot.app.auf_photo_ui_install")
    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")
    receipt = importlib.import_module("velvet_bot.app.auf_generation_receipt_install")

    install_owner_review_screens(photo_ui, portal)
    install_owner_queue_confirmations(photo_ui, portal)
    install_public_receipt_policy(receipt)
    install_owner_aware_progress_policy(FriendlyKieGenerationWorker)
    _INSTALLED = True


__all__ = ("install_auf_owner_cost_privacy",)
