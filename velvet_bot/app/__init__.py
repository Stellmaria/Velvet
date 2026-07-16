from __future__ import annotations

from typing import Any

__all__ = ("run_application",)


def __getattr__(name: str) -> Any:
    if name != "run_application":
        raise AttributeError(name)

    from velvet_bot.app.bootstrap import run_application

    globals()[name] = run_application
    return run_application
