from __future__ import annotations

import unittest
from pathlib import Path

from velvet_bot.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


class Release130Tests(unittest.TestCase):
    def test_application_version_is_stable_release(self) -> None:
        self.assertEqual(APP_VERSION, "1.3.0")
        self.assertNotIn("dev", APP_VERSION.casefold())

    def test_release_is_documented_consistently(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        status = (ROOT / "docs/development_status.md").read_text(encoding="utf-8")

        self.assertIn("Текущая версия: `1.3.0`.", readme)
        self.assertIn("## [1.3.0] - 2026-07-17", changelog)
        self.assertIn("Текущая стабильная версия: `1.3.0`.", status)

    def test_release_workflow_checks_tag_against_app_version(self) -> None:
        workflow = (
            ROOT / ".github/workflows/release.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('tags:', workflow)
        self.assertIn('APP_VERSION', workflow)
        self.assertIn('gh release create', workflow)


if __name__ == "__main__":
    unittest.main()
