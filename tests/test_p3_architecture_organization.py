from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTER_ROOT = ROOT / "velvet_bot/presentation/telegram/router.py"
BUNDLE_DIR = ROOT / "velvet_bot/presentation/telegram/routers"

EXPECTED_ROUTER_MODULES = {
    "velvet_bot.handlers.admin_directory",
    "velvet_bot.handlers.admin_large_media_preview",
    "velvet_bot.handlers.admin_media_display",
    "velvet_bot.handlers.admin_media_spoiler",
    "velvet_bot.handlers.admin_stories",
    "velvet_bot.handlers.admin_uncategorized",
    "velvet_bot.handlers.admin_universe_story_flow",
    "velvet_bot.handlers.ai_jobs",
    "velvet_bot.handlers.analytics_dashboard",
    "velvet_bot.handlers.analytics_dashboard_overrides",
    "velvet_bot.handlers.analytics_discussion_overrides",
    "velvet_bot.handlers.analytics_management",
    "velvet_bot.handlers.archive",
    "velvet_bot.handlers.backup_center",
    "velvet_bot.handlers.channel_analytics",
    "velvet_bot.handlers.character_aliases",
    "velvet_bot.handlers.characters",
    "velvet_bot.handlers.discussion_updates",
    "velvet_bot.handlers.error_center",
    "velvet_bot.handlers.guest_archive",
    "velvet_bot.handlers.inline_help",
    "velvet_bot.handlers.kr_profile_overrides",
    "velvet_bot.handlers.kr_universe_entry",
    "velvet_bot.handlers.media_browser",
    "velvet_bot.handlers.media_prompt_binding",
    "velvet_bot.handlers.multi_story_kr",
    "velvet_bot.handlers.owner_actions",
    "velvet_bot.handlers.owner_menu",
    "velvet_bot.handlers.public_archive",
    "velvet_bot.handlers.public_manager",
    "velvet_bot.handlers.public_media_display",
    "velvet_bot.handlers.public_notification_open",
    "velvet_bot.handlers.publication_center_safe",
    "velvet_bot.handlers.quality_ai",
    "velvet_bot.handlers.quality_ai_preview",
    "velvet_bot.handlers.quality_calibration",
    "velvet_bot.handlers.quality_center",
    "velvet_bot.handlers.quality_duplicates",
    "velvet_bot.handlers.quality_operations",
    "velvet_bot.handlers.quality_set_ai",
    "velvet_bot.handlers.quality_sets",
    "velvet_bot.handlers.reference_albums",
    "velvet_bot.handlers.reference_comparison",
    "velvet_bot.handlers.reference_comparison_help",
    "velvet_bot.handlers.reference_documents",
    "velvet_bot.handlers.reference_management",
    "velvet_bot.handlers.references",
    "velvet_bot.handlers.spoiler_save",
    "velvet_bot.handlers.start",
    "velvet_bot.presentation.telegram.routers.supervisor.control",
    "velvet_bot.presentation.telegram.routers.system",
    "velvet_bot.handlers.telegram_analytics_import",
    "velvet_bot.handlers.velvet_ai",
    "velvet_bot.handlers.velvet_ai_formatting",
    "velvet_bot.handlers.velvet_ai_visual",
}


def _active_router_module(module: str) -> bool:
    return module.startswith("velvet_bot.handlers.") or module.startswith(
        "velvet_bot.presentation.telegram.routers."
    )


class P3RouterOrganizationTests(unittest.TestCase):
    def test_root_router_depends_only_on_domain_bundles(self) -> None:
        source = ROUTER_ROOT.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(ROUTER_ROOT))
        handler_imports = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("velvet_bot.handlers")
        ]
        self.assertEqual([], handler_imports)
        self.assertEqual(4, source.count("root.include_router("))

    def test_router_bundles_cover_each_active_router_once(self) -> None:
        modules: list[str] = []
        for path in sorted(BUNDLE_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            modules.extend(
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module
                and _active_router_module(node.module)
            )
        self.assertEqual(len(modules), len(set(modules)))
        self.assertEqual(EXPECTED_ROUTER_MODULES, set(modules))

    def test_publication_router_precedes_archive_catch_all(self) -> None:
        source = (BUNDLE_DIR / "archive_and_public.py").read_text(encoding="utf-8")
        self.assertLess(
            source.index("router.include_router(publication_center_router)"),
            source.index("router.include_router(archive_router)"),
        )

    def test_active_compatibility_is_staged_and_enumerated(self) -> None:
        path = ROOT / "velvet_bot/presentation/telegram/compat.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        assignments = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id
            in {"PRE_IMPORT_COMPONENTS", "POST_IMPORT_COMPONENTS"}
        }
        self.assertEqual(
            (
                "ai-quality-schema",
                "set-consistency-dashboard",
                "quality-calibration-dashboard",
                "media-set-actions",
                "media-set-ai-discovery",
                "media-set-ui",
                "owner-menu-navigation",
            ),
            assignments["PRE_IMPORT_COMPONENTS"],
        )
        self.assertEqual(
            ("quality-calibration-report-ui",),
            assignments["POST_IMPORT_COMPONENTS"],
        )
        self.assertIn(
            "install_pre_router_compatibility()",
            ROUTER_ROOT.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "install_post_router_compatibility()",
            ROUTER_ROOT.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
