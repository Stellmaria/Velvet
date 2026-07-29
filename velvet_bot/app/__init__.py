from __future__ import annotations

from typing import Any

from velvet_bot.runtime_stability import install_runtime_stability

__all__ = ("run_application",)


def __getattr__(name: str) -> Any:
    if name != "run_application":
        raise AttributeError(name)

    install_runtime_stability()

    from velvet_bot.app.bootstrap import run_application as application

    async def configured_run_application() -> None:
        from velvet_bot.infrastructure.ai_model_routing import install_ai_model_routing

        install_ai_model_routing()
        await application()

    globals()[name] = configured_run_application
    return configured_run_application
