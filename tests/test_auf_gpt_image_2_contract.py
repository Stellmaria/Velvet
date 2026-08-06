from __future__ import annotations

import asyncio
import inspect
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from velvet_bot.app import auf_gpt_image_2_install
from velvet_bot.app import auf_gpt_image_2_quality_install
from velvet_bot.app.composition import build_application_composition
from velvet_bot.domains.codex_image import (
    CODEX_IMAGE_RESOLUTIONS,
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
        stage_source = inspect.getsource(
            composition.feature_stages_factory
        )
        self.assertIn("install_gpt_image_with_byesu_quality", stage_source)
        self.assertIn("install_auf_gpt_image_2_quality", stage_source)

    def test_worker_bootstrap_finalizes_after_feature_wrappers(self) -> None:
        from velvet_bot.app import bootstrap
        from velvet_bot.app import gpt_image_2_bootstrap
        from velvet_bot.app import workers as workers_module

        original_runner = bootstrap.run_application
        original_bootstrap_builder = bootstrap.build_worker_manager
        original_workers_builder = workers_module.build_worker_manager
        original_installed = gpt_image_2_bootstrap._INSTALLED
        original_finalized = gpt_image_2_bootstrap._FINALIZED
        observed: list[object] = []

        async def fake_runner() -> None:
            observed.append(bootstrap.build_worker_manager)

        def later_feature_builder(*args: object, **kwargs: object) -> object:
            del args, kwargs
            return object()

        try:
            bootstrap.run_application = fake_runner
            bootstrap.build_worker_manager = original_bootstrap_builder
            workers_module.build_worker_manager = original_workers_builder
            gpt_image_2_bootstrap._INSTALLED = False
            gpt_image_2_bootstrap._FINALIZED = False

            with patch.dict(os.environ, {"CODEX_IMAGE_ENABLED": "true"}):
                gpt_image_2_bootstrap.install_gpt_image_2_bootstrap()
                delayed_runner = bootstrap.run_application

                workers_module.build_worker_manager = later_feature_builder
                bootstrap.build_worker_manager = later_feature_builder
                asyncio.run(delayed_runner())

            final_builder = workers_module.build_worker_manager
            self.assertIs(bootstrap.build_worker_manager, final_builder)
            self.assertIsNot(final_builder, later_feature_builder)
            closure_values = tuple(
                cell.cell_contents for cell in (final_builder.__closure__ or ())
            )
            self.assertIn(later_feature_builder, closure_values)
            self.assertEqual(observed, [final_builder])
        finally:
            bootstrap.run_application = original_runner
            bootstrap.build_worker_manager = original_bootstrap_builder
            workers_module.build_worker_manager = original_workers_builder
            gpt_image_2_bootstrap._INSTALLED = original_installed
            gpt_image_2_bootstrap._FINALIZED = original_finalized

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

    def test_progress_card_keeps_primary_codex_export_honest(self) -> None:
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
        self.assertIn("Экспорт: <b>JPEG · 9:16</b>", text)
        self.assertNotIn("4K JPEG", text)
        self.assertIn("82.0% → 79.0% (-3.0 п.п.)", text)
        self.assertIn("65.0% → 64.0% (-1.0 п.п.)", text)
        self.assertIn("В очереди: <b>15 сек</b>", text)
        self.assertIn("Выполнение: <b>1 мин 29 сек</b>", text)
        self.assertIn("Всего: <b>1 мин 44 сек</b>", text)

    def test_quality_selector_uses_codex_first_and_parameter_routing(self) -> None:
        base_source = inspect.getsource(auf_gpt_image_2_install)
        patch_source = inspect.getsource(auf_gpt_image_2_quality_install)

        self.assertIn("_INTERNAL_EXPORT_PROFILE", base_source)
        self.assertEqual(CODEX_IMAGE_RESOLUTIONS, ("1K", "2K", "4K"))
        self.assertIn("1K: сначала Codex Plus", patch_source)
        self.assertIn("gpt-image-2", patch_source)
        self.assertIn("firefly-gpt-image-2", patch_source)
        self.assertIn("от 1 до 6 общих референсов", patch_source)
        self.assertIn("Один файл: до 8 МБ", patch_source)
        self.assertIn("gpt2_resolution", patch_source)
        self.assertIn("gpt2_choose_resolution", patch_source)
        self.assertIn("resolution=resolution", patch_source)
        self.assertNotIn("апскейл до выбранного качества", patch_source)

    def test_enqueue_persists_progress_message_and_timestamp(self) -> None:
        source = inspect.getsource(auf_gpt_image_2_install._enqueue)
        self.assertIn('"progress_message_id"', source)
        self.assertIn('"queued_at"', source)
        self.assertIn("render_codex_image_progress", source)


if __name__ == "__main__":
    unittest.main()
