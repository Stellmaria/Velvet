from __future__ import annotations

from typing import Any

from velvet_bot.runtime_stability import install_runtime_stability

__all__ = ("run_application",)


def __getattr__(name: str) -> Any:
    if name != "run_application":
        raise AttributeError(name)

    install_runtime_stability()
    from velvet_bot.app.channel_analytics_datetime_compat import (
        install_channel_analytics_datetime_compat,
    )

    install_channel_analytics_datetime_compat()
    from velvet_bot.app.bootstrap import run_application as application

    async def configured_run_application() -> None:
        from velvet_bot.app.auf_active_delivery_fix import (
            install_auf_active_delivery_fix,
        )
        from velvet_bot.app.auf_branding import install_auf_branding
        from velvet_bot.app.auf_cancel_ui_install import install_auf_cancel_ui
        from velvet_bot.app.auf_grs_brand_install import install_auf_grs_brand
        from velvet_bot.app.auf_photo_ratio_callback_fix import (
            install_auf_photo_ratio_callback_fix,
        )
        from velvet_bot.app.auf_photo_ui_install import install_auf_photo_ui
        from velvet_bot.app.auf_reconciliation_install import install_auf_reconciliation
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

        install_ai_model_routing()
        install_friendly_media_worker()
        install_grs_resilience()
        install_grs_campaign_retry()
        install_grs_speedups()
        install_auf_grs_brand()
        install_telegram_progress_resilience()
        install_auf_cancel_ui()
        install_auf_runtime_dispatcher()
        install_auf_reconciliation()
        install_auf_workspace_ui()
        install_auf_wallet_ui()
        install_auf_photo_ui()
        install_auf_photo_ratio_callback_fix()
        install_auf_user_portal()
        install_original_image_delivery_hotfix()
        install_original_video_delivery_hotfix()
        install_auf_result_delivery_recovery()
        install_auf_active_delivery_fix()
        install_krita_remote_worker()
        install_auf_branding()
        await application()

    globals()[name] = configured_run_application
    return configured_run_application
