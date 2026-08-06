from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timezone

from velvet_bot.app import auf_gpt_image_2_install
from velvet_bot.app.composition import build_application_composition
from velvet_bot.domains.codex_image import (
    CODEX_IMAGE_TASK_TYPE,
    CodexImageRequest,
    GPT_IMAGE_2_NAME,
    render_codex_image_progress,
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


    def test_progress_card_shows_codex_delta_and_elapsed_time(self) -> None:
        request = CodexImageRequest(
            prompt="Нарисуй персонажа",
            references=(),
            input_mode="text",
            aspect_ratio="9:16",
            resolution="4K",
            analysis_model="gpt-5.6-terra",
            reasoning_effort="high",
        )
        queued = datetime(2026, 8, 5, 22, 0, tzinfo=timezone.utc)
        started = datetime(2026, 8, 5, 22, 0, 15, tzinfo=timezone.utc)
        finished = datetime(2026, 8, 5, 22, 1, 44, tzinfo=timezone.utc)
        text = render_codex_image_progress(
            request,
            task_id="task-1",
            progress=100,
            stage="завершено",
            queued_at=queued,
            started_at=started,
            finished_at=finished,
            rate_limits_before={
                "primary": {"used_percent": 18},
                "secondary": {"used_percent": 35},
            },
            rate_limits_after={
                "primary": {"used_percent": 21},
                "secondary": {"used_percent": 36},
            },
        )
        self.assertIn("завершено · 100%", text)
        self.assertIn("82.0% → 79.0% (-3.0 п.п.)", text)
        self.assertIn("65.0% → 64.0% (-1.0 п.п.)", text)
        self.assertIn("В очереди: <b>15 сек</b>", text)
        self.assertIn("Выполнение: <b>1 мин 29 сек</b>", text)
        self.assertIn("Всего: <b>1 мин 44 сек</b>", text)

    def test_enqueue_persists_progress_message_and_timestamp(self) -> None:
        source = inspect.getsource(auf_gpt_image_2_install._enqueue)
        self.assertIn('"progress_message_id"', source)
        self.assertIn('"queued_at"', source)
        self.assertIn("render_codex_image_progress", source)


if __name__ == "__main__":
    unittest.main()
