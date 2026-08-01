from __future__ import annotations

import unittest

from velvet_bot.app import auf_photo_model_modes
from velvet_bot.domains.media_generation import KieModelAlias
from velvet_bot.presentation.telegram.routers import (
    workspace_auf,
    workspace_auf_photo,
    workspace_auf_root,
)


_RETIRED_MODELS = frozenset(
    {
        KieModelAlias.QWEN2_IMAGE_EDIT,
        KieModelAlias.FLUX_2_PRO_IMAGE,
    }
)


class AufGenerationSurfacePolicyTests(unittest.TestCase):
    def test_qwen_and_flux_are_absent_from_active_photo_catalogs(self) -> None:
        self.assertTrue(
            _RETIRED_MODELS.isdisjoint(workspace_auf_photo._PHOTO_MODELS)
        )
        self.assertTrue(
            _RETIRED_MODELS.isdisjoint(auf_photo_model_modes._PHOTO_MODELS)
        )
        for model in _RETIRED_MODELS:
            with self.subTest(model=model):
                self.assertIsNone(workspace_auf_photo._model(model.value))
                self.assertIsNone(auf_photo_model_modes._model(model.value))

    def test_every_root_keyboard_uses_photo_and_video_labels(self) -> None:
        for builder in (
            workspace_auf.build_auf_root_keyboard,
            workspace_auf_photo.build_auf_root_keyboard,
            workspace_auf_root.build_auf_root_keyboard,
        ):
            with self.subTest(builder=builder.__module__):
                keyboard = builder(workspace_id=9, enabled=True)
                labels = [
                    button.text
                    for row in keyboard.inline_keyboard
                    for button in row
                ]
                self.assertEqual(
                    ["Фото", "Видео", "↩️ Моё пространство"],
                    labels,
                )
                self.assertIn(
                    "auf:create:",
                    keyboard.inline_keyboard[0][0].callback_data or "",
                )
                self.assertIn(
                    "auf:animate:",
                    keyboard.inline_keyboard[0][1].callback_data or "",
                )


if __name__ == "__main__":
    unittest.main()
