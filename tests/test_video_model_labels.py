from __future__ import annotations

import unittest
from pathlib import Path

from velvet_bot.domains.media_generation.models import KieModelAlias, KieModelCatalog
from velvet_bot.presentation.telegram.routers.workspace_meow_balance import _MODEL_NAMES


_ROOT = Path(__file__).resolve().parents[1]


class VideoModelLabelTests(unittest.TestCase):
    def test_wan_legacy_alias_uses_current_name_and_route(self) -> None:
        self.assertEqual("Wan 2.7", KieModelAlias.WAN_26_IMAGE_TO_VIDEO.display_name)
        self.assertEqual(
            "wan/2-7-image-to-video",
            KieModelCatalog().wan_26_image_to_video,
        )

    def test_balance_names_include_grok_15_and_wan_27(self) -> None:
        self.assertEqual(
            "Grok Imagine Video 1.5",
            _MODEL_NAMES["grok_imagine_video_15"],
        )
        self.assertEqual("Wan 2.7", _MODEL_NAMES["wan_26_image_to_video"])

    def test_meow_overview_lists_all_current_video_models(self) -> None:
        source = (
            _ROOT
            / "velvet_bot"
            / "presentation"
            / "telegram"
            / "routers"
            / "workspace_meow_root.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Grok Imagine v1", source)
        self.assertIn("Grok Imagine Video 1.5", source)
        self.assertIn("Seedance 1.5 Pro", source)
        self.assertIn("Wan 2.7", source)
        self.assertNotIn("Wan 2.6", source)


if __name__ == "__main__":
    unittest.main()
