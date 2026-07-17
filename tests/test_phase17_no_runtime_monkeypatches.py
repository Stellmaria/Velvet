from __future__ import annotations

import ast
import unittest
from pathlib import Path

import velvet_bot.analytics_review as analytics_review
import velvet_bot.media_quality as media_quality
from velvet_bot import runtime_log_hotfixes
from velvet_bot.safe_analytics_edit import install_safe_analytics_edit


ROOT = Path(__file__).resolve().parents[1]


class RuntimeCompatibilityRemovalTests(unittest.TestCase):
    def test_runtime_exports_are_canonical_functions(self) -> None:
        self.assertIs(
            runtime_log_hotfixes.set_manual_publication_type,
            analytics_review.set_manual_publication_type,
        )
        self.assertIs(
            runtime_log_hotfixes.decide_duplicate_candidate,
            media_quality.decide_duplicate_candidate,
        )
        self.assertIs(
            runtime_log_hotfixes.scan_media_target,
            media_quality.scan_media_target,
        )

    def test_installers_are_noops(self) -> None:
        self.assertIsNone(runtime_log_hotfixes.install_runtime_log_hotfixes())
        self.assertIsNone(install_safe_analytics_edit())

    def test_root_router_does_not_install_legacy_compatibility(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/router.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("install_legacy_compatibility", source)

    def test_compatibility_modules_do_not_assign_foreign_functions(self) -> None:
        for relative in (
            "velvet_bot/runtime_log_hotfixes.py",
            "velvet_bot/safe_analytics_edit.py",
            "velvet_bot/presentation/telegram/compat.py",
        ):
            path = ROOT / relative
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            assignments = [
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.Assign, ast.AnnAssign))
                and isinstance(getattr(node, "target", None), ast.Attribute)
            ]
            self.assertEqual([], assignments, relative)

    def test_manual_classification_sql_is_explicitly_typed(self) -> None:
        source = (ROOT / "velvet_bot/analytics_review.py").read_text(encoding="utf-8")
        self.assertIn("post_type = $3::VARCHAR", source)
        self.assertIn("publication_key = $2::VARCHAR", source)
        self.assertIn("$3::VARCHAR = 'prompt'::VARCHAR", source)


if __name__ == "__main__":
    unittest.main()
