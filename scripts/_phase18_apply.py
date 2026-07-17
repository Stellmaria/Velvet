from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(source: str, old: str, new: str, *, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: ожидалось одно совпадение, найдено {count}")
    return source.replace(old, new, 1)


def main() -> None:
    database_path = ROOT / "velvet_bot" / "database.py"
    database_source = database_path.read_text(encoding="utf-8")
    acquire_method = '''    def acquire(self):
        """Return a public PostgreSQL connection acquisition context."""
        return self._require_pool().acquire()

'''
    if "    def acquire(self):\n" not in database_source:
        database_source = replace_once(
            database_source,
            "    def _require_pool(self) -> asyncpg.Pool:\n",
            acquire_method + "    def _require_pool(self) -> asyncpg.Pool:\n",
            label="database acquire boundary",
        )
    database_path.write_text(database_source, encoding="utf-8")

    repository_paths = (
        ROOT / "velvet_bot" / "domains" / "characters" / "repository.py",
        ROOT / "velvet_bot" / "domains" / "stories" / "repository.py",
    )
    old_acquire = "self._database._require_pool().acquire()"
    new_acquire = "self._database.acquire()"
    for path in repository_paths:
        source = path.read_text(encoding="utf-8")
        count = source.count(old_acquire)
        if count == 0 and new_acquire not in source:
            raise RuntimeError(f"{path}: не найдены обращения к PostgreSQL boundary")
        source = source.replace(old_acquire, new_acquire)
        path.write_text(source, encoding="utf-8")

    test_path = ROOT / "tests" / "test_phase18_database_boundary.py"
    test_path.write_text(
        '''from __future__ import annotations

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
''',
        encoding="utf-8",
    )

    changelog_path = ROOT / "CHANGELOG.md"
    changelog = changelog_path.read_text(encoding="utf-8")
    changelog = replace_once(
        changelog,
        "Пока нет изменений после выпуска `1.3.0`.",
        "### Changed\n\n- добавлена публичная граница `Database.acquire()` для PostgreSQL repositories;\n- character и story repositories больше не обращаются к приватному `_require_pool()`.",
        label="changelog unreleased",
    )
    changelog_path.write_text(changelog, encoding="utf-8")

    status_path = ROOT / "docs" / "development_status.md"
    status = status_path.read_text(encoding="utf-8")
    phase_section = '''## Фаза 18: публичная граница PostgreSQL

Статус: первый P2-срез завершён.

Реализованы:

- публичный `Database.acquire()` для infrastructure и domain repositories;
- character repository переведён с приватного `_require_pool()`;
- story repository переведён с приватного `_require_pool()`;
- regression-тест запрещает возврат приватного pool access в эти домены.

'''
    if "## Фаза 18: публичная граница PostgreSQL" not in status:
        status = replace_once(
            status,
            "## Оставшийся долг\n",
            phase_section + "## Оставшийся долг\n",
            label="development status phase 18",
        )
    status = status.replace(
        "1. Заменять прямой `Database._require_pool()` repositories по одному домену.",
        "1. Продолжить перевод оставшихся repositories на публичный `Database.acquire()`; character и story домены завершены.",
        1,
    )
    status_path.write_text(status, encoding="utf-8")

    for temporary in (
        ROOT / ".github" / "workflows" / "phase18-apply.yml",
        ROOT / "scripts" / "_phase18_apply.py",
    ):
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
