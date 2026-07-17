from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "velvet_bot/handlers/owner_actions.py"
text = path.read_text(encoding="utf-8")
marker = "router = Router(name=__name__)\n"
if text.count(marker) != 1:
    raise RuntimeError("Owner router marker changed")
_, rest = text.split(marker, 1)
imports = '''from __future__ import annotations\n\nimport re\nfrom html import escape\n\nfrom aiogram import Bot, Router\nfrom aiogram.exceptions import TelegramBadRequest\nfrom aiogram.filters import BaseFilter\nfrom aiogram.types import (\n    CallbackQuery,\n    ForceReply,\n    InlineKeyboardButton,\n    InlineKeyboardMarkup,\n    Message,\n)\n\nfrom velvet_bot.application.owner_profiles import rebuild_alias_index\nfrom velvet_bot.application.owner_references import finish_reference_upload\nfrom velvet_bot.audit import TelegramAuditLogger\nfrom velvet_bot.database import Database\nfrom velvet_bot.owner_callbacks import (\n    OwnerActionCallback,\n    owner_action_callback,\n    owner_callback,\n)\nfrom velvet_bot.presentation.telegram.owner_actions import (\n    handle_owner_data_action,\n    handle_owner_media_action,\n    handle_owner_profile_action,\n    handle_owner_reference_action,\n)\nfrom velvet_bot.reference_uploads import ReferenceUploadSessions\n\n'''
path.write_text(imports + marker + rest, encoding="utf-8")

(ROOT / "scripts/_phase16_imports.py").unlink()
(ROOT / ".github/workflows/phase16-imports.yml").unlink()
