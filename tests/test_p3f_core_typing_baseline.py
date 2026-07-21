from __future__ import annotations

import configparser
import unittest
from pathlib import Path


_EXPECTED_SCOPE = {
    "velvet_bot/core/access",
    "velvet_bot/core/config",
    "velvet_bot/domains/characters/models.py",
    "velvet_bot/domains/archive/models.py",
    "velvet_bot/domains/references/models.py",
    "velvet_bot/domains/stories/models.py",
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

    def test_type_check_workflow_uses_pinned_development_dependencies(self) -> None:
        workflow = Path(".github/workflows/type-check.yml").read_text(encoding="utf-8")
        requirements = Path("requirements-dev.txt").read_text(encoding="utf-8")

        self.assertIn("python -m pip install -r requirements-dev.txt", workflow)
        self.assertIn("python -m mypy", workflow)
        self.assertIn("mypy==2.3.0", requirements)
        self.assertIn("-r requirements.txt", requirements)


if __name__ == "__main__":
    unittest.main()
