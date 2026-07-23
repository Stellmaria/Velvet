from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class KritaSvgWatermarkHotfixTests(unittest.TestCase):
    def test_plugin_installs_svg_raster_patch_before_extension(self) -> None:
        init_source = (ROOT / "tools/krita/velvet_logo/__init__.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("install_svg_logo_patch(VelvetLogoExtension)", init_source)
        self.assertLess(
            init_source.index("install_svg_logo_patch(VelvetLogoExtension)"),
            init_source.index("Krita.instance().addExtension"),
        )

    def test_custom_svg_is_rendered_to_transparent_png(self) -> None:
        source = (ROOT / "tools/krita/velvet_logo/svg_logo_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("QSvgRenderer", source)
        self.assertIn("QImage.Format_ARGB32_Premultiplied", source)
        self.assertIn('href="data:image/png;base64,', source)
        self.assertIn('PATCH_VERSION = "2.1.0"', source)

    def test_workspace_watermark_accepts_next_photo_without_reply(self) -> None:
        ui = (ROOT / "velvet_bot/workspace_watermark_ui.py").read_text(
            encoding="utf-8"
        )
        router = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_watermark.py"
        ).read_text(encoding="utf-8")
        self.assertIn("waiting_source = State()", ui)
        self.assertIn('text="⚡ Быстрый watermark"', ui)
        self.assertIn("handle_workspace_watermark_source", router)
        self.assertIn("Просто отправьте следующим сообщением фото", router)

    def test_archive_quick_watermark_precedes_legacy_destination_gate(self) -> None:
        router = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_watermark.py"
        ).read_text(encoding="utf-8")
        bundle = (
            ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        adjustments = (
            ROOT / "velvet_bot/presentation/telegram/workspace_ui_adjustments.py"
        ).read_text(encoding="utf-8")
        self.assertIn("handle_workspace_archive_fast_watermark", router)
        self.assertIn(
            'WorkspacePersonalArchiveCallback.filter(F.action == "watermark")',
            router,
        )
        self.assertLess(
            bundle.index("router.include_router(workspace_watermark_router)"),
            bundle.index("router.include_router(workspace_owner_controls_router)"),
        )
        self.assertIn('text="⚡ Быстрый watermark"', adjustments)
        self.assertNotIn("место хранения не настроены", adjustments)


if __name__ == "__main__":
    unittest.main()
