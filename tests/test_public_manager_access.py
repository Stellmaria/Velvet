import unittest

from aiogram.types import User

from velvet_bot.access import AccessPolicy
from velvet_bot.public_manager_access import has_public_manager_access
from velvet_bot.public_ui import PUBLIC_DOWNLOAD_USER_ID


class PublicManagerAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = AccessPolicy(
            allowed_user_ids=frozenset({101}),
            allowed_usernames=frozenset({"va_stellmaria"}),
        )

    @staticmethod
    def user(user_id: int, username: str | None = None) -> User:
        return User(
            id=user_id,
            is_bot=False,
            first_name="Test",
            username=username,
        )

    def test_dedicated_editor_has_access(self) -> None:
        self.assertTrue(
            has_public_manager_access(
                self.user(PUBLIC_DOWNLOAD_USER_ID),
                self.policy,
            )
        )

    def test_owner_id_has_access(self) -> None:
        self.assertTrue(has_public_manager_access(self.user(101), self.policy))

    def test_owner_username_has_access(self) -> None:
        self.assertTrue(
            has_public_manager_access(
                self.user(202, "VA_Stellmaria"),
                self.policy,
            )
        )

    def test_stranger_has_no_access(self) -> None:
        self.assertFalse(
            has_public_manager_access(
                self.user(303, "somebody_else"),
                self.policy,
            )
        )


if __name__ == "__main__":
    unittest.main()
