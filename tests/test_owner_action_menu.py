from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from velvet_bot.presentation.telegram.routers.core_operations_controllers.owner_actions import (
    OwnerActionCallback,
    OwnerActionReplyFilter,
    _FORM_COPY,
    _MEDIA_FORMS,
    _main_keyboard,
    _section_keyboard,
)
from velvet_bot.owner_menu import build_owner_main_keyboard
from velvet_bot.presentation.telegram.router import get_root_router


class OwnerActionMenuTests(unittest.TestCase):
    def test_composition_root_builds_with_owner_action_router(self) -> None:
        self.assertIs(get_root_router(), get_root_router())

    def test_every_owner_action_callback_fits_telegram_limit(self) -> None:
        keyboards = [
            build_owner_main_keyboard(),
            _main_keyboard(),
            *(
                _section_keyboard(section)
                for section in ("characters", "media", "references", "aliases", "data")
            ),
        ]
        for keyboard in keyboards:
            for row in keyboard.inline_keyboard:
                for button in row:
                    if button.callback_data is not None:
                        self.assertLessEqual(
                            len(button.callback_data.encode("utf-8")),
                            64,
                            msg=button.callback_data,
                        )

    def test_main_owner_menu_contains_all_actions_entry(self) -> None:
        values = {
            button.callback_data
            for row in build_owner_main_keyboard().inline_keyboard
            for button in row
            if button.callback_data is not None
        }
        self.assertIn(OwnerActionCallback(action="menu").pack(), values)

    def test_historical_admin_commands_are_covered_by_buttons_or_forms(self) -> None:
        historical_commands = {
            "system",
            "version",
            "analytics",
            "backup",
            "quality",
            "publish",
            "checkpost",
            "create",
            "topic",
            "characters",
            "category",
            "universe",
            "story",
            "stories",
            "storyadd",
            "prompt",
            "character",
            "save",
            "save18",
            "refadd",
            "refdone",
            "refcancel",
            "refs",
            "refdel",
            "aliasadd",
            "aliases",
            "aliasdel",
            "aliasreindex",
            "channelstats",
            "promptstats",
            "tagstats",
            "characterstats",
            "importchannel",
            "importdiscussion",
            "trackdiscussion",
            "discussionstats",
            "supervisor",
            "logs",
            "restart",
            "update",
            "rollback",
            "codex",
            "codex_status",
        }
        panel_commands = {
            "system",
            "version",
            "analytics",
            "backup",
            "quality",
            "publish",
            "characters",
            "channelstats",
            "promptstats",
            "characterstats",
            "supervisor",
            "logs",
            "restart",
            "update",
            "rollback",
            "codex",
            "codex_status",
        }
        form_commands = set(_FORM_COPY)
        context_mapping = {
            "save_media": "save",
            "save_spoiler": "save18",
            "check_post": "checkpost",
            "import_channel": "importchannel",
            "import_discussion": "importdiscussion",
        }
        context_commands = {
            context_mapping[action] for action in _MEDIA_FORMS
        }
        direct_commands = {"refdone", "refcancel", "aliasreindex"}
        covered = panel_commands | form_commands | context_commands | direct_commands
        self.assertEqual(historical_commands, covered)

    def test_form_marker_filter_isolated_from_other_reply_workflows(self) -> None:
        filter_ = OwnerActionReplyFilter()
        valid = SimpleNamespace(
            reply_to_message=SimpleNamespace(
                text="Введите значение\nOWNER_ACTION:create",
                caption=None,
            )
        )
        media = SimpleNamespace(
            reply_to_message=SimpleNamespace(
                text=None,
                caption="OWNER_ACTION:save_media",
            )
        )
        unrelated = SimpleNamespace(
            reply_to_message=SimpleNamespace(
                text="SUPERVISOR_INPUT:codex",
                caption=None,
            )
        )
        self.assertEqual(
            asyncio.run(filter_(valid)),
            {"owner_action": "create"},
        )
        self.assertEqual(
            asyncio.run(filter_(media)),
            {"owner_action": "save_media"},
        )
        self.assertFalse(asyncio.run(filter_(unrelated)))


if __name__ == "__main__":
    unittest.main()
