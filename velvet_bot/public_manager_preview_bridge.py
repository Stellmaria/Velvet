from __future__ import annotations

import sys

from velvet_bot.public_preview_overrides import replace_viewer_archive_page


def connect_public_manager_preview() -> None:
    manager_module = sys.modules.get("velvet_bot.handlers.public_manager")
    if manager_module is not None:
        manager_module.replace_viewer_archive_page = replace_viewer_archive_page
