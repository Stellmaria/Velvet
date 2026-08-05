from __future__ import annotations

import asyncio
import unittest

import velvet_bot.app as app
from velvet_bot.app.composition import (
    ApplicationComposition,
    CompositionStage,
    build_application_composition,
    run_application,
)


EXPECTED_STAGE_NAMES = (
    "install_runtime_stability",
    "install_channel_analytics_datetime_compat",
    "install_friendly_media_worker",
    "install_telegram_progress_resilience",
    "install_auf_cancel_ui",
    "install_auf_runtime_dispatcher",
    "install_auf_reconciliation",
    "install_auf_workspace_ui",
    "install_auf_wallet_ui",
    "install_auf_photo_ui",
    "install_auf_reference_privacy",
    "install_auf_photo_ratio_callback_fix",
    "install_auf_user_portal",
    "install_auf_photo_model_modes",
    "install_auf_owner_pricing_ui",
    "install_auf_margin_dashboard",
    "install_original_image_delivery_hotfix",
    "install_original_video_delivery_hotfix",
    "install_auf_result_delivery_recovery",
    "install_auf_active_delivery_fix",
    "install_auf_charged_queue",
    "install_auf_generation_receipts",
    "install_krita_remote_worker",
    "install_auf_branding",
)


class ApplicationCompositionTests(unittest.TestCase):
    def test_default_composition_preserves_complete_startup_order(self) -> None:
        composition = build_application_composition()

        self.assertEqual(EXPECTED_STAGE_NAMES, composition.stage_names)
        self.assertEqual(2, len(composition.bootstrap_stages))
        self.assertEqual(22, len(composition.feature_stage_names))

    def test_run_loads_bootstrap_before_building_feature_stages(self) -> None:
        events: list[str] = []

        async def runner() -> None:
            events.append("runner")

        def runner_factory():
            events.append("runner_factory")
            return runner

        def feature_stages_factory():
            events.append("feature_stages_factory")
            return (
                CompositionStage("feature-1", lambda: events.append("feature-1")),
                CompositionStage("feature-2", lambda: events.append("feature-2")),
            )

        composition = ApplicationComposition(
            bootstrap_stages=(
                CompositionStage("bootstrap-1", lambda: events.append("bootstrap-1")),
                CompositionStage("bootstrap-2", lambda: events.append("bootstrap-2")),
            ),
            feature_stage_names=("feature-1", "feature-2"),
            feature_stages_factory=feature_stages_factory,
            runner_factory=runner_factory,
        )

        asyncio.run(composition.run())

        self.assertEqual(
            [
                "bootstrap-1",
                "bootstrap-2",
                "runner_factory",
                "feature_stages_factory",
                "feature-1",
                "feature-2",
                "runner",
            ],
            events,
        )

    def test_run_rejects_declared_and_actual_stage_order_drift(self) -> None:
        async def runner() -> None:
            return None

        composition = ApplicationComposition(
            bootstrap_stages=(),
            feature_stage_names=("declared",),
            feature_stages_factory=lambda: (
                CompositionStage("actual", lambda: None),
            ),
            runner_factory=lambda: runner,
        )

        with self.assertRaisesRegex(RuntimeError, "stage order drifted"):
            asyncio.run(composition.run())

    def test_app_package_exports_explicit_entry_point(self) -> None:
        self.assertIs(run_application, app.run_application)
        self.assertIs(build_application_composition, app.build_application_composition)
        self.assertFalse(hasattr(app, "__getattr__"))


if __name__ == "__main__":
    unittest.main()
