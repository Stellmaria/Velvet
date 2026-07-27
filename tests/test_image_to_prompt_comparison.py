from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from velvet_bot.presentation.telegram.routers.quality_operations_controllers import (
    velvet_ai_image_prompt,
)


class ImageToPromptComparisonTests(unittest.TestCase):
    def test_single_model_when_compare_model_is_empty(self) -> None:
        with patch.dict(os.environ, {"AI_VISION_COMPARE_MODEL": ""}, clear=False):
            self.assertEqual(("primary",), velvet_ai_image_prompt._comparison_models("primary"))

    def test_second_distinct_model_is_added(self) -> None:
        with patch.dict(
            os.environ,
            {"AI_VISION_COMPARE_MODEL": "qwen3-vl:8b"},
            clear=False,
        ):
            self.assertEqual(
                ("primary", "qwen3-vl:8b"),
                velvet_ai_image_prompt._comparison_models("primary"),
            )

    def test_duplicate_compare_model_is_ignored(self) -> None:
        with patch.dict(
            os.environ,
            {"AI_VISION_COMPARE_MODEL": "primary"},
            clear=False,
        ):
            self.assertEqual(("primary",), velvet_ai_image_prompt._comparison_models("primary"))


if __name__ == "__main__":
    unittest.main()
