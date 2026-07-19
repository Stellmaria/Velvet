from __future__ import annotations

from aiogram import F, Router

from velvet_bot.presentation.telegram.routers.archive.save import (
    PendingSaveUploadFilter,
    handle_pending_save_upload,
)

router = Router(name=__name__)

# This narrow router is included before reference-upload routers. It reuses the
# canonical save handler so an active `/save` session wins over broad media
# handlers that belong to other workflows.
router.message.register(
    handle_pending_save_upload,
    F.photo | F.video | F.animation | F.document,
    PendingSaveUploadFilter(),
)

__all__ = ("router",)
