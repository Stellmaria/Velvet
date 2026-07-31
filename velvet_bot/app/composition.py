from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

Installer = Callable[[], None]
ApplicationRunner = Callable[[], Awaitable[None]]
RunnerFactory = Callable[[], ApplicationRunner]
StageFactory = Callable[[], tuple["CompositionStage", ...]]


@dataclass(frozen=True, slots=True)
class CompositionStage:
    """One ordered, side-effecting application installation step."""

    name: str
    install: Installer


@dataclass(frozen=True, slots=True)
class ApplicationComposition:
    """Explicit startup phases for application-wide runtime composition."""

    bootstrap_stages: tuple[CompositionStage, ...]
    feature_stage_names: tuple[str, ...]
    feature_stages_factory: StageFactory
    runner_factory: RunnerFactory

    @property
    def stage_names(self) -> tuple[str, ...]:
        return (
            *(stage.name for stage in self.bootstrap_stages),
            *self.feature_stage_names,
        )

    async def run(self) -> None:
        for stage in self.bootstrap_stages:
            stage.install()

        runner = self.runner_factory()
        feature_stages = self.feature_stages_factory()
        actual_names = tuple(stage.name for stage in feature_stages)
        if actual_names != self.feature_stage_names:
            raise RuntimeError(
                "Application composition stage order drifted: "
                f"declared={self.feature_stage_names!r} actual={actual_names!r}"
            )

        for stage in feature_stages:
            stage.install()

        await runner()


def _install_runtime_stability() -> None:
    from velvet_bot.runtime_stability import install_runtime_stability

    install_runtime_stability()


def _install_channel_analytics_datetime_compat() -> None:
    from velvet_bot.app.channel_analytics_datetime_compat import (
        install_channel_analytics_datetime_compat,
    )

    install_channel_analytics_datetime_compat()


def _load_bootstrap_runner() -> ApplicationRunner:
    from velvet_bot.app.bootstrap import run_application

    return run_application


_FEATURE_STAGE_NAMES = (
    "install_ai_model_routing",
    "install_friendly_media_worker",
    "install_grs_resilience",
    "install_grs_campaign_retry",
    "install_grs_speedups",
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
    "install_auf_owner_pricing_ui",
    "install_auf_photo_model_modes",
    "install_original_image_delivery_hotfix",
    "install_original_video_delivery_hotfix",
    "install_auf_result_delivery_recovery",
    "install_auf_active_delivery_fix",
    "install_auf_charged_queue",
    "install_auf_generation_receipts",
    "install_krita_remote_worker",
    "install_auf_grs_brand",
    "install_auf_branding",
)


