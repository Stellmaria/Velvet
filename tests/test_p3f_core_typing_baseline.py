from __future__ import annotations

import ast
import configparser
import unittest
from pathlib import Path


_EXPECTED_SCOPE = {
    "velvet_bot/core/access",
    "velvet_bot/core/config",
    "velvet_bot/topics.py",
    "velvet_bot/post_classification.py",
    "velvet_bot/domains/references/models.py",
}


class P3FTypingBaselineTests(unittest.TestCase):
    def test_mypy_scope_is_strict_and_bounded(self) -> None:
        parser = configparser.ConfigParser()
        parser.read("mypy.ini", encoding="utf-8")

        settings = parser["mypy"]
        scope = {
            item.strip()
            for item in (settings.get("files") or "").replace("\n", "").split(",")
            if item.strip()
        }

        self.assertEqual("3.13", settings.get("python_version"))
        self.assertEqual(_EXPECTED_SCOPE, scope)
        self.assertEqual("True", settings.get("strict"))
        self.assertNotIn("ignore_errors", settings)
        self.assertNotIn("follow_imports", settings)

    def test_domain_packages_keep_persistence_exports_lazy(self) -> None:
        package_exports = {
            "velvet_bot/domains/characters/__init__.py": {
                "velvet_bot.domains.characters.repository",
                "velvet_bot.domains.characters.service",
            },
            "velvet_bot/domains/references/__init__.py": {
                "velvet_bot.domains.references.repository",
                "velvet_bot.domains.references.service",
            },
        }

        for package_path, forbidden_modules in package_exports.items():
            with self.subTest(package=package_path):
                tree = ast.parse(Path(package_path).read_text(encoding="utf-8"))
                imported_modules = {
                    node.module
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module is not None
                }
                self.assertTrue(forbidden_modules.isdisjoint(imported_modules))

        from velvet_bot.domains.characters import (
            CharacterDirectoryRepository,
            CharacterDirectoryService,
        )
        from velvet_bot.domains.references import ReferenceRepository, ReferenceService

        self.assertEqual(
            "velvet_bot.domains.characters.repository",
            CharacterDirectoryRepository.__module__,
        )
        self.assertEqual(
            "velvet_bot.domains.characters.service",
            CharacterDirectoryService.__module__,
        )
        self.assertEqual(
            "velvet_bot.domains.references.repository",
            ReferenceRepository.__module__,
        )
        self.assertEqual(
            "velvet_bot.domains.references.service",
            ReferenceService.__module__,
        )

    def test_type_check_workflow_uses_pinned_development_dependencies(self) -> None:
        workflow = Path(".github/workflows/type-check.yml").read_text(encoding="utf-8")
        requirements = Path("requirements-dev.txt").read_text(encoding="utf-8")

        self.assertIn("python -m pip install -r requirements-dev.txt", workflow)
        self.assertIn("python -m mypy", workflow)
        self.assertIn("mypy==2.3.0", requirements)
        self.assertIn("-r requirements.txt", requirements)
        self.assertIn("mypy-output.txt", workflow)


if __name__ == "__main__":
    unittest.main()
