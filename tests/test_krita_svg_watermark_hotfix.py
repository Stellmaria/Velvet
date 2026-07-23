from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_svg_patch_module():
    path = ROOT / "tools/krita/velvet_logo/svg_logo_patch.py"
    spec = importlib.util.spec_from_file_location("velvet_svg_logo_patch_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Не удалось загрузить svg_logo_patch.py для теста.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KritaSvgWatermarkHotfixTests(unittest.TestCase):
    def test_plugin_installs_svg_patch_before_extension_and_fails_open(self) -> None:
        init_source = (ROOT / "tools/krita/velvet_logo/__init__.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("install_svg_logo_patch(VelvetLogoExtension)", init_source)
        self.assertLess(
            init_source.index("install_svg_logo_patch(VelvetLogoExtension)"),
            init_source.index("Krita.instance().addExtension"),
        )
        self.assertIn("except Exception as error", init_source)
        self.assertIn("SVG compatibility patch disabled", init_source)

    def test_custom_svg_uses_safe_vector_flattening_without_qtsvg(self) -> None:
        source = (ROOT / "tools/krita/velvet_logo/svg_logo_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("PyQt5.QtSvg", source)
        self.assertNotIn("QSvgRenderer", source)
        self.assertNotIn("QImage", source)
        self.assertNotIn('href="data:image/png;base64,', source)
        self.assertIn("_flatten_svg", source)
        self.assertIn("_strip_namespaces", source)
        self.assertIn("translate(", source)
        self.assertIn("scale(", source)
        self.assertIn('PATCH_VERSION = "2.1.1"', source)

    def test_flattened_svg_has_no_nested_root_or_namespace_prefixes(self) -> None:
        module = _load_svg_patch_module()
        raw = b"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 50'>
        <defs><linearGradient id='g'><stop offset='0' stop-color='#fff'/></linearGradient></defs>
        <path d='M0 0h100v50H0z' fill='url(#g)'/>
        </svg>"""
        body = module._flatten_svg(
            raw,
            x=10.0,
            y=20.0,
            logo_width=200.0,
            logo_height=100.0,
            source_width=100.0,
            source_height=50.0,
        )
        self.assertNotIn("<svg", body)
        self.assertNotIn("ns0:", body)
        self.assertIn("<defs>", body)
        self.assertIn("<g transform=", body)
        self.assertIn("<path", body)
        self.assertIn("url(#g)", body)

    def test_desktop_metadata_exposes_safe_plugin_version(self) -> None:
        source = (ROOT / "tools/krita/velvet_logo.desktop").read_text(
            encoding="utf-8"
        )
        self.assertIn("X-Velvet-Plugin-Version=2.1.1", source)

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
