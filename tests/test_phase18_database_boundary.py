from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock

from velvet_bot.database import Database


ROOT = Path(__file__).resolve().parents[1]


class DatabaseAcquireBoundaryTests(unittest.TestCase):
    def test_acquire_delegates_to_initialized_pool(self) -> None:
        database = Database("postgresql://unused")
        pool = Mock()
        context = object()
        pool.acquire.return_value = context
        database._pool = pool

        self.assertIs(database.acquire(), context)
        pool.acquire.assert_called_once_with()

    def test_acquire_rejects_uninitialized_database(self) -> None:
        database = Database("postgresql://unused")

        with self.assertRaisesRegex(RuntimeError, "ещё не инициализировано"):
            database.acquire()

    def test_character_and_story_repositories_use_public_boundary(self) -> None:
        paths = (
            ROOT / "velvet_bot/domains/characters/repository.py",
            ROOT / "velvet_bot/domains/stories/repository.py",
        )
        for path in paths:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("._require_pool()", source)
            self.assertIn("self._database.acquire()", source)


if __name__ == "__main__":
    unittest.main()