def _build_feature_stages() -> tuple[CompositionStage, ...]:
    from velvet_bot.app.auf_active_delivery_fix import install_auf_active_delivery_fix
    from velvet_bot.app.auf_branding import install_auf_branding
    from velvet_bot.app.auf_cancel_ui_install import install_auf_cancel_ui
    from velvet_bot.app.auf_charged_queue_install import install_auf_charged_queue
    from velvet_bot.app.auf_generation_receipt_install import (
        install_auf_generation_receipts,
    )
    from velvet_bot.app.auf_grs_brand_install import install_auf_grs_brand
    from velvet_bot.app.auf_owner_pricing_ui_install import install_auf_owner_pricing_ui
    from velvet_bot.app.auf_photo_model_modes import install_auf_photo_model_modes
    from velvet_bot.app.auf_photo_ratio_callback_fix import (
        install_auf_photo_ratio_callback_fix,
    )
    from velvet_bot.app.auf_photo_ui_install import install_auf_photo_ui
    from velvet_bot.app.auf_reconciliation_install import install_auf_reconciliation
    from velvet_bot.app.auf_reference_privacy_install import (
        install_auf_reference_privacy,
    )
    from velvet_bot.app.auf_result_delivery_recovery import (
        install_auf_result_delivery_recovery,
    )
    from velvet_bot.app.auf_runtime_install import install_auf_runtime_dispatcher
    from velvet_bot.app.auf_user_portal_install import install_auf_user_portal
    from velvet_bot.app.auf_wallet_ui_install import install_auf_wallet_ui
    from velvet_bot.app.auf_workspace_ui_install import install_auf_workspace_ui
    from velvet_bot.app.grs_campaign_retry import install_grs_campaign_retry
    from velvet_bot.app.grs_resilience import install_grs_resilience
    from velvet_bot.app.grs_speedups import install_grs_speedups
    from velvet_bot.app.krita_remote_install import install_krita_remote_worker
    from velvet_bot.app.original_image_delivery_hotfix import (
        install_original_image_delivery_hotfix,
    )
    from velvet_bot.app.original_video_delivery_hotfix import (
        install_original_video_delivery_hotfix,
    )
    from velvet_bot.app.telegram_progress_resilience import (
        install_telegram_progress_resilience,
    )
    from velvet_bot.domains.media_generation.friendly_worker import (
        install_friendly_media_worker,
    )
    from velvet_bot.infrastructure.ai_model_routing import install_ai_model_routing

    return (
        CompositionStage("install_ai_model_routing", install_ai_model_routing),
        CompositionStage("install_friendly_media_worker", install_friendly_media_worker),
        CompositionStage("install_grs_resilience", install_grs_resilience),
        CompositionStage("install_grs_campaign_retry", install_grs_campaign_retry),
        CompositionStage("install_grs_speedups", install_grs_speedups),
        CompositionStage(
            "install_telegram_progress_resilience",
            install_telegram_progress_resilience,
        ),
        CompositionStage("install_auf_cancel_ui", install_auf_cancel_ui),
        CompositionStage(
            "install_auf_runtime_dispatcher",
            install_auf_runtime_dispatcher,
        ),
        CompositionStage("install_auf_reconciliation", install_auf_reconciliation),
        CompositionStage("install_auf_workspace_ui", install_auf_workspace_ui),
        CompositionStage("install_auf_wallet_ui", install_auf_wallet_ui),
        CompositionStage("install_auf_photo_ui", install_auf_photo_ui),
        CompositionStage(
            "install_auf_reference_privacy",
            install_auf_reference_privacy,
        ),
        CompositionStage(
            "install_auf_photo_ratio_callback_fix",
            install_auf_photo_ratio_callback_fix,
        ),
        CompositionStage("install_auf_user_portal", install_auf_user_portal),
        CompositionStage(
            "install_auf_owner_pricing_ui",
            install_auf_owner_pricing_ui,
        ),
        # Install after the legacy photo and wallet layers so the model-first flow
        # becomes the final photo controller before delivery/privacy wrappers.
        CompositionStage(
            "install_auf_photo_model_modes",
            install_auf_photo_model_modes,
        ),
        CompositionStage(
            "install_original_image_delivery_hotfix",
            install_original_image_delivery_hotfix,
        ),
        CompositionStage(
            "install_original_video_delivery_hotfix",
            install_original_video_delivery_hotfix,
        ),
        CompositionStage(
            "install_auf_result_delivery_recovery",
            install_auf_result_delivery_recovery,
        ),
        CompositionStage(
            "install_auf_active_delivery_fix",
            install_auf_active_delivery_fix,
        ),
        CompositionStage("install_auf_charged_queue", install_auf_charged_queue),
        CompositionStage(
            "install_auf_generation_receipts",
            install_auf_generation_receipts,
        ),
        CompositionStage("install_krita_remote_worker", install_krita_remote_worker),
        # Privacy and branding remain last until later bounded slices migrate
        # their controller replacement contracts.
        CompositionStage("install_auf_grs_brand", install_auf_grs_brand),
        CompositionStage("install_auf_branding", install_auf_branding),
    )


def build_application_composition() -> ApplicationComposition:
    return ApplicationComposition(
        bootstrap_stages=(
            CompositionStage("install_runtime_stability", _install_runtime_stability),
            CompositionStage(
                "install_channel_analytics_datetime_compat",
                _install_channel_analytics_datetime_compat,
            ),
        ),
        feature_stage_names=_FEATURE_STAGE_NAMES,
        feature_stages_factory=_build_feature_stages,
        runner_factory=_load_bootstrap_runner,
    )


async def run_application() -> None:
    await build_application_composition().run()


__all__ = (
    "ApplicationComposition",
    "CompositionStage",
    "build_application_composition",
    "run_application",
)
