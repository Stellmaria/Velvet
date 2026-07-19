from __future__ import annotations

from typing import Any

from velvet_bot.runtime_stability import install_runtime_stability

__all__ = ("run_application",)


def __getattr__(name: str) -> Any:
    if name != "run_application":
        raise AttributeError(name)

    install_runtime_stability()

    from velvet_bot.app.bootstrap import run_application

    globals()[name] = run_application
    return run_application
