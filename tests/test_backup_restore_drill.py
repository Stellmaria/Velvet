from __future__ import annotations

import unittest

from velvet_bot.backup_restore_drill import (
    database_name_from_dsn,
    replace_database_name,
    validate_database_name,
)


class BackupRestoreDrillTests(unittest.TestCase):
    def test_database_name_is_read_from_url(self) -> None:
        self.assertEqual(
            database_name_from_dsn(
                "postgresql://velvet:secret@localhost:5432/velvet_test"
            ),
            "velvet_test",
        )

    def test_database_name_is_replaced_without_losing_query(self) -> None:
        self.assertEqual(
            replace_database_name(
                "postgresql://velvet:secret@localhost:5432/velvet?sslmode=disable",
                "velvet_restore_1",
            ),
            "postgresql://velvet:secret@localhost:5432/velvet_restore_1?sslmode=disable",
        )

    def test_unsafe_database_name_is_rejected(self) -> None:
        for value in ("", "1restore", "restore-db", "restore db", 'restore"db'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_database_name(value)

    def test_safe_database_name_is_preserved(self) -> None:
        self.assertEqual(
            validate_database_name("velvet_restore_2026"),
            "velvet_restore_2026",
        )


if __name__ == "__main__":
    unittest.main()
