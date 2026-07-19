import unittest

from aiogram.types import User

from velvet_bot.access import (
    AccessPolicy,
    is_owner_only_command_text,
    is_public_command_text,
    is_save_mention_text,
    normalize_username,
)
from velvet_bot.config import (
    _parse_allowed_user_ids,
    _parse_allowed_usernames,
)


class AccessPolicyTests(unittest.TestCase):
    def test_username_is_normalized(self) -> None:
        self.assertEqual("owner_example", normalize_username(" @OWNER_EXAMPLE "))

    def test_owner_is_allowed_by_username(self) -> None:
        policy = AccessPolicy(
            allowed_user_ids=frozenset(),
            allowed_usernames=frozenset({"owner_example"}),
        )
        owner = User(
            id=100,
            is_bot=False,
            first_name="Owner",
            username="OWNER_EXAMPLE",
        )
        self.assertTrue(policy.allows_user(owner))

    def test_stranger_is_rejected(self) -> None:
        policy = AccessPolicy(
            allowed_user_ids=frozenset({100}),
            allowed_usernames=frozenset({"owner_example"}),
        )
        stranger = User(
            id=200,
            is_bot=False,
            first_name="Other",
            username="someone_else",
        )
        self.assertFalse(policy.allows_user(stranger))

    def test_numeric_id_has_priority_over_missing_username(self) -> None:
        policy = AccessPolicy(
            allowed_user_ids=frozenset({100}),
            allowed_usernames=frozenset(),
        )
        owner = User(id=100, is_bot=False, first_name="Owner")
        self.assertTrue(policy.allows_user(owner))

    def test_allowlist_parsers_accept_comma_separated_values(self) -> None:
        self.assertEqual(
            frozenset({100, 200}),
            _parse_allowed_user_ids("100, 200"),
        )
        self.assertEqual(
            frozenset({"owner_example", "second_owner"}),
            _parse_allowed_usernames("@OWNER_EXAMPLE, second_owner"),
        )

    def test_public_commands_are_archive_entry_points_only(self) -> None:
        self.assertTrue(is_public_command_text("/start"))
        self.assertTrue(is_public_command_text("/archive"))
        self.assertTrue(is_public_command_text("/archive@dominusVelvetbot"))
        self.assertTrue(is_public_command_text("/gallery"))
        self.assertFalse(is_public_command_text("/menu"))

    def test_owner_commands_are_not_public(self) -> None:
        self.assertFalse(is_public_command_text("/characters"))
        self.assertFalse(is_public_command_text("/save Аид"))
        self.assertFalse(is_public_command_text("/supervisor"))
        self.assertFalse(is_public_command_text("/update"))
        self.assertFalse(is_public_command_text("archive"))

    def test_owner_only_command_catalog_contains_system_controls(self) -> None:
        for command in (
            "/menu",
            "/system",
            "/backup",
            "/publish",
            "/supervisor",
            "/logs",
            "/restart",
            "/update",
            "/rollback",
            "/codex",
        ):
            with self.subTest(command=command):
                self.assertTrue(is_owner_only_command_text(command))

    def test_save_mention_is_protected_in_all_supported_positions(self) -> None:
        username = "dominusVelvetbot"
        self.assertTrue(is_save_mention_text("@dominusVelvetbot save Аид", username))
        self.assertTrue(is_save_mention_text("save @dominusVelvetbot Аид", username))
        self.assertTrue(is_save_mention_text("save Аид @dominusVelvetbot", username))

    def test_reference_add_mention_is_owner_only(self) -> None:
        username = "dominusVelvetbot"
        self.assertTrue(is_save_mention_text("@dominusVelvetbot refadd Аид", username))
        self.assertTrue(is_save_mention_text("refadd Аид @dominusVelvetbot", username))

    def test_other_bot_mention_is_not_treated_as_ours(self) -> None:
        self.assertFalse(
            is_save_mention_text(
                "save Аид @another_bot",
                "dominusVelvetbot",
            )
        )


if __name__ == "__main__":
    unittest.main()
