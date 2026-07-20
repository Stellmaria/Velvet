from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "velvet_bot.presentation.telegram.routers.quality_operations_controllers"
MODULES = (
    "backup_center",
    "ai_jobs",
    "quality_operations",
    "velvet_ai_formatting",
    "velvet_ai_visual",
    "velvet_ai",
    "quality_duplicates",
    "quality_sets",
    "quality_set_ai",
    "quality_calibration",
    "quality_ai_preview",
    "quality_ai",
    "quality_center",
)
RETIRED_ALIASES = {
    "ai_jobs",
    "quality_ai",
    "quality_ai_preview",
    "quality_calibration",
    "quality_center",
    "quality_duplicates",
    "quality_operations",
    "quality_set_ai",
    "quality_sets",
    "velvet_ai",
    "velvet_ai_formatting",
    "velvet_ai_visual",
}
ALIASES = {
    f"velvet_bot.handlers.{name}": f"{PACKAGE}.{name}"
    for name in MODULES
    if name not in RETIRED_ALIASES
}
INCLUDE_ORDER = (
    "backup_center",
    "ai_jobs",
    "quality_operations",
    "velvet_ai_formatting",
    "velvet_ai_visual",
    "velvet_ai",
    "quality_duplicates",
    "quality_sets",
    "quality_set_ai",
    "quality_calibration",
    "quality_ai_preview",
    "quality_ai",
    "quality_center",
)


class P3CQualityOperationsControllersTests(unittest.TestCase):
    def test_remaining_legacy_imports_resolve_to_canonical_module_objects(self) -> None:
        for legacy_name, canonical_name in ALIASES.items():
            with self.subTest(legacy=legacy_name):
                legacy = importlib.import_module(legacy_name)
                canonical = importlib.import_module(canonical_name)
                self.assertIs(legacy, canonical)

    def test_remaining_legacy_files_are_only_module_aliases(self) -> None:
        for legacy_name, canonical_name in ALIASES.items():
            with self.subTest(legacy=legacy_name):
                path = ROOT / Path(*legacy_name.split(".")).with_suffix(".py")
                source = path.read_text(encoding="utf-8")
                self.assertIn("P3_COMPAT_MODULE_ALIAS", source)
                self.assertIn(canonical_name, source)
                self.assertNotIn("@router.", source)
                self.assertLessEqual(len(source.splitlines()), 10)

    def test_retired_quality_alias_files_are_absent(self) -> None:
        for name in RETIRED_ALIASES:
            with self.subTest(alias=name):
                path = ROOT / "velvet_bot" / "handlers" / f"{name}.py"
                self.assertFalse(path.exists())

    def test_canonical_modules_own_real_router_implementations(self) -> None:
        root = ROOT / "velvet_bot/presentation/telegram/routers/quality_operations_controllers"
        for name in MODULES:
            with self.subTest(module=name):
                source = (root / f"{name}.py").read_text(encoding="utf-8")
                self.assertIn("router = Router(name=__name__)", source)
                self.assertIn("@router.", source)

        markers = {
            "backup_center.py": ('Command("backup")', "BackupCallback.filter()"),
            "ai_jobs.py": ('F.action == "aijobs"',),
            "quality_operations.py": ("QualityUploadReplyFilter", "AIJobTracker.create"),
            "velvet_ai_formatting.py": ("AIJobTracker.create", 'kind="velvet_formatting"'),
            "velvet_ai_visual.py": ("AIJobTracker.create", 'kind="palette_composition"'),
            "velvet_ai.py": ("AIJobTracker.create", 'kind="prompt_result"'),
            "quality_duplicates.py": ('F.action == "duplicates"',),
            "quality_sets.py": ('F.action == "sets"',),
            "quality_set_ai.py": ("AIJobTracker.create", 'kind="media_set_consistency"'),
        }
        for filename, expected in markers.items():
            source = (root / filename).read_text(encoding="utf-8")
            for marker in expected:
                self.assertIn(marker, source, filename)

    def test_quality_bundle_uses_canonical_controllers_in_original_order(self) -> None:
        path = ROOT / "velvet_bot/presentation/telegram/routers/quality_operations.py"
        source = path.read_text(encoding="utf-8")
        for legacy_name, canonical_name in ALIASES.items():
            self.assertNotIn(legacy_name, source)
            self.assertIn(canonical_name, source)

        includes = [
            f"router.include_router({name}_router)" for name in INCLUDE_ORDER
        ]
        positions = [source.index(item) for item in includes]
        self.assertEqual(sorted(positions), positions)


if __name__ == "__main__":
    unittest.main()
