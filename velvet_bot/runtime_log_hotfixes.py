from __future__ import annotations

from velvet_bot.analytics_review import set_manual_publication_type
from velvet_bot.media_quality import (
    _claim_pending_images as claim_pending_images,
    decide_duplicate_candidate,
    scan_media_target,
)


def install_runtime_log_hotfixes() -> None:
    """Compatibility no-op: fixes now live in canonical modules."""


__all__ = (
    "claim_pending_images",
    "decide_duplicate_candidate",
    "install_runtime_log_hotfixes",
    "scan_media_target",
    "set_manual_publication_type",
)
