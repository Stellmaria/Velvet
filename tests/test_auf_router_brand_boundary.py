from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTERS = ROOT / "velvet_bot/presentation/telegram/routers"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class AufRouterBrandBoundaryTests(unittest.TestCase):
    def test_canonical_auf_routers_do_not_import_retired_paths(self) -> None:
        for path in ROUTERS.glob("workspace_auf*.py"):
            if path.name == "workspace_auf_legacy.py":
                continue
            with self.subTest(path=path.name):
                source = _read(path)
                self.assertNotIn("workspace_meow", source)
                self.assertNotIn("class Meow", source)

    def test_retired_generation_routers_are_only_compatibility_modules(self) -> None:
        for path in ROUTERS.glob("workspace_meow*.py"):
            with self.subTest(path=path.name):
                source = _read(path)
                self.assertIn("Compatibility", source)
                self.assertLessEqual(len(source.splitlines()), 28)

    def test_new_callback_protocol_is_auf_and_legacy_is_read_only(self) -> None:
        photo = _read(ROUTERS / "workspace_auf.py")
        video = _read(ROUTERS / "workspace_auf_video.py")
        legacy = _read(ROUTERS / "workspace_auf_legacy.py")
        controller = _read(
            ROOT / "velvet_bot/presentation/telegram/workspace_home_controller.py"
        )
        self.assertIn('class AufCallback(CallbackData, prefix="auf")', photo)
        self.assertIn('class AufVideoCallback(CallbackData, prefix="aufv")', video)
        self.assertIn('class LegacyMeowCallback(CallbackData, prefix="meow")', legacy)
        self.assertIn('class LegacyMeowVideoCallback(CallbackData, prefix="meowv")', legacy)
        self.assertIn('class MeowForm(StatesGroup)', legacy)
        self.assertIn("_auf_callback_filter", controller)
        self.assertIn('F.action.in_({"auf", "meow"})', controller)
        self.assertIn("MeowRuntimeForm.waiting_limit", controller)

    def test_new_workspace_buttons_use_auf_action(self) -> None:
        source = _read(ROOT / "velvet_bot/domains/auf_runtime/__init__.py")
        self.assertIn('AUF_WORKSPACE_ACTION = "auf"', source)
        self.assertIn('LEGACY_AUF_WORKSPACE_ACTION = "meow"', source)

    def test_photo_flow_writes_auf_state_and_dual_reads_legacy_data(self) -> None:
        photo = _read(ROUTERS / "workspace_auf_photo.py")
        installer = _read(ROOT / "velvet_bot/app/auf_photo_ui_install.py")
        legacy = _read(ROUTERS / "workspace_auf_legacy.py")
        self.assertIn("class AufPhotoForm(StatesGroup)", photo)
        self.assertIn("class MeowPhotoForm(StatesGroup)", legacy)
        self.assertIn('key.replace("auf_", "meow_", 1)', photo)
        self.assertNotIn("meow_prompt=", photo)
        self.assertNotIn("controller._require_meow", installer)
        self.assertNotIn("controller.handle_scoped_meow_action", installer)

    def test_runtime_uses_canonical_storage_identifiers(self) -> None:
        store = _read(ROOT / "velvet_bot/domains/auf_runtime/store.py")
        queue = _read(ROOT / "velvet_bot/domains/auf_runtime/queue.py")
        self.assertIn("workspace_auf_settings", store)
        self.assertIn("workspace_auf_settings", queue)
        self.assertNotIn("workspace_meow_settings", store)
        self.assertNotIn("workspace_meow_settings", queue)

    def test_active_routers_write_only_auf_fsm_keys_and_labels(self) -> None:
        paths = (
            ROUTERS / "workspace_auf.py",
            ROUTERS / "workspace_auf_grs.py",
            ROUTERS / "workspace_auf_balance.py",
            ROUTERS / "workspace_auf_grs_balance.py",
            ROUTERS / "workspace_auf_video.py",
            ROUTERS / "workspace_auf_video_simple.py",
        )
        for path in paths:
            with self.subTest(path=path.name):
                source = _read(path)
                self.assertNotIn("Мяу", source)
                self.assertNotIn("мяу", source)
        core = _read(ROUTERS / "workspace_auf.py")
        for key in (
            "meow_input_mode=",
            "meow_prompt=",
            "meow_references=",
            "meow_model=",
            'data.get("meow_',
        ):
            self.assertNotIn(key, core)
        self.assertIn('key.replace("auf_", "meow_", 1)', core)

    def test_final_telegram_branding_guard_is_installed_last(self) -> None:
        app = _read(ROOT / "velvet_bot/app/__init__.py")
        self.assertIn("install_auf_branding", app)
        self.assertLess(
            app.index("install_krita_remote_worker()"),
            app.index("install_auf_branding()"),
        )
        branding = _read(ROOT / "velvet_bot/app/auf_branding.py")
        self.assertIn('field_name in _IDENTIFIER_FIELDS', branding)
        self.assertIn('.replace("Мяу", "Ауф")', branding)

    def test_core_router_defines_and_uses_state_dual_read(self) -> None:
        core = _read(ROUTERS / "workspace_auf.py")
        self.assertIn("def _state_value(", core)
        self.assertIn('_state_value(data, "auf_workspace_id")', core)
        self.assertIn('_state_value(data, "auf_input_mode")', core)
        self.assertIn('_state_value(data, "auf_prompt")', core)
        self.assertIn('_state_value(data, "auf_references")', core)


if __name__ == "__main__":
    unittest.main()
