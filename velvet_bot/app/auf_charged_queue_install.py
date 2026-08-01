from __future__ import annotations

import importlib
import logging

from velvet_bot.domains.auf_wallet import build_auf_charged_task_queue_service

logger = logging.getLogger(__name__)
_INSTALLED = False


def install_auf_charged_queue() -> None:
    """Make the production bootstrap use the atomic Auf wallet queue."""

    global _INSTALLED
    if _INSTALLED:
        return
    bootstrap = importlib.import_module("velvet_bot.app.bootstrap")
    charged_queue = importlib.import_module("velvet_bot.domains.auf_wallet.charged_queue")
    pricing = importlib.import_module("velvet_bot.domains.auf_wallet.pricing")
    privacy = importlib.import_module(
        "velvet_bot.app.auf_generation_price_privacy_install"
    )

    # Owner pricing installs before the charged queue. Apply the final privacy
    # surface here so later generation screens cannot restore internal fields.
    privacy.install_auf_generation_price_privacy()

    # Photo model modes may wrap the quote function, for example to multiply
    # Wan Image by the requested result count. Rebind the already-imported queue
    # module so the displayed and reserved prices use the same runtime function.
    charged_queue.quote_auf_payload = pricing.quote_auf_payload
    bootstrap.build_ai_task_queue_service = build_auf_charged_task_queue_service
    logger.info("Installed charged Auf task queue in production bootstrap")
    _INSTALLED = True


__all__ = ("install_auf_charged_queue",)
