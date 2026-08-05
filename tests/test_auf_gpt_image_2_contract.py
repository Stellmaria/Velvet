from __future__ import annotations

import unittest

from velvet_bot.app.composition import build_application_composition
from velvet_bot.domains.codex_image import (
    CODEX_IMAGE_TASK_TYPE,
    CodexImageRequest,
    GPT_IMAGE_2_NAME,
)


class AufGptImage2ContractTests(unittest.TestCase):
    def test_composition_installs_gpt_image_2_before_final_branding(self) -> None:
        composition = build_application_composition()
        self.assertEqual(
            composition.feature_stage_names[-2:],
            ("install_auf_gpt_image_2", "install_auf_branding"),
        )

    def test_text_mode_accepts_zero_references(self) -> None:
        request = CodexImageRequest(
            prompt="Нарисуй персонажа",
            references=(),
            input_mode="text",
            aspect_ratio="9:16",
            resolution="1K",
            analysis_model="gpt-5.6-terra",
            reasoning_effort="high",
        )
        self.assertEqual(request.references, ())
        self.assertEqual(request.resolution, "1K")

    def test_model_name_and_task_type_are_stable(self) -> None:
        self.assertEqual(GPT_IMAGE_2_NAME, "GPT Image 2")
        self.assertEqual(
            CODEX_IMAGE_TASK_TYPE,
            "media.generate.codex_image",
        )


if __name__ == "__main__":
    unittest.main()
