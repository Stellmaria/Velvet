from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from velvet_bot.core.access import AccessPolicy, normalize_username
from velvet_bot.core.config import (
    parse_allowed_user_ids,
    parse_allowed_usernames,
    parse_timezone,
)


class CoreAccessTests(unittest.TestCase):
    def test_policy_accepts_generic_identity_without_telegram_type(self) -> None:
        policy = AccessPolicy(
            allowed_user_ids=frozenset({100}),
            allowed_usernames=frozenset({"owner_example"}),
        )
        self.assertTrue(policy.allows(user_id=100, username=None))
        self.assertTrue(
            policy.allows_user(
                SimpleNamespace(id=200, username="OWNER_EXAMPLE")
            )
        )
        self.assertFalse(
            policy.allows_user(SimpleNamespace(id=300, username="other"))
        )
        self.assertEqual("owner_example", normalize_username(" @OWNER_EXAMPLE "))


class CoreConfigTests(unittest.TestCase):
    def test_parsers_are_framework_independent(self) -> None:
        self.assertEqual(
            frozenset({100, 200}),
            parse_allowed_user_ids("100, 200"),
        )
        self.assertEqual(
            frozenset({"owner_example", "second_owner"}),
            parse_allowed_usernames("@OWNER_EXAMPLE, second_owner"),
        )
        self.assertEqual("Europe/Berlin", parse_timezone("Europe/Berlin"))

    def test_core_config_does_not_import_telegram_layer(self) -> None:
        source = Path("velvet_bot/core/config/settings.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("aiogram", source)
        self.assertNotIn("velvet_bot.access", source)
        self.assertIn("velvet_bot.core.access", source)

    def test_legacy_modules_are_small_facades(self) -> None:
        access_source = Path("velvet_bot/access.py").read_text(encoding="utf-8")
        config_source = Path("velvet_bot/config.py").read_text(encoding="utf-8")
        self.assertLessEqual(len(access_source.splitlines()), 8)
        self.assertLessEqual(len(config_source.splitlines()), 16)
        self.assertNotIn("class OwnerAccessMiddleware", access_source)
        self.assertNotIn("def load_settings", config_source)


if __name__ == "__main__":
    unittest.main()
