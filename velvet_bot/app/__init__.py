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
        from velvet_bot.app.auf_branding import install_auf_branding
        from velvet_bot.app.auf_runtime_install import install_auf_runtime_dispatcher
        from velvet_bot.app.auf_workspace_ui_install import install_auf_workspace_ui
        from velvet_bot.app.grs_campaign_retry import install_grs_campaign_retry
        from velvet_bot.app.grs_resilience import install_grs_resilience
        from velvet_bot.app.grs_speedups import install_grs_speedups
        from velvet_bot.app.meow_cancel_ui_install import install_meow_cancel_ui
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
        install_telegram_progress_resilience()
        install_meow_cancel_ui()
        install_auf_runtime_dispatcher()
        install_auf_workspace_ui()
        install_auf_branding()
        await application()

    globals()[name] = configured_run_application
    return configured_run_application
