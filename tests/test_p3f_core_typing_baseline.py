from __future__ import annotations

import configparser
import unittest
from pathlib import Path


class P3FCoreTypingBaselineTests(unittest.TestCase):
    def test_mypy_scope_is_strict_and_bounded(self) -> None:
        parser = configparser.ConfigParser()
        parser.read("mypy.ini", encoding="utf-8")

        settings = parser["mypy"]
        self.assertEqual("3.13", settings.get("python_version"))
        self.assertEqual(
            "velvet_bot/core/access, velvet_bot/core/config",
            settings.get("files"),
        )
        self.assertEqual("True", settings.get("strict"))
        self.assertNotIn("ignore_errors", settings)

    def test_type_check_workflow_uses_pinned_development_dependencies(self) -> None:
        workflow = Path(".github/workflows/type-check.yml").read_text(encoding="utf-8")
        requirements = Path("requirements-dev.txt").read_text(encoding="utf-8")

        self.assertIn("python -m pip install -r requirements-dev.txt", workflow)
        self.assertIn("python -m mypy", workflow)
        self.assertIn("mypy==2.3.0", requirements)
        self.assertIn("-r requirements.txt", requirements)


if __name__ == "__main__":
    unittest.main()
